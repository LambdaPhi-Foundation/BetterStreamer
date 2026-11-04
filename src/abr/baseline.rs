//! Conventional throughput/buffer ABR baseline (PIPELINE.md Stage 5 / SUPER.md §11-P5).
//!
//! Combines an EWMA + last-k harmonic-mean throughput estimator with a BOLA-lite
//! buffer safety rule:
//!   Rung = min(Rung_throughput, Rung_buffer)
//! Buffer rule: b(t) < 2s → rung 0; 2s ≤ b(t) < 5s → cap rung 2; b(t) ≥ 5s → unrestricted.
//!
//! Stateful across segments: each `select` observes the current throughput
//! estimate before deciding.

use std::collections::VecDeque;

use super::{AbrPolicy, PlayerCtx, RepresentationId};
use crate::media::Segment;

/// EWMA + last-k harmonic mean throughput estimator.
///
/// Maintains a sliding window of the last `k` throughput samples (bps) and an
/// exponentially weighted moving average. The reported estimate is the harmonic
/// mean of the window (robust to spikes), warmed up by the EWMA.
#[derive(Debug, Clone)]
pub struct ThroughputEstimator {
    /// EWMA smoothing factor in (0,1].
    alpha: f64,
    /// Sliding window size.
    k: usize,
    history: VecDeque<f64>,
    ewma: f64,
    initialized: bool,
}

impl Default for ThroughputEstimator {
    fn default() -> Self {
        Self {
            alpha: 0.3,
            k: 8,
            history: VecDeque::with_capacity(8),
            ewma: 0.0,
            initialized: false,
        }
    }
}

impl ThroughputEstimator {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record one throughput sample (bps) and update internal state.
    pub fn observe(&mut self, bps: f64) {
        if !self.initialized {
            self.ewma = bps.max(0.0);
            self.initialized = true;
        } else {
            self.ewma = self.alpha * bps.max(0.0) + (1.0 - self.alpha) * self.ewma;
        }
        self.history.push_back(bps.max(0.0));
        if self.history.len() > self.k {
            self.history.pop_front();
        }
    }

    /// EWMA estimate in bps (0.0 until first observation).
    pub fn ewma(&self) -> f64 {
        self.ewma
    }

    /// Combined estimate in bps: harmonic mean of the window, falling back to
    /// EWMA, then to 0.0 when nothing has been observed.
    pub fn estimate_bps(&self) -> f64 {
        if self.history.is_empty() {
            return 0.0;
        }
        let mut sum_inv = 0.0f64;
        let mut valid = 0;
        for &x in &self.history {
            if x > 0.0 {
                sum_inv += 1.0 / x;
                valid += 1;
            }
        }
        if valid > 0 && sum_inv > 0.0 {
            return valid as f64 / sum_inv;
        }
        self.ewma
    }
}

/// BOLA-lite buffer safety cap.
///
/// Returns `None` (unrestricted) when the buffer is comfortable, otherwise the
/// maximum allowed rung index.
pub fn buffer_rung_cap(buffer_s: f64) -> Option<usize> {
    if buffer_s < 2.0 {
        Some(0) // critical: force lowest rung to prevent rebuffering
    } else if buffer_s < 5.0 {
        Some(2) // depleted: cap at 720p
    } else {
        None // comfortable: unrestricted
    }
}

/// Conventional ABR policy: `min(throughput_choice, buffer_choice)`.
#[derive(Debug, Clone)]
pub struct BaselineAbr {
    estimator: ThroughputEstimator,
    /// Fraction of estimated throughput considered safe to spend.
    safety_margin: f64,
}

impl Default for BaselineAbr {
    fn default() -> Self {
        Self {
            estimator: ThroughputEstimator::new(),
            safety_margin: 0.85,
        }
    }
}

impl BaselineAbr {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn with_safety_margin(mut self, margin: f64) -> Self {
        self.safety_margin = margin.clamp(0.0, 1.0);
        self
    }

    /// Highest rung whose bitrate fits within `estimate * safety_margin`.
    fn throughput_rung(&self, estimate_bps: f64, segment: &Segment) -> RepresentationId {
        if estimate_bps <= 0.0 || segment.representations.is_empty() {
            return 0;
        }
        let limit = estimate_bps * self.safety_margin;
        let n = segment.representations.len();
        (0..n)
            .rev()
            .find(|&r| segment.representations[r].bitrate_bps as f64 <= limit)
            .unwrap_or(0)
    }
}

impl AbrPolicy for BaselineAbr {
    fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId {
        let n = segment.representations.len();
        if n == 0 {
            return 0;
        }

        if ctx.estimated_throughput_bps > 0.0 {
            self.estimator.observe(ctx.estimated_throughput_bps);
        }
        let estimate = self.estimator.estimate_bps();

        let thr_rung = self.throughput_rung(estimate, segment);

        match buffer_rung_cap(ctx.buffer_s) {
            Some(cap) => thr_rung.min(cap.min(n - 1)),
            None => thr_rung,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seg(bitrates: &[u64]) -> Segment {
        let representations: Vec<crate::media::Representation> = bitrates
            .iter()
            .enumerate()
            .map(|(i, &b)| crate::media::Representation {
                id: i,
                width: 640,
                height: 360,
                bitrate_bps: b,
            })
            .collect();
        Segment {
            id: 0,
            duration_s: 4.0,
            features: crate::media::SegmentFeatures::default(),
            representations,
        }
    }

    #[test]
    fn estimator_harmonic_mean() {
        let mut e = ThroughputEstimator::new();
        e.observe(4_000_000.0);
        e.observe(4_000_000.0);
        assert!((e.estimate_bps() - 4_000_000.0).abs() < 1e-6);
    }

    #[test]
    fn estimator_robust_to_spike() {
        let mut e = ThroughputEstimator::new();
        for _ in 0..7 {
            e.observe(4_000_000.0);
        }
        e.observe(40_000_000.0); // spike
        let est = e.estimate_bps();
        assert!(
            est < 4_000_000.0 * 2.0,
            "harmonic mean should damp the spike: {est}"
        );
        assert!(est > 1_000_000.0);
    }

    #[test]
    fn estimator_empty_is_zero() {
        assert_eq!(ThroughputEstimator::new().estimate_bps(), 0.0);
    }

    #[test]
    fn buffer_cap_critical_forces_rung0() {
        assert_eq!(buffer_rung_cap(1.0), Some(0));
        assert_eq!(buffer_rung_cap(1.99), Some(0));
    }

    #[test]
    fn buffer_cap_depleted_caps_at_rung2() {
        assert_eq!(buffer_rung_cap(2.0), Some(2));
        assert_eq!(buffer_rung_cap(4.99), Some(2));
    }

    #[test]
    fn buffer_cap_comfortable_unrestricted() {
        assert_eq!(buffer_rung_cap(5.0), None);
        assert_eq!(buffer_rung_cap(30.0), None);
    }

    #[test]
    fn select_low_buffer_forces_rung0() {
        let mut p = BaselineAbr::new();
        let segment = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000]);
        let ctx = PlayerCtx {
            buffer_s: 1.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 0);
    }

    #[test]
    fn select_depleted_buffer_caps_at_rung2() {
        let mut p = BaselineAbr::new();
        let segment = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000]);
        let ctx = PlayerCtx {
            buffer_s: 3.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 2);
    }

    #[test]
    fn select_throughput_limits_rung() {
        let mut p = BaselineAbr::new();
        let segment = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000]);
        // 2 Mbps estimate * 0.85 = 1.7 Mbps → highest rung ≤1.7M is rung 2 (1.5M).
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 2_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 2);
    }

    #[test]
    fn select_zero_throughput_is_rung0() {
        let mut p = BaselineAbr::new();
        let segment = seg(&[400_000, 800_000]);
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 0.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 0);
    }

    #[test]
    fn select_stateful_estimate_changes() {
        let mut p = BaselineAbr::new();
        let segment = seg(&[400_000, 8_000_000]);
        let high_ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&high_ctx, &segment), 1);
        let low_ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 100_000.0,
            segment_index: 1,
        };
        assert_eq!(p.select(&low_ctx, &segment), 0);
    }

    #[test]
    fn select_empty_representations_is_zero() {
        let mut p = BaselineAbr::new();
        let segment = Segment {
            id: 0,
            duration_s: 4.0,
            features: crate::media::SegmentFeatures::default(),
            representations: vec![],
        };
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 0);
    }
}
