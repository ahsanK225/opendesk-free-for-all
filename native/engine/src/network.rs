use crate::{
    app::Shared,
    session::{HostSession, Permissions},
    store::{self, token, verify_proof},
};
use anyhow::{Result, bail};
use axum::{
    Router,
    extract::{
        ConnectInfo, Request, State, WebSocketUpgrade,
        ws::{Message, WebSocket},
    },
    middleware::{Next, from_fn_with_state},
    response::{IntoResponse, Response},
    routing::get,
};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet, VecDeque},
    net::{IpAddr, SocketAddr},
    sync::{Arc, Mutex, atomic::Ordering},
    time::{Duration, Instant},
};
use tokio::sync::{Semaphore, mpsc};
use tower_http::services::ServeDir;

#[derive(Debug)]
pub enum Outbound {
    Packet(Value),
    Video(Vec<u8>),
    Close,
    Pong(Vec<u8>),
}
pub fn packet(typ: &str, payload: Value) -> Value {
    json!({"type":typ,"payload":payload})
}
struct Pending {
    id: String,
    peer: String,
    deadline: Instant,
}
struct Challenge {
    nonce: String,
    deadline: Instant,
}
struct Host {
    authorization: HostSession,
    pending: Option<Pending>,
    active: Option<(String, crate::media::HostWorker)>,
    challenges: HashMap<String, Challenge>,
    failures: VecDeque<Instant>,
    password: Option<Value>,
    /// What the connecting viewer says about itself, shown to the person at this PC.
    viewer: Value,
    /// Challenges sent with `identity`, by peer, for viewers to sign with their device key.
    viewer_challenges: HashMap<String, (String, Instant)>,
    /// The device key the pending or active viewer proved, if it proved one.
    viewer_key: Option<String>,
}
/// Viewers allowed to connect without approval are stored by device key, at most this many.
const MAX_ALLOWED_VIEWERS: usize = 50;
/// The stored permissions of a viewer this desktop allows without asking.
fn allowed_viewer(list: &Value, key: &str) -> Option<Permissions> {
    list.as_array()?
        .iter()
        .find(|entry| entry["key"] == key)
        .and_then(|entry| serde_json::from_value(entry["permissions"].clone()).ok())
}
/// The name and ID a viewer from 3.5 on sends. It is not proof of identity.
fn viewer_info(payload: &Value) -> Value {
    let clean = |value: &Value, limit: usize| -> String {
        value.as_str().unwrap_or("").chars().filter(|c| !c.is_control()).take(limit).collect::<String>().trim().to_owned()
    };
    let (id, name) = (clean(&payload["from"]["id"], 16), clean(&payload["from"]["name"], 64));
    if id.is_empty() && name.is_empty() { Value::Null } else { json!({"id":id,"name":name}) }
}
pub struct Runtime {
    pub shared: Arc<Shared>,
    peers: Mutex<HashMap<String, crate::transport::Sender<Outbound>>>,
    legacy_peers: Mutex<HashSet<String>>,
    host: Mutex<Host>,
    clients: Mutex<HashMap<String, mpsc::Sender<Value>>>,
    connections: Arc<Semaphore>,
    started: Instant,
    mic_test: Mutex<Option<(crate::audio::Voice, Instant)>>,
}
impl Runtime {
    fn stop_mic_test(&self) {
        if self.mic_test.lock().unwrap().take().is_some() {
            self.shared.update(|v| v["micTest"] = Value::Null);
        }
    }
    fn lan_access(&self) -> bool {
        self.shared.store.lock().unwrap().config["native_settings"]["lanAccess"]
            .as_bool()
            .unwrap_or(false)
    }
    fn send(&self, peer: &str, typ: &str, payload: Value) {
        if let Some(tx) = self.peers.lock().unwrap().get(peer) {
            let _ = tx.try_send(Outbound::Packet(packet(typ, payload)));
        }
    }
    fn error(&self, peer: &str, message: impl ToString) {
        self.send(
            peer,
            "connect_resp",
            json!({"status":"error","message":message.to_string()}),
        );
    }
    fn end_host(&self, reason: &str) {
        let mut host = self.host.lock().unwrap();
        host.authorization.revoke();
        host.challenges.clear();
        host.viewer_key = None;
        if let Some(pending) = host.pending.take() {
            self.error(&pending.peer, reason);
        }
        if let Some((peer, worker)) = host.active.take() {
            worker.stop();
            self.send(&peer, "session_end", json!({"message":reason}));
        }
        drop(host);
        self.shared.update(|v| {
            v["hostSession"] = Value::Null;
            v["remoteCursor"] = Value::Null;
            v["incoming"] = Value::Null;
        });
    }
    fn pair(&self, peer: &str, permissions: Permissions, request: &str) -> Result<()> {
        let permissions = permissions.for_edition();
        let mut host = self.host.lock().unwrap();
        let id = token();
        host.authorization
            .approve(
                request,
                id.clone(),
                permissions,
                self.started.elapsed().as_millis() as u64,
            )
            .map_err(|e| anyhow::anyhow!("Invalid approval: {e:?}"))?;
        let tx = self
            .peers
            .lock()
            .unwrap()
            .get(peer)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Remote peer disconnected"))?;
        let worker =
            crate::media::HostWorker::start(self.shared.clone(), id.clone(), permissions, tx)?;
        host.active = Some((peer.into(), worker));
        host.pending = None;
        let from = host.viewer.clone();
        drop(host);
        let host_id = self.shared.store.lock().unwrap().id();
        let mic_enabled = permissions.audio
            && self.shared.store.lock().unwrap().config["native_settings"]["micEnabled"]
                .as_bool()
                .unwrap_or(false);
        self.send(peer,"connect_resp",json!({"status":"ok","target_id":host_id,"session_id":id,"permissions":permissions,"protocol":2,"codecs":if cfg!(feature="full"){vec!["opus"]}else{Vec::new()},"files":["folders","thumbnails"]}));
        self.shared.update(|v| {
            v["incoming"] = Value::Null;
            v["hostSession"] =
                json!({"peer":peer,"from":from,"since":store::now(),"sessionId":id,"permissions":permissions,"micEnabled":mic_enabled});
        });
        Ok(())
    }
    fn message(&self, peer: &str, typ: &str, mut payload: Value) {
        match typ {
            "identify" => {
                if let Some(nonce) = payload["nonce"]
                    .as_str()
                    .filter(|n| (16..=128).contains(&n.len()))
                {
                    let mut result = self.shared.store.lock().unwrap().identity_packet(nonce);
                    let challenge = token();
                    {
                        let mut host = self.host.lock().unwrap();
                        host.viewer_challenges.retain(|_, (_, at)| at.elapsed() < Duration::from_secs(120));
                        if host.viewer_challenges.len() < 64 {
                            host.viewer_challenges.insert(peer.into(), (challenge.clone(), Instant::now()));
                            result["viewer_challenge"] = json!(challenge);
                        }
                    }
                    self.send(peer, "identity", result);
                }
            }
            "heartbeat" => self.send(peer, "heartbeat", json!({"echo":payload["sent_at"]})),
            "session_end" => {
                let should_end = {
                    let host = self.host.lock().unwrap();
                    host.active.as_ref().is_some_and(|(p, _)| p == peer)
                        || host.pending.as_ref().is_some_and(|p| p.peer == peer)
                };
                if should_end {
                    self.end_host("Session disconnected.");
                }
            }
            "connect" => {
                let target = store::clean_id(payload["target_id"].as_str().unwrap_or(""));
                let local = self.shared.store.lock().unwrap().id();
                if target != local && target != "remote_host" {
                    self.error(peer, "Host ID not found.");
                    return;
                }
                let (unattended, own_key, allowed) = {
                    let store = self.shared.store.lock().unwrap();
                    (
                        store.config["native_settings"]["unattendedEnabled"].as_bool().unwrap_or(false),
                        store.key(),
                        store.config["allowed_viewers"].clone(),
                    )
                };
                let legacy = self.legacy_peers.lock().unwrap().contains(peer);
                let mut host = self.host.lock().unwrap();
                if host.active.is_some() || host.pending.is_some() {
                    self.error(peer, "This desktop is busy.");
                    return;
                }
                // A one-time challenge, so a proof can neither be replayed nor reused for another host.
                host.viewer_key = host
                    .viewer_challenges
                    .remove(peer)
                    .filter(|(_, at)| !legacy && at.elapsed() < Duration::from_secs(120))
                    .and_then(|(challenge, _)| store::verify_viewer(&payload["viewer"], &challenge, &own_key).ok());
                host.viewer = viewer_info(&payload);
                if let Some(key) = host.viewer_key.clone() {
                    host.viewer["verified"] = json!(true);
                    host.viewer["fingerprint"] = json!(hex::encode(&<sha2::Sha256 as sha2::Digest>::digest(key.as_bytes())[..6]));
                }
                let from = host.viewer.clone();
                if let Some(permissions) = host.viewer_key.as_deref().and_then(|key| allowed_viewer(&allowed, key)) {
                    let request = token();
                    let result = host.authorization.request(request.clone(), peer.into(), self.started.elapsed().as_millis() as u64);
                    drop(host);
                    if result.is_err() {
                        self.error(peer, "This desktop is busy.");
                    } else if let Err(error) = self.pair(peer, permissions, &request) {
                        self.error(peer, error);
                    }
                    return;
                }
                while host
                    .failures
                    .front()
                    .is_some_and(|time| time.elapsed() > Duration::from_secs(60))
                {
                    host.failures.pop_front();
                }
                if host.failures.len() >= 5 {
                    self.error(peer, "Too many password attempts. Retry in one minute.");
                    return;
                }
                if let Some(record) = host
                    .password
                    .clone()
                    .filter(|_| unattended && !self.legacy_peers.lock().unwrap().contains(peer))
                {
                    if let Some(proof) = payload["proof"].as_str() {
                        let valid = host.challenges.remove(peer).is_some_and(|challenge| {
                            challenge.deadline > Instant::now()
                                && verify_proof(&record, &challenge.nonce, proof)
                        });
                        if !valid {
                            host.failures.push_back(Instant::now());
                            self.error(peer, "Invalid or expired password proof.");
                            return;
                        }
                        let request = token();
                        let result = host.authorization.request(
                            request.clone(),
                            peer.into(),
                            self.started.elapsed().as_millis() as u64,
                        );
                        drop(host);
                        if result.is_err() {
                            self.error(peer, "This desktop is busy.");
                            return;
                        }
                        if let Err(error) = self.pair(
                            peer,
                            Permissions {
                                input: true,
                                audio: true,
                                clipboard: true,
                                file_transfer: true,
                            },
                            &request,
                        ) {
                            self.error(peer, error);
                        }
                        return;
                    }
                    let nonce = token();
                    host.challenges.insert(
                        peer.into(),
                        Challenge {
                            nonce: nonce.clone(),
                            deadline: Instant::now() + Duration::from_secs(30),
                        },
                    );
                    self.send(peer,"auth_challenge",json!({"target_id":local,"salt":record["salt"],"iterations":record["iterations"],"nonce":nonce}));
                    return;
                }
                let request = token();
                if host
                    .authorization
                    .request(
                        request.clone(),
                        peer.into(),
                        self.started.elapsed().as_millis() as u64,
                    )
                    .is_err()
                {
                    self.error(peer, "This desktop is busy.");
                    return;
                }
                host.pending = Some(Pending {
                    id: request.clone(),
                    peer: peer.into(),
                    deadline: Instant::now() + Duration::from_secs(60),
                });
                drop(host);
                self.shared
                    .update(|v| v["incoming"] = json!({"requestId":request,"peer":peer,"from":from,"legacy":self.legacy_peers.lock().unwrap().contains(peer)}));
                self.send(
                    peer,
                    "connect_resp",
                    json!({"status":"waiting_approval","target_id":local}),
                );
            }
            _ => {
                let host = self.host.lock().unwrap();
                let Some((active, worker)) = &host.active else {
                    return;
                };
                let session = worker.session.as_str();
                if active != peer || !host.authorization.allows(peer, session, typ) {
                    return;
                }
                payload["session_id"] = json!(session);
                if worker.send(typ, payload).is_err() {
                    drop(host);
                    self.end_host("The media worker stopped. Reconnect to continue.");
                }
            }
        }
    }
    async fn command(self: &Arc<Self>, command: Value) {
        let typ = command["type"].as_str().unwrap_or("");
        let key = command["key"].as_str().unwrap_or("").to_owned();
        match typ {
            #[cfg(test)]
            "test_audio" => {
                let host = self.host.lock().unwrap();
                if let Some((peer, worker)) = &host.active {
                    let mut payload = command["payload"].clone();
                    payload["session_id"] = json!(worker.session);
                    self.send(peer, "audio_chunk", payload);
                }
            }
            "check_updates" => crate::updater::start(self.shared.clone(), false),
            "install_update" => crate::updater::start(self.shared.clone(), true),
            "cancel_update" => self.shared.update_cancel.store(true, Ordering::Release),
            "mic_test" => {
                if self.mic_test.lock().unwrap().is_some() {
                    self.stop_mic_test();
                } else {
                    match crate::audio::Voice::start_test(self.shared.clone()) {
                        Ok(voice) => {
                            *self.mic_test.lock().unwrap() = Some((voice, Instant::now()));
                            self.shared.update(|v| v["micTest"] = json!({"active":true}));
                        }
                        Err(error) => self.shared.error(format!("Microphone test: {error:#}")),
                    }
                }
            }
            "shutdown" => {
                self.shared.stop.store(true, Ordering::Release);
                self.end_host("OpenDesk closed.");
                for tx in self.clients.lock().unwrap().values() {
                    let _ = tx.try_send(json!({"type":"disconnect"}));
                }
            }
            "dismiss_notice" => self.shared.update(|v| v["notice"] = Value::Null),
            "end_sharing" => self.end_host("Sharing ended by the host."),
            "approve" => {
                let request = command["requestId"].as_str().unwrap_or("");
                let pending = {
                    let host = self.host.lock().unwrap();
                    host.pending
                        .as_ref()
                        .filter(|p| p.id == request && p.deadline > Instant::now())
                        .map(|p| p.peer.clone())
                };
                let Some(peer) = pending else { return };
                if command["allow"].as_bool() == Some(true) {
                    let mut permissions: Permissions =
                        serde_json::from_value(command["permissions"].clone()).unwrap_or_default();
                    if self.legacy_peers.lock().unwrap().contains(&peer) {
                        permissions.file_transfer = false;
                    }
                    // "Always allow" needs a device key the viewer proved for this request.
                    let (key, from) = {
                        let host = self.host.lock().unwrap();
                        (host.viewer_key.clone(), host.viewer.clone())
                    };
                    if command["remember"].as_bool() == Some(true) && let Some(key) = key {
                        let result = {
                            let mut store = self.shared.store.lock().unwrap();
                            if !store.config["allowed_viewers"].is_array() {
                                store.config["allowed_viewers"] = json!([]);
                            }
                            let list = store.config["allowed_viewers"].as_array_mut().unwrap();
                            list.retain(|entry| entry["key"] != key.as_str());
                            list.insert(0, json!({"key":key,"id":from["id"],"name":from["name"],"fingerprint":from["fingerprint"],"permissions":permissions.for_edition(),"added":store::now()}));
                            list.truncate(MAX_ALLOWED_VIEWERS);
                            store.save()
                        };
                        if let Err(error) = result {
                            self.shared.error(error);
                        }
                        self.shared.sync_config();
                    }
                    if let Err(error) = self.pair(&peer, permissions, request) {
                        self.error(&peer, error);
                    }
                } else {
                    let mut host = self.host.lock().unwrap();
                    host.authorization.reject(request);
                    host.pending = None;
                    drop(host);
                    self.send(
                        &peer,
                        "connect_resp",
                        json!({"status":"rejected","message":"Connection declined by host."}),
                    );
                    self.shared.update(|v| v["incoming"] = Value::Null);
                }
            }
            "set_password" => {
                let password = command["password"].as_str().unwrap_or("").to_owned();
                if !password.is_empty() && (password.chars().count() < 8 || password.len() > 1024) {
                    self.shared.error(
                        "Use an unattended password of at least 8 characters (at most 1024 bytes).",
                    );
                    return;
                }
                let shared = self.shared.clone();
                let result = tokio::task::spawn_blocking(move || -> Result<Option<Value>> {
                    let mut store = shared.store.lock().unwrap();
                    store.config["unattended_password"] = json!(if password.is_empty() {
                        String::new()
                    } else {
                        store::protect(&password)?
                    });
                    store.save()?;
                    store.password_record()
                })
                .await;
                match result {
                    Ok(Ok(record)) => {
                        let mut host = self.host.lock().unwrap();
                        host.password = record;
                        host.challenges.clear();
                        drop(host);
                        self.shared.sync_config();
                    }
                    Ok(Err(error)) => self.shared.error(error),
                    Err(error) => self.shared.error(error),
                }
            }
            "toggle_host_mic" => {
                if let Some((_, worker)) = &self.host.lock().unwrap().active {
                    let _ = worker.send("local_mic_toggle", json!({}));
                }
            }
            "setting" => {
                let name = command["name"].as_str().unwrap_or("");
                let value = command["value"].clone();
                let valid = match name {
                    "profile" => {
                        matches!(value.as_str(), Some("balanced" | "performance" | "sharp"))
                    }
                    "theme" => matches!(value.as_str(), Some("dark" | "light")),
                    "graphics" => matches!(value.as_str(), Some("auto" | "direct3d" | "opengl" | "software")),
                    "micEnabled" | "speakerEnabled" | "publicAccess" | "lanAccess" | "unattendedEnabled" | "sessionDot" => value.is_boolean(),
                    "speakerVolume" => value.as_f64().is_some_and(|n| (0.0..=1.0).contains(&n)),
                    "micGain" => value.as_f64().is_some_and(|n| (0.0..=3.0).contains(&n)),
                    "sharedRoot" => value.as_str().is_some_and(|p| {
                        p.len() <= 32768
                            && std::path::Path::new(p).is_absolute()
                            && !p.starts_with("\\\\")
                            && std::path::Path::new(p).is_dir()
                    }),
                    _ => false,
                };
                if !valid {
                    return;
                }
                let result = {
                    let mut store = self.shared.store.lock().unwrap();
                    store.config["native_settings"][name] = value;
                    store.save()
                };
                if let Err(error) = result {
                    self.shared.error(error);
                }
                self.shared.sync_config();
                if name == "sharedRoot" {
                    self.end_host(
                        "The shared folder changed. Reconnect to grant access to the new folder.",
                    );
                }
                if let Some((_, worker)) = &self.host.lock().unwrap().active {
                    let _ = worker.send("audio_settings", json!({"applyMic":name=="micEnabled"}));
                }
                for tx in self.clients.lock().unwrap().values() {
                    let _ =
                        tx.try_send(json!({"type":"audio_settings","applyMic":name=="micEnabled"}));
                }
            }
            "favorite" => {
                let id = store::device_reference(command["id"].as_str().unwrap_or(""));
                let result = {
                    let mut store = self.shared.store.lock().unwrap();
                    if let Some(item) =
                        store.config["recent_sessions"]
                            .as_array_mut()
                            .and_then(|values| {
                                values.iter_mut().find(|v| {
                                    store::device_reference(v["id"].as_str().unwrap_or("")) == id
                                })
                            })
                    {
                        item["favorite"] = json!(!item["favorite"].as_bool().unwrap_or(false));
                    }
                    store.save()
                };
                if let Err(error) = result {
                    self.shared.error(error);
                }
                self.shared.sync_config();
            }
            "forget_viewer" => {
                let key = command["key"].as_str().unwrap_or("");
                let result = {
                    let mut store = self.shared.store.lock().unwrap();
                    let before = store.config["allowed_viewers"].as_array().map_or(0, Vec::len);
                    if let Some(list) = store.config["allowed_viewers"].as_array_mut() {
                        list.retain(|entry| entry["key"] != key);
                    }
                    if store.config["allowed_viewers"].as_array().map_or(0, Vec::len) != before { store.save() } else { Ok(()) }
                };
                if let Err(error) = result {
                    self.shared.error(error);
                }
                self.shared.sync_config();
            }
            "save_device" | "remove_device" => {
                let id = command["id"].as_str().unwrap_or("");
                let result = {
                    let mut store = self.shared.store.lock().unwrap();
                    let values = store.config["recent_sessions"].as_array_mut().unwrap();
                    let changed = if typ == "save_device" {
                        store::save_device(
                            values,
                            command["oldId"].as_str().unwrap_or(""),
                            id,
                            command["alias"].as_str().unwrap_or(""),
                        )
                    } else {
                        store::remove_device(values, id)
                    };
                    if changed { store.save() } else { Ok(()) }
                };
                if let Err(error) = result {
                    self.shared.error(error);
                }
                self.shared.sync_config();
            }
            "render_metrics" => self
                .shared
                .connection(&key, |v| v["fps"] = command["fps"].clone()),
            "connect" => {
                let target = command["target"].as_str().unwrap_or("").trim().to_owned();
                if target.is_empty() || target.len() > 2048 {
                    return;
                }
                if self.clients.lock().unwrap().len() >= 6 {
                    self.shared
                        .error("Close an existing session before opening another.");
                    return;
                }
                let key = token();
                let (tx, rx) = mpsc::channel(256);
                self.clients.lock().unwrap().insert(key.clone(), tx);
                self.shared.update(|v|{
v["connections"].as_array_mut().unwrap().push(json!({
"key":key,"target":target,"name":target,"state":"connecting","message":"Resolving the desktop…","fps":0,"rtt":0,"permissions":{
}
,"files":{
"path":".","entries":[]}
}
));
v["activeTab"]=json!(key);
}
);

                let runtime = self.clone();
                let shared = self.shared.clone();
                let password = command["password"].as_str().unwrap_or("").to_owned();
                tokio::spawn(async move {
                    if let Err(error) =
                        crate::client::run(shared.clone(), key.clone(), target, password, rx).await
                    {
                        shared.connection(&key, |v| {
                            v["state"] = json!("error");
                            v["message"] = json!(format!("{error}"));
                            v["details"] = json!(format!("{error:#}"));
                            v["needsTrust"] = json!(false);
                            v["needsPassword"] = json!(false);
                        });
                    }
                    runtime.clients.lock().unwrap().remove(&key);
                });
            }
            "close_session" => {
                if let Some(tx) = self.clients.lock().unwrap().get(&key) {
                    let _ = tx.try_send(json!({"type":"disconnect"}));
                }
                self.shared.frames.lock().unwrap().remove(&key);
                self.shared.update(|v| {
                    v["connections"]
                        .as_array_mut()
                        .unwrap()
                        .retain(|item| item["key"] != key);
                    if v["activeTab"] == key {
                        v["activeTab"] = json!("home");
                    }
                });
            }
            _ => {
                let tx = self.clients.lock().unwrap().get(&key).cloned();
                if let Some(tx) = tx
                    && tx.try_send(command).is_err()
                {
                    self.shared.error("The session command queue is busy.");
                }
            }
        }
    }
}
/// The tunnel and this PC arrive over loopback; everything else needs the local network setting.
async fn local_only(
    State(runtime): State<Arc<Runtime>>,
    ConnectInfo(address): ConnectInfo<SocketAddr>,
    request: Request,
    next: Next,
) -> Response {
    if !address.ip().is_loopback() && !runtime.lan_access() {
        return axum::http::StatusCode::FORBIDDEN.into_response();
    }
    next.run(request).await
}
async fn upgrade(
    State(runtime): State<Arc<Runtime>>,
    ConnectInfo(address): ConnectInfo<SocketAddr>,
    ws: WebSocketUpgrade,
) -> impl IntoResponse {
    let Ok(permit) = runtime.connections.clone().try_acquire_owned() else {
        return axum::http::StatusCode::TOO_MANY_REQUESTS.into_response();
    };
    ws.max_message_size(2 * 1024 * 1024)
        .max_frame_size(2 * 1024 * 1024)
        .on_upgrade(move |socket| async move {
            let _permit = permit;
            peer(runtime, socket, !address.ip().is_loopback()).await
        })
        .into_response()
}
async fn peer(runtime: Arc<Runtime>, socket: WebSocket, lan: bool) {
    let (mut sink, mut source) = socket.split();
    let first = tokio::time::timeout(Duration::from_secs(10), source.next()).await;
    let Ok(Some(Ok(Message::Text(text)))) = first else {
        return;
    };
    if text.len() > 4096 {
        return;
    }
    let Ok(value) = serde_json::from_str::<Value>(&text) else {
        return;
    };
    let protocol = crate::legacy::protocol(&value["payload"]);
    if value["type"] != "register" || value["payload"]["role"] != "client" || protocol.is_none() {
        let _=sink.send(Message::Text(packet("connect_resp",json!({"status":"error","message":"A supported client registration is required (protocol 1 or 2). External host registration is denied."})).to_string().into())).await;
        return;
    }
    let peer = loop {
        let id = format!(
            "{}",
            100_000_000 + u64::from_str_radix(&token()[..8], 16).unwrap() % 900_000_000
        );
        if !runtime.peers.lock().unwrap().contains_key(&id) {
            break id;
        }
    };
    let (tx, mut rx) = crate::transport::channel();
    runtime.peers.lock().unwrap().insert(peer.clone(), tx);
    let legacy = protocol == Some(1);
    if legacy {
        runtime.legacy_peers.lock().unwrap().insert(peer.clone());
    }
    runtime.send(
        &peer,
        "register_resp",
        json!({"status":"ok","id":peer,"clean_id":peer,"role":"client","protocol":protocol,"supported_protocols":[2,1]}),
    );
    let mut counter = 0u32;
    let mut last = Instant::now();
    let mut last_received = Instant::now();
    let registered = Instant::now();
    let mut health = tokio::time::interval(Duration::from_secs(1));
    let reporter = runtime.clone();
    let writer_peer = peer.clone();
    let writer = tokio::spawn(async move {
        while let Some(outgoing) = rx.recv().await {
            let mut ack = None;
            let message = match outgoing {
                Outbound::Packet(value) if legacy => match crate::legacy::outgoing(value) {
                    Ok(Some(p)) => Message::Text(p.to_string().into()),
                    Ok(None) => continue,
                    Err(_) => break,
                },
                Outbound::Packet(value) => Message::Text(value.to_string().into()),
                Outbound::Video(bytes) if legacy => {
                    let Ok(value) = crate::legacy::video_json(&bytes) else {
                        break;
                    };
                    ack = value["payload"]["frame_id"].as_u64();
                    Message::Text(value.to_string().into())
                }
                Outbound::Video(bytes) => Message::Binary(bytes.into()),
                Outbound::Pong(bytes) => Message::Pong(bytes.into()),
                Outbound::Close => break,
            };
            if !matches!(
                tokio::time::timeout(crate::transport::WRITE_TIMEOUT, sink.send(message)).await,
                Ok(Ok(()))
            ) {
                break;
            }
            if let Some(frame) = ack {
                reporter.message(&writer_peer, "video_ack", json!({"frame_id":frame}));
            }
        }
    });
    loop {
        tokio::select! {
                    incoming=source.next()=>{
        match incoming{
        Some(Ok(Message::Text(text)))=>{
        last_received=Instant::now();
        if last.elapsed()>=Duration::from_secs(1){
        last=Instant::now();
        counter=0;
        }
        counter+=1;
        if counter>2000{
        break}
        if text.len()>2*1024*1024{
        break}
        if let Ok(value)=serde_json::from_str::<Value>(&text)
        && let (Some(typ),Some(payload))=(value["type"].as_str(),value["payload"].as_object()){
        let mut payload=if legacy{crate::legacy::incoming(typ,&Value::Object(payload.clone()))}else{Value::Object(payload.clone())};
        if legacy&&typ=="video_config"{payload["fps"]=json!(payload["fps"].as_u64().unwrap_or(20).clamp(10,20));payload["max_width"]=json!(payload["max_width"].as_u64().unwrap_or(1280).clamp(640,1280));}
        runtime.message(&peer,if legacy&&typ=="keyframe_req"{"video_refresh"}else{typ},payload);
        }
        }
        ,Some(Ok(Message::Ping(bytes)))=>{
        last_received=Instant::now();
        if let Some(tx)=runtime.peers.lock().unwrap().get(&peer){
        let _=tx.try_send(Outbound::Pong(bytes.to_vec()));
        }
        }
        ,Some(Ok(Message::Pong(_)))=>{last_received=Instant::now();}
        ,Some(Ok(Message::Close(_)))|None|Some(Err(_))=>break,_=>{
        }
        }
        }
        ,
                    _=health.tick()=>{
                        if runtime.shared.stop.load(Ordering::Acquire)||writer.is_finished()||last_received.elapsed()>Duration::from_secs(45)||(lan&&!runtime.lan_access()){break}
                        let has_session={let host=runtime.host.lock().unwrap();host.active.as_ref().is_some_and(|(id,_)|id==&peer)||host.pending.as_ref().is_some_and(|p|p.peer==peer)};
                        if !has_session&&registered.elapsed()>Duration::from_secs(120){break}
                    },
                }
    }
    writer.abort();
    runtime.message(&peer, "session_end", json!({}));
    runtime.peers.lock().unwrap().remove(&peer);
    runtime.legacy_peers.lock().unwrap().remove(&peer);
    runtime.host.lock().unwrap().challenges.remove(&peer);
}
/// The private address of the interface that carries this PC's default route.
pub fn private_address() -> Option<IpAddr> {
    let socket = std::net::UdpSocket::bind("0.0.0.0:0").ok()?;
    socket.connect("8.8.8.8:80").ok()?;
    let address = socket.local_addr().ok()?.ip();
    match address {
        IpAddr::V4(ip) if ip.is_private() || ip.is_link_local() => Some(address),
        _ => None,
    }
}
type LanServer = (IpAddr, tokio::task::JoinHandle<std::io::Result<()>>);
/// Keeps the second listener on the private address only while the setting allows it.
async fn sync_lan(runtime: &Runtime, router: &Router, port: u16, lan: &mut Option<LanServer>, report: bool) {
    let wanted = if runtime.lan_access() { private_address() } else { None };
    if lan.as_ref().map(|(ip, _)| *ip) == wanted {
        return;
    }
    if let Some((_, server)) = lan.take() {
        server.abort();
    }
    if let Some(ip) = wanted {
        match tokio::net::TcpListener::bind((ip, port)).await {
            Ok(listener) => {
                let service = router.clone().into_make_service_with_connect_info::<SocketAddr>();
                *lan = Some((ip, tokio::spawn(async move { axum::serve(listener, service).await })));
            }
            // Periodic retries stay quiet so a busy address does not repeat the notice.
            Err(error) if report => runtime.shared.error(format!("Local network access could not start: {error}")),
            Err(_) => {}
        }
    }
    let url = lan.as_ref().map(|(ip, _)| format!("http://{ip}:{port}"));
    runtime.shared.update(|v| v["lanUrl"] = json!(url));
}
pub async fn run(shared: Arc<Shared>, mut commands: mpsc::Receiver<Value>) -> Result<()> {
    let password = {
        let shared = shared.clone();
        tokio::task::spawn_blocking(move || shared.store.lock().unwrap().password_record())
            .await??
    };
    let runtime = Arc::new(Runtime {
        shared: shared.clone(),
        peers: Mutex::new(HashMap::new()),
        legacy_peers: Mutex::new(HashSet::new()),
        host: Mutex::new(Host {
            authorization: HostSession::default(),
            pending: None,
            active: None,
            challenges: HashMap::new(),
            failures: VecDeque::new(),
            password,
            viewer: Value::Null,
            viewer_challenges: HashMap::new(),
            viewer_key: None,
        }),
        clients: Mutex::new(HashMap::new()),
        connections: Arc::new(Semaphore::new(16)),
        started: Instant::now(),
        mic_test: Mutex::new(None),
    });
    let mut listener = None;
    for port in 8080..8100 {
        // Skip a port another app holds on all interfaces: the local network could not reach us there.
        if tokio::net::TcpListener::bind((std::net::Ipv4Addr::UNSPECIFIED, port)).await.is_err() {
            continue;
        }
        if let Ok(value) =
            tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, port)).await
        {
            listener = Some(value);
            break;
        }
    }
    let Some(listener) = listener else {
        bail!("No local relay port is available")
    };
    let port = listener.local_addr()?.port();
    let binary = std::env::current_exe()?;
    let web = [
        binary.parent().unwrap().join("web"),
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../web"),
    ]
    .into_iter()
    .find(|p| p.join("index.html").is_file());
    let mut router = Router::new().route("/ws", get(upgrade)).route("/health",get(||async{axum::Json(json!({"app":"OpenDesk","protocol":2,"supported_protocols":[2,1]}))}));
    if let Some(web) = web {
        router = router.fallback_service(ServeDir::new(web).append_index_html_on_directories(true));
    }
    let router = router
        .layer(from_fn_with_state(runtime.clone(), local_only))
        .with_state(runtime.clone());
    let service = router.clone().into_make_service_with_connect_info::<SocketAddr>();
    let server = tokio::spawn(async move { axum::serve(listener, service).await });
    let mut lan = None;
    sync_lan(&runtime, &router, port, &mut lan, true).await;
    shared.update(|v| {
        v["localUrl"] = json!(format!("http://127.0.0.1:{port}"));
        v["status"] = json!("Local host ready");
        v["statusTone"] = json!("ready");
    });
    crate::updater::check_on_start(shared.clone());
    let tunnel = if std::env::var_os("OPENDESK_DEV_NO_TUNNEL").is_none() {
        tokio::spawn(crate::p2p::serve(shared.clone(), port));
        tokio::spawn(crate::directory::announce(shared.clone()));
        tokio::spawn(crate::directory::presence(shared.clone()));
        Some(tokio::spawn(crate::directory::tunnel(shared.clone(), port)))
    } else {
        None
    };
    let mut health = tokio::time::interval(Duration::from_secs(1));
    let mut ticks = 0u32;
    loop {
        tokio::select! {
                    command=commands.recv()=>{let Some(command)=command else{break};let lan_changed=command["type"]=="setting"&&command["name"]=="lanAccess";runtime.command(command).await;if lan_changed{sync_lan(&runtime,&router,port,&mut lan,true).await;}},
                    _=health.tick()=>{
        // The private address can change when the PC moves between networks.
        ticks=ticks.wrapping_add(1);
        if runtime.mic_test.lock().unwrap().as_ref().is_some_and(|(_,started)|started.elapsed()>Duration::from_secs(20)){runtime.stop_mic_test();}
        if ticks.is_multiple_of(10){sync_lan(&runtime,&router,port,&mut lan,false).await;}
        if shared.stop.load(Ordering::Acquire){
        break}
        let (expired, stopped)={
        let host=runtime.host.lock().unwrap();
        (host.pending.as_ref().is_some_and(|p|p.deadline<=Instant::now()),host.active.as_ref().is_some_and(|(_,w)|w.is_stopped()))}
        ;
        if expired{
        runtime.end_host("Connection approval expired.");
        }
        else if stopped{
        runtime.end_host("Screen sharing stopped. Reconnect to continue.");
        }
        }
        ,
                }
    }
    runtime.stop_mic_test();
    runtime.end_host("OpenDesk closed.");
    server.abort();
    if let Some((_, server)) = lan {
        server.abort();
    }
    if let Some(tunnel) = tunnel {
        let _ = tokio::time::timeout(Duration::from_secs(2), tunnel).await;
    }
    Ok(())
}
