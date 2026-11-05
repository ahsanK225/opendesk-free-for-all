use crate::{
    app::App,
    files::HostFiles,
    store::{self, Store},
};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    thread,
    time::{Duration, Instant},
};

struct Case {
    root: PathBuf,
    base: PathBuf,
}
impl Case {
    fn new() -> Self {
        let base = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".test-state");
        fs::create_dir_all(&base).unwrap();
        let base = fs::canonicalize(base).unwrap();
        let root = base.join(store::token());
        fs::create_dir(&root).unwrap();
        Self { root, base }
    }
    fn directory(&self, name: &str) -> PathBuf {
        let path = self.root.join(name);
        fs::create_dir_all(&path).unwrap();
        path
    }
}
impl Drop for Case {
    fn drop(&mut self) {
        if fs::canonicalize(&self.root).is_ok_and(|path| path.parent() == Some(self.base.as_path()))
        {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
}
fn snapshot(app: &App) -> Value {
    app.shared.view.lock().unwrap().clone()
}
fn wait(label: &str, mut ready: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(15);
    while !ready() {
        assert!(Instant::now() < deadline, "Timed out: {label}");
        thread::sleep(Duration::from_millis(20));
    }
}
fn config(directory: &Path, shared: &Path) {
    fs::write(directory.join("config.json"),serde_json::to_vec(&json!({"native_settings":{"publicAccess":false,"profile":"performance","micEnabled":false,"speakerEnabled":false,"sharedRoot":shared}})).unwrap()).unwrap();
}

#[cfg(feature = "full")]
#[test]
fn native_endpoints_approve_stream_transfer_and_revoke() {
    let case = Case::new();
    let host_dir = case.directory("host");
    let client_dir = case.directory("client");
    let shared_dir = case.directory("shared");
    config(&host_dir, &shared_dir);
    config(&client_dir, &shared_dir);
    let host = App::create(host_dir).unwrap();
    let client = App::create(client_dir).unwrap();
    wait("host listener", || {
        !snapshot(&host)["localUrl"]
            .as_str()
            .unwrap_or("")
            .is_empty()
    });
    let url = snapshot(&host)["localUrl"].as_str().unwrap().to_owned();
    // A remote socket cannot register itself as this application's built-in host.
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap()
        .block_on(async {
            use futures_util::{SinkExt, StreamExt};
            use tokio_tungstenite::tungstenite::Message;
            let (mut socket, _) =
                tokio_tungstenite::connect_async(crate::directory::ws_url(&url).unwrap())
                    .await
                    .unwrap();
            socket
                .send(Message::Text(
                    json!({"type":"register","payload":{"role":"host","protocol":2}})
                        .to_string()
                        .into(),
                ))
                .await
                .unwrap();
            let reply = socket.next().await.unwrap().unwrap();
            let value: Value = serde_json::from_str(reply.to_text().unwrap()).unwrap();
            assert_eq!(value["payload"]["status"], "error");
        });
    client.command(json!({"type":"connect","target":url}));
    wait("device verification", || {
        snapshot(&client)["connections"][0]["needsTrust"] == true
    });
    let key = snapshot(&client)["connections"][0]["key"]
        .as_str()
        .unwrap()
        .to_owned();
    client.command(json!({"type":"trust","key":key,"allow":true}));
    wait("attended approval", || {
        snapshot(&host)["incoming"].is_object()
    });
    let request = snapshot(&host)["incoming"]["requestId"]
        .as_str()
        .unwrap()
        .to_owned();
    host.command(json!({"type":"approve","requestId":request,"allow":true,"permissions":{"input":true,"audio":true,"clipboard":false,"file_transfer":true}}));
    wait("connected state", || {
        snapshot(&client)["connections"][0]["state"] == "connected"
    });
    wait("decoded desktop frame", || {
        client.shared.frames.lock().unwrap().contains_key(&key)
    });
    {
        let frames = client.shared.frames.lock().unwrap();
        let frame = &frames[&key];
        assert!(frame.width > 0 && frame.width <= 2560);
        assert_eq!(
            frame.pixels.len(),
            frame.width as usize * frame.height as usize * 4
        );
    }
    assert_eq!(
        snapshot(&client)["connections"][0]["permissions"]["input"],
        true
    );
    let source = case.root.join("payload.bin");
    let bytes: Vec<u8> = (0..(200 * crate::files::CHUNK + 17))
        .map(|index| (index * 31 % 251) as u8)
        .collect();
    fs::write(&source, &bytes).unwrap();
    let timer = Instant::now();
    client.command(json!({"type":"upload","key":key,"source":source,"directory":shared_dir}));
    let uploaded = shared_dir.join("payload.bin");
    wait("atomic upload", || uploaded.is_file());
    wait("upload progress finished", || {
        snapshot(&client)["connections"][0]["transferInfo"]["state"] == "done"
    });
    println!("upload {} bytes in {:?}", bytes.len(), timer.elapsed());
    assert_eq!(fs::read(&uploaded).unwrap(), bytes);
    let timer = Instant::now();
    let downloaded = case.root.join("downloaded.bin");
    client.command(json!({"type":"download","key":key,"path":uploaded,"destination":downloaded}));
    wait("atomic download", || downloaded.is_file());
    println!("download {} bytes in {:?}", bytes.len(), timer.elapsed());
    assert_eq!(fs::read(&downloaded).unwrap(), bytes);
    // Exercise both voice directions while forcing video updates for longer
    // than the reported 10–20 second failure window. No OS input is injected;
    // microphones are muted and speaker volume is disabled in this fixture.
    let pcm: Vec<u8> = (0..960)
        .flat_map(|i| (((i as f32 * 0.06).sin() * 1200.0) as i16).to_le_bytes())
        .collect();
    let audio =
        json!({"data":B64.encode(pcm),"sample_rate":48000,"channels":1,"format":"pcm_s16le"});
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        let mut payload = audio.clone();
        payload["type"] = json!("audio_chunk");
        client.command(json!({"type":"input","key":key,"payload":payload}));
        host.command(json!({"type":"test_audio","payload":audio}));
        client.command(json!({"type":"input","key":key,"payload":{"type":"video_refresh"}}));
        assert_eq!(snapshot(&client)["connections"][0]["state"], "connected");
        thread::sleep(Duration::from_millis(100));
    }
    wait("host voice reception", || {
        snapshot(&host)["hostSession"]["audio"]["rxPackets"]
            .as_u64()
            .unwrap_or(0)
            >= 200
    });
    wait("client voice reception", || {
        snapshot(&client)["connections"][0]["audio"]["rxPackets"]
            .as_u64()
            .unwrap_or(0)
            >= 200
    });
    host.command(json!({"type":"end_sharing"}));
    wait("session revocation", || {
        snapshot(&client)["connections"][0]["state"] == "disconnected"
    });
    assert!(snapshot(&host)["hostSession"].is_null());
    drop(client);
    drop(host);
}

#[test]
fn legacy_configuration_and_challenges_keep_the_same_identity() {
    let case = Case::new();
    let directory = case.directory("configuration");
    let secret = [7u8; 32];
    fs::write(directory.join("config.json"),serde_json::to_vec(&json!({"host_id":"123 456 789","device_identity":B64.encode(secret),"unattended_password":"fixture-password","custom_legacy_field":{"retained":true}})).unwrap()).unwrap();
    let store = Store::load(directory).unwrap();
    assert_eq!(store.id(), "123456789");
    assert!(
        store.config["device_identity"]
            .as_str()
            .unwrap()
            .starts_with("dpapi:")
    );
    assert!(
        store.config["unattended_password"]
            .as_str()
            .unwrap()
            .starts_with("dpapi:")
    );
    assert_eq!(store.config["custom_legacy_field"]["retained"], true);
    let expected = B64.encode(
        ed25519_dalek::SigningKey::from_bytes(&secret)
            .verifying_key()
            .as_bytes(),
    );
    assert_eq!(store.key(), expected);
    let nonce = "native-fixture-nonce-0123456789";
    assert_eq!(
        store::verify_identity(&store.identity_packet(nonce), nonce).unwrap(),
        expected
    );
    assert!(store::verify_identity(&store.identity_packet(nonce), "wrong-nonce").is_err());
    let record = store.password_record().unwrap().unwrap();
    let challenge = json!({"salt":record["salt"],"iterations":record["iterations"],"nonce":nonce});
    let proof = store::password_proof("fixture-password", &challenge).unwrap();
    assert!(store::verify_proof(&record, nonce, &proof));
    assert!(!store::verify_proof(&record, "different-nonce", &proof));
}

#[test]
fn file_upload_hash_failure_is_atomic_and_paths_are_confined() {
    let case = Case::new();
    let root = case.directory("shared");
    let existing = root.join("keep.txt");
    fs::write(&existing, b"original").unwrap();
    let mut files = HostFiles::new(root.clone()).unwrap();
    assert!(
        files
            .packet("file_list_req", &json!({"path":r"\\127.0.0.1\not-shared"}))
            .is_err()
    );
    assert!(
        files
            .packet("file_list_req", &json!({"path":root.join("../outside")}))
            .is_err()
    );
    files.packet("file_upload_start",&json!({"upload_id":"test-upload","filename":"keep.txt","target_dir":root,"file_size":3,"total_chunks":1,"sha256":"0".repeat(64)})).unwrap();
    assert!(
        files
            .packet(
                "file_chunk",
                &json!({"upload_id":"test-upload","chunk_index":0,"data":B64.encode(b"bad")})
            )
            .is_err()
    );
    assert_eq!(fs::read(&existing).unwrap(), b"original");
    assert!(
        !fs::read_dir(&root)
            .unwrap()
            .flatten()
            .any(|entry| entry.file_name().to_string_lossy().ends_with(".part"))
    );
}

#[test]
fn older_viewer_reaches_attended_approval_without_files() {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::Message;
    let case = Case::new();
    let directory = case.directory("host");
    let shared = case.directory("shared");
    config(&directory, &shared);
    let host = App::create(directory).unwrap();
    wait("host listener", || {
        !snapshot(&host)["localUrl"].as_str().unwrap_or("").is_empty()
    });
    let url = snapshot(&host)["localUrl"].as_str().unwrap().to_owned();
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap()
        .block_on(async {
            let (mut socket, _) =
                tokio_tungstenite::connect_async(crate::directory::ws_url(&url).unwrap())
                    .await
                    .unwrap();
            // An older viewer states no protocol at all.
            let register = json!({"type":"register","payload":{"role":"client"}});
            socket
                .send(Message::Text(register.to_string().into()))
                .await
                .unwrap();
            let mut approved = false;
            let connect = json!({"type":"connect","payload":{"target_id":"remote_host"}});
            let deadline = Instant::now() + Duration::from_secs(20);
            loop {
                let next = tokio::time::timeout_at(deadline.into(), socket.next())
                    .await
                    .expect("Timed out waiting for the host")
                    .unwrap()
                    .unwrap();
                let Message::Text(text) = next else { continue };
                let value: Value = serde_json::from_str(&text).unwrap();
                let payload = &value["payload"];
                match value["type"].as_str().unwrap_or("") {
                    "register_resp" => {
                        assert_eq!(payload["status"], "ok");
                        socket
                            .send(Message::Text(connect.to_string().into()))
                            .await
                            .unwrap();
                    }
                    "connect_resp" if payload["status"] == "waiting_approval" => {
                        let view = snapshot(&host);
                        let incoming = &view["incoming"];
                        assert_eq!(incoming["legacy"], true);
                        host.command(json!({"type":"approve","requestId":incoming["requestId"],"allow":true,"permissions":{"input":true,"audio":false,"clipboard":false,"file_transfer":true}}));
                        approved = true;
                    }
                    "connect_resp" => {
                        assert!(approved);
                        assert_eq!(payload["status"], "ok");
                        assert_eq!(payload["permissions"]["input"], true);
                        assert_eq!(payload["permissions"]["file_transfer"], false);
                        break;
                    }
                    _ => {}
                }
            }
        });
}

/// Runs against the relay.py of the v1.9 tag; the ports come from its loopback harness.
#[test]
#[ignore = "needs the archived v1.9 relay running on loopback"]
fn archived_v1_9_relay_connects_in_compatibility_mode() {
    let port = std::env::var("OPENDESK_V19_OPEN_PORT").unwrap();
    let case = Case::new();
    let app = viewer(&case, json!({}));
    let key = dial(&app, format!("127.0.0.1:{port}"));
    wait("compatibility consent", || {
        snapshot(&app)["connections"][0]["needsLegacy"] == true
    });
    app.command(json!({"type":"legacy_accept","key":key,"allow":true,"permissions":{"input":true,"audio":false,"clipboard":false,"file_transfer":false}}));
    wait("connected to the archived relay", || {
        snapshot(&app)["connections"][0]["state"] == "connected"
    });
    let view = snapshot(&app);
    let session = &view["connections"][0];
    assert_eq!(session["protocol"], 1);
    assert_eq!(session["permissions"]["input"], true);
    assert_eq!(session["permissions"]["file_transfer"], false);
}
#[test]
#[ignore = "needs the archived v1.9 relay running on loopback"]
fn archived_v1_9_relay_with_a_password_is_refused_without_sending_it() {
    let port = std::env::var("OPENDESK_V19_LOCKED_PORT").unwrap();
    let case = Case::new();
    let app = viewer(&case, json!({}));
    let key = dial(&app, format!("127.0.0.1:{port}"));
    wait("compatibility consent", || {
        snapshot(&app)["connections"][0]["needsLegacy"] == true
    });
    app.command(json!({"type":"legacy_accept","key":key,"allow":true,"permissions":{"input":true,"audio":false,"clipboard":false,"file_transfer":false}}));
    assert!(wait_for_error(&app).contains("does not send passwords"));
}

#[test]
fn local_network_access_follows_its_setting() {
    use futures_util::{SinkExt, StreamExt};
    use tokio_tungstenite::tungstenite::Message;
    let Some(ip) = crate::network::private_address() else {
        eprintln!("skipped: this PC has no private network address");
        return;
    };
    let case = Case::new();
    let directory = case.directory("host");
    let shared = case.directory("shared");
    config(&directory, &shared);
    let host = App::create(directory).unwrap();
    wait("host listener", || {
        !snapshot(&host)["localUrl"].as_str().unwrap_or("").is_empty()
    });
    let local = snapshot(&host)["localUrl"].as_str().unwrap().to_owned();
    let port = local.rsplit(':').next().unwrap().to_owned();
    let address = format!("{ip}:{port}");
    let view = snapshot(&host);
    assert_eq!(view["settings"]["lanAccess"], false);
    assert!(view["lanUrl"].is_null());
    assert!(std::net::TcpStream::connect(&address).is_err(), "off by default");
    host.command(json!({"type":"setting","name":"lanAccess","value":true}));
    wait("local network address", || snapshot(&host)["lanUrl"].is_string());
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap()
        .block_on(async {
            let (mut socket, _) =
                tokio_tungstenite::connect_async(crate::directory::ws_url(&address).unwrap())
                    .await
                    .unwrap();
            let register = json!({"type":"register","payload":{"role":"client","protocol":2}});
            socket
                .send(Message::Text(register.to_string().into()))
                .await
                .unwrap();
            let first = socket.next().await.unwrap().unwrap().into_text().unwrap();
            assert!(first.contains("register_resp"));
            host.command(json!({"type":"setting","name":"lanAccess","value":false}));
            // A connection already open must not outlive the setting.
            tokio::time::timeout(std::time::Duration::from_secs(10), async {
                while let Some(Ok(_)) = socket.next().await {}
            })
            .await
            .expect("the open local network connection was closed");
        });
    wait("local network address removed", || snapshot(&host)["lanUrl"].is_null());
    assert!(std::net::TcpStream::connect(&address).is_err(), "closed again");
    let loopback = local.trim_start_matches("http://");
    assert!(std::net::TcpStream::connect(loopback).is_ok(), "this PC keeps access");
}

const SECRET: &str = "fixture-remote-secret";

struct ScriptedPeer {
    port: u16,
    received: std::sync::Arc<std::sync::Mutex<Vec<Value>>>,
    thread: thread::JoinHandle<()>,
}
impl ScriptedPeer {
    /// A loopback desktop that answers each viewer packet and records all of them.
    fn start(mut respond: impl FnMut(&Value) -> Vec<Value> + Send + 'static) -> Self {
        use futures_util::{SinkExt, StreamExt};
        use tokio_tungstenite::tungstenite::Message;
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let port = listener.local_addr().unwrap().port();
        let received = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
        let log = received.clone();
        let thread = thread::spawn(move || {
            tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap()
                .block_on(async move {
                    let listener = tokio::net::TcpListener::from_std(listener).unwrap();
                    let (stream, _) = listener.accept().await.unwrap();
                    let mut socket = tokio_tungstenite::accept_async(stream).await.unwrap();
                    while let Some(Ok(message)) = socket.next().await {
                        let Message::Text(text) = message else {
                            continue;
                        };
                        let value: Value = serde_json::from_str(&text).unwrap();
                        log.lock().unwrap().push(value.clone());
                        for reply in respond(&value) {
                            let reply = Message::Text(reply.to_string().into());
                            if socket.send(reply).await.is_err() {
                                return;
                            }
                        }
                    }
                });
        });
        Self {
            port,
            received,
            thread,
        }
    }
    fn sent(&self, kind: &str) -> Vec<Value> {
        let received = self.received.lock().unwrap();
        received
            .iter()
            .filter(|p| p["type"] == kind)
            .cloned()
            .collect()
    }
    fn assert_secret_not_sent(&self) {
        let received = self.received.lock().unwrap();
        assert!(!Value::Array(received.clone()).to_string().contains(SECRET));
    }
}
fn reply(kind: &str, payload: Value) -> Vec<Value> {
    vec![json!({"type":kind,"payload":payload})]
}
fn older_desktop(answer: Value) -> ScriptedPeer {
    ScriptedPeer::start(move |packet| match packet["type"].as_str().unwrap_or("") {
        "register" => reply("register_resp", json!({"status":"ok","protocol":1})),
        "connect" => reply("connect_resp", answer.clone()),
        _ => Vec::new(),
    })
}
fn viewer(case: &Case, trusted: Value) -> App {
    let directory = case.directory("viewer");
    let shared = case.directory("shared");
    fs::write(directory.join("config.json"),serde_json::to_vec(&json!({"trusted_devices":trusted,"native_settings":{"publicAccess":false,"profile":"performance","micEnabled":false,"speakerEnabled":false,"sharedRoot":shared}})).unwrap()).unwrap();
    App::create(directory).unwrap()
}
fn dial(app: &App, target: String) -> String {
    app.command(json!({"type":"connect","target":target,"password":SECRET}));
    wait("viewer connection entry", || {
        snapshot(app)["connections"][0]["key"].is_string()
    });
    snapshot(app)["connections"][0]["key"]
        .as_str()
        .unwrap()
        .to_owned()
}
fn wait_for_error(app: &App) -> String {
    wait("refused connection", || {
        snapshot(app)["connections"][0]["state"] == "error"
    });
    snapshot(app)["connections"][0]["message"]
        .as_str()
        .unwrap()
        .to_owned()
}

#[test]
fn saved_device_answering_as_protocol_1_is_refused_without_a_password() {
    for by_address in [false, true] {
        let case = Case::new();
        let peer = older_desktop(json!({"status":"waiting_approval"}));
        let address = format!("127.0.0.1:{}", peer.port);
        let (saved_as, target) = if by_address {
            (format!("ws://{address}/ws"), address)
        } else {
            ("123456789".to_owned(), format!("123456789@{address}"))
        };
        let app = viewer(&case, json!({ saved_as: "c2F2ZWQtZGV2aWNlLWtleQ==" }));
        dial(&app, target);
        assert!(wait_for_error(&app).contains("cannot prove its identity"));
        assert_ne!(snapshot(&app)["connections"][0]["needsLegacy"], true);
        assert!(peer.sent("connect").is_empty());
        peer.assert_secret_not_sent();
    }
}

#[test]
fn compatibility_mode_reports_a_required_password_instead_of_sending_it() {
    let case = Case::new();
    let peer = older_desktop(json!({"status":"error","message":"Invalid password."}));
    let app = viewer(&case, json!({}));
    let key = dial(&app, format!("127.0.0.1:{}", peer.port));
    wait("compatibility consent", || {
        snapshot(&app)["connections"][0]["needsLegacy"] == true
    });
    app.command(json!({"type":"legacy_accept","key":key,"allow":true,"permissions":{"input":true,"audio":false,"clipboard":false,"file_transfer":false}}));
    assert!(wait_for_error(&app).contains("does not send passwords"));
    assert_ne!(snapshot(&app)["connections"][0]["needsPassword"], true);
    let connect = peer.sent("connect");
    assert_eq!(connect.len(), 1);
    assert!(connect[0]["payload"].get("password").is_none());
    peer.assert_secret_not_sent();
}

#[test]
fn password_command_is_not_forwarded_in_compatibility_mode() {
    let case = Case::new();
    let peer = older_desktop(json!({"status":"waiting_approval"}));
    let app = viewer(&case, json!({}));
    let key = dial(&app, format!("127.0.0.1:{}", peer.port));
    wait("compatibility consent", || {
        snapshot(&app)["connections"][0]["needsLegacy"] == true
    });
    app.command(json!({"type":"legacy_accept","key":key,"allow":true,"permissions":{"input":true,"audio":false,"clipboard":false,"file_transfer":false}}));
    wait("attended request", || {
        snapshot(&app)["connections"][0]["state"] == "waiting"
    });
    app.command(json!({"type":"password","key":key,"password":SECRET}));
    app.command(json!({"type":"disconnect","key":key}));
    wait("peer connection closed", || peer.thread.is_finished());
    assert_eq!(peer.sent("connect").len(), 1);
    peer.assert_secret_not_sent();
}

#[test]
fn downgrade_after_a_verified_identity_is_refused() {
    let case = Case::new();
    let device = Store::load(case.directory("device")).unwrap();
    let peer = ScriptedPeer::start(move |packet| match packet["type"].as_str().unwrap_or("") {
        "register" => reply("register_resp", json!({"status":"ok","protocol":2})),
        "identify" => reply(
            "identity",
            device.identity_packet(packet["payload"]["nonce"].as_str().unwrap()),
        ),
        // Registration is answered a second time once the viewer trusts this key.
        "connect" => reply("register_resp", json!({"status":"ok","protocol":1})),
        _ => Vec::new(),
    });
    let app = viewer(&case, json!({}));
    let key = dial(&app, format!("127.0.0.1:{}", peer.port));
    wait("device verification", || {
        snapshot(&app)["connections"][0]["needsTrust"] == true
    });
    app.command(json!({"type":"trust","key":key,"allow":true}));
    assert!(wait_for_error(&app).contains("repeated its registration"));
    assert_ne!(snapshot(&app)["connections"][0]["needsLegacy"], true);
    assert_eq!(peer.sent("connect").len(), 1);
    peer.assert_secret_not_sent();
}

/// Uses the real tunnel and directories, so it needs internet access and the tunnel enabled.
#[test]
#[ignore = "uses public services"]
fn a_desktop_is_reached_by_id_alone_through_the_public_services() {
    fn slow_wait(label: &str, seconds: u64, mut ready: impl FnMut() -> bool) -> f64 {
        let start = Instant::now();
        while !ready() {
            assert!(start.elapsed().as_secs() < seconds, "Timed out: {label}");
            thread::sleep(Duration::from_millis(100));
        }
        start.elapsed().as_secs_f64()
    }
    assert!(std::env::var_os("OPENDESK_DEV_NO_TUNNEL").is_none());
    let case = Case::new();
    let (host_dir, client_dir, late_dir, shared_dir) = (case.directory("host"), case.directory("client"), case.directory("late"), case.directory("shared"));
    fs::write(host_dir.join("config.json"), serde_json::to_vec(&json!({"native_settings":{"publicAccess":true,"lanAccess":false,"micEnabled":false,"speakerEnabled":false,"sharedRoot":shared_dir}})).unwrap()).unwrap();
    for directory in [&client_dir, &late_dir] { config(directory, &shared_dir); }
    let host = App::create(host_dir).unwrap();
    let client = App::create(client_dir).unwrap();
    let id: String = snapshot(&host)["deviceId"].as_str().unwrap().chars().filter(char::is_ascii_digit).collect();
    let tunnel = slow_wait("tunnel ready", 120, || !snapshot(&host)["shareUrl"].as_str().unwrap_or("").is_empty());
    println!("tunnel ready after {tunnel:.1} s");
    thread::sleep(Duration::from_secs(5));
    let brokers = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
        tokio::time::sleep(Duration::from_secs(5)).await;
        let mut seen = Vec::new();
        for broker in crate::mqtt::BROKERS {
            seen.push(crate::mqtt::read(broker, &id).await.map(|v| v.map(|t| t.len())).map_err(|e| e.to_string()));
        }
        seen
    });
    println!("brokers hold: {brokers:?}");
    client.command(json!({"type":"connect","target":id}));
    let lookup = slow_wait("device verification", 90, || snapshot(&client)["connections"][0]["needsTrust"] == true);
    println!("found by ID and connected after {lookup:.1} s, route {}", snapshot(&client)["connections"][0]["route"]);
    let key = snapshot(&client)["connections"][0]["key"].as_str().unwrap().to_owned();
    client.command(json!({"type":"trust","key":key,"allow":true}));
    slow_wait("attended approval", 30, || snapshot(&host)["incoming"].is_object());
    let request = snapshot(&host)["incoming"]["requestId"].as_str().unwrap().to_owned();
    host.command(json!({"type":"approve","requestId":request,"allow":true,"permissions":{"input":false,"audio":false,"clipboard":false,"file_transfer":false}}));
    let first = slow_wait("decoded desktop frame", 30, || client.shared.frames.lock().unwrap().contains_key(&key));
    println!("first frame after {first:.1} s");
    let mut rtts = Vec::new();
    let mut seconds = 0;
    while seconds < 45 {
        seconds += 1;
        thread::sleep(Duration::from_secs(1));
        let rtt = snapshot(&client)["connections"][0]["rtt"].as_f64();
        if let Some(rtt) = rtt { rtts.push(rtt); }
        println!("second: rtt {:.0} route {} {}ms host {}", rtt.unwrap_or(0.0), snapshot(&client)["connections"][0]["route"], snapshot(&client)["connections"][0]["routeMs"], snapshot(&host)["hostSession"]["video"]);
    }
    rtts.sort_by(f64::total_cmp);
    println!("round trip through the tunnel: {} samples, median {:.0} ms, worst {:.0} ms", rtts.len(), rtts.get(rtts.len() / 2).copied().unwrap_or(0.0), rtts.last().copied().unwrap_or(0.0));
    drop(client);
    drop(host);
    if std::env::var_os("OPENDESK_E2E_SKIP_OFFLINE").is_some() { return }
    thread::sleep(Duration::from_secs(130));
    let late = App::create(late_dir).unwrap();
    late.command(json!({"type":"connect","target":id}));
    slow_wait("offline message", 120, || snapshot(&late)["connections"][0]["message"].as_str().is_some_and(|m| m.contains("last online")));
    println!("offline desktop says: {}", snapshot(&late)["connections"][0]["message"].as_str().unwrap().replace(&id, "<id>"));
}
