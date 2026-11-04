//! Motion analysis: temporal change per chunk.
//!
//! Implements PIPELINE.md §3.1: Mean Squared Frame Difference (MSFD) averaged
//! over the chunk, normalized to [0,1]. Mirrors ML1's `extract_features.py`
//! reference (`norm_motion = min(1.0, raw_motion / 450.0)`).
//!
//! `frame_diffs` holds per-frame squared-difference samples (one per adjacent
//! frame pair), already computed by the feature extractor sidecar.
//!
//! Phase 2: pure, deterministic, no I/O. Signature `&[f64] -> f64` is frozen.

/// Denominator used to normalize raw MSFD into [0,1].
///
/// Matches the ML1 Python reference: a static podcast interview scores ~0.04;
/// soccer / auto-racing scores ~0.88.
const MSFD_NORM_DENOM: f64 = 450.0;

/// Normalized motion score for a chunk, clamped to [0,1].
///
/// Returns 0.0 for empty input. Raw mean of the squared frame-difference
/// samples is divided by [`MSFD_NORM_DENOM`] and clamped.
pub fn motion_score(frame_diffs: &[f64]) -> f64 {
    if frame_diffs.is_empty() {
        return 0.0;
    }
    let mean = frame_diffs.iter().sum::<f64>() / frame_diffs.len() as f64;
    (mean / MSFD_NORM_DENOM).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_is_zero() {
        assert_eq!(motion_score(&[]), 0.0);
    }

    #[test]
    fn clamps_to_unit_range() {
        assert_eq!(
            motion_score(&[2.0, 3.0]),
            (5.0 / 2.0 / MSFD_NORM_DENOM).clamp(0.0, 1.0)
        );
        assert_eq!(motion_score(&[-1.0]), 0.0);
    }

    #[test]
    fn matches_normalization_denominator() {
        assert!((motion_score(&[MSFD_NORM_DENOM]) - 1.0).abs() < 1e-12);
        assert!((motion_score(&[MSFD_NORM_DENOM * 2.0]) - 1.0).abs() < 1e-12);
        assert!((motion_score(&[MSFD_NORM_DENOM / 2.0]) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn monotonic_in_mean_diff() {
        let low = motion_score(&[100.0, 100.0]);
        let high = motion_score(&[400.0, 400.0]);
        assert!(low < high);
    }
}
