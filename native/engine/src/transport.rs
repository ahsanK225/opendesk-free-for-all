//! Independent bounded lanes keep video/file backlog from evicting voice or input.
use crate::network::Outbound;
use tokio::sync::mpsc;
pub struct Sender<T> {
    control: mpsc::Sender<T>,
    audio: mpsc::Sender<T>,
    bulk: mpsc::Sender<T>,
    video: mpsc::Sender<T>,
}
impl<T> Clone for Sender<T> {
    fn clone(&self) -> Self {
        Self {
            control: self.control.clone(),
            audio: self.audio.clone(),
            bulk: self.bulk.clone(),
            video: self.video.clone(),
        }
    }
}
pub struct Receiver {
    control: mpsc::Receiver<Outbound>,
    audio: mpsc::Receiver<Outbound>,
    bulk: mpsc::Receiver<Outbound>,
    video: mpsc::Receiver<Outbound>,
}
pub fn channel() -> (Sender<Outbound>, Receiver) {
    let (control, cr) = mpsc::channel(128);
    let (audio, ar) = mpsc::channel(12);
    let (bulk, br) = mpsc::channel(8);
    let (video, vr) = mpsc::channel(2);
    (
        Sender {
            control,
            audio,
            bulk,
            video,
        },
        Receiver {
            control: cr,
            audio: ar,
            bulk: br,
            video: vr,
        },
    )
}
impl Sender<Outbound> {
    fn lane(&self, value: &Outbound) -> &mpsc::Sender<Outbound> {
        match value {
            Outbound::Video(_) => &self.video,
            Outbound::Packet(p) if p["type"] == "audio_chunk" => &self.audio,
            Outbound::Packet(p) if p["type"].as_str().is_some_and(|t| t.starts_with("file_")) => {
                &self.bulk
            }
            _ => &self.control,
        }
    }
    pub async fn send(&self, value: Outbound) -> Result<(), mpsc::error::SendError<Outbound>> {
        self.lane(&value).send(value).await
    }
    pub fn try_send(&self, value: Outbound) -> Result<(), mpsc::error::TrySendError<Outbound>> {
        self.lane(&value).try_send(value)
    }
    pub fn blocking_send(&self, value: Outbound) -> Result<(), mpsc::error::SendError<Outbound>> {
        self.lane(&value).blocking_send(value)
    }
    pub fn capacity(&self) -> usize {
        self.video.capacity()
    }
    pub fn audio_capacity(&self) -> usize {
        self.audio.capacity()
    }
}
impl Receiver {
    pub async fn recv(&mut self) -> Option<Outbound> {
        tokio::select! {biased;v=self.control.recv()=>v,v=self.audio.recv()=>v,v=self.bulk.recv()=>v,v=self.video.recv()=>v}
    }
}
pub const WRITE_TIMEOUT: std::time::Duration = std::time::Duration::from_secs(30);
#[cfg(test)]
mod tests {
    use super::*;
    use crate::network::packet;
    use serde_json::json;
    #[tokio::test]
    async fn file_messages_remain_ordered_across_priority_lanes() {
        let (tx, mut rx) = channel();
        for kind in ["file_upload_start", "file_chunk", "file_upload_complete"] {
            tx.try_send(Outbound::Packet(packet(kind, json!({}))))
                .unwrap();
        }
        tx.try_send(Outbound::Pong(vec![])).unwrap();
        assert!(matches!(rx.recv().await, Some(Outbound::Pong(_))));
        for kind in ["file_upload_start", "file_chunk", "file_upload_complete"] {
            assert!(matches!(rx.recv().await,Some(Outbound::Packet(p)) if p["type"]==kind));
        }
    }
    #[tokio::test]
    async fn saturated_video_and_files_do_not_starve_voice_and_control() {
        let (tx, mut rx) = channel();
        for _ in 0..2 {
            tx.try_send(Outbound::Video(vec![1; 1024])).unwrap();
        }
        assert!(tx.try_send(Outbound::Video(vec![])).is_err());
        for _ in 0..8 {
            tx.try_send(Outbound::Packet(packet("file_chunk", json!({}))))
                .unwrap();
        }
        tx.try_send(Outbound::Packet(packet(
            "audio_chunk",
            json!({"data":"voice"}),
        )))
        .unwrap();
        tx.try_send(Outbound::Pong(vec![9])).unwrap();
        assert!(matches!(rx.recv().await, Some(Outbound::Pong(_))));
        assert!(matches!(rx.recv().await,Some(Outbound::Packet(p)) if p["type"]=="audio_chunk"));
    }
}
