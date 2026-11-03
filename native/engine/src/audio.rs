use crate::{
    app::Shared,
    network::{Outbound, packet},
};
use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use cpal::{
    FromSample, Sample, SampleFormat, SizedSample, Stream, StreamConfig,
    traits::{DeviceTrait, HostTrait, StreamTrait},
};
use serde_json::{Value, json};
use std::{
    collections::VecDeque,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering},
        mpsc,
    },
    time::Duration,
};

pub struct Resampler {
    source: u32,
    target: u32,
    phase: f64,
    previous: Option<f32>,
}
impl Resampler {
    pub fn new(source: u32, target: u32) -> Self {
        Self {
            source,
            target,
            phase: 0.0,
            previous: None,
        }
    }
    pub fn process(&mut self, input: &[f32]) -> Vec<f32> {
        if input.is_empty() {
            return Vec::new();
        }
        if self.source == self.target {
            return input.to_vec();
        }
        let mut buffer = Vec::with_capacity(input.len() + 1);
        if let Some(previous) = self.previous {
            buffer.push(previous)
        }
        buffer.extend_from_slice(input);
        let step = self.source as f64 / self.target as f64;
        let mut output = Vec::with_capacity((input.len() as f64 / step) as usize + 2);
        while self.phase + 1.0 < (buffer.len() as f64) {
            let index = self.phase as usize;
            let fraction = (self.phase - index as f64) as f32;
            output.push(buffer[index] + (buffer[index + 1] - buffer[index]) * fraction);
            self.phase += step;
        }
        self.phase -= (buffer.len() - 1) as f64;
        self.previous = buffer.last().copied();
        output
    }
}
struct Playback {
    queue: VecDeque<f32>,
    resampler: Resampler,
    source: u32,
    target: u32,
    last: f32,
}
struct Controls {
    stop: AtomicBool,
    input_failed: AtomicBool,
    output_failed: AtomicBool,
    mic: AtomicBool,
    volume: AtomicU32,
    gain: AtomicU32,
    received: AtomicU64,
    playback: Mutex<Playback>,
}
pub struct Voice {
    controls: Arc<Controls>,
    shared: Arc<Shared>,
}
impl Voice {
    pub fn start(
        shared: Arc<Shared>,
        sender: crate::transport::Sender<Outbound>,
        session: String,
    ) -> Result<Self> {
        let controls = Arc::new(Controls {
            stop: AtomicBool::new(false),
            input_failed: AtomicBool::new(false),
            output_failed: AtomicBool::new(false),
            mic: AtomicBool::new(false),
            volume: AtomicU32::new(0.8f32.to_bits()),
            gain: AtomicU32::new(1f32.to_bits()),
            received: AtomicU64::new(0),
            playback: Mutex::new(Playback {
                queue: VecDeque::with_capacity(6000),
                resampler: Resampler::new(48000, 48000),
                source: 48000,
                target: 48000,
                last: 0.0,
            }),
        });
        let voice = Self {
            controls: controls.clone(),
            shared: shared.clone(),
        };
        voice.refresh_settings(true);
        std::thread::Builder::new()
            .name("opendesk-voice".into())
            .spawn(move || {
                if let Err(error) = run_audio(shared.clone(), controls, sender, session) {
                    shared.error(format!("Voice: {error:#}"));
                }
            })?;
        Ok(voice)
    }
    pub fn refresh_settings(&self, apply_mic: bool) {
        let store = self.shared.store.lock().unwrap();
        let settings = &store.config["native_settings"];
        if apply_mic {
            self.controls.mic.store(
                settings["micEnabled"].as_bool().unwrap_or(false),
                Ordering::Release,
            );
        }
        self.controls.volume.store(
            (if settings["speakerEnabled"].as_bool().unwrap_or(true) {
                settings["speakerVolume"]
                    .as_f64()
                    .unwrap_or(0.8)
                    .clamp(0.0, 1.0) as f32
            } else {
                0.0
            })
            .to_bits(),
            Ordering::Relaxed,
        );
        self.controls.gain.store(
            (settings["micGain"].as_f64().unwrap_or(1.0).clamp(0.0, 3.0) as f32).to_bits(),
            Ordering::Relaxed,
        );
    }
    pub fn mic_enabled(&self) -> bool {
        self.controls.mic.load(Ordering::Acquire)
    }
    pub fn toggle_mic(&self) {
        let value = !self.controls.mic.load(Ordering::Relaxed);
        self.controls.mic.store(value, Ordering::Release);
        self.shared.update(|v|v["notice"]=json!({"tone":"info","message":if value{"Microphone enabled for this session"}else{"Microphone muted for this session"}}));
    }
    pub fn push(&self, payload: &Value) {
        if payload["channels"].as_u64().unwrap_or(1) != 1
            || payload["format"].as_str().is_some_and(|f| f != "pcm_s16le")
        {
            return;
        }
        let rate = payload["sample_rate"].as_u64().unwrap_or(48000) as u32;
        if !matches!(rate, 8000 | 16000 | 24000 | 44100 | 48000 | 96000) {
            return;
        }
        let Some(encoded) = payload["data"].as_str().filter(|s| s.len() < 64 * 1024) else {
            return;
        };
        let Ok(bytes) = B64.decode(encoded) else {
            return;
        };
        if bytes.len() % 2 != 0 || bytes.len() > rate as usize * 2 / 5 {
            return;
        }
        let mono: Vec<f32> = bytes
            .chunks_exact(2)
            .map(|v| i16::from_le_bytes([v[0], v[1]]) as f32 / 32768.0)
            .collect();
        let mut playback = self.controls.playback.lock().unwrap();
        if playback.source != rate {
            playback.source = rate;
            playback.resampler = Resampler::new(rate, playback.target);
        }
        let samples = playback.resampler.process(&mono);
        let maximum = (playback.target as usize * 120 / 1000).max(1);
        let overflow = playback
            .queue
            .len()
            .saturating_add(samples.len())
            .saturating_sub(maximum);
        let drain = overflow.min(playback.queue.len());
        playback.queue.drain(..drain);
        let skip = samples.len().saturating_sub(maximum);
        playback.queue.extend(samples.into_iter().skip(skip));
        self.controls.received.fetch_add(1, Ordering::Relaxed);
    }
}
impl Drop for Voice {
    fn drop(&mut self) {
        self.controls.stop.store(true, Ordering::Release);
    }
}
fn output<T>(
    device: &cpal::Device,
    config: &StreamConfig,
    controls: Arc<Controls>,
) -> Result<Stream>
where
    T: SizedSample + FromSample<f32>,
{
    let channels = config.channels as usize;
    let errors = controls.clone();
    Ok(device.build_output_stream(
        config,
        move |data: &mut [T], _| {
            let volume = f32::from_bits(controls.volume.load(Ordering::Relaxed));
            if let Ok(mut state) = controls.playback.try_lock() {
                for frame in data.chunks_mut(channels) {
                    let sample = if let Some(value) = state.queue.pop_front() {
                        state.last = value;
                        value
                    } else {
                        state.last *= 0.92;
                        state.last
                    };
                    let sample = T::from_sample((sample * volume).clamp(-1.0, 1.0));
                    frame.fill(sample);
                }
            } else {
                data.fill(T::from_sample(0.0));
            }
        },
        move |_| {
            errors.output_failed.store(true, Ordering::Release);
        },
        Some(Duration::from_secs(2)),
    )?)
}
fn input<T>(
    device: &cpal::Device,
    config: &StreamConfig,
    controls: Arc<Controls>,
    sender: mpsc::SyncSender<Vec<f32>>,
) -> Result<Stream>
where
    T: SizedSample,
    f32: FromSample<T>,
{
    let channels = config.channels as usize;
    let mut resampler = Resampler::new(config.sample_rate, 48000);
    let mut block = Vec::with_capacity(960);
    let errors = controls.clone();
    Ok(device.build_input_stream(
        config,
        move |data: &[T], _| {
            if !controls.mic.load(Ordering::Acquire) {
                return;
            }
            let gain = f32::from_bits(controls.gain.load(Ordering::Relaxed));
            let mono: Vec<f32> = data
                .chunks(channels)
                .map(|frame| {
                    frame.iter().map(|v| f32::from_sample(*v)).sum::<f32>() / channels as f32
                })
                .collect();
            for sample in resampler.process(&mono) {
                block.push((sample * gain).clamp(-1.0, 1.0));
                if block.len() == 960 {
                    let ready = std::mem::replace(&mut block, Vec::with_capacity(960));
                    let _ = sender.try_send(ready);
                }
            }
        },
        move |_| {
            errors.input_failed.store(true, Ordering::Release);
        },
        Some(Duration::from_secs(2)),
    )?)
}
fn run_audio(
    shared: Arc<Shared>,
    controls: Arc<Controls>,
    sender: crate::transport::Sender<Outbound>,
    session: String,
) -> Result<()> {
    let host = cpal::default_host();
    let (mut output_stream, mut input_stream) = (None, None);
    let (mic_tx, mic_rx) = mpsc::sync_channel(6);
    let mut last_status = std::time::Instant::now() - Duration::from_secs(2);
    let mut microphone_error = String::new();
    let mut speaker_error = String::new();
    let mut sent_packets = 0u64;
    let mut retry = std::time::Instant::now() - Duration::from_secs(5);
    let mut output_retry = std::time::Instant::now() - Duration::from_secs(5);
    let mut devices_checked = std::time::Instant::now() - Duration::from_secs(5);
    let (mut input_id, mut output_id) = (None, None);
    while !controls.stop.load(Ordering::Acquire) {
        if devices_checked.elapsed() >= Duration::from_secs(2) {
            devices_checked = std::time::Instant::now();
            let next_input = host
                .default_input_device()
                .and_then(|d| d.id().ok())
                .map(|id| id.to_string());
            let next_output = host
                .default_output_device()
                .and_then(|d| d.id().ok())
                .map(|id| id.to_string());
            if input_id != next_input {
                drop(input_stream.take());
                input_id = next_input;
            }
            if output_id != next_output {
                drop(output_stream.take());
                output_id = next_output;
            }
        }
        if controls.input_failed.swap(false, Ordering::AcqRel) {
            drop(input_stream.take());
        }
        if controls.output_failed.swap(false, Ordering::AcqRel) {
            drop(output_stream.take());
            shared.error("The speaker disconnected. Retrying the default audio device…");
        }
        if output_stream.is_none() && output_retry.elapsed() > Duration::from_secs(2) {
            output_retry = std::time::Instant::now();
            let result = (|| -> Result<Stream> {
                let device = host
                    .default_output_device()
                    .context("No speaker device is available")?;
                let supported = device.default_output_config()?;
                let config: StreamConfig = supported.clone().into();
                {
                    let mut playback = controls.playback.lock().unwrap();
                    playback.target = config.sample_rate;
                    playback.resampler = Resampler::new(playback.source, config.sample_rate);
                    playback.queue.clear();
                }
                let stream = match supported.sample_format() {
                    SampleFormat::F32 => output::<f32>(&device, &config, controls.clone()),
                    SampleFormat::I16 => output::<i16>(&device, &config, controls.clone()),
                    SampleFormat::U16 => output::<u16>(&device, &config, controls.clone()),
                    _ => bail!("Unsupported speaker sample format"),
                }?;
                stream.play()?;
                Ok(stream)
            })();
            match result {
                Ok(stream) => {
                    output_stream = Some(stream);
                    speaker_error.clear();
                }
                Err(error) => speaker_error = format!("Speaker: {error:#}"),
            }
        }
        if controls.mic.load(Ordering::Acquire)
            && input_stream.is_none()
            && retry.elapsed() > Duration::from_secs(2)
        {
            retry = std::time::Instant::now();
            let result = (|| -> Result<Stream> {
                let device = host
                    .default_input_device()
                    .context("No microphone device is available")?;
                let supported = device.default_input_config()?;
                let config = supported.clone().into();
                let stream = match supported.sample_format() {
                    SampleFormat::F32 => {
                        input::<f32>(&device, &config, controls.clone(), mic_tx.clone())
                    }
                    SampleFormat::I16 => {
                        input::<i16>(&device, &config, controls.clone(), mic_tx.clone())
                    }
                    SampleFormat::U16 => {
                        input::<u16>(&device, &config, controls.clone(), mic_tx.clone())
                    }
                    _ => bail!("Unsupported microphone sample format"),
                }?;
                stream.play()?;
                Ok(stream)
            })();
            match result {
                Ok(stream) => {
                    input_stream = Some(stream);
                    microphone_error.clear();
                }
                Err(error) => {
                    microphone_error = format!(
                        "Microphone: {error:#}. Check Windows Privacy > Microphone > desktop app access."
                    );
                }
            }
        }
        if !controls.mic.load(Ordering::Acquire) {
            drop(input_stream.take());
            while mic_rx.try_recv().is_ok() {}
        }
        if last_status.elapsed() >= Duration::from_millis(500) {
            last_status = std::time::Instant::now();
            let status = json!({"micRequested":controls.mic.load(Ordering::Acquire),"micReady":input_stream.is_some(),"speakerReady":output_stream.is_some(),"txPackets":sent_packets,"rxPackets":controls.received.load(Ordering::Relaxed),"error":if !microphone_error.is_empty()&&controls.mic.load(Ordering::Acquire){&microphone_error}else{&speaker_error}});
            shared.update(|v| {
                if v["hostSession"]["sessionId"] == session {
                    v["hostSession"]["audio"] = status.clone();
                }
                if let Some(items) = v["connections"].as_array_mut() {
                    for item in items {
                        if item["sessionId"] == session {
                            item["audio"] = status.clone();
                        }
                    }
                }
            });
        }
        if let Ok(samples) = mic_rx.recv_timeout(Duration::from_millis(20))
            && controls.mic.load(Ordering::Acquire)
            && sender.audio_capacity() > 0
        {
            let bytes: Vec<u8> = samples
                .into_iter()
                .flat_map(|v| ((v * 32767.0) as i16).to_le_bytes())
                .collect();
            if sender.try_send(Outbound::Packet(packet("audio_chunk",json!({"session_id":session,"data":B64.encode(bytes),"sample_rate":48000,"channels":1,"format":"pcm_s16le"})))).is_ok(){sent_packets+=1;}
        }
    }
    drop(input_stream);
    drop(output_stream);
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn conversion_preserves_duration_across_chunks() {
        let mut converter = Resampler::new(44100, 48000);
        let mut count = 0;
        for _ in 0..100 {
            count += converter.process(&vec![0.25; 441]).len();
        }
        assert!((count as isize - 48000).abs() <= 2);
    }
    #[test]
    fn same_rate_is_exact() {
        let mut converter = Resampler::new(48000, 48000);
        assert_eq!(converter.process(&[0.1, -0.2]), vec![0.1, -0.2]);
    }
}
