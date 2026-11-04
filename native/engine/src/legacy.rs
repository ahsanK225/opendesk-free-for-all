//! Bounded adapter for the historical JSON/JPEG protocol (no app-version gate).
use crate::{network::packet, protocol::VideoPacket, session::Permissions};
use anyhow::{Context, Result, bail};
use base64::{Engine, engine::general_purpose::STANDARD as B64};
use serde_json::{Value, json};

pub fn protocol(request: &Value) -> Option<u64> {
    if request["protocol"] == 2
        || request["supported_protocols"]
            .as_array()
            .is_some_and(|v| v.iter().any(|p| p == 2))
    {
        Some(2)
    } else if request["protocol"].is_null() || request["protocol"] == 1 {
        Some(1)
    } else {
        None
    }
}
/// Protocol 1 cannot prove an identity, so a device with a known key must never enter it.
pub fn may_enter(pinned: Option<&str>, directory_key: Option<&str>) -> bool {
    pinned.is_none() && directory_key.is_none()
}
pub fn incoming(typ: &str, p: &Value) -> Value {
    let mut p = p.clone();
    if typ == "heartbeat"
        && let Some(t) = p.get("t").cloned()
    {
        p["sent_at"] = t.clone();
        p["echo"] = t;
    }
    if typ == "audio_chunk" && p["sample_rate"].is_null() {
        let samples = p["data"]
            .as_str()
            .and_then(|s| B64.decode(s).ok())
            .map(|v| v.len() / 2)
            .unwrap_or(960);
        p["sample_rate"] = json!(if samples < 600 { 16000 } else { 48000 });
        p["channels"] = json!(1);
        p["format"] = json!("pcm_s16le");
    }
    p
}
pub fn outgoing(value: Value) -> Result<Option<Value>> {
    let typ = value["type"].as_str().unwrap_or("");
    if typ == "video_ack" {
        return Ok(None);
    }
    let mut p = value["payload"].clone();
    if typ == "heartbeat" {
        p["t"] = p
            .get("echo")
            .or_else(|| p.get("sent_at"))
            .cloned()
            .unwrap_or(Value::Null);
    }
    if typ == "audio_chunk" {
        let raw = B64.decode(p["data"].as_str().unwrap_or(""))?;
        if raw.len() > 64 * 1024 || raw.len() % 2 != 0 {
            bail!("Invalid legacy audio size")
        }
        let samples: Vec<f32> = raw
            .chunks_exact(2)
            .map(|b| i16::from_le_bytes([b[0], b[1]]) as f32 / 32768.0)
            .collect();
        let rate = p["sample_rate"].as_u64().unwrap_or(48000) as u32;
        if !(8000..=96000).contains(&rate) {
            bail!("Invalid legacy audio rate")
        }
        let samples = crate::audio::Resampler::new(rate, 16000).process(&samples);
        let bytes: Vec<u8> = samples
            .into_iter()
            .flat_map(|v| ((v.clamp(-1.0, 1.0) * 32767.0) as i16).to_le_bytes())
            .collect();
        p["data"] = json!(B64.encode(bytes));
        p["sample_rate"] = json!(16000);
    }
    Ok(Some(packet(
        if typ == "video_refresh" {
            "keyframe_req"
        } else {
            typ
        },
        p,
    )))
}
pub fn video_json(bytes: &[u8]) -> Result<Value> {
    if bytes.len() < 8 || bytes.len() > crate::protocol::MAX_FRAME_BYTES {
        bail!("Invalid video envelope")
    }
    let length = u32::from_be_bytes(bytes[4..8].try_into()?) as usize;
    if length > crate::protocol::MAX_HEADER_BYTES || length > bytes.len() - 8 {
        bail!("Invalid video header")
    }
    let header: Value = serde_json::from_slice(&bytes[8..8 + length])?;
    let frame = VideoPacket::decode(
        bytes,
        header["payload"]["session_id"].as_str().unwrap_or(""),
    )
    .map_err(|e| anyhow::anyhow!("Invalid frame: {e:?}"))?;
    let p = &frame.header.payload;
    let mut payload = json!({"width":p.width,"height":p.height,"frame_id":p.frame_id});
    if frame.header.kind == "video_full" {
        payload["image"] = json!(B64.encode(frame.image(0).context("Missing full frame")?));
    } else {
        payload["tiles"]=json!(p.tiles.iter().enumerate().map(|(i,t)|json!({"x":t.x,"y":t.y,"w":t.w,"h":t.h,"image":B64.encode(frame.image(i).unwrap_or_default())})).collect::<Vec<_>>());
    }
    Ok(packet(&frame.header.kind, payload))
}
pub fn permissions(value: &Value, limits: Permissions) -> Permissions {
    Permissions {
        input: limits.input && value["input"].as_bool().unwrap_or(true),
        audio: limits.audio && value["audio"].as_bool().unwrap_or(true),
        clipboard: limits.clipboard && value["clipboard"].as_bool().unwrap_or(true),
        file_transfer: false,
    }
}
#[derive(Default)]
pub struct VideoBridge {
    width: u32,
    height: u32,
    last: u64,
    offset: u64,
}
impl VideoBridge {
    pub fn convert(&mut self, typ: &str, p: &Value, session: &str) -> Result<Vec<u8>> {
        if !matches!(typ, "video_full" | "video_delta") {
            bail!("Invalid legacy video type")
        }
        let full = typ == "video_full";
        let width = p["width"].as_u64().unwrap_or(self.width as u64);
        let height = p["height"].as_u64().unwrap_or(self.height as u64);
        if width == 0
            || height == 0
            || width > 8192
            || height > 8192
            || width * height > 16 * 1024 * 1024
        {
            bail!("Legacy screen dimensions exceed limits")
        }
        let source = p["frame_id"].as_u64().unwrap_or(self.last);
        let mut id = source
            .checked_add(self.offset.max(1))
            .context("Legacy frame counter overflow")?;
        if full && id <= self.last {
            self.offset = self
                .last
                .checked_add(1)
                .and_then(|n| n.checked_sub(source))
                .context("Legacy frame sequence overflow")?;
            id = source + self.offset;
        }
        if id <= self.last {
            bail!("Stale legacy frame")
        }
        let values = if full {
            vec![json!({"x":0,"y":0,"w":width,"h":height,"image":p["image"]})]
        } else {
            p["tiles"]
                .as_array()
                .context("Missing legacy tiles")?
                .clone()
        };
        if values.is_empty() || values.len() > 4096 {
            bail!("Invalid legacy tile count")
        }
        let mut body = Vec::new();
        let mut tiles = Vec::new();
        for tile in values {
            let encoded = tile["image"].as_str().context("Missing legacy JPEG")?;
            if encoded.len() > 16 * 1024 * 1024 {
                bail!("Oversized legacy JPEG")
            }
            let bytes = B64.decode(encoded)?;
            let offset = body.len();
            if offset.saturating_add(bytes.len()) > crate::protocol::MAX_FRAME_BYTES {
                bail!("Oversized legacy frame")
            }
            tiles.push(json!({"x":tile["x"],"y":tile["y"],"w":tile["w"],"h":tile["h"],"offset":offset,"length":bytes.len()}));
            body.extend(bytes);
        }
        let header=json!({"type":typ,"payload":{"width":width,"height":height,"frame_id":id,"session_id":session,"tiles":tiles}}).to_string().into_bytes();
        let mut result = b"ODV2".to_vec();
        result.extend((header.len() as u32).to_be_bytes());
        result.extend(header);
        result.extend(body);
        VideoPacket::decode(&result, session)
            .map_err(|e| anyhow::anyhow!("Invalid legacy frame: {e:?}"))?;
        self.width = width as u32;
        self.height = height as u32;
        self.last = id;
        Ok(result)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn legacy_roundtrip_preserves_jpeg_and_resets_frame_counter() {
        let mut bridge = VideoBridge::default();
        let p = json!({"width":4,"height":4,"frame_id":0,"image":B64.encode([1,2,3])});
        let bytes = bridge
            .convert("video_full", &p, "session-legacy-123456")
            .unwrap();
        let old = video_json(&bytes).unwrap();
        assert_eq!(old["payload"]["image"], p["image"]);
        let next = bridge
            .convert("video_full", &p, "session-legacy-123456")
            .unwrap();
        assert!(
            VideoPacket::decode(&next, "session-legacy-123456")
                .unwrap()
                .header
                .payload
                .frame_id
                > 1
        );
        assert!(
            bridge
                .convert(
                    "video_full",
                    &json!({"width":99999,"height":4,"image":"AAA="}),
                    "session"
                )
                .is_err()
        );
    }
    #[test]
    fn known_device_keys_block_compatibility_mode() {
        assert!(may_enter(None, None));
        assert!(!may_enter(Some("saved"), None));
        assert!(!may_enter(None, Some("signed-record")));
        assert!(!may_enter(Some("saved"), Some("signed-record")));
    }
    #[test]
    fn negotiation_prefers_verified_protocol_and_legacy_audio_is_16k() {
        assert_eq!(
            protocol(&json!({"protocol":9,"supported_protocols":[1,2]})),
            Some(2)
        );
        assert_eq!(protocol(&json!({})), Some(1));
        assert_eq!(protocol(&json!({"protocol":7})), None);
        let value = outgoing(packet(
            "audio_chunk",
            json!({"data":B64.encode(vec![0;1920]),"sample_rate":48000}),
        ))
        .unwrap()
        .unwrap();
        assert_eq!(
            B64.decode(value["payload"]["data"].as_str().unwrap())
                .unwrap()
                .len(),
            640
        );
        assert_eq!(
            incoming("audio_chunk", &value["payload"])["sample_rate"],
            16000
        );
    }
}
