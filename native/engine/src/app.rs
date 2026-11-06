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
    pub update_cancel: AtomicBool,
    pub peer: tokio::sync::OnceCell<iroh::Endpoint>,
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
fn normalize_settings(settings:&mut Value)->bool{
    if !settings.is_object(){*settings=serde_json::json!({});}
    let defaults=serde_json::json!({"profile":"balanced","theme":"dark","micGain":1.0,"speakerVolume":0.8,"micEnabled":false,"speakerEnabled":true,"publicAccess":true,"lanAccess":false,"unattendedEnabled":false,"sessionGlow":true});
    let mut changed=false;
    for (key,fallback) in defaults.as_object().unwrap(){
        let value=match key.as_str(){
            "micGain"=>settings[key].as_f64().filter(|n|n.is_finite()).map(|n|serde_json::json!(n.clamp(0.0,3.0))),
            "speakerVolume"=>settings[key].as_f64().filter(|n|n.is_finite()).map(|n|serde_json::json!(n.clamp(0.0,1.0))),
            "profile"=>settings[key].as_str().filter(|s|matches!(*s,"balanced"|"performance"|"sharp")).map(|s|serde_json::json!(s)),
            "theme"=>settings[key].as_str().filter(|s|matches!(*s,"dark"|"light")).map(|s|serde_json::json!(s)),
            _=>settings[key].as_bool().map(|v|serde_json::json!(v))
        }.unwrap_or_else(||fallback.clone());
        if settings[key]!=value{settings[key]=value;changed=true;}
    }
    changed
}
impl App {
    pub fn create(directory: PathBuf) -> Result<Self> {
        let mut store = Store::load(directory)?;
        if normalize_settings(&mut store.config["native_settings"]) {
            store.save()?;
        }
        if !store.config["native_settings"]["sharedRoot"].is_string() {
            store.config["native_settings"]["sharedRoot"] =
                json!(std::env::var("USERPROFILE").unwrap_or_default());
            store.save()?;
        }
        let view = json!({"edition":if cfg!(feature="full"){"full"}else{"lite"},"version":env!("CARGO_PKG_VERSION").strip_suffix(".0").unwrap_or(env!("CARGO_PKG_VERSION")),"deviceId":format_id(&store.id()),"deviceName":std::env::var("COMPUTERNAME").unwrap_or_else(|_|"This desktop".into()),"fingerprint":store.fingerprint(),
            "status":"Starting local host…","statusTone":"pending","localUrl":"","shareUrl":"","activeTab":"home","connections":[],"incoming":null,"hostSession":null,"trustRequest":null,
            "recents":store.config["recent_sessions"],"settings":store.config["native_settings"],"hasPassword":!store.config["unattended_password"].as_str().unwrap_or("").is_empty(),"notice":null,"audioDevices":{"inputs":[],"outputs":[]}});
        let shared = Arc::new(Shared {
            store: Mutex::new(store),
            view: Mutex::new(view),
            revision: AtomicU64::new(1),
            frames: Mutex::new(HashMap::new()),
            stop: AtomicBool::new(false),
            update_busy: AtomicBool::new(false),
            update_cancel: AtomicBool::new(false),peer:tokio::sync::OnceCell::new(),
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
#[cfg(test)]mod settings_tests{
    use super::*;
    #[test]fn migrated_audio_settings_match_the_display_and_preserve_explicit_mute(){let mut value=json!({"speakerEnabled":false,"micEnabled":false,"micGain":0.0,"custom":"kept"});assert!(normalize_settings(&mut value));assert_eq!(value["speakerVolume"],0.8);assert_eq!(value["micGain"],0.0);assert_eq!(value["speakerEnabled"],false);assert_eq!(value["publicAccess"],true);assert_eq!(value["custom"],"kept");assert!(!normalize_settings(&mut value));}
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
