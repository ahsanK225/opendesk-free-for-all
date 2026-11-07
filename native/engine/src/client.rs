use crate::{
    app::Shared,
    network::{Outbound, packet},
    session::Permissions,
    store::{self, password_proof, verify_identity},
};
use anyhow::{Context, Result, bail};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;

/// The connect request names this viewer for the host's indicator. Older hosts ignore it.
/// The connect request; `proof` is this device's signature over the host challenge, or null.
fn hello(shared: &Shared, target_id: &str, proof: &Value) -> Value {
    let id = store::format_id(&shared.store.lock().unwrap().id());
    let mut request = json!({"target_id":target_id,"from":{"id":id,"name":std::env::var("COMPUTERNAME").unwrap_or_default()}});
    if !proof.is_null() {
        request["viewer"] = proof.clone();
    }
    request
}
pub fn profile(name: &str) -> Value {
    match name {
        "performance" => json!({"fps":60,"max_width":1280,"quality":55,"codecs":codecs()}),
        "sharp" => json!({"fps":30,"max_width":2560,"quality":85,"codecs":codecs()}),
        _ => json!({"fps":30,"max_width":1600,"quality":65,"codecs":codecs()}),
    }
}
async fn send(tx: &crate::transport::Sender<Outbound>, typ: &str, payload: Value) -> Result<()> {
    tx.send(Outbound::Packet(packet(typ, payload)))
        .await
        .context("Remote socket closed")
}
/// What this viewer can decode beyond the JPEG tiles every peer has.
fn codecs() -> Vec<&'static str> {
    let mut codecs = Vec::new();
    if crate::h264::available() {
        codecs.push("h264");
    }
    if cfg!(feature = "full") {
        codecs.push("opus");
    }
    codecs
}
fn has_codec(payload: &Value, name: &str) -> bool {
    payload["codecs"].as_array().is_some_and(|codecs| codecs.iter().any(|codec| codec == name))
}
async fn establish(
    shared: &Arc<Shared>,
    key: &str,
    target: &str,
) -> Result<(String, String, Option<String>, crate::net::Socket)> {
    let mut last = None;
    for attempt in 0..3 {
        if attempt > 0 {
            tokio::time::sleep(Duration::from_millis(500 * attempt)).await;
        }
        shared.connection(key, |v| {
            v["message"] = json!(if attempt == 0 {
                "Finding the desktop…".to_owned()
            } else {
                format!("Retrying connection ({}/3)…", attempt + 1)
            })
        });
        match crate::directory::resolve(shared, target, key).await {
            Ok((id, url, public)) => {
                shared.connection(key, |v| {
                    v["url"] = json!(url);
                    if !url.starts_with("ws://127.0.0.1") {
                        v["route"] = json!(if url.contains(".trycloudflare.com") { "Cloudflare" } else { "Local network" });
                    }
                    v["message"] = json!("Connecting securely to the desktop…");
                });
                match crate::net::connect(&url).await {
                    Ok(socket) => return Ok((id, url, public, socket)),
                    Err(error) => last = Some(error),
                }
            }
            Err(error) => last = Some(error),
        }
    }
    bail!("{}", last.context("No desktop address is available")?)
}

pub async fn run(
    shared: Arc<Shared>,
    key: String,
    target: String,
    mut password: String,
    mut commands: mpsc::Receiver<Value>,
) -> Result<()> {
    let connecting = establish(&shared, &key, &target);
    tokio::pin!(connecting);
    let (target_id, url, directory_key, socket) = loop {
        tokio::select! {
            result=&mut connecting=>break result?,
            command=commands.recv()=>{if command.is_none_or(|c|c["type"]=="disconnect"){
                shared.connection(&key,|v|{v["state"]=json!("disconnected");v["message"]=json!("Connection cancelled");});return Ok(())
            }}
        }
    };
    let (mut sink, mut source) = socket.split();
    let (tx, mut outgoing) = crate::transport::channel();
    let legacy_wire = Arc::new(AtomicBool::new(false));
    let writer_legacy = legacy_wire.clone();
    let mut writer = tokio::spawn(async move {
        while let Some(value) = outgoing.recv().await {
            let message = match value {
                Outbound::Packet(value) if writer_legacy.load(Ordering::Acquire) => {
                    match crate::legacy::outgoing(value) {
                        Ok(Some(p)) => Message::Text(p.to_string().into()),
                        Ok(None) => continue,
                        Err(_) => return,
                    }
                }
                Outbound::Packet(value) => Message::Text(value.to_string().into()),
                Outbound::Video(bytes) => Message::Binary(bytes.into()),
                Outbound::Pong(bytes) => Message::Pong(bytes.into()),
                Outbound::Close => {
                    let _ = sink.close().await;
                    return;
                }
            };
            if !matches!(
                tokio::time::timeout(crate::transport::WRITE_TIMEOUT, sink.send(message)).await,
                Ok(Ok(()))
            ) {
                return;
            }
        }
    });
    let result=async {
        send(&tx,"register",json!({"role":"client","protocol":2,"supported_protocols":[2,1]})).await?;
        let nonce=store::token();let device=if target_id=="remote_host"{url.clone()}else{target_id.clone()};
        let pinned=shared.store.lock().unwrap().config["trusted_devices"][&device].as_str().map(str::to_owned);
        let mut registered=false;let mut verified=false;let mut legacy=false;let mut legacy_limits=Permissions::default();let mut offered_key=String::new();let mut viewer_proof=Value::Null;let mut session=String::new();let mut permissions=Permissions::default();
        let mut voice:Option<crate::audio::Voice>=None;let mut decoder:Option<crate::media::DecodeWorker>=None;
        let mut clipboard=crate::platform::Clipboard::new();let mut files=crate::files::ClientFiles::new(shared.clone(),key.clone());
        let started=Instant::now();let mut heartbeat=tokio::time::interval(Duration::from_secs(1));let mut disconnected=false;
        let mut last_received=Instant::now();
        loop{tokio::select!{
            incoming=source.next()=>{
                let Some(incoming)=incoming else{break};last_received=Instant::now();match incoming?{
                    Message::Binary(bytes) if !session.is_empty()=>{
                        let Some(worker)=decoder.as_ref() else {continue};
                        worker.push(bytes.to_vec()).await?;
                    },
                    Message::Text(text)=>{
                        if text.len()>if legacy{12*1024*1024}else{2*1024*1024}{bail!("Oversized remote control packet")}
                        let value:Value=serde_json::from_str(&text)?;let typ=value["type"].as_str().unwrap_or("");
                        let mut payload=if legacy{crate::legacy::incoming(typ,&value["payload"])}else{value["payload"].clone()};
                        if legacy&&!session.is_empty(){payload["session_id"]=json!(session);}
                        let p=&payload;
                        match typ{
                            "register_resp"=>{if registered{bail!("The remote desktop repeated its registration, so the connection was refused.")};registered=true;if p["status"]!="ok"{bail!("The remote desktop declined registration")};
                                if p["protocol"]==2{send(&tx,"identify",json!({"nonce":nonce})).await?;}
                                else if p["protocol"].is_null()||p["protocol"]==1{if !crate::legacy::may_enter(pinned.as_deref(),directory_key.as_deref()){bail!("This known desktop answered with an older protocol that cannot prove its identity, so the connection was refused.")};legacy=true;legacy_wire.store(true,Ordering::Release);shared.connection(&key,|v|{v["needsLegacy"]=json!(true);v["message"]=json!("This older desktop needs compatibility mode. Verify it with its owner to continue.");});}
                                else{bail!("The remote desktop uses an unsupported protocol. Supported protocols: 1 and 2.")}
                            },
                            "identity" if !legacy=>{
                                let public=verify_identity(p,&nonce)?;if let Some(challenge)=p["viewer_challenge"].as_str().filter(|c|(16..=128).contains(&c.len())){viewer_proof=shared.store.lock().unwrap().viewer_proof(challenge,&public);}
                                if directory_key.as_ref().is_some_and(|key|*key!=public){bail!("Directory key does not match the connected device")}
                                if pinned.as_ref().is_some_and(|key|*key!=public){bail!("Saved device identity changed. Compare the fingerprint on the host before clearing its trust record.")}
                                if pinned.is_some(){verified=true;send(&tx,"connect",hello(&shared,&target_id,&viewer_proof)).await?;}
                                else{
offered_key=public;
use sha2::{
Digest,Sha256}
;
use base64::Engine;
let bytes=base64::engine::general_purpose::STANDARD.decode(&offered_key)?;
let fingerprint=hex::encode(Sha256::digest(bytes));
shared.connection(&key,|v|{
v["needsTrust"]=json!(true);
v["fingerprint"]=json!(fingerprint);
v["message"]=json!("Compare the device fingerprint to continue.");
}
);
}

                            },
                            "auth_challenge" if verified&&!legacy=>{
                                if password.is_empty(){shared.connection(&key,|v|{v["needsPassword"]=json!(true);v["message"]=json!("A remote access password is required.");});}
                                else{
let challenge=p.clone();
let secret=password.clone();
let proof=tokio::task::spawn_blocking(move||password_proof(&secret,&challenge)).await??;
send(&tx,"connect",{let mut request=hello(&shared,&target_id,&viewer_proof);request["proof"]=json!(proof);request}).await?;
}

                            },
                            "connect_resp"=>match p["status"].as_str().unwrap_or(""){
                                "waiting_approval"=>shared.connection(&key,|v|{v["state"]=json!("waiting");v["message"]=json!("Waiting for the host to approve your connection.");}),
                                "ok" if verified=>{
                                    session=if legacy{p["session_id"].as_str().filter(|s|(16..=128).contains(&s.len())).map(str::to_owned).unwrap_or_else(store::token)}else{p["session_id"].as_str().context("Missing session token")?.into()};if session.len()<16||session.len()>128{bail!("Invalid session token")}
                                    permissions=if legacy{crate::legacy::permissions(&p["permissions"],legacy_limits)}else{serde_json::from_value(p["permissions"].clone()).context("Invalid session permissions")?};
                                    permissions=permissions.for_edition();
                                    if permissions.file_transfer{let _=files.command(&json!({"type":"file_features","features":p["files"]}),&tx).await;}
                                    let profile_name=shared.store.lock().unwrap().config["native_settings"]["profile"].as_str().unwrap_or("balanced").to_owned();
                                    send(&tx,"video_config",profile(&profile_name)).await?;
                                    decoder=Some(crate::media::DecodeWorker::start(shared.clone(),key.clone(),session.clone(),tx.clone())?);
                                    if permissions.audio{match crate::audio::Voice::start(shared.clone(),tx.clone(),session.clone()){Ok(stream)=>{stream.set_peer_opus(has_codec(p,"opus"));voice=Some(stream)},Err(error)=>shared.error(format!("Voice is unavailable: {error:#}"))}}
                                    {let mut store=shared.store.lock().unwrap();store.remember(&target)?;}shared.sync_config();
                                    shared.connection(&key,|v|{
v["state"]=json!("connected");
v["sessionId"]=json!(session);
v["message"]=json!("Connected");
v["permissions"]=json!(permissions);
v["needsPassword"]=json!(false);
v["profile"]=json!(profile_name);
v["protocol"]=json!(if legacy{1}else{2});
v["compatibility"]=json!(legacy);
v["micEnabled"]=json!(voice.as_ref().is_some_and(|s|s.mic_enabled()));
}
);

                                },
                                "error" if legacy&&p["message"].as_str().is_some_and(|s|s.to_lowercase().contains("password"))=>bail!("This older desktop requires its access password. OpenDesk does not send passwords to a desktop that cannot prove its identity. Update that desktop, or ask its owner to turn off its password."),
                                "error"|"rejected"=>bail!("{}",p["message"].as_str().unwrap_or("Connection declined")),_=>{}
                            },
                            "video_full"|"video_delta" if legacy&&!session.is_empty()=>{if let Some(worker)=&decoder{worker.push_legacy(typ,p.clone())?;}},
                            "heartbeat"=>{
if let Some(sent)=p["echo"].as_f64(){
let rtt=((started.elapsed().as_secs_f64()-sent)*1000.0).max(0.0);
if rtt<=60_000.0{
if let Some(worker)=&decoder{
worker.rtt.store(rtt as u64,Ordering::Relaxed);
}
shared.connection(&key,|v|v["rtt"]=json!(rtt));
}
}
}
,
                            "session_end"=>{shared.connection(&key,|v|v["message"]=json!(p["message"].as_str().unwrap_or("Session ended.")));break},
                            "audio_chunk" if permissions.audio&&p["session_id"]==session=>{if let Some(voice)=&voice{voice.push(p);}},
                            "clipboard_text" if permissions.clipboard&&p["session_id"]==session=>{if let Some(text)=p["text"].as_str().filter(|t|t.len()<=1024*1024){let _=clipboard.set(text);}},
                            typ if typ.starts_with("file_")&&permissions.file_transfer&&p["session_id"]==session=>{if let Err(error)=files.packet(typ,p,&tx).await{shared.error(error);}},_=>{}
                        }
                    },
                    Message::Ping(bytes)=>{let _=tx.try_send(Outbound::Pong(bytes.to_vec()));},Message::Close(_)=>break,_=>{}
                }
            },
            command=commands.recv()=>{
                let Some(command)=command else{break};let typ=command["type"].as_str().unwrap_or("");
                match typ{
                    "disconnect"=>{if !session.is_empty(){send(&tx,"input_reset",json!({})).await?;send(&tx,"session_end",json!({})).await?;}disconnected=true;break},
                    "legacy_accept" if legacy&&!verified=>{
                        if command["allow"]!=true{disconnected=true;break}
                        legacy_limits=serde_json::from_value(command["permissions"].clone()).unwrap_or_default();legacy_limits.file_transfer=false;
                        verified=true;shared.connection(&key,|v|{v["needsLegacy"]=json!(false);v["message"]=json!("Requesting permission from the older desktop…");});
                        send(&tx,"connect",hello(&shared,&target_id,&viewer_proof)).await?;
                    },
                    "trust" if !offered_key.is_empty()&&!verified=>{
                        if command["allow"]!=true{disconnected=true;break}
                        {let mut store=shared.store.lock().unwrap();store.config["trusted_devices"][&device]=json!(offered_key);store.save()?;}
                        verified=true;shared.connection(&key,|v|v["needsTrust"]=json!(false));send(&tx,"connect",hello(&shared,&target_id,&viewer_proof)).await?;
                    },
                    "password" if verified&&!legacy=>{password=command["password"].as_str().unwrap_or("").to_owned();shared.connection(&key,|v|v["needsPassword"]=json!(false));send(&tx,"connect",hello(&shared,&target_id,&viewer_proof)).await?;},
                    "video_profile" if !session.is_empty()=>{let name=command["profile"].as_str().unwrap_or("balanced");let width=command["maxWidth"].as_u64().filter(|w|(640..=2560).contains(w));let mut config=profile(name);if let Some(width)=width{config["max_width"]=json!(width);}send(&tx,"video_config",config).await?;shared.connection(&key,|v|{v["profile"]=json!(name);v["maxWidth"]=json!(width.unwrap_or(0));});},
                    "input" if !session.is_empty()=>{
                        let mut p=command["payload"].clone();
let typ=p["type"].as_str().unwrap_or("").to_owned();
if permissions.input||typ=="input_reset"{
if (typ=="key_down"||typ=="key_up")
&& let Some(vk)=p["vk"].as_u64(){
p["code"]=json!(crate::platform::key_code(vk as u16));
}
p.as_object_mut().map(|v|v.remove("type"));
send(&tx,&typ,p).await?;
}

                    },
                    "toggle_mic" if permissions.audio=>{if let Some(voice)=&voice{voice.toggle_mic();shared.connection(&key,|v|v["micEnabled"]=json!(voice.mic_enabled()));}},
                    "audio_settings"=>{if let Some(voice)=&voice{voice.refresh_settings(command["applyMic"]==true);shared.connection(&key,|v|v["micEnabled"]=json!(voice.mic_enabled()));}},
                    "list_files"|"upload"|"download"|"cancel_transfer" if permissions.file_transfer&&!session.is_empty()=>{if let Err(error)=files.command(&command,&tx).await{shared.error(error);}},_=>{}
                }
            },
            _=heartbeat.tick()=>{
                if shared.stop.load(Ordering::Acquire){break}
                if last_received.elapsed()>Duration::from_secs(45){bail!("The remote desktop stopped responding. Reconnect to continue.")}
                if let Some(voice)=&voice{shared.connection(&key,|v|v["micEnabled"]=json!(voice.mic_enabled()));}
                send(&tx,"heartbeat",json!({"sent_at":started.elapsed().as_secs_f64()})).await?;
                if !session.is_empty()&&permissions.clipboard&& let Some(text)=clipboard.poll(){send(&tx,"clipboard_text",json!({"text":text})).await?;}
            }
        }}
        drop(decoder);drop(voice);
        shared.frames.lock().unwrap().remove(&key);
        shared.connection(&key,|v|{v["state"]=json!("disconnected");v["needsTrust"]=json!(false);v["needsLegacy"]=json!(false);v["needsPassword"]=json!(false);if disconnected{v["message"]=json!("Disconnected");}});Ok(())
    }.await;
    shared.frames.lock().unwrap().remove(&key);
    let _ = tx.send(Outbound::Close).await;
    if tokio::time::timeout(Duration::from_secs(1), &mut writer)
        .await
        .is_err()
    {
        writer.abort();
    }
    result
}
