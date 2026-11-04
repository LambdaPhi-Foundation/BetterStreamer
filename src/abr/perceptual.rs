//! Content-aware ABR policy (PIPELINE.md Stage 4 / SUPER.md §11-P4–P5).
//!
//! Selects a rung per chunk using the chunk's priority score, the current
//! buffer, and estimated throughput. Mirrors the client-side plugin in
//! PIPELINE.md §9.3:
//!   effective_budget = bandwidth * (0.50 + 0.35 * priority)
//! Buffer safety override (BOLA-lite): b(t) < 2s → rung 0; 2s–5s → cap rung 2.

use super::{AbrPolicy, PlayerCtx, RepresentationId};
use crate::media::Segment;

/// Buffer below this forces the lowest rung (critical zone).
const BUFFER_CRITICAL_S: f64 = 2.0;
/// Buffer below this caps the allowed rung at 720p (rung 2).
const BUFFER_DEPLETED_S: f64 = 5.0;

/// Base share of bandwidth always spendable, even for lowest-priority chunks.
const BASE_SPEND_SHARE: f64 = 0.50;
/// Extra spend share per unit of priority (max total 0.85).
const PRIORITY_SPEND_SHARE: f64 = 0.35;

#[derive(Debug, Default, Clone)]
pub struct PerceptualAbr;

impl PerceptualAbr {
    pub fn new() -> Self {
        Self
    }
}

impl AbrPolicy for PerceptualAbr {
    fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId {
        let n = segment.representations.len();
        if n == 0 {
            return 0;
        }

        // Buffer safety override: critical zone forces the lowest rung.
        if ctx.buffer_s < BUFFER_CRITICAL_S {
            return 0;
        }

        let estimate = ctx.estimated_throughput_bps;
        if estimate <= 0.0 {
            return 0;
        }

        // Content-aware spending: complex/dynamic chunks may use more bandwidth.
        let priority = segment.features.priority.clamp(0.0, 1.0);
        let multiplier = BASE_SPEND_SHARE + PRIORITY_SPEND_SHARE * priority;
        let effective_budget_bps = estimate * multiplier;

        // Buffer cap: depleted zone limits to rung 2 (720p).
        let cap = if ctx.buffer_s < BUFFER_DEPLETED_S {
            2usize
        } else {
            n - 1
        };
        let cap = cap.min(n - 1);

        for r in (0..=cap).rev() {
            if segment.representations[r].bitrate_bps as f64 <= effective_budget_bps {
                return r;
            }
        }
        0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seg(bitrates: &[u64], priority: f64) -> Segment {
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
            features: crate::media::SegmentFeatures {
                motion: 0.0,
                complexity: 0.0,
                priority,
            },
            representations,
        }
    }

    fn ladder() -> Segment {
        seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000], 0.5)
    }

    #[test]
    fn critical_buffer_forces_rung0() {
        let mut p = PerceptualAbr::new();
        let ctx = PlayerCtx {
            buffer_s: 1.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &ladder()), 0);
    }

    #[test]
    fn high_priority_spends_more_than_low() {
        let low = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000], 0.0);
        let high = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000], 1.0);
        let mut pl = PerceptualAbr::new();
        let mut ph = PerceptualAbr::new();
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 2_000_000.0,
            segment_index: 0,
        };
        // low: 0.5*2M = 1M → rung 1 (800k); high: 0.85*2M = 1.7M → rung 2 (1.5M)
        assert_eq!(pl.select(&ctx, &low), 1);
        assert_eq!(ph.select(&ctx, &high), 2);
    }

    #[test]
    fn depleted_buffer_caps_at_rung2() {
        let mut p = PerceptualAbr::new();
        let seg_high = seg(&[400_000, 800_000, 1_500_000, 3_000_000, 6_000_000], 1.0);
        let ctx = PlayerCtx {
            buffer_s: 3.0,
            estimated_throughput_bps: 50_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &seg_high), 2);
    }

    #[test]
    fn zero_throughput_is_rung0() {
        let mut p = PerceptualAbr::new();
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 0.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &ladder()), 0);
    }

    #[test]
    fn empty_representations_is_zero() {
        let mut p = PerceptualAbr::new();
        let segment = Segment {
            id: 0,
            duration_s: 4.0,
            features: crate::media::SegmentFeatures::default(),
            representations: vec![],
        };
        let ctx = PlayerCtx {
            buffer_s: 10.0,
            estimated_throughput_bps: 5_000_000.0,
            segment_index: 0,
        };
        assert_eq!(p.select(&ctx, &segment), 0);
    }
}
