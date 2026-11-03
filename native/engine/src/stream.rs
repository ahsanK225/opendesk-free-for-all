//! Frame dependency and backpressure accounting; arbitrary delta dropping is forbidden.
use std::collections::VecDeque;

#[derive(Debug)]
pub struct AckWindow {
    outstanding: VecDeque<(u64, u64)>,
    limit: usize,
    last_sent: u64,
    pub needs_keyframe: bool,
}

impl AckWindow {
    pub fn new(limit: usize) -> Self {
        Self {
            outstanding: VecDeque::new(),
            limit: limit.clamp(1, 10),
            last_sent: 0,
            needs_keyframe: true,
        }
    }
    pub fn can_send(&self) -> bool {
        self.outstanding.len() < self.limit
    }
    pub fn set_limit(&mut self, limit: usize) {
        self.limit = limit.clamp(1, 10);
    }
    pub fn oldest_age(&self, now_ms: u64) -> u64 {
        self.outstanding
            .front()
            .map(|(_, sent)| now_ms.saturating_sub(*sent))
            .unwrap_or(0)
    }
    pub fn sent(&mut self, frame: u64, now_ms: u64, keyframe: bool) -> bool {
        if frame <= self.last_sent || !self.can_send() || (self.needs_keyframe && !keyframe) {
            return false;
        }
        self.outstanding.push_back((frame, now_ms));
        self.last_sent = frame;
        if keyframe {
            self.needs_keyframe = false;
        }
        true
    }
    /// Cumulative ACKs only free frames actually issued by this window.
    pub fn acknowledge(&mut self, frame: u64, now_ms: u64) -> Option<u64> {
        let index = self.outstanding.iter().position(|(id, _)| *id == frame)?;
        let sent = self.outstanding[index].1;
        self.outstanding.drain(..=index);
        Some(now_ms.saturating_sub(sent))
    }
    pub fn refresh(&mut self) {
        self.outstanding.clear();
        self.needs_keyframe = true;
    }
    pub fn stalled(&self, now_ms: u64) -> bool {
        self.outstanding
            .front()
            .is_some_and(|(_, sent)| now_ms.saturating_sub(*sent) > 2000)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn backpressure_prevents_unbounded_frames() {
        let mut w = AckWindow::new(2);
        assert!(!w.sent(1, 0, false));
        assert!(w.sent(1, 0, true));
        assert!(w.sent(2, 10, false));
        assert!(!w.sent(3, 20, false));
        assert_eq!(w.acknowledge(1, 25), Some(25));
        assert!(w.sent(3, 26, false));
    }
    #[test]
    fn forged_ack_does_not_free_window() {
        let mut w = AckWindow::new(1);
        w.sent(1, 0, true);
        assert_eq!(w.acknowledge(999, 30), None);
        assert!(!w.can_send());
    }
    #[test]
    fn refresh_requires_keyframe_and_monotonic_id() {
        let mut w = AckWindow::new(3);
        w.sent(1, 0, true);
        w.refresh();
        assert!(!w.sent(2, 1, false));
        assert!(!w.sent(1, 1, true));
        assert!(w.sent(2, 1, true));
    }
    #[test]
    fn cumulative_ack_and_stall_detection() {
        let mut w = AckWindow::new(3);
        w.sent(1, 0, true);
        w.sent(2, 1, false);
        assert!(w.stalled(2001));
        assert_eq!(w.acknowledge(2, 2001), Some(2000));
        assert!(!w.stalled(4000));
    }
}
