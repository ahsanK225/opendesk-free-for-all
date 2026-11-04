use crate::transport::Sender;
use crate::{
    app::Shared,
    network::{Outbound, packet},
    store::token,
};
use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs::{self, File, OpenOptions},
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    time::{Duration, Instant},
};
use windows::{
    Win32::Storage::FileSystem::{MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH, MoveFileExW},
    core::PCWSTR,
};
pub const CHUNK: usize = 65536;
/// Chunks a peer may have in flight. Peers that do not state a window get one at a time.
const WINDOW: u64 = 24;
const MAX_SIZE: u64 = 4 * 1024 * 1024 * 1024;
fn replace(source: &Path, target: &Path) -> Result<()> {
    use std::os::windows::ffi::OsStrExt;
    let s: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let t: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    unsafe {
        MoveFileExW(
            PCWSTR(s.as_ptr()),
            PCWSTR(t.as_ptr()),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )?;
    }
    Ok(())
}
pub fn valid_name(name: &str) -> bool {
    if name.is_empty()
        || name.len() > 240
        || name == "."
        || name == ".."
        || name.ends_with([' ', '.'])
        || name.chars().any(|c| c < ' ' || "/\\:<>\"|?*".contains(c))
    {
        return false;
    }
    let base = name.split('.').next().unwrap_or("").to_ascii_uppercase();
    !matches!(base.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        && !(base.len() == 4
            && (base.starts_with("COM") || base.starts_with("LPT"))
            && matches!(base.as_bytes()[3], b'1'..=b'9'))
}
fn chunks(size: u64) -> u64 {
    size.div_ceil(CHUNK as u64).max(1)
}
fn text(value: &Value, key: &str) -> Result<String> {
    Ok(value[key]
        .as_str()
        .with_context(|| format!("Missing {key}"))?
        .to_owned())
}
fn number(value: &Value, key: &str) -> Result<u64> {
    value[key]
        .as_u64()
        .with_context(|| format!("Invalid {key}"))
}
fn scope(root: &Path, path: &str) -> Result<PathBuf> {
    use std::{os::windows::fs::MetadataExt, path::Component};
    let path = if path.is_empty() || path == "." {
        root.to_owned()
    } else {
        let input = PathBuf::from(path);
        if input.is_absolute() {
            input
        } else if input
            .components()
            .any(|p| matches!(p, Component::Prefix(_) | Component::RootDir))
        {
            bail!("Drive-relative paths are not shared")
        } else {
            root.join(input)
        }
    };
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::ParentDir => {
                if !normalized.pop() {
                    bail!("Invalid parent path")
                }
            }
            Component::CurDir => {}
            Component::Normal(name) if name == ".." => {
                if !normalized.pop() {
                    bail!("Invalid parent path")
                }
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    fn key(path: &Path) -> String {
        let text = path.to_string_lossy().replace('/', "\\").to_lowercase();
        let text = if let Some(path) = text.strip_prefix("\\\\?\\unc\\") {
            format!("\\\\{path}")
        } else {
            text.strip_prefix("\\\\?\\").unwrap_or(&text).to_owned()
        };
        text.trim_end_matches('\\').to_owned()
    }
    let root_key = key(root);
    let path_key = key(&normalized);
    if path_key != root_key && !path_key.starts_with(&(root_key + "\\")) {
        bail!("Path is outside the shared folder")
    }
    // Reject reparse points before canonicalize can follow a junction or UNC path.
    let mut walk = root.to_owned();
    for component in normalized.components().skip(root.components().count()) {
        let Component::Normal(name) = component else {
            bail!("Invalid shared path")
        };
        if name.to_string_lossy().contains(':') {
            bail!("Alternate data streams are not shared")
        };
        walk.push(name);
        if fs::symlink_metadata(&walk)?.file_attributes() & 0x400 != 0 {
            bail!("Symbolic links and junctions are not shared")
        }
    }
    let resolved = fs::canonicalize(normalized)?;
    if !resolved.starts_with(root) {
        bail!("Path is outside the shared home folder")
    }
    Ok(resolved)
}
struct Partial {
    temporary: PathBuf,
    final_path: PathBuf,
    file: Option<File>,
}
impl Partial {
    fn create(final_path: PathBuf) -> Result<Self> {
        let parent = final_path
            .parent()
            .context("Missing destination directory")?;
        let temporary = parent.join(format!(".opendesk-{}.part", token()));
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        Ok(Self {
            temporary,
            final_path,
            file: Some(file),
        })
    }
    fn finish(&mut self) -> Result<()> {
        if let Some(mut file) = self.file.take() {
            file.flush()?;
            file.sync_all()?;
        }
        replace(&self.temporary, &self.final_path)
    }
}
impl Drop for Partial {
    fn drop(&mut self) {
        drop(self.file.take());
        let _ = fs::remove_file(&self.temporary);
    }
}
struct HostUpload {
    partial: Partial,
    size: u64,
    total: u64,
    index: u64,
    received: u64,
    hash: Sha256,
    expected: Option<String>,
}
pub struct HostFiles {
    root: PathBuf,
    uploads: HashMap<String, HostUpload>,
}
impl HostFiles {
    pub fn new(root: PathBuf) -> Result<Self> {
        Ok(Self {
            root: fs::canonicalize(root)?,
            uploads: HashMap::new(),
        })
    }
    pub fn packet(&mut self, typ: &str, p: &Value) -> Result<Value> {
        match typ {
            "file_list_req" => {
                let path = scope(&self.root, p["path"].as_str().unwrap_or("."))?;
                if !path.is_dir() {
                    bail!("This path is not a directory")
                };
                let mut entries = Vec::new();
                let mut budget = 0usize;
                let mut truncated = false;
                for entry in fs::read_dir(&path)?.take(10_000).flatten() {
                    if let Ok(metadata) = entry.metadata() {
                        use std::os::windows::fs::MetadataExt;
                        if metadata.file_attributes() & 0x400 != 0 {
                            continue;
                        }
                        budget += entry.file_name().to_string_lossy().len() * 6 + 160;
                        if budget > 1024 * 1024 {
                            truncated = true;
                            break;
                        }
                        entries.push(json!({"name":entry.file_name().to_string_lossy(),"is_dir":metadata.is_dir(),"size":if metadata.is_dir(){0}else{metadata.len()},"modified":metadata.modified().ok().and_then(|t|t.duration_since(std::time::UNIX_EPOCH).ok()).map(|d|d.as_secs()).unwrap_or(0)}));
                    }
                }
                entries.sort_by_key(|v| {
                    (
                        !v["is_dir"].as_bool().unwrap_or(false),
                        v["name"].as_str().unwrap_or("").to_lowercase(),
                    )
                });
                Ok(
                    json!({"path":path,"parent":if path==self.root{None}else{path.parent()},"entries":entries,"truncated":truncated}),
                )
            }
            "file_download_req" => {
                let path = scope(&self.root, &text(p, "path")?)?;
                let index = number(p, "chunk_index")?;
                let mut file = File::open(&path)?;
                let size = file.metadata()?.len();
                if size > MAX_SIZE {
                    bail!("File exceeds the 4 GiB transfer limit")
                };
                let total = chunks(size);
                if index >= total {
                    bail!("Invalid chunk index")
                };
                file.seek(SeekFrom::Start(index * CHUNK as u64))?;
                let mut bytes = vec![0; ((size - index * CHUNK as u64).min(CHUNK as u64)) as usize];
                file.read_exact(&mut bytes)?;
                Ok(
                    json!({"window":WINDOW,"file_path":path,"filename":path.file_name().unwrap_or_default().to_string_lossy(),"file_size":size,"chunk_index":index,"total_chunks":total,"data":B64.encode(bytes),"is_last":index+1==total}),
                )
            }
            "file_upload_start" => {
                let id = text(p, "upload_id")?;
                if id.is_empty()
                    || id.len() > 64
                    || !id
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
                {
                    bail!("Invalid transfer ID")
                };
                if self.uploads.contains_key(&id) || self.uploads.len() >= 4 {
                    bail!("Transfer limit reached")
                }
                let filename = text(p, "filename")?;
                if !valid_name(&filename) {
                    bail!("Invalid filename")
                };
                let size = number(p, "file_size")?;
                let total = number(p, "total_chunks")?;
                if size > MAX_SIZE || total != chunks(size) {
                    bail!("Invalid declared file size or chunk count")
                }
                let expected = p["sha256"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .map(str::to_ascii_lowercase);
                if expected
                    .as_ref()
                    .is_some_and(|s| s.len() != 64 || hex::decode(s).is_err())
                {
                    bail!("Invalid SHA-256 digest")
                }
                let directory = scope(&self.root, p["target_dir"].as_str().unwrap_or("."))?;
                if !directory.is_dir() {
                    bail!("Destination is not a directory")
                };
                let destination = directory.join(filename);
                if destination.exists() {
                    scope(&self.root, &destination.to_string_lossy())?;
                }
                self.uploads.insert(
                    id.clone(),
                    HostUpload {
                        partial: Partial::create(destination)?,
                        size,
                        total,
                        index: 0,
                        received: 0,
                        hash: Sha256::new(),
                        expected,
                    },
                );
                Ok(json!({"upload_id":id,"status":"ready","window":WINDOW}))
            }
            "file_chunk" => {
                let id = text(p, "upload_id")?;
                let index = number(p, "chunk_index")?;
                let data = B64.decode(text(p, "data")?)?;
                let result = (|| -> Result<Value> {
                    let transfer = self.uploads.get_mut(&id).context("Unknown transfer")?;
                    if index != transfer.index {
                        bail!("Duplicate or out-of-order chunk")
                    };
                    let expected = (transfer.size - transfer.received).min(CHUNK as u64) as usize;
                    if data.len() != expected {
                        bail!("Chunk length differs from the declared file size")
                    };
                    transfer
                        .partial
                        .file
                        .as_mut()
                        .context("Closed transfer")?
                        .write_all(&data)?;
                    transfer.hash.update(&data);
                    transfer.received += data.len() as u64;
                    transfer.index += 1;
                    if transfer.index == transfer.total {
                        let digest = hex::encode(transfer.hash.clone().finalize());
                        if transfer
                            .expected
                            .as_ref()
                            .is_some_and(|expected| *expected != digest)
                        {
                            bail!("Upload SHA-256 mismatch")
                        };
                        let parent = transfer.partial.final_path.parent().unwrap();
                        scope(&self.root, &parent.to_string_lossy())?;
                        if transfer.partial.final_path.exists() {
                            scope(&self.root, &transfer.partial.final_path.to_string_lossy())?;
                        }
                        transfer.partial.finish()?;
                        Ok(
                            json!({"upload_id":id,"status":"complete","final_path":transfer.partial.final_path,"sha256":digest}),
                        )
                    } else {
                        Ok(
                            json!({"upload_id":id,"status":"in_progress","received_chunks":transfer.index,"total_chunks":transfer.total}),
                        )
                    }
                })();
                if result.as_ref().is_ok_and(|v| v["status"] == "complete") || result.is_err() {
                    self.uploads.remove(&id);
                }
                result
            }
            _ => bail!("Unknown file operation"),
        }
    }
}
struct Download {
    partial: Partial,
    remote: String,
    name: String,
    started: Instant,
    requested: u64,
    index: u64,
    size: Option<u64>,
    hash: Sha256,
}
struct Upload {
    file: File,
    id: String,
    filename: String,
    directory: String,
    started: Instant,
    expected: String,
    total: u64,
    index: u64,
    acked: u64,
    window: u64,
    size: u64,
}
enum FileEvent {
    Command(Value, Sender<Outbound>),
    Packet(String, Value, Sender<Outbound>),
}
pub struct ClientFiles {
    sender: mpsc::SyncSender<FileEvent>,
    stop: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
}
impl ClientFiles {
    pub fn new(shared: Arc<Shared>, key: String) -> Self {
        let (sender, receiver) = mpsc::sync_channel(64);
        let stop = Arc::new(AtomicBool::new(false));
        let worker_stop = stop.clone();
        let cancel = Arc::new(AtomicBool::new(false));
        let worker_cancel = cancel.clone();
        let _ = std::thread::Builder::new()
            .name("opendesk-files".into())
            .spawn(move || {
                let mut worker = ClientWorker {
                    shared,
                    key,
                    stop: worker_stop,
                    cancel: worker_cancel,
                    shown: Instant::now(),
                    download: None,
                    upload: None,
                };
                while !worker.stop.load(Ordering::Acquire) {
                    match receiver.recv_timeout(Duration::from_millis(50)) {
                        Ok(event) => {
                            if let Err(error) = worker.event(event) {
                                worker.shared.error(format!("File transfer: {error:#}"));
                                worker.download = None;
                                worker.upload = None;
                                worker.status("Transfer failed");
                                worker.finished("failed", &format!("{error:#}"));
                            }
                        }
                        Err(mpsc::RecvTimeoutError::Timeout) => {}
                        Err(_) => break,
                    }
                }
            });
        Self { sender, stop, cancel }
    }
    pub async fn command(&mut self, p: &Value, tx: &Sender<Outbound>) -> Result<()> {
        if p["type"] == "cancel_transfer" {
            self.cancel.store(true, Ordering::Release);
        }
        self.sender
            .try_send(FileEvent::Command(p.clone(), tx.clone()))
            .map_err(|_| anyhow::anyhow!("File transfer queue is busy"))
    }
    pub async fn packet(&mut self, typ: &str, p: &Value, tx: &Sender<Outbound>) -> Result<()> {
        self.sender
            .try_send(FileEvent::Packet(typ.into(), p.clone(), tx.clone()))
            .map_err(|_| anyhow::anyhow!("File transfer queue is busy"))
    }
}
impl Drop for ClientFiles {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
    }
}
struct ClientWorker {
    shared: Arc<Shared>,
    key: String,
    stop: Arc<AtomicBool>,
    cancel: Arc<AtomicBool>,
    shown: Instant,
    download: Option<Download>,
    upload: Option<Upload>,
}
impl ClientWorker {
    fn status(&self, message: impl ToString) {
        self.shared
            .connection(&self.key, |v| v["transfer"] = json!(message.to_string()));
    }
    /// Publishes progress at most five times a second, except when forced.
    fn progress(&mut self, state: &str, direction: &str, name: &str, (done, total): (u64, u64), started: Instant, force: bool) {
        if !force && self.shown.elapsed() < Duration::from_millis(200) {
            return;
        }
        self.shown = Instant::now();
        let speed = done as f64 / started.elapsed().as_secs_f64().max(0.001);
        self.shared.connection(&self.key, |v| {
            v["transferInfo"] = json!({"state":state,"direction":direction,"name":name,"done":done,"total":total,"speed":speed});
        });
    }
    fn finished(&self, state: &str, message: &str) {
        self.shared.connection(&self.key, |v| {
            v["transferInfo"]["state"] = json!(state);
            v["transferInfo"]["message"] = json!(message);
        });
    }
    fn upload_fill(&mut self, tx: &Sender<Outbound>) -> Result<()> {
        while self
            .upload
            .as_ref()
            .is_some_and(|u| u.index < u.total && u.index - u.acked < u.window)
        {
            self.upload_chunk(tx)?;
        }
        Ok(())
    }
    fn send(tx: &Sender<Outbound>, typ: &str, p: Value) -> Result<()> {
        tx.blocking_send(Outbound::Packet(packet(typ, p)))
            .context("Session disconnected")
    }
    fn upload_chunk(&mut self, tx: &Sender<Outbound>) -> Result<()> {
        let upload = self.upload.as_mut().context("Upload has ended")?;
        if upload.index >= upload.total {
            bail!("Unexpected upload acknowledgement")
        };
        let length = (upload.size - upload.index * CHUNK as u64).min(CHUNK as u64) as usize;
        let mut data = vec![0; length];
        upload.file.read_exact(&mut data)?;
        Self::send(
            tx,
            "file_chunk",
            json!({"upload_id":upload.id,"chunk_index":upload.index,"data":B64.encode(data)}),
        )?;
        upload.index += 1;
        Ok(())
    }
    fn event(&mut self, event: FileEvent) -> Result<()> {
        match event {
            FileEvent::Command(p, tx) => match p["type"].as_str().unwrap_or("") {
                "list_files" => Self::send(
                    &tx,
                    "file_list_req",
                    json!({"path":p["path"].as_str().unwrap_or(".")}),
                ),
                "cancel_transfer" => {
                    self.cancel.store(false, Ordering::Release);
                    self.download = None;
                    self.upload = None;
                    self.status("Transfer cancelled");
                    self.finished("cancelled", "Transfer cancelled");
                    Ok(())
                }
                "download" => {
                    if self.download.is_some() {
                        bail!("A download is already running")
                    };
                    let remote = text(&p, "path")?;
                    let final_path = PathBuf::from(text(&p, "destination")?);
                    let parent = fs::canonicalize(
                        final_path.parent().context("Choose a destination folder")?,
                    )?;
                    let filename = final_path
                        .file_name()
                        .context("Choose a destination filename")?;
                    if !valid_name(&filename.to_string_lossy()) {
                        bail!("Invalid local filename")
                    };
                    let partial = Partial::create(parent.join(filename))?;
                    let name = filename.to_string_lossy().into_owned();
                    let started = Instant::now();
                    self.progress("running", "download", &name, (0, 0), started, true);
                    self.download = Some(Download {
                        partial,
                        remote: remote.clone(),
                        name,
                        started,
                        requested: 1,
                        index: 0,
                        size: None,
                        hash: Sha256::new(),
                    });
                    self.status("Downloading…");
                    Self::send(
                        &tx,
                        "file_download_req",
                        json!({"path":remote,"chunk_index":0}),
                    )
                }
                "upload" => {
                    if self.upload.is_some() {
                        bail!("An upload is already running")
                    };
                    let source = PathBuf::from(text(&p, "source")?);
                    let filename = source
                        .file_name()
                        .context("Missing source filename")?
                        .to_string_lossy()
                        .into_owned();
                    if !valid_name(&filename) {
                        bail!("Invalid source filename")
                    };
                    let mut file = File::open(source)?;
                    let size = file.metadata()?.len();
                    if size > MAX_SIZE {
                        bail!("File exceeds the 4 GiB transfer limit")
                    };
                    self.status(format!("Preparing {filename}…"));
                    let started = Instant::now();
                    let mut hashed = 0u64;
                    self.progress("preparing", "upload", &filename, (0, size), started, true);
                    let mut hash = Sha256::new();
                    let mut bytes = [0; CHUNK];
                    loop {
                        if self.stop.load(Ordering::Acquire) || self.cancel.load(Ordering::Acquire) {
                            bail!("Transfer cancelled")
                        };
                        let count = file.read(&mut bytes)?;
                        if count == 0 {
                            break;
                        };
                        hash.update(&bytes[..count]);
                        hashed += count as u64;
                        self.progress("preparing", "upload", &filename, (hashed, size), started, false);
                    }
                    file.seek(SeekFrom::Start(0))?;
                    let expected = hex::encode(hash.finalize());
                    let id = token();
                    let total = chunks(size);
                    Self::send(
                        &tx,
                        "file_upload_start",
                        json!({"upload_id":id,"filename":filename,"target_dir":p["directory"].as_str().unwrap_or("."),"file_size":size,"total_chunks":total,"sha256":expected}),
                    )?;
                    self.upload = Some(Upload {
                        file,
                        id,
                        filename,
                        directory: p["directory"].as_str().unwrap_or(".").to_owned(),
                        started: Instant::now(),
                        expected,
                        total,
                        index: 0,
                        acked: 0,
                        window: 1,
                        size,
                    });
                    Ok(())
                }
                _ => Ok(()),
            },
            FileEvent::Packet(typ, p, tx) => {
                if p["error"].is_string() || typ == "file_error" {
                    bail!(
                        "{}",
                        p["error"]
                            .as_str()
                            .or(p["message"].as_str())
                            .unwrap_or("Remote file operation failed")
                    )
                }
                match typ.as_str() {
                    "file_list_resp" => {
                        self.shared.connection(&self.key, |v| v["files"] = p);
                        Ok(())
                    }
                    "file_upload_start" => {
                        if let Some(upload) = &mut self.upload
                            && p["upload_id"] == upload.id
                            && p["status"] == "ready"
                        {
                            upload.window = p["window"].as_u64().unwrap_or(1).clamp(1, WINDOW);
                            upload.started = Instant::now();
                            return self.upload_fill(&tx);
                        }
                        Ok(())
                    }
                    "file_chunk" if p["upload_id"].is_string() => {
                        let Some(upload) = &self.upload else {
                            return Ok(());
                        };
                        if p["upload_id"] != upload.id {
                            // A late reply to a transfer that was cancelled.
                            return Ok(());
                        };
                        if p["status"] == "complete" {
                            if upload.index != upload.total
                                || p["sha256"]
                                    .as_str()
                                    .is_some_and(|hash| hash != upload.expected)
                            {
                                bail!("Upload integrity verification failed")
                            };
                            let (name, size, started, directory) = (upload.filename.clone(), upload.size, upload.started, upload.directory.clone());
                            self.status(format!("Sent {name} • SHA-256 verified"));
                            self.progress("done", "upload", &name, (size, size), started, true);
                            self.upload = None;
                            Self::send(&tx, "file_list_req", json!({"path":directory}))
                        } else if p["status"] == "in_progress"
                            && p["received_chunks"].as_u64() == Some(upload.acked + 1)
                            && upload.acked < upload.index
                        {
                            let acked = upload.acked + 1;
                            let (name, size, started, total) = (upload.filename.clone(), upload.size, upload.started, upload.total);
                            if let Some(upload) = &mut self.upload {
                                upload.acked = acked;
                            }
                            self.status(format!("Sending {name} • {}%", acked * 100 / total));
                            self.progress("running", "upload", &name, ((acked * CHUNK as u64).min(size), size), started, false);
                            self.upload_fill(&tx)
                        } else {
                            bail!("Invalid upload acknowledgement")
                        }
                    }
                    "file_chunk" => {
                        let Some(download) = self.download.as_mut() else {
                            return Ok(());
                        };
                        let index = number(&p, "chunk_index")?;
                        let size = number(&p, "file_size")?;
                        let total = number(&p, "total_chunks")?;
                        if index != download.index
                            || size > MAX_SIZE
                            || total != chunks(size)
                            || download.size.is_some_and(|expected| expected != size)
                        {
                            bail!("Invalid download chunk sequence")
                        }
                        let bytes = B64.decode(text(&p, "data")?)?;
                        let expected = (size - index * CHUNK as u64).min(CHUNK as u64) as usize;
                        if bytes.len() != expected {
                            bail!("Download chunk length differs from declared size")
                        };
                        download.size = Some(size);
                        download
                            .partial
                            .file
                            .as_mut()
                            .context("Closed download")?
                            .write_all(&bytes)?;
                        download.hash.update(&bytes);
                        download.index += 1;
                        if download.index == total {
                            if p["is_last"] != true {
                                bail!("Missing final download marker")
                            };
                            if let Some(expected) = p["sha256"].as_str()
                                && hex::encode(download.hash.clone().finalize()) != expected
                            {
                                bail!("Download SHA-256 mismatch")
                            }
                            download.partial.finish()?;
                            let (name, started) = (download.name.clone(), download.started);
                            self.status("Download complete");
                            self.progress("done", "download", &name, (size, size), started, true);
                            self.download = None;
                            Ok(())
                        } else {
                            let remote = download.remote.clone();
                            let index = download.index;
                            let window = p["window"].as_u64().unwrap_or(1).clamp(1, WINDOW);
                            let first = download.requested;
                            let last = (index + window).min(total);
                            download.requested = last.max(first);
                            let (name, started) = (download.name.clone(), download.started);
                            self.status(format!("Downloading • {}%", index * 100 / total));
                            self.progress("running", "download", &name, ((index * CHUNK as u64).min(size), size), started, false);
                            for next in first..last {
                                Self::send(
                                    &tx,
                                    "file_download_req",
                                    json!({"path":remote,"chunk_index":next}),
                                )?;
                            }
                            Ok(())
                        }
                    }
                    _ => Ok(()),
                }
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_windows_filename_tricks() {
        for name in [
            "../secret",
            "C:secret",
            "LPT1.txt",
            "file.",
            "NUL",
            "a\\b",
            "file ",
            "CON.log",
            "",
        ] {
            assert!(!valid_name(name), "{name}");
        }
        assert!(valid_name("Quarterly report.pdf"));
    }
    #[test]
    fn chunk_counts_cover_empty_and_partial() {
        assert_eq!(chunks(0), 1);
        assert_eq!(chunks(65536), 1);
        assert_eq!(chunks(65537), 2);
    }
}
