//! Strict, borrowed decoding of the existing ODV2 media envelope.
use serde::Deserialize;

pub const MAX_FRAME_BYTES: usize = 32 * 1024 * 1024;
pub const MAX_HEADER_BYTES: usize = 256 * 1024;
pub const MAX_DIMENSION: u32 = 8192;
pub const MAX_PIXELS: u64 = 33_554_432;

#[derive(Debug, PartialEq, Eq)]
pub enum DecodeError {
    Size,
    Magic,
    Header,
    Metadata,
    Session,
    Tile,
    Coverage,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tile {
    pub offset: usize,
    pub length: usize,
    pub x: Option<u32>,
    pub y: Option<u32>,
    pub w: Option<u32>,
    pub h: Option<u32>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Payload {
    pub width: u32,
    pub height: u32,
    pub frame_id: u64,
    pub session_id: String,
    pub tiles: Vec<Tile>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Header {
    #[serde(rename = "type")]
    pub kind: String,
    pub payload: Payload,
}

#[derive(Debug)]
pub struct VideoPacket<'a> {
    pub header: Header,
    body: &'a [u8],
}

impl<'a> VideoPacket<'a> {
    pub fn decode(bytes: &'a [u8], session: &str) -> Result<Self, DecodeError> {
        if bytes.len() < 8 || bytes.len() > MAX_FRAME_BYTES {
            return Err(DecodeError::Size);
        }
        if &bytes[..4] != b"ODV2" {
            return Err(DecodeError::Magic);
        }
        let count = u32::from_be_bytes(bytes[4..8].try_into().unwrap()) as usize;
        if count == 0 || count > MAX_HEADER_BYTES || count > bytes.len() - 8 {
            return Err(DecodeError::Header);
        }
        let header: Header =
            serde_json::from_slice(&bytes[8..8 + count]).map_err(|_| DecodeError::Header)?;
        let p = &header.payload;
        if p.width == 0
            || p.height == 0
            || p.width > MAX_DIMENSION
            || p.height > MAX_DIMENSION
            || u64::from(p.width) * u64::from(p.height) > MAX_PIXELS
            || p.frame_id == 0
            || !matches!(header.kind.as_str(), "video_full" | "video_delta")
        {
            return Err(DecodeError::Metadata);
        }
        if session.is_empty() || p.session_id != session {
            return Err(DecodeError::Session);
        }
        let body = &bytes[8 + count..];
        let full = header.kind == "video_full";
        if p.tiles.is_empty() || p.tiles.len() > 4096 || (full && p.tiles.len() != 1) {
            return Err(DecodeError::Tile);
        }
        let mut expected_offset = 0usize;
        for tile in &p.tiles {
            if tile.offset != expected_offset || tile.length == 0 {
                return Err(DecodeError::Tile);
            }
            expected_offset = expected_offset
                .checked_add(tile.length)
                .ok_or(DecodeError::Tile)?;
            if expected_offset > body.len() {
                return Err(DecodeError::Tile);
            }
            if !full {
                let (Some(x), Some(y), Some(w), Some(h)) = (tile.x, tile.y, tile.w, tile.h) else {
                    return Err(DecodeError::Tile);
                };
                if w == 0
                    || h == 0
                    || x.checked_add(w).is_none_or(|v| v > p.width)
                    || y.checked_add(h).is_none_or(|v| v > p.height)
                {
                    return Err(DecodeError::Tile);
                }
            }
        }
        if expected_offset != body.len() {
            return Err(DecodeError::Coverage);
        }
        Ok(Self { header, body })
    }

    pub fn image(&self, index: usize) -> Option<&'a [u8]> {
        let tile = self.header.payload.tiles.get(index)?;
        self.body
            .get(tile.offset..tile.offset.checked_add(tile.length)?)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn packet(mutator: impl FnOnce(&mut Value)) -> Vec<u8> {
        let mut header = json!({"type":"video_full","payload":{"width":1280,"height":720,
            "frame_id":1,"session_id":"session-a","tiles":[{"offset":0,"length":3}]}});
        mutator(&mut header);
        let raw = serde_json::to_vec(&header).unwrap();
        let mut data = b"ODV2".to_vec();
        data.extend_from_slice(&(raw.len() as u32).to_be_bytes());
        data.extend(raw);
        data.extend([1, 2, 3]);
        data
    }

    #[test]
    fn borrows_image_without_copy() {
        let data = packet(|_| {});
        let parsed = VideoPacket::decode(&data, "session-a").unwrap();
        assert_eq!(parsed.image(0), Some(&[1, 2, 3][..]));
        assert_eq!(
            parsed.image(0).unwrap().as_ptr(),
            data[data.len() - 3..].as_ptr()
        );
    }
    #[test]
    fn rejects_cross_session() {
        assert!(matches!(
            VideoPacket::decode(&packet(|_| {}), "session-b"),
            Err(DecodeError::Session)
        ));
    }
    #[test]
    fn rejects_length_overflow() {
        assert!(
            VideoPacket::decode(
                &packet(|v| v["payload"]["tiles"][0]["length"] = json!(u64::MAX)),
                "session-a"
            )
            .is_err()
        );
    }
    #[test]
    fn rejects_decompression_bomb_dimensions() {
        assert!(matches!(
            VideoPacket::decode(
                &packet(|v| v["payload"]["height"] = json!(u32::MAX)),
                "session-a"
            ),
            Err(DecodeError::Metadata)
        ));
    }
    #[test]
    fn rejects_tile_outside_desktop() {
        let data = packet(|v| {
            v["type"] = json!("video_delta");
            v["payload"]["tiles"][0] = json!({"offset":0,"length":3,"x":1279,"y":0,"w":2,"h":1});
        });
        assert!(matches!(
            VideoPacket::decode(&data, "session-a"),
            Err(DecodeError::Tile)
        ));
    }
    #[test]
    fn rejects_truncated_and_unknown_headers() {
        assert!(VideoPacket::decode(b"ODV2\0\0\0\xff", "session-a").is_err());
        assert!(VideoPacket::decode(&packet(|v| v["host"] = json!(true)), "session-a").is_err());
    }
    #[test]
    fn rejects_trailing_hidden_data() {
        let mut data = packet(|_| {});
        data.push(9);
        assert!(matches!(
            VideoPacket::decode(&data, "session-a"),
            Err(DecodeError::Coverage)
        ));
    }
}
