//! H.264 through the codecs built into Windows, which needs no bundled codec. It uses far less
//! data than JPEG tiles on a moving picture. Peers that lack it keep using JPEG tiles.
use anyhow::{Context, Result, bail};
use std::{mem::ManuallyDrop, time::Instant};
use windows::{
    Win32::{
        Media::MediaFoundation::*,
        System::Com::{CLSCTX_INPROC_SERVER, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx},
        System::Variant::VARIANT,
    },
    core::{GUID, Interface},
};
pub const MAGIC: &[u8; 4] = b"ODH4";
const CLSID_DECODER: GUID = GUID::from_u128(0x62ce7e72_4c71_4d20_b15d_452831a87d9d);
const MAX_DIMENSION: u32 = 8192;

fn start() -> Result<()> {
    unsafe {
        // Another part of this thread may have set COM up already, which is fine.
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
        MFStartup(MF_VERSION, MFSTARTUP_LITE)?;
    }
    Ok(())
}
/// Some Windows editions ship without media codecs.
pub fn available() -> bool {
    static AVAILABLE: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *AVAILABLE.get_or_init(|| {
        std::thread::spawn(|| Encoder::new(640, 360, 30, 1_000_000).is_ok() && Decoder::new().is_ok()).join().unwrap_or(false)
    })
}
/// BT.601 with chroma averaged over each 2x2 block.
pub fn bgra_to_nv12(source: &[u8], stride: usize, width: usize, height: usize, out: &mut Vec<u8>) {
    out.clear();
    out.resize(width * height * 3 / 2, 0);
    let (luma, chroma) = out.split_at_mut(width * height);
    for y in 0..height {
        let row = &source[y * stride..y * stride + width * 4];
        for (pixel, value) in row.chunks_exact(4).zip(&mut luma[y * width..(y + 1) * width]) {
            *value = (((66 * pixel[2] as i32 + 129 * pixel[1] as i32 + 25 * pixel[0] as i32 + 128) >> 8) + 16) as u8;
        }
    }
    for y in (0..height).step_by(2) {
        let (first, second) = (&source[y * stride..], &source[(y + 1) * stride..]);
        let line = &mut chroma[y / 2 * width..y / 2 * width + width];
        for x in (0..width).step_by(2) {
            let (mut b, mut g, mut r) = (0i32, 0i32, 0i32);
            for pixel in [&first[x * 4..x * 4 + 4], &first[x * 4 + 4..x * 4 + 8], &second[x * 4..x * 4 + 4], &second[x * 4 + 4..x * 4 + 8]] {
                b += pixel[0] as i32;
                g += pixel[1] as i32;
                r += pixel[2] as i32;
            }
            let (b, g, r) = (b >> 2, g >> 2, r >> 2);
            line[x] = (((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128) as u8;
            line[x + 1] = (((112 * r - 94 * g - 18 * b + 128) >> 8) + 128) as u8;
        }
    }
}
pub fn nv12_to_bgra(source: &[u8], stride: usize, chroma_start: usize, width: usize, height: usize) -> Vec<u8> {
    let mut out = vec![255u8; width * height * 4];
    for y in 0..height {
        let luma = &source[y * stride..y * stride + width];
        let chroma = &source[chroma_start + y / 2 * stride..chroma_start + y / 2 * stride + width];
        let row = &mut out[y * width * 4..(y + 1) * width * 4];
        for x in 0..width {
            let c = 298 * (luma[x] as i32 - 16);
            let (u, v) = (chroma[x & !1] as i32 - 128, chroma[x | 1] as i32 - 128);
            let pixel = &mut row[x * 4..x * 4 + 4];
            pixel[0] = ((c + 516 * u + 128) >> 8).clamp(0, 255) as u8;
            pixel[1] = ((c - 100 * u - 208 * v + 128) >> 8).clamp(0, 255) as u8;
            pixel[2] = ((c + 409 * v + 128) >> 8).clamp(0, 255) as u8;
        }
    }
    out
}
fn video_type(subtype: &GUID, width: u32, height: u32, fps: u32) -> Result<IMFMediaType> {
    unsafe {
        let kind = MFCreateMediaType()?;
        kind.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video)?;
        kind.SetGUID(&MF_MT_SUBTYPE, subtype)?;
        kind.SetUINT64(&MF_MT_FRAME_SIZE, ((width as u64) << 32) | height as u64)?;
        kind.SetUINT64(&MF_MT_FRAME_RATE, ((fps as u64) << 32) | 1)?;
        kind.SetUINT32(&MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive.0 as u32)?;
        Ok(kind)
    }
}
fn buffer_sample(data: &[u8]) -> Result<IMFSample> {
    unsafe {
        let sample = MFCreateSample()?;
        let buffer = MFCreateMemoryBuffer(data.len() as u32)?;
        let mut target = std::ptr::null_mut();
        buffer.Lock(&mut target, None, None)?;
        std::ptr::copy_nonoverlapping(data.as_ptr(), target, data.len());
        buffer.Unlock()?;
        buffer.SetCurrentLength(data.len() as u32)?;
        sample.AddBuffer(&buffer)?;
        Ok(sample)
    }
}
fn sample_bytes(sample: &IMFSample) -> Result<Vec<u8>> {
    unsafe {
        let buffer = sample.ConvertToContiguousBuffer()?;
        let (mut source, mut length) = (std::ptr::null_mut(), 0u32);
        buffer.Lock(&mut source, None, Some(&mut length))?;
        let bytes = std::slice::from_raw_parts(source, length as usize).to_vec();
        buffer.Unlock()?;
        Ok(bytes)
    }
}
enum Output {
    Sample(IMFSample),
    NeedMoreInput,
    StreamChange,
}
fn next_output(transform: &IMFTransform) -> Result<Output> {
    unsafe {
        let info = transform.GetOutputStreamInfo(0)?;
        let provided = info.dwFlags & MFT_OUTPUT_STREAM_PROVIDES_SAMPLES.0 as u32 != 0;
        let sample = if provided {
            None
        } else {
            let sample = MFCreateSample()?;
            sample.AddBuffer(&MFCreateMemoryBuffer(info.cbSize.max(1))?)?;
            Some(sample)
        };
        let mut output = [MFT_OUTPUT_DATA_BUFFER { dwStreamID: 0, pSample: ManuallyDrop::new(sample), dwStatus: 0, pEvents: ManuallyDrop::new(None) }];
        let mut status = 0;
        let result = transform.ProcessOutput(0, &mut output, &mut status);
        let sample = ManuallyDrop::take(&mut output[0].pSample);
        drop(ManuallyDrop::take(&mut output[0].pEvents));
        match result {
            Ok(()) => Ok(Output::Sample(sample.context("The codec returned no picture")?)),
            Err(error) if error.code() == MF_E_TRANSFORM_NEED_MORE_INPUT => Ok(Output::NeedMoreInput),
            Err(error) if error.code() == MF_E_TRANSFORM_STREAM_CHANGE => Ok(Output::StreamChange),
            Err(error) => Err(error.into()),
        }
    }
}
pub struct Encoder {
    transform: IMFTransform,
    codec: ICodecAPI,
    pub width: u32,
    pub height: u32,
    frame: u64,
    started: Instant,
    bitrate: u32,
    nv12: Vec<u8>,
    interval: i64,
}
impl Encoder {
    pub fn new(width: u32, height: u32, fps: u32, bitrate: u32) -> Result<Self> {
        start()?;
        unsafe {
            let transform: IMFTransform = CoCreateInstance(&CLSID_MSH264EncoderMFT, None, CLSCTX_INPROC_SERVER)?;
            let codec: ICodecAPI = transform.cast()?;
            let output = video_type(&MFVideoFormat_H264, width, height, fps)?;
            output.SetUINT32(&MF_MT_AVG_BITRATE, bitrate)?;
            output.SetUINT32(&MF_MT_MPEG2_PROFILE, eAVEncH264VProfile_Base.0 as u32)?;
            transform.SetOutputType(0, &output, 0)?;
            transform.SetInputType(0, &video_type(&MFVideoFormat_NV12, width, height, fps)?, 0)?;
            // Settings a codec does not offer are only a loss of tuning.
            let _ = codec.SetValue(&CODECAPI_AVLowLatencyMode, &VARIANT::from(true));
            let _ = codec.SetValue(&CODECAPI_AVEncMPVGOPSize, &VARIANT::from(fps * 20));
            transform.ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0)?;
            transform.ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0)?;
            Ok(Self { transform, codec, width, height, frame: 0, started: Instant::now(), bitrate, nv12: Vec::new(), interval: 10_000_000 / fps as i64 })
        }
    }
    pub fn set_bitrate(&mut self, bitrate: u32) {
        if self.bitrate.abs_diff(bitrate) * 10 > self.bitrate {
            self.bitrate = bitrate;
            let _ = unsafe { self.codec.SetValue(&CODECAPI_AVEncCommonMeanBitRate, &VARIANT::from(bitrate)) };
        }
    }
    /// Returns the coded picture and whether a viewer can start from it.
    pub fn encode(&mut self, source: &[u8], stride: usize, frame: u64, keyframe: bool, session: &str) -> Result<Option<(Vec<u8>, bool)>> {
        self.frame = frame;
        bgra_to_nv12(source, stride, self.width as usize, self.height as usize, &mut self.nv12);
        unsafe {
            if keyframe {
                let _ = self.codec.SetValue(&CODECAPI_AVEncVideoForceKeyFrame, &VARIANT::from(1u32));
            }
            let sample = buffer_sample(&self.nv12)?;
            sample.SetSampleTime(self.started.elapsed().as_micros() as i64 * 10)?;
            sample.SetSampleDuration(self.interval)?;
            self.transform.ProcessInput(0, &sample, 0)?;
            let mut result = None;
            loop {
                match next_output(&self.transform)? {
                    Output::Sample(sample) => {
                        let key = sample.GetUINT32(&MFSampleExtension_CleanPoint).unwrap_or(0) != 0;
                        result = Some((wrap(self.width, self.height, frame, key, session, &sample_bytes(&sample)?), key));
                    }
                    Output::NeedMoreInput => break,
                    Output::StreamChange => bail!("The encoder changed its format"),
                }
            }
            Ok(result)
        }
    }
}
impl Drop for Encoder {
    fn drop(&mut self) {
        unsafe {
            let _ = self.transform.ProcessMessage(MFT_MESSAGE_COMMAND_FLUSH, 0);
        }
    }
}
fn wrap(width: u32, height: u32, frame: u64, key: bool, session: &str, picture: &[u8]) -> Vec<u8> {
    let mut data = Vec::with_capacity(22 + session.len() + picture.len());
    data.extend(MAGIC);
    data.extend(width.to_be_bytes());
    data.extend(height.to_be_bytes());
    data.extend(frame.to_be_bytes());
    data.push(u8::from(key));
    data.push(session.len() as u8);
    data.extend(session.as_bytes());
    data.extend(picture);
    data
}
#[derive(Debug, PartialEq)]
pub struct Packet<'a> {
    pub width: u32,
    pub height: u32,
    pub frame: u64,
    pub key: bool,
    pub picture: &'a [u8],
}
pub fn read<'a>(data: &'a [u8], session: &str) -> Result<Packet<'a>> {
    if data.len() < 22 || &data[..4] != MAGIC {
        bail!("Invalid H.264 frame")
    }
    let width = u32::from_be_bytes(data[4..8].try_into()?);
    let height = u32::from_be_bytes(data[8..12].try_into()?);
    let frame = u64::from_be_bytes(data[12..20].try_into()?);
    let length = data[21] as usize;
    let end = 22 + length;
    if data.get(22..end).is_none_or(|name| name != session.as_bytes()) {
        bail!("This frame belongs to another session")
    }
    if width == 0 || height == 0 || width > MAX_DIMENSION || u64::from(width) * u64::from(height) > 16 * 1024 * 1024 || width % 2 != 0 || height % 2 != 0 {
        bail!("Video dimensions exceed the native profile limits")
    }
    Ok(Packet { width, height, frame, key: data[20] != 0, picture: &data[end..] })
}
pub struct Decoder {
    transform: IMFTransform,
    stride: usize,
    coded_height: usize,
    configured: bool,
}
impl Decoder {
    pub fn new() -> Result<Self> {
        start()?;
        unsafe {
            let transform: IMFTransform = CoCreateInstance(&CLSID_DECODER, None, CLSCTX_INPROC_SERVER)?;
            if let Ok(attributes) = transform.GetAttributes() {
                let _ = attributes.SetUINT32(&MF_LOW_LATENCY, 1);
            }
            let input = MFCreateMediaType()?;
            input.SetGUID(&MF_MT_MAJOR_TYPE, &MFMediaType_Video)?;
            input.SetGUID(&MF_MT_SUBTYPE, &MFVideoFormat_H264)?;
            transform.SetInputType(0, &input, 0)?;
            let mut decoder = Self { transform, stride: 0, coded_height: 0, configured: false };
            decoder.choose_output()?;
            decoder.transform.ProcessMessage(MFT_MESSAGE_NOTIFY_BEGIN_STREAMING, 0)?;
            decoder.transform.ProcessMessage(MFT_MESSAGE_NOTIFY_START_OF_STREAM, 0)?;
            Ok(decoder)
        }
    }
    fn choose_output(&mut self) -> Result<()> {
        unsafe {
            for index in 0.. {
                let kind = self.transform.GetOutputAvailableType(0, index)?;
                if kind.GetGUID(&MF_MT_SUBTYPE)? == MFVideoFormat_NV12 {
                    self.transform.SetOutputType(0, &kind, 0)?;
                    let size = kind.GetUINT64(&MF_MT_FRAME_SIZE).unwrap_or(0);
                    let width = (size >> 32) as usize;
                    self.coded_height = (size & 0xffff_ffff) as usize;
                    self.stride = kind.GetUINT32(&MF_MT_DEFAULT_STRIDE).map(|v| v as i32 as usize).unwrap_or(width).max(width);
                    self.configured = width > 0;
                    return Ok(());
                }
            }
        }
        bail!("The H.264 decoder offers no usable format")
    }
    /// The picture as BGRA pixels, or nothing when the codec is still waiting for more data.
    pub fn decode(&mut self, packet: &Packet) -> Result<Option<Vec<u8>>> {
        unsafe {
            let sample = buffer_sample(packet.picture)?;
            sample.SetSampleTime(packet.frame as i64 * 1000)?;
            self.transform.ProcessInput(0, &sample, 0)?;
            let mut picture = None;
            loop {
                match next_output(&self.transform)? {
                    Output::Sample(sample) => {
                        let (width, height) = (packet.width as usize, packet.height as usize);
                        let bytes = sample_bytes(&sample)?;
                        let chroma = self.stride * self.coded_height;
                        if !self.configured || self.stride < width || self.coded_height < height || bytes.len() < chroma + self.stride * height / 2 {
                            bail!("The decoded picture does not match the frame")
                        }
                        picture = Some(nv12_to_bgra(&bytes, self.stride, chroma, width, height));
                    }
                    Output::NeedMoreInput => return Ok(picture),
                    Output::StreamChange => self.choose_output()?,
                }
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn picture(width: usize, height: usize, step: usize) -> Vec<u8> {
        let mut bytes = vec![255u8; width * height * 4];
        for y in 0..height {
            for x in 0..width {
                let i = (y * width + x) * 4;
                let v = if ((x + step * 6) / 9 + y / 11) % 5 == 0 { 230 } else { 40 + ((x + step * 6) % 60) as u8 };
                bytes[i..i + 3].copy_from_slice(&[v, v, (v / 2).wrapping_add(60)]);
            }
        }
        bytes
    }
    #[test]
    fn color_conversion_comes_back_close() {
        let source = picture(64, 48, 0);
        let mut nv12 = Vec::new();
        bgra_to_nv12(&source, 64 * 4, 64, 48, &mut nv12);
        let back = nv12_to_bgra(&nv12, 64, 64 * 48, 64, 48);
        assert_eq!(back.len(), source.len());
        // Luma-only comparison, because chroma is shared across each 2x2 block.
        let error: i64 = source.chunks_exact(4).zip(back.chunks_exact(4)).map(|(a, b)| (a[1] as i64 - b[1] as i64).abs()).sum();
        assert!(error / (64 * 48) < 30, "{}", error / (64 * 48));
    }
    #[test]
    fn broken_frames_are_refused() {
        let good = wrap(640, 360, 7, true, "s", &[1, 2, 3]);
        let packet = read(&good, "s").unwrap();
        assert_eq!((packet.width, packet.height, packet.frame, packet.key, packet.picture), (640, 360, 7, true, &[1u8, 2, 3][..]));
        assert!(read(&good, "other").is_err());
        assert!(read(&good[..10], "s").is_err());
        assert!(read(&wrap(9000, 360, 1, true, "s", &[]), "s").is_err());
        assert!(read(&wrap(641, 360, 1, true, "s", &[]), "s").is_err());
        assert!(read(&wrap(8000, 8000, 1, true, "s", &[]), "s").is_err());
        let mut short = good.clone();
        short[21] = 200;
        assert!(read(&short, "s").is_err());
    }
    #[test]
    fn a_moving_picture_survives_the_windows_codecs_and_uses_little_data() {
        let (width, height) = (1600u32, 900u32);
        let mut encoder = Encoder::new(width, height, 30, 4_000_000).unwrap();
        let mut decoder = Decoder::new().unwrap();
        let (mut total, mut outputs, mut encode_ms, mut decode_ms) = (0usize, 0, 0u128, 0u128);
        for frame in 1..=60u64 {
            let source = picture(width as usize, height as usize, frame as usize);
            let timer = Instant::now();
            let coded = encoder.encode(&source, width as usize * 4, frame, frame == 1, "s").unwrap();
            encode_ms += timer.elapsed().as_millis();
            let Some((data, key)) = coded else { continue };
            if frame == 1 {
                assert!(key, "the first frame must be a starting point");
            }
            total += data.len();
            let packet = read(&data, "s").unwrap();
            let timer = Instant::now();
            if let Some(pixels) = decoder.decode(&packet).unwrap() {
                decode_ms += timer.elapsed().as_millis();
                assert_eq!(pixels.len(), (width * height * 4) as usize);
                outputs += 1;
            }
        }
        println!("h264: {} KB for 60 frames, encode {} ms/frame, decode {} ms/frame, {outputs} pictures", total / 1024, encode_ms / 60, decode_ms / 60);
        assert!(outputs >= 55, "{outputs}");
    }
}
