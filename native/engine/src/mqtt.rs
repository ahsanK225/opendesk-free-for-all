//! A small MQTT 3.1.1 client over WebSocket, used only to keep one retained directory record on
//! public brokers. They need no account and have no daily message limit like the first directory.
//! Anyone can write to a topic, so readers trust only what the device signed.
use anyhow::{Context, Result, bail};
use futures_util::{SinkExt, StreamExt};
use std::time::Duration;
use tokio_tungstenite::{
    connect_async,
    tungstenite::{Message, client::IntoClientRequest},
};
pub const BROKERS: [&str; 2] = ["wss://broker.emqx.io:8084/mqtt", "wss://broker.hivemq.com:8884/mqtt"];
const WAIT: Duration = Duration::from_secs(5);

fn topic(id: &str) -> String {
    format!("opendesk/v1/device/{id}")
}
fn remaining_length(mut value: usize) -> Vec<u8> {
    let mut bytes = Vec::new();
    loop {
        let mut byte = (value % 128) as u8;
        value /= 128;
        if value > 0 {
            byte |= 128;
        }
        bytes.push(byte);
        if value == 0 {
            return bytes;
        }
    }
}
fn with_string(out: &mut Vec<u8>, text: &str) {
    out.extend((text.len() as u16).to_be_bytes());
    out.extend(text.as_bytes());
}
fn packet(kind: u8, body: Vec<u8>) -> Vec<u8> {
    let mut out = vec![kind];
    out.extend(remaining_length(body.len()));
    out.extend(body);
    out
}
fn connect_packet(client: &str) -> Vec<u8> {
    let mut body = Vec::new();
    with_string(&mut body, "MQTT");
    body.extend([4, 2, 0, 30]);
    with_string(&mut body, client);
    packet(0x10, body)
}
/// Retained, and acknowledged by the broker.
fn publish_packet(topic: &str, payload: &str) -> Vec<u8> {
    let mut body = Vec::new();
    with_string(&mut body, topic);
    body.extend(1u16.to_be_bytes());
    body.extend(payload.as_bytes());
    packet(0x33, body)
}
fn subscribe_packet(topic: &str) -> Vec<u8> {
    let mut body = 1u16.to_be_bytes().to_vec();
    with_string(&mut body, topic);
    body.push(0);
    packet(0x82, body)
}
/// Splits a message into packets, as (first byte, body).
fn split(mut data: &[u8]) -> Vec<(u8, &[u8])> {
    let mut packets = Vec::new();
    while data.len() >= 2 {
        let (mut length, mut shift, mut index) = (0usize, 0, 1);
        loop {
            let Some(byte) = data.get(index) else { return packets };
            length |= ((byte & 127) as usize) << shift;
            index += 1;
            if byte & 128 == 0 {
                break;
            }
            shift += 7;
            if shift > 21 {
                return packets;
            }
        }
        let Some(body) = data.get(index..index + length) else { return packets };
        packets.push((data[0], body));
        data = &data[index + length..];
    }
    packets
}
/// The text of a QoS 0 publish message.
fn published_text(body: &[u8]) -> Option<String> {
    let length = u16::from_be_bytes([*body.first()?, *body.get(1)?]) as usize;
    String::from_utf8(body.get(2 + length..)?.to_vec()).ok()
}
type Socket = tokio_tungstenite::WebSocketStream<tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>>;
async fn open(broker: &str) -> Result<Socket> {
    let mut request = broker.into_client_request()?;
    request.headers_mut().insert("Sec-WebSocket-Protocol", "mqtt".parse()?);
    let (mut socket, _) = tokio::time::timeout(WAIT, connect_async(request)).await.context("Broker timed out")??;
    socket.send(Message::Binary(connect_packet(&format!("opendesk-{}", crate::store::token()[..16].to_owned())).into())).await?;
    next_packet(&mut socket, 0x20).await?;
    Ok(socket)
}
async fn next_packet(socket: &mut Socket, kind: u8) -> Result<Vec<u8>> {
    let read = async {
        while let Some(message) = socket.next().await {
            if let Message::Binary(data) = message? {
                for (first, body) in split(&data) {
                    if first & 0xf0 == kind {
                        return Ok(body.to_vec());
                    }
                }
            }
        }
        bail!("Broker closed the connection")
    };
    tokio::time::timeout(WAIT, read).await.context("Broker timed out")?
}
pub async fn publish(broker: &str, id: &str, record: &str) -> Result<()> {
    let mut socket = open(broker).await?;
    socket.send(Message::Binary(publish_packet(&topic(id), record).into())).await?;
    next_packet(&mut socket, 0x40).await?;
    let _ = socket.send(Message::Binary(vec![0xe0, 0].into())).await;
    Ok(())
}
pub async fn read(broker: &str, id: &str) -> Result<Option<String>> {
    let mut socket = open(broker).await?;
    socket.send(Message::Binary(subscribe_packet(&topic(id)).into())).await?;
    next_packet(&mut socket, 0x90).await?;
    // A broker sends the retained message right after the acknowledgement, if it has one.
    let found = match tokio::time::timeout(Duration::from_secs(2), next_packet(&mut socket, 0x30)).await {
        Ok(Ok(body)) => published_text(&body),
        _ => None,
    };
    let _ = socket.send(Message::Binary(vec![0xe0, 0].into())).await;
    Ok(found)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn lengths_use_the_mqtt_variable_encoding() {
        assert_eq!(remaining_length(0), [0]);
        assert_eq!(remaining_length(127), [127]);
        assert_eq!(remaining_length(128), [0x80, 1]);
        assert_eq!(remaining_length(321), [0xc1, 2]);
    }
    #[test]
    fn a_published_record_can_be_read_back() {
        let data = publish_packet("a/b", &"x".repeat(300));
        let packets = split(&data);
        assert_eq!(packets.len(), 1);
        assert_eq!(packets[0].0, 0x33);
        // The acknowledged form carries a packet id before the payload.
        assert_eq!(&packets[0].1[..5], [0, 3, b'a', b'/', b'b']);
        let mut plain = Vec::new();
        with_string(&mut plain, "a/b");
        plain.extend(b"record");
        assert_eq!(published_text(&plain).unwrap(), "record");
    }
    #[test]
    fn broken_packets_are_not_read_past_their_end() {
        assert!(split(&[0x30, 10, 1, 2]).is_empty());
        assert!(split(&[0x30]).is_empty());
        assert!(split(&[0x30, 0xff, 0xff, 0xff, 0xff, 0xff]).is_empty());
        assert_eq!(split(&[0x20, 2, 0, 0, 0x90, 1, 0]).len(), 2);
        assert!(published_text(&[0, 9, 1]).is_none());
    }
}
