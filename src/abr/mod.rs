//! ABR policies: shared trait + baseline / perceptual / allocator.
//!
//! Phase 0: stable `AbrPolicy` contract so Phases 4–5 plug in without refactors.

pub mod allocator;
pub mod baseline;
pub mod perceptual;

use crate::media::Segment;

/// Snapshot of player state handed to a policy at decision time.
#[derive(Debug, Clone, Copy)]
pub struct PlayerCtx {
    /// Current buffer occupancy in seconds.
    pub buffer_s: f64,
    /// Estimated throughput in bps (from estimator; 0 = unknown).
    pub estimated_throughput_bps: f64,
    /// Index of the segment being decided.
    pub segment_index: usize,
}

/// Policy decision: which representation id to download.
pub type RepresentationId = usize;

/// Every ABR policy (baseline + content-aware + future ML) implements this.
pub trait AbrPolicy {
    /// Select a representation for `segment` given player context.
    fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId;
}
