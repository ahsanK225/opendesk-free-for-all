use crate::transport::Sender;
use crate::{
    app::{Frame, Shared},
    network::{Outbound, packet},
    protocol::VideoPacket,
    session::Permissions,
    stream::AckWindow,
};
use anyhow::{Context, Result, bail};
use image::{ImageFormat, ImageReader};
use jpeg_encoder::{ColorType, Encoder, SamplingFactor};
use serde_json::{Value, json};
use std::{
    io::Cursor,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    time::{Duration, Instant},
};

struct Encoded {
    data: Vec<u8>,
    full: bool,
    id: u64,
}
#[derive(Default)]
pub struct TileEncoder {
    previous: Vec<u8>,
    width: u32,
    height: u32,
    frame: u64,
    last_full: Option<Instant>,
    resizer: fast_image_resize::Resizer,
}
impl TileEncoder {
    fn jpeg(bytes: &[u8], width: u32, height: u32, quality: u8) -> Result<Vec<u8>> {
        if let Some(result) = crate::jpeg::encode(bytes, width, height, quality) {
            return result;
        }
        let mut output = Vec::new();
        let mut encoder = Encoder::new(&mut output, quality);
        encoder.set_sampling_factor(if quality >= 80 {
            SamplingFactor::F_1_1
        } else {
            SamplingFactor::F_2_2
        });
        encoder.encode(
            bytes,
            width.try_into()?,
            height.try_into()?,
            ColorType::Bgra,
        )?;
        Ok(output)
    }
    fn encode(
        &mut self,
        raw: &(u32, u32, Vec<u8>),
        max_width: u32,
        quality: u8,
        force: bool,
        session: &str,
    ) -> Result<Option<Encoded>> {
        let (w, h, bytes) = raw;
        let mut resized;
        let (width, height, current) = if *w > max_width {
            let view = fast_image_resize::images::ImageRef::new(
                *w,
                *h,
                bytes.as_slice(),
                fast_image_resize::PixelType::U8x4,
            )?;
            let height = ((*h as u64 * max_width as u64) / (*w as u64)).max(1) as u32;
            resized = fast_image_resize::images::Image::new(
                max_width,
                height,
                fast_image_resize::PixelType::U8x4,
            );
            let algorithm = if quality <= 55 {
                fast_image_resize::ResizeAlg::Interpolation(fast_image_resize::FilterType::Bilinear)
            } else {
                fast_image_resize::ResizeAlg::Convolution(fast_image_resize::FilterType::Bilinear)
            };
            let options = fast_image_resize::ResizeOptions::new()
                .use_alpha(false)
                .resize_alg(algorithm);
            self.resizer.resize(&view, &mut resized, Some(&options))?;
            (max_width, height, resized.buffer())
        } else {
            (*w, *h, bytes.as_slice())
        };
        let changed_size =
            self.width != width || self.height != height || self.previous.len() != current.len();
        let mut rectangles: Vec<(u32, u32, u32, u32)> = Vec::new();
        let block = 128;
        let mut dirty = 0u64;
        if !changed_size && !force {
            let mut previous_row: Vec<(u32, u32, usize)> = Vec::new();
            for y in (0..height).step_by(block) {
                let tile_h = (height - y).min(block as u32);
                let mut row = Vec::new();
                let mut start = None;
                for x in (0..width).step_by(block) {
                    let tile_w = (width - x).min(block as u32);
                    let different = (y..y + tile_h).any(|line| {
                        let offset = ((line * width + x) * 4) as usize;
                        current[offset..offset + tile_w as usize * 4]
                            != self.previous[offset..offset + tile_w as usize * 4]
                    });
                    if different {
                        dirty += u64::from(tile_w) * u64::from(tile_h);
                        if start.is_none() {
                            start = Some(x)
                        }
                    }
                    if (!different || x + tile_w == width) && start.is_some() {
                        let left = start.take().unwrap();
                        let right = if different { x + tile_w } else { x };
                        let length = right - left;
                        let index = if let Some((_, _, index)) =
                            previous_row.iter().find(|(left_old, width_old, _)| {
                                *left_old == left && *width_old == length
                            }) {
                            let index = *index;
                            rectangles[index].3 += tile_h;
                            index
                        } else {
                            rectangles.push((left, y, length, tile_h));
                            rectangles.len() - 1
                        };
                        row.push((left, length, index));
                    }
                }
                previous_row = row;
            }
        }
        if !changed_size && dirty == 0 && !force {
            return Ok(None);
        }
        let full = changed_size
            || force
            || dirty * 100 > u64::from(width) * u64::from(height) * 45
            || self
                .last_full
                .is_none_or(|last| last.elapsed() > Duration::from_secs(15));
        self.frame = self
            .frame
            .checked_add(1)
            .context("Video frame counter exhausted")?;
        let mut body = Vec::new();
        let mut tiles = Vec::new();
        if full {
            let bytes = Self::jpeg(current, width, height, quality)?;
            tiles.push(json!({"offset":0,"length":bytes.len()}));
            body.extend(bytes);
            self.last_full = Some(Instant::now());
        } else {
            for (x, y, w, h) in rectangles {
                let mut cropped = Vec::with_capacity((w * h * 4) as usize);
                for row in y..y + h {
                    let offset = ((row * width + x) * 4) as usize;
                    cropped.extend_from_slice(&current[offset..offset + w as usize * 4]);
                }
                let bytes = Self::jpeg(&cropped, w, h, quality)?;
                tiles.push(
                    json!({"x":x,"y":y,"w":w,"h":h,"offset":body.len(),"length":bytes.len()}),
                );
                body.extend(bytes);
            }
        }
        self.previous.clear();
        self.previous.extend_from_slice(current);
        self.width = width;
        self.height = height;
        let header=json!({"type":if full{"video_full"}else{"video_delta"},"payload":{"width":width,"height":height,"frame_id":self.frame,"session_id":session,"tiles":tiles}}).to_string().into_bytes();
        let mut data = Vec::with_capacity(8 + header.len() + body.len());
        data.extend(b"ODV2");
        data.extend((header.len() as u32).to_be_bytes());
        data.extend(header);
        data.extend(body);
        Ok(Some(Encoded {
            data,
            full,
            id: self.frame,
        }))
    }
}
pub struct HostWorker {
    pub session: String,
    commands: mpsc::SyncSender<(String, Value)>,
    stop: Arc<AtomicBool>,
    input: Mutex<crate::platform::Input>,
    input_allowed: bool,
    voice: Option<Arc<crate::audio::Voice>>,
    shared: Arc<Shared>,
}
impl HostWorker {
    pub fn start(
        shared: Arc<Shared>,
        session: String,
        permissions: Permissions,
        sender: Sender<Outbound>,
    ) -> Result<Self> {
        let (commands, receiver) = mpsc::sync_channel(128);
        let stop = Arc::new(AtomicBool::new(false));
        let signal = stop.clone();
        let id = session.clone();
        let voice = if permissions.audio {
            Some(Arc::new(crate::audio::Voice::start(
                shared.clone(),
                sender.clone(),
                session.clone(),
            )?))
        } else {
            None
        };
        let capture_voice = voice.clone();
        let capture_shared = shared.clone();
        let input_allowed = permissions.input;
        std::thread::Builder::new()
            .name("opendesk-capture".into())
            .spawn(move || {
                let shared = capture_shared;
                let exited = signal.clone();
                if let Err(error) = host_loop(
                    shared.clone(),
                    id,
                    permissions,
                    sender.clone(),
                    receiver,
                    signal,
                    capture_voice,
                ) {
                    shared.error(format!("Screen sharing: {error:#}"));
                    let _ = sender.try_send(Outbound::Packet(packet(
                        "session_end",
                        json!({"message":format!("Capture stopped: {error}")}),
                    )));
                }
                exited.store(true, Ordering::Release);
            })?;
        Ok(Self {
            session,
            commands,
            stop,
            input: Mutex::new(crate::platform::Input::default()),
            input_allowed,
            voice,
            shared,
        })
    }
    pub fn send(&self, typ: &str, payload: Value) -> Result<()> {
        if self.is_stopped() {
            bail!("Media worker stopped")
        }
        if typ == "input_reset"
            || (self.input_allowed && (typ.starts_with("mouse_") || typ.starts_with("key_")))
        {
            let mut input = self.input.lock().unwrap();
            if typ == "input_reset" {
                input.release_all();
            } else {
                input.handle(typ, &payload);
            }
            if typ.starts_with("mouse_") && payload["x"].is_number() && payload["y"].is_number() {
                self.shared.update(|v| {
                    v["remoteCursor"] =
                        json!({"x":payload["x"],"y":payload["y"],"pressed":typ=="mouse_down"})
                });
            }
            return Ok(());
        }
        if let Some(voice) = &self.voice {
            match typ {
                "audio_chunk" => {
                    voice.push(&payload);
                    return Ok(());
                }
                "audio_settings" => {
                    voice.refresh_settings(payload["applyMic"] == true);
                    return Ok(());
                }
                "local_mic_toggle" => {
                    voice.toggle_mic();
                    self.shared.update(|v|{if v["hostSession"].is_object(){v["hostSession"]["micEnabled"]=json!(voice.mic_enabled());}});
                    return Ok(());
                }
                _ => {}
            }
        }
        match self.commands.try_send((typ.into(), payload)) {
            Ok(()) | Err(mpsc::TrySendError::Full(_)) => Ok(()),
            Err(mpsc::TrySendError::Disconnected(_)) => bail!("Media worker stopped"),
        }
    }
    pub fn stop(&self) {
        self.stop.store(true, Ordering::Release);
        self.input.lock().unwrap().release_all();
    }
    pub fn is_stopped(&self) -> bool {
        self.stop.load(Ordering::Acquire)
    }
}
impl Drop for HostWorker {
    fn drop(&mut self) {
        self.stop();
    }
}
// Keep the file payload move inside its arm; moving it in a guard can fall through.
#[allow(clippy::collapsible_match)]
fn host_loop(
    shared: Arc<Shared>,
    session: String,
    permissions: Permissions,
    sender: Sender<Outbound>,
    receiver: mpsc::Receiver<(String, Value)>,
    stop: Arc<AtomicBool>,
    voice: Option<Arc<crate::audio::Voice>>,
) -> Result<()> {
    let mut capture = crate::capture::Capture::new()?;
    let mut input = crate::platform::Input::default();
    let mut clipboard = crate::platform::Clipboard::new();
    let (file_tx, file_rx) = mpsc::sync_channel::<(String, Value)>(64);
    if permissions.file_transfer {
        let file_stop = stop.clone();
        let file_shared = shared.clone();
        let out = sender.clone();
        let id = session.clone();
        let file_root = shared.store.lock().unwrap().config["native_settings"]["sharedRoot"]
            .as_str()
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| {
                std::path::PathBuf::from(std::env::var("USERPROFILE").unwrap_or_default())
            });
        std::thread::Builder::new().name("opendesk-host-files".into()).spawn(move||{
        let Ok(mut files)=crate::files::HostFiles::new(file_root)else{return};
        while !file_stop.load(Ordering::Acquire){
match file_rx.recv_timeout(Duration::from_millis(50)){
Ok((typ,payload))=>{
let reply=match files.packet(&typ,&payload){
Ok(mut reply)=>{
if reply["status"]=="complete"&&let Some(saved)=reply["final_path"].as_str(){let saved=saved.to_owned();file_shared.update(|v|{if v["hostSession"].is_object(){v["hostSession"]["lastFile"]=json!(saved);}});}
reply["session_id"]=json!(id);
packet(if typ=="file_list_req"{
"file_list_resp"}
else if typ=="file_download_req"{
"file_chunk"}
else{
&typ}
,reply)}
,Err(error)=>packet("file_error",json!({
"session_id":id,"message":error.to_string(),"upload_id":payload["upload_id"]}
))}
;
if out.blocking_send(Outbound::Packet(reply)).is_err(){
break}
}
,Err(mpsc::RecvTimeoutError::Timeout)=>{
}
,Err(_)=>break}
}

    })?;
    }
    let mut encoder = TileEncoder::default();
    let mut window = AckWindow::new(3);
    let start = Instant::now();
    let mut last_raw = None;
    let mut next = Instant::now();
    let mut clipboard_time = Instant::now();
    let mut requested_width = 1600;
    let mut width = 1600;
    let mut quality = 65u8;
    let mut requested_quality = 65u8;
    let mut fps = 30u32;
    let mut adapt = Instant::now();
    let mut baseline_rtt = 0u64;
    while !stop.load(Ordering::Acquire) && !shared.stop.load(Ordering::Acquire) {
        let budget = Instant::now();
        for _ in 0..128 {
            let Ok((typ, p)) = receiver.try_recv() else {
                break;
            };
            if stop.load(Ordering::Acquire) {
                break;
            }
            match typ.as_str() {
                "video_config" => {
                    fps = p["fps"].as_u64().unwrap_or(30).clamp(10, 60) as u32;
                    requested_width =
                        p["max_width"].as_u64().unwrap_or(1600).clamp(640, 2560) as u32;
                    width = requested_width;
                    requested_quality = p["quality"].as_u64().unwrap_or(65).clamp(20, 95) as u8;
                    quality = requested_quality;
                    window.refresh();
                }
                "video_refresh" => window.refresh(),
                "video_ack" => {
                    if let Some(frame) = p["frame_id"].as_u64() {
                        let _ = window.acknowledge(frame, start.elapsed().as_millis() as u64);
                    }
                    let rtt = p["rtt_ms"].as_u64().unwrap_or(0).min(2000);
                    if rtt > 0 {
                        baseline_rtt = if baseline_rtt == 0 {
                            rtt
                        } else {
                            baseline_rtt.min(rtt)
                        };
                        window.set_limit(
                            ((rtt as f64 / 1000.0 * fps as f64 * 1.2).ceil() as usize).clamp(3, 10),
                        );
                    }
                }
                "input_reset" => input.release_all(),
                "clipboard_text" if permissions.clipboard => {
                    if let Some(text) = p["text"].as_str() {
                        let _ = clipboard.set(text);
                    }
                }
                "audio_chunk" if permissions.audio => {
                    if let Some(voice) = &voice {
                        voice.push(&p);
                    }
                }
                "audio_settings" => {
                    if let Some(voice) = &voice {
                        voice.refresh_settings(p["applyMic"] == true);
                        shared.update(|v| {
                            if v["hostSession"].is_object() {
                                v["hostSession"]["micEnabled"] = json!(voice.mic_enabled());
                            }
                        });
                    }
                }
                "local_mic_toggle" => {
                    if let Some(voice) = &voice {
                        voice.toggle_mic();
                        shared.update(|v| {
                            if v["hostSession"].is_object() {
                                v["hostSession"]["micEnabled"] = json!(voice.mic_enabled());
                            }
                        });
                    }
                }
                typ if permissions.file_transfer && typ.starts_with("file_") => {
                    if file_tx.try_send((typ.into(), p)).is_err() {
                        let _ = sender.try_send(Outbound::Packet(packet(
                            "file_error",
                            json!({"session_id":session,"message":"File operation queue is busy."}),
                        )));
                    }
                }
                typ if permissions.input => input.handle(typ, &p),
                _ => {}
            }
            if budget.elapsed() > Duration::from_millis(2) {
                break;
            }
        }
        if permissions.clipboard && clipboard_time.elapsed() > Duration::from_millis(300) {
            clipboard_time = Instant::now();
            if let Some(text) = clipboard.poll() {
                let _ = sender.try_send(Outbound::Packet(packet(
                    "clipboard_text",
                    json!({"session_id":session,"text":text}),
                )));
            }
        }
        let elapsed = start.elapsed().as_millis() as u64;
        if window.stalled(elapsed) {
            window.refresh();
        }
        if adapt.elapsed() > Duration::from_secs(1) {
            adapt = Instant::now();
            if let Some(voice) = &voice {
                shared.update(|v| {
                    if v["hostSession"].is_object() {
                        v["hostSession"]["micEnabled"] = json!(voice.mic_enabled());
                    }
                });
            }
            let old = window.oldest_age(elapsed);
            if !window.can_send() && old > baseline_rtt + 100 {
                width = (width * 85 / 100).max(640);
                quality = quality.saturating_sub(5).max(35);
            } else if window.can_send() {
                width = (width + 64).min(requested_width);
                quality = quality.saturating_add(1).min(requested_quality);
            }
        }
        if Instant::now() >= next && window.can_send() && sender.capacity() > 0 {
            next = Instant::now() + Duration::from_secs_f64(1.0 / fps as f64);
            let captured = capture.grab()?;
            let changed = captured.is_some();
            if let Some(raw) = captured {
                last_raw = Some(raw);
            }
            if (changed || window.needs_keyframe)
                && let Some(raw) = &last_raw
                && let Some(encoded) =
                    encoder.encode(raw, width, quality, window.needs_keyframe, &session)?
            {
                let id = encoded.id;
                let full = encoded.full;
                if sender.try_send(Outbound::Video(encoded.data)).is_ok() {
                    if !window.sent(id, elapsed, full) {
                        window.refresh();
                    }
                } else {
                    window.refresh();
                }
            }
        }
        std::thread::sleep(Duration::from_millis(2));
    }
    input.release_all();
    drop(voice);
    Ok(())
}

enum DecodeInput {
    Binary(Vec<u8>),
    Legacy(String, Value),
}
pub struct DecodeWorker {
    sender: mpsc::SyncSender<DecodeInput>,
    stop: Arc<AtomicBool>,
    pub rtt: Arc<AtomicU64>,
    reset: Arc<AtomicBool>,
}
impl DecodeWorker {
    pub fn start(
        shared: Arc<Shared>,
        key: String,
        session: String,
        out: Sender<Outbound>,
    ) -> Result<Self> {
        let (sender, receiver) = mpsc::sync_channel::<DecodeInput>(4);
        let stop = Arc::new(AtomicBool::new(false));
        let signal = stop.clone();
        let rtt = Arc::new(AtomicU64::new(0));
        let rtt_worker = rtt.clone();
        let reset = Arc::new(AtomicBool::new(false));
        let reset_worker = reset.clone();
        std::thread::Builder::new().name("opendesk-video-decode".into()).spawn(move||{let mut decoder=Decoder::default();let mut legacy=crate::legacy::VideoBridge::default();while !signal.load(Ordering::Acquire){
            if reset_worker.swap(false,Ordering::AcqRel){while receiver.try_recv().is_ok(){} decoder=Decoder::default();let _=out.try_send(Outbound::Packet(packet("video_refresh",json!({}))));}
            match receiver.recv_timeout(Duration::from_millis(50)){
            Ok(input)=>match (match input{DecodeInput::Binary(bytes)=>Ok(bytes),DecodeInput::Legacy(typ,p)=>legacy.convert(&typ,&p,&session)}).and_then(|bytes|decoder.decode(&bytes,&session)){
Ok(frame)=>{
let frame_id=frame.generation;
shared.frames.lock().unwrap().insert(key.clone(),frame);
let _=out.blocking_send(Outbound::Packet(packet("video_ack",json!({
"frame_id":frame_id,"rtt_ms":rtt_worker.load(Ordering::Relaxed)}
))));
}
,Err(_)=>{
decoder=Decoder::default();
let _=out.blocking_send(Outbound::Packet(packet("video_refresh",json!({
}
))));
}
}
,
            Err(mpsc::RecvTimeoutError::Timeout)=>{},Err(_)=>break
        }}})?;
        Ok(Self {
            sender,
            stop,
            rtt,
            reset,
        })
    }
    pub async fn push(&self, bytes: Vec<u8>) -> Result<()> {
        self.enqueue(DecodeInput::Binary(bytes))
    }
    pub fn push_legacy(&self, typ: &str, p: Value) -> Result<()> {
        self.enqueue(DecodeInput::Legacy(typ.into(), p))
    }
    fn enqueue(&self, input: DecodeInput) -> Result<()> {
        let sender = self.sender.clone();
        match sender.try_send(input) {
            Ok(()) => Ok(()),
            Err(mpsc::TrySendError::Full(_)) => {
                // A dropped delta invalidates the chain. Reset on the worker,
                // drain dependent frames and request a full frame, without
                // blocking the WebSocket reader (voice, pings and input).
                self.reset.store(true, Ordering::Release);
                Ok(())
            }
            Err(_) => bail!("Video decoder stopped"),
        }
    }
}
impl Drop for DecodeWorker {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
    }
}
#[derive(Default)]
struct Decoder {
    frame: Option<Arc<Frame>>,
}
impl Decoder {
    fn decode(&mut self, bytes: &[u8], session: &str) -> Result<Arc<Frame>> {
        let packet = VideoPacket::decode(bytes, session)
            .map_err(|e| anyhow::anyhow!("Invalid video: {e:?}"))?;
        let p = &packet.header.payload;
        if p.width > 8192 || u64::from(p.width) * u64::from(p.height) > 16 * 1024 * 1024 {
            bail!("Video dimensions exceed the native profile limits")
        }
        let full = packet.header.kind == "video_full";
        if !full
            && self.frame.as_ref().is_none_or(|frame| {
                frame.width != p.width
                    || frame.height != p.height
                    || frame.generation.checked_add(1) != Some(p.frame_id)
            })
        {
            bail!("A keyframe is required")
        }
        if full {
            if self
                .frame
                .as_ref()
                .is_some_and(|f| f.generation >= p.frame_id)
            {
                bail!("Stale keyframe")
            };
            self.frame = Some(Arc::new(Frame {
                width: p.width,
                height: p.height,
                generation: 0,
                pixels: Vec::new(),
            }));
        }
        let frame = Arc::make_mut(self.frame.as_mut().context("No initial frame")?);
        for (index, tile) in p.tiles.iter().enumerate() {
            let (mut x, mut y, w, h) = (
                tile.x.unwrap_or(0),
                tile.y.unwrap_or(0),
                tile.w.unwrap_or(p.width),
                tile.h.unwrap_or(p.height),
            );
            if full {
                x = 0;
                y = 0;
            }
            let image = if let Some(result) =
                crate::jpeg::decode(packet.image(index).context("Missing tile")?, w, h)
            {
                result?
            } else {
                let mut reader = ImageReader::with_format(
                    Cursor::new(packet.image(index).context("Missing tile")?),
                    ImageFormat::Jpeg,
                );
                let mut limits = image::Limits::default();
                limits.max_image_width = Some(w);
                limits.max_image_height = Some(h);
                limits.max_alloc = Some(u64::from(w) * u64::from(h) * 8 + 1024 * 1024);
                reader.limits(limits);
                let image = reader.decode()?.into_rgba8();
                if image.width() != w || image.height() != h {
                    bail!("JPEG dimensions do not match the envelope")
                }
                {
                    let mut pixels = image.into_raw();
                    for p in pixels.chunks_exact_mut(4) {
                        p.swap(0, 2);
                    }
                    pixels
                }
            };
            if full {
                frame.pixels = image;
                continue;
            }
            for row in 0..h as usize {
                let from = row * w as usize * 4;
                let to = ((y as usize + row) * p.width as usize + x as usize) * 4;
                frame.pixels[to..to + w as usize * 4]
                    .copy_from_slice(&image[from..from + w as usize * 4]);
            }
        }
        frame.generation = p.frame_id;
        Ok(self.frame.as_ref().unwrap().clone())
    }
}
pub fn benchmark() -> Result<Value> {
    let (width, height) = (2560u32, 1440u32);
    let mut source = vec![0; (width * height * 4) as usize];
    for y in 0..height {
        for x in 0..width {
            let i = ((y * width + x) * 4) as usize;
            source[i + 3] = 255;
            source[i] = ((x / 8 * 17 + y / 16 * 3) % 255) as u8;
            source[i + 1] = ((x / 32 * 13 + y / 8 * 11) % 255) as u8;
            source[i + 2] = ((x ^ y) % 127 + 64) as u8;
        }
    }
    let base = (width, height, source);
    let session = "native-benchmark-session";
    let mut profiles = Vec::new();
    for (name, max_width, quality) in [
        ("performance", 1280, 55),
        ("balanced", 1600, 65),
        ("sharp", 2560, 85),
    ] {
        let mut encoder = TileEncoder::default();
        let mut decoder = Decoder::default();
        let mut encode_times = Vec::new();
        let mut decode_times = Vec::new();
        let mut bytes = 0usize;
        for _ in 0..12 {
            let clock = Instant::now();
            let encoded = encoder
                .encode(&base, max_width, quality, true, session)?
                .context("Missing keyframe")?;
            encode_times.push(clock.elapsed().as_secs_f64() * 1000.0);
            bytes += encoded.data.len();
            let clock = Instant::now();
            let frame = decoder.decode(&encoded.data, session)?;
            std::hint::black_box(frame.width);
            decode_times.push(clock.elapsed().as_secs_f64() * 1000.0);
        }
        let mut raw = base.clone();
        let mut delta_times = Vec::new();
        let mut delta_bytes = 0;
        let mut deltas = 0;
        for index in 0..24u32 {
            raw.2.clone_from(&base.2);
            let left = (index * 113) % (width - 160);
            let top = (index * 53) % (height - 80);
            for y in top..top + 64 {
                for x in left..left + 128 {
                    let offset = ((y * width + x) * 4) as usize;
                    raw.2[offset..offset + 3].copy_from_slice(&[210, 45, 70]);
                }
            }
            let clock = Instant::now();
            if let Some(encoded) = encoder.encode(&raw, max_width, quality, false, session)? {
                delta_times.push(clock.elapsed().as_secs_f64() * 1000.0);
                delta_bytes += encoded.data.len();
                deltas += 1;
                decoder.decode(&encoded.data, session)?;
            }
        }
        profiles.push(json!({
"profile":name,"source":[width,height],"max_width":max_width,"quality":quality,"full_encode":crate::diagnostics::timing(encode_times),"full_decode":crate::diagnostics::timing(decode_times),"mean_full_bytes":bytes/12,"changed_region_encode":crate::diagnostics::timing(delta_times),"mean_delta_bytes":delta_bytes/deltas.max(1)}
));
    }
    Ok(json!(profiles))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn delta_roundtrip_and_unchanged_screen() {
        let mut encoder = TileEncoder::default();
        let mut decoder = Decoder::default();
        let mut raw = (256, 256, vec![40; 256 * 256 * 4]);
        let first = encoder
            .encode(&raw, 256, 90, true, "session-native-12345")
            .unwrap()
            .unwrap();
        let frame = decoder.decode(&first.data, "session-native-12345").unwrap();
        assert_eq!(frame.pixels.len(), 256 * 256 * 4);
        assert!(
            encoder
                .encode(&raw, 256, 90, false, "session-native-12345")
                .unwrap()
                .is_none()
        );
        raw.2[0] = 200;
        let delta = encoder
            .encode(&raw, 256, 90, false, "session-native-12345")
            .unwrap()
            .unwrap();
        assert!(!delta.full);
        let next = decoder.decode(&delta.data, "session-native-12345").unwrap();
        assert_eq!(next.generation, 2);
        assert_eq!(frame.generation, 1);
    }
}
