//! Player buffer state machine for the deterministic simulator.
//!
//! Tracks playback time, buffer fill, rebuffer/startup time, and total bytes.
//! All logic is pure and deterministic given the same inputs.

use serde::{Deserialize, Serialize};

/// Snapshot of player state exposed to policies and reports.
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq)]
pub struct PlayerState {
    /// Buffered video in seconds.
    pub buffer_s: f64,
    /// Playback clock in seconds.
    pub playback_time_s: f64,
    /// Cumulative rebuffering time in seconds.
    pub rebuffer_s: f64,
    /// Total bytes downloaded.
    pub total_bytes: u64,
    /// Startup delay in seconds (rebuffer before first frame).
    pub startup_s: f64,
}

/// Deterministic player model.
///
/// `step(download_s, duration_s, bytes)` simulates downloading one chunk
/// (draining the buffer during download, rebuffering if it runs dry) and then
/// adding the chunk's duration to the buffer.
#[derive(Debug, Clone)]
pub struct Player {
    state: PlayerState,
    started: bool,
}

impl Default for Player {
    fn default() -> Self {
        Self::new()
    }
}

impl Player {
    pub fn new() -> Self {
        Self {
            state: PlayerState::default(),
            started: false,
        }
    }

    pub fn state(&self) -> PlayerState {
        self.state
    }

    pub fn buffer_s(&self) -> f64 {
        self.state.buffer_s
    }

    pub fn playback_time_s(&self) -> f64 {
        self.state.playback_time_s
    }

    pub fn rebuffer_s(&self) -> f64 {
        self.state.rebuffer_s
    }

    pub fn total_bytes(&self) -> u64 {
        self.state.total_bytes
    }

    /// Simulate one segment: download `bytes` at `download_s` seconds, then
    /// buffer `duration_s` seconds of video. Returns rebuffer added this step.
    pub fn step(&mut self, download_s: f64, duration_s: f64, bytes: u64) -> f64 {
        // During the download the buffer drains at 1x speed.
        let drain = download_s;
        let mut rebuffer_added = 0.0;
        if self.state.buffer_s < drain {
            rebuffer_added = drain - self.state.buffer_s;
            self.state.buffer_s = 0.0;
        } else {
            self.state.buffer_s -= drain;
        }

        if !self.started {
            // Startup delay = time before the first chunk is buffered.
            self.state.startup_s = rebuffer_added;
            self.started = true;
        }

        self.state.rebuffer_s += rebuffer_added;
        self.state.buffer_s += duration_s;
        self.state.playback_time_s += duration_s;
        self.state.total_bytes += bytes;
        rebuffer_added
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn step_buffers_and_plays() {
        let mut p = Player::new();
        // 1 MB chunk at 8 Mbps = 1s download; 4s duration chunk.
        let rb = p.step(1.0, 4.0, 1_000_000);
        assert_eq!(rb, 1.0); // startup: empty buffer → 1s rebuffer
        assert!((p.state().buffer_s - 4.0).abs() < 1e-12);
        assert_eq!(p.state().startup_s, 1.0);
        assert_eq!(p.state().total_bytes, 1_000_000);
    }

    #[test]
    fn rebuffer_when_download_exceeds_buffer() {
        let mut p = Player::new();
        p.step(1.0, 4.0, 1_000_000); // buffer now 4s
        // 3s download > 4s buffer? no. Use 5s download.
        let rb = p.step(5.0, 4.0, 1_000_000);
        assert!((rb - 1.0).abs() < 1e-12); // 5-4 = 1s rebuffer
        assert!((p.state().buffer_s - 4.0).abs() < 1e-12); // 0 + 4
        assert!((p.state().rebuffer_s - 2.0).abs() < 1e-12);
    }

    #[test]
    fn no_rebuffer_when_buffer_covers_download() {
        let mut p = Player::new();
        p.step(1.0, 4.0, 1_000_000); // buffer 4s, startup counted once
        let rb = p.step(1.0, 4.0, 1_000_000); // buffer covers download
        assert_eq!(rb, 0.0);
        assert!((p.state().buffer_s - 7.0).abs() < 1e-12); // 4 - 1 + 4 = 7
    }
}
