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
    sync::{Arc, atomic::Ordering},
    time::{Duration, Instant},
};
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};

pub fn profile(name: &str) -> Value {
    match name {
        "performance" => json!({"fps":60,"max_width":1280,"quality":55}),
        "sharp" => json!({"fps":30,"max_width":2560,"quality":85}),
        _ => json!({"fps":30,"max_width":1600,"quality":65}),
    }
}
async fn send(tx: &crate::transport::Sender<Outbound>, typ: &str, payload: Value) -> Result<()> {
    tx.send(Outbound::Packet(packet(typ, payload)))
        .await
        .context("Remote socket closed")
}

pub async fn run(
    shared: Arc<Shared>,
    key: String,
    target: String,
    mut password: String,
    mut commands: mpsc::Receiver<Value>,
) -> Result<()> {
    let (target_id, url, directory_key) = crate::directory::resolve(&shared, &target).await?;
    shared.connection(&key, |v| {
        v["message"] = json!("Verifying the remote device…");
        v["url"] = json!(url);
    });
    let (socket, _) = tokio::time::timeout(Duration::from_secs(15), connect_async(&url))
        .await
        .context("Connection timed out")??;
    let (mut sink, mut source) = socket.split();
    let (tx, mut outgoing) = crate::transport::channel();
    let mut writer = tokio::spawn(async move {
        while let Some(value) = outgoing.recv().await {
            let message = match value {
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
        send(&tx,"register",json!({"role":"client","protocol":2})).await?;
        let nonce=store::token();let device=if target_id=="remote_host"{url.clone()}else{target_id.clone()};
        let pinned=shared.store.lock().unwrap().config["trusted_devices"][&device].as_str().map(str::to_owned);
        let mut verified=false;let mut offered_key=String::new();let mut session=String::new();let mut permissions=Permissions::default();
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
                        if text.len()>2*1024*1024{bail!("Oversized remote control packet")}
                        let value:Value=serde_json::from_str(&text)?;let p=&value["payload"];let typ=value["type"].as_str().unwrap_or("");
                        match typ{
                            "register_resp"=>{if p["status"]!="ok"||p["protocol"]!=2{bail!("The remote device requires a compatible protocol-v2 build")};send(&tx,"identify",json!({"nonce":nonce})).await?;},
                            "identity"=>{
                                let public=verify_identity(p,&nonce)?;
                                if directory_key.as_ref().is_some_and(|key|*key!=public){bail!("Directory key does not match the connected device")}
                                if pinned.as_ref().is_some_and(|key|*key!=public){bail!("Saved device identity changed. Compare the fingerprint on the host before clearing its trust record.")}
                                if pinned.is_some(){verified=true;send(&tx,"connect",json!({"target_id":target_id})).await?;}
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
                            "auth_challenge" if verified=>{
                                if password.is_empty(){shared.connection(&key,|v|{v["needsPassword"]=json!(true);v["message"]=json!("A remote access password is required.");});}
                                else{
let challenge=p.clone();
let secret=password.clone();
let proof=tokio::task::spawn_blocking(move||password_proof(&secret,&challenge)).await??;
send(&tx,"connect",json!({
"target_id":target_id,"proof":proof}
)).await?;
}

                            },
                            "connect_resp"=>match p["status"].as_str().unwrap_or(""){
                                "waiting_approval"=>shared.connection(&key,|v|{v["state"]=json!("waiting");v["message"]=json!("Waiting for the host to approve your connection.");}),
                                "ok" if verified=>{
                                    session=p["session_id"].as_str().context("Missing session token")?.into();if session.len()<16||session.len()>128{bail!("Invalid session token")}
                                    permissions=serde_json::from_value(p["permissions"].clone()).context("Invalid session permissions")?;
                                    let profile_name=shared.store.lock().unwrap().config["native_settings"]["profile"].as_str().unwrap_or("balanced").to_owned();
                                    send(&tx,"video_config",profile(&profile_name)).await?;
                                    decoder=Some(crate::media::DecodeWorker::start(shared.clone(),key.clone(),session.clone(),tx.clone())?);
                                    if permissions.audio{match crate::audio::Voice::start(shared.clone(),tx.clone(),session.clone()){Ok(stream)=>voice=Some(stream),Err(error)=>shared.error(format!("Voice is unavailable: {error:#}"))}}
                                    {let mut store=shared.store.lock().unwrap();store.remember(&target)?;}shared.sync_config();
                                    shared.connection(&key,|v|{
v["state"]=json!("connected");
v["sessionId"]=json!(session);
v["message"]=json!("Connected");
v["permissions"]=json!(permissions);
v["needsPassword"]=json!(false);
v["profile"]=json!(profile_name);
v["micEnabled"]=json!(voice.as_ref().is_some_and(|s|s.mic_enabled()));
}
);

                                },
                                "error"|"rejected"=>bail!("{}",p["message"].as_str().unwrap_or("Connection declined")),_=>{}
                            },
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
                    "trust" if !offered_key.is_empty()&&!verified=>{
                        if command["allow"]!=true{disconnected=true;break}
                        {let mut store=shared.store.lock().unwrap();store.config["trusted_devices"][&device]=json!(offered_key);store.save()?;}
                        verified=true;shared.connection(&key,|v|v["needsTrust"]=json!(false));send(&tx,"connect",json!({"target_id":target_id})).await?;
                    },
                    "password" if verified=>{password=command["password"].as_str().unwrap_or("").to_owned();shared.connection(&key,|v|v["needsPassword"]=json!(false));send(&tx,"connect",json!({"target_id":target_id})).await?;},
                    "video_profile" if !session.is_empty()=>{let name=command["profile"].as_str().unwrap_or("balanced");send(&tx,"video_config",profile(name)).await?;shared.connection(&key,|v|v["profile"]=json!(name));},
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
                    "list_files"|"upload"|"download" if permissions.file_transfer&&!session.is_empty()=>{if let Err(error)=files.command(&command,&tx).await{shared.error(error);}},_=>{}
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
        shared.connection(&key,|v|{v["state"]=json!("disconnected");v["needsTrust"]=json!(false);v["needsPassword"]=json!(false);if disconnected{v["message"]=json!("Disconnected");}});Ok(())
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
