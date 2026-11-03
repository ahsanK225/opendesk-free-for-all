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
    let bytes: Vec<u8> = (0..(2 * crate::files::CHUNK + 17))
        .map(|index| (index * 31 % 251) as u8)
        .collect();
    fs::write(&source, &bytes).unwrap();
    client.command(json!({"type":"upload","key":key,"source":source,"directory":shared_dir}));
    let uploaded = shared_dir.join("payload.bin");
    wait("atomic upload", || uploaded.is_file());
    assert_eq!(fs::read(&uploaded).unwrap(), bytes);
    let downloaded = case.root.join("downloaded.bin");
    client.command(json!({"type":"download","key":key,"path":uploaded,"destination":downloaded}));
    wait("atomic download", || downloaded.is_file());
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
