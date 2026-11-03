use crate::store::{Store, format_id};
use anyhow::Result;
use serde_json::{Value, json};
use std::{
    collections::HashMap,
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
    },
};
use tokio::sync::mpsc;

#[derive(Clone)]
pub struct Frame {
    pub width: u32,
    pub height: u32,
    pub generation: u64,
    /// Opaque BGRA8 pixels, row stride `width * 4`, matching Windows/Qt ARGB32.
    pub pixels: Vec<u8>,
}
pub struct Shared {
    pub store: Mutex<Store>,
    pub view: Mutex<Value>,
    pub revision: AtomicU64,
    pub frames: Mutex<HashMap<String, Arc<Frame>>>,
    pub stop: AtomicBool,
    pub update_busy: AtomicBool,
}
impl Shared {
    pub fn update(&self, change: impl FnOnce(&mut Value)) {
        change(&mut self.view.lock().unwrap());
        self.revision.fetch_add(1, Ordering::Release);
    }
    pub fn error(&self, error: impl ToString) {
        self.update(|v| v["notice"] = json!({"message":error.to_string(),"tone":"error"}));
    }
    pub fn connection(&self, key: &str, change: impl FnOnce(&mut Value)) {
        self.update(|v| {
            if let Some(connection) = v["connections"]
                .as_array_mut()
                .and_then(|items| items.iter_mut().find(|item| item["key"] == key))
            {
                change(connection)
            }
        });
    }
    pub fn sync_config(&self) {
        let store = self.store.lock().unwrap();
        self.update(|v| {
            v["recents"] = store.config["recent_sessions"].clone();
            v["settings"] = store.config["native_settings"].clone();
            v["hasPassword"] = json!(
                !store.config["unattended_password"]
                    .as_str()
                    .unwrap_or("")
                    .is_empty()
            );
        });
    }
}
pub struct App {
    pub shared: Arc<Shared>,
    pub commands: mpsc::Sender<Value>,
    pub last_poll: AtomicU64,
    completed: std::sync::mpsc::Receiver<()>,
}
impl App {
    pub fn create(directory: PathBuf) -> Result<Self> {
        let mut store = Store::load(directory)?;
        if !store.config["native_settings"].is_object() {
            store.config["native_settings"] = json!({"profile":"balanced","micGain":1.0,"speakerVolume":0.8,"micEnabled":false,"speakerEnabled":true,"publicAccess":true});
            store.save()?;
        }
        if !store.config["native_settings"]["sharedRoot"].is_string() {
            store.config["native_settings"]["sharedRoot"] =
                json!(std::env::var("USERPROFILE").unwrap_or_default());
            store.save()?;
        }
        let view = json!({"version":"3.0.0-alpha.2","deviceId":format_id(&store.id()),"deviceName":std::env::var("COMPUTERNAME").unwrap_or_else(|_|"This desktop".into()),"fingerprint":store.fingerprint(),
            "status":"Starting local host…","statusTone":"pending","localUrl":"","shareUrl":"","activeTab":"home","connections":[],"incoming":null,"hostSession":null,"trustRequest":null,
            "recents":store.config["recent_sessions"],"settings":store.config["native_settings"],"hasPassword":!store.config["unattended_password"].as_str().unwrap_or("").is_empty(),"notice":null,"audioDevices":{"inputs":[],"outputs":[]}});
        let shared = Arc::new(Shared {
            store: Mutex::new(store),
            view: Mutex::new(view),
            revision: AtomicU64::new(1),
            frames: Mutex::new(HashMap::new()),
            stop: AtomicBool::new(false),
            update_busy: AtomicBool::new(false),
        });
        let (commands, receiver) = mpsc::channel(256);
        let worker = shared.clone();
        let (done, completed) = std::sync::mpsc::sync_channel(1);
        std::thread::Builder::new()
            .name("opendesk-engine".into())
            .spawn(move || {
                match tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .enable_all()
                    .build()
                {
                    Ok(runtime) => {
                        if let Err(error) =
                            runtime.block_on(crate::network::run(worker.clone(), receiver))
                        {
                            worker.error(format!("Host startup: {error:#}"));
                            worker.update(|v| {
                                v["status"] = json!("Host unavailable");
                                v["statusTone"] = json!("error");
                            });
                        }
                    }
                    Err(error) => worker.error(error),
                }
                let _ = done.send(());
            })?;
        Ok(Self {
            shared,
            commands,
            last_poll: AtomicU64::new(0),
            completed,
        })
    }
    pub fn command(&self, value: Value) {
        if self.commands.try_send(value).is_err() {
            self.shared
                .error("The command queue is busy. Please retry.");
        }
    }
}
impl Drop for App {
    fn drop(&mut self) {
        self.shared.stop.store(true, Ordering::Release);
        let _ = self.commands.try_send(json!({"type":"shutdown"}));
        let _ = self
            .completed
            .recv_timeout(std::time::Duration::from_secs(2));
    }
}
