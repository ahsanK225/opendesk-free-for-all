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
            .is_some_and(|(_, sent)| now_ms.saturating_sub(*sent) > STALL_MS)
    }
}

/// TCP loses nothing and a viewer asks for a full frame when it needs one, so a late ACK means a
/// slow link. Forgetting those frames would only add a full frame, the largest kind, to the queue.
const STALL_MS: u64 = 20_000;
const MIN_QUALITY: u8 = 35;
const MIN_WIDTH: u32 = 640;
/// Delay above the fastest recent trip that means frames are queueing, and that means they are not.
const QUEUE_HIGH_MS: u64 = 300;
const QUEUE_LOW_MS: u64 = 150;
/// Below this, too little was sent to say anything about the link. Bytes per millisecond.
const MIN_RATE: f64 = 50.0 * 1024.0 / 1000.0;
/// Above this the link is not a limit worth tracking.
const MAX_RATE: f64 = 100.0 * 1024.0 * 1024.0 / 1000.0;

/// Sends frames no faster than the link delivers them, so they do not queue in the tunnel.
/// When delay grows, the rate drops just below what actually reached the viewer. When delay is
/// low it rises again, until the link stops being a limit.
#[derive(Debug)]
pub struct Pace {
    wanted: (f64, u32, u8),
    pub fps: f64,
    pub width: u32,
    pub quality: u8,
    delay: u64,
    baseline: u64,
    previous_low: u64,
    low: u64,
    low_started: u64,
    rate: Option<f64>,
    acked_bytes: u64,
    acked_started: u64,
    sizes: VecDeque<(u64, u64)>,
    next_allowed: u64,
    second_bytes: u64,
    second_frames: u64,
    second_started: u64,
    calm: u32,
    downs: u32,
}
impl Pace {
    pub fn new(fps: u32, width: u32, quality: u8) -> Self {
        let mut pace = Self { wanted: (0.0, 0, 0), fps: 0.0, width: 0, quality: 0, delay: 0, baseline: 0, previous_low: u64::MAX, low: u64::MAX, low_started: 0, rate: None, acked_bytes: 0, acked_started: 0, sizes: VecDeque::new(), next_allowed: 0, second_bytes: 0, second_frames: 0, second_started: 0, calm: 0, downs: 0 };
        pace.configure(fps, width, quality);
        pace
    }
    pub fn configure(&mut self, fps: u32, width: u32, quality: u8) {
        self.wanted = (fps as f64, width, quality);
        (self.fps, self.width, self.quality) = self.wanted;
        (self.calm, self.downs) = (0, 0);
    }
    /// The current limit in KB/s, or 0 when the link is not limiting.
    pub fn speed(&self) -> u64 {
        (self.rate.unwrap_or(0.0) * 1000.0 / 1024.0) as u64
    }
    pub fn delays(&self) -> (u64, u64) {
        (self.delay, self.baseline)
    }
    pub fn on_sent(&mut self, frame: u64, size: u64, now: u64) {
        self.sizes.push_back((frame, size));
        if self.sizes.len() > 16 {
            self.sizes.pop_front();
        }
        self.second_bytes += size;
        self.second_frames += 1;
        if let Some(rate) = self.rate {
            self.next_allowed = now + ((size as f64 / rate) as u64).min(1000);
        }
    }
    pub fn on_ack(&mut self, frame: u64, delay: u64, heartbeat: u64, now: u64) {
        if now.saturating_sub(self.low_started) >= 15000 {
            self.previous_low = self.low;
            self.low = u64::MAX;
            self.low_started = now;
        }
        self.low = self.low.min(delay);
        if heartbeat > 0 {
            self.low = self.low.min(heartbeat);
        }
        self.baseline = self.low.min(self.previous_low);
        self.delay = if self.delay == 0 { delay } else { (self.delay * 3 + delay) / 4 };
        if let Some(index) = self.sizes.iter().position(|(id, _)| *id == frame) {
            self.acked_bytes += self.sizes[index].1;
            self.sizes.drain(..=index);
        }
    }
    pub fn ready(&self, now: u64) -> bool {
        now >= self.next_allowed
    }
    /// Frames allowed in flight. This follows the fastest delay, never the current one,
    /// because a larger window on a queueing link only makes the queue longer.
    pub fn limit(&self) -> usize {
        ((self.baseline as f64 / 1000.0 * self.fps * 1.2).ceil() as usize).clamp(2, 6)
    }
    pub fn tick(&mut self, now: u64) {
        let measured = now.saturating_sub(self.acked_started);
        if measured >= 500 {
            let delivered = self.acked_bytes as f64 / measured as f64;
            (self.acked_bytes, self.acked_started) = (0, now);
            let queue = self.delay.saturating_sub(self.baseline);
            if queue > QUEUE_HIGH_MS && delivered >= MIN_RATE {
                let lower = delivered * 0.85;
                self.rate = Some(self.rate.map_or(lower, |rate| rate.min(lower)).max(MIN_RATE));
            } else if queue < QUEUE_LOW_MS {
                self.rate = self.rate.map(|rate| rate.max(delivered) * 1.25).filter(|rate| *rate < MAX_RATE);
            }
        }
        // The picture only gets smaller when frames are too large for the link at the wanted frame rate.
        if now.saturating_sub(self.second_started) < 1000 {
            return;
        }
        let (bytes, frames) = (self.second_bytes, self.second_frames);
        (self.second_bytes, self.second_frames, self.second_started) = (0, 0, now);
        let needed = if frames == 0 { 0.0 } else { bytes as f64 / frames as f64 * self.wanted.0 / 1000.0 };
        if self.rate.is_some_and(|rate| needed > rate * 1.4) {
            self.calm = 0;
            self.downs += 1;
            self.quality = self.quality.saturating_sub(8).max(MIN_QUALITY.min(self.wanted.2));
            // Changing the size forces a full frame, so it follows the cheaper step.
            if self.downs >= 3 {
                self.width = (self.width * 85 / 100).max(MIN_WIDTH.min(self.wanted.1));
            }
        } else if self.rate.is_none_or(|rate| needed < rate) {
            self.calm += 1;
            self.downs = 0;
            if self.calm >= 3 && self.quality < self.wanted.2 {
                self.quality = (self.quality + 2).min(self.wanted.2);
            } else if self.calm >= 10 && self.width < self.wanted.1 {
                self.width = (self.width + 128).min(self.wanted.1);
                self.calm = 3;
            }
        } else {
            self.calm = 0;
        }
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
        assert!(!w.stalled(2001));
        assert!(w.stalled(STALL_MS + 1));
        assert_eq!(w.acknowledge(2, STALL_MS + 1), Some(STALL_MS));
        assert!(!w.stalled(STALL_MS * 2));
    }
    /// One frame every half second over a link of this speed, with a small heartbeat beside it.
    fn drive(pace: &mut Pace, size: u64, kb_per_second: u64, seconds: u64) {
        let start = pace.acked_started.max(pace.second_started);
        for step in 1..=seconds * 2 {
            let now = start + step * 500;
            pace.on_sent(now, size, now - 400);
            pace.on_ack(now, 80 + size * 1000 / (kb_per_second * 1024), 80, now);
            pace.tick(now);
        }
    }
    #[test]
    fn a_growing_queue_limits_the_rate_to_what_was_delivered() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 100_000, 200, 2);
        // 100 000 bytes every 500 ms is 195 KB/s delivered, and 85% of that is the limit.
        assert_eq!(pace.speed(), 166);
        pace.on_sent(99, 100_000, 10_000);
        assert!(!pace.ready(10_000));
        assert!(!pace.ready(10_500));
        assert!(pace.ready(10_000 + 600));
    }
    #[test]
    fn jitter_with_little_data_does_not_limit_the_link() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 2_000, 2, 5);
        assert_eq!(pace.speed(), 0);
        assert!(pace.ready(100_000));
        assert_eq!((pace.fps, pace.width, pace.quality), (30.0, 1600, 65));
    }
    #[test]
    fn a_large_frame_never_stops_the_stream_for_long() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 100_000, 100, 3);
        pace.on_sent(99, 5_000_000, 50_000);
        assert!(pace.ready(51_000));
    }
    #[test]
    fn the_limit_lifts_when_the_queue_is_gone() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 100_000, 200, 3);
        assert!(pace.speed() > 0);
        pace.delay = 80;
        drive(&mut pace, 100, 20_000, 60);
        assert_eq!(pace.speed(), 0);
    }
    #[test]
    fn the_heartbeat_keeps_large_frames_from_hiding_the_queue() {
        let mut pace = Pace::new(30, 1600, 65);
        pace.on_sent(1, 100_000, 0);
        pace.on_ack(1, 580, 80, 580);
        assert_eq!(pace.delays(), (580, 80));
    }
    #[test]
    fn the_window_does_not_grow_with_delay() {
        let mut pace = Pace::new(30, 1600, 65);
        pace.on_sent(1, 1000, 0);
        pace.on_ack(1, 100, 0, 100);
        let limit = pace.limit();
        for frame in 2..50 {
            pace.on_sent(frame, 50_000, frame * 500);
            pace.on_ack(frame, 100 + frame * 100, 0, frame * 500 + 100);
            assert!(pace.limit() <= limit);
        }
    }
    #[test]
    fn frames_too_large_for_the_link_lower_the_picture_within_its_floors() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 100_000, 200, 40);
        assert_eq!((pace.width, pace.quality), (MIN_WIDTH, MIN_QUALITY));
    }
    #[test]
    fn a_link_that_fits_the_frames_returns_to_the_requested_picture() {
        let mut pace = Pace::new(30, 1600, 65);
        drive(&mut pace, 100_000, 200, 40);
        pace.delay = 80;
        drive(&mut pace, 100, 20_000, 300);
        assert_eq!((pace.fps, pace.width, pace.quality), (30.0, 1600, 65));
    }
    #[test]
    fn a_profile_below_the_floors_is_respected() {
        let mut pace = Pace::new(10, 640, 20);
        drive(&mut pace, 100_000, 100, 40);
        assert_eq!((pace.width, pace.quality), (640, 20));
    }
}
