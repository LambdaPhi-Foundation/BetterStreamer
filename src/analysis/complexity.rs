//! Visual-complexity analysis: spatial detail per chunk.
//!
//! Implements PIPELINE.md §3.2: spatial energy (Laplacian variance / DCT
//! energy proxy) averaged over the chunk, normalized to [0,1]. Mirrors ML1's
//! `extract_features.py` reference (`norm_complexity = min(1.0,
//! raw_complexity / 1400.0)`).
//!
//! `spatial_energy` holds per-frame spatial-energy samples computed by the
//! feature extractor sidecar.
//!
//! Phase 2: pure, deterministic, no I/O. Signature `&[f64] -> f64` is frozen.

/// Denominator used to normalize raw spatial energy into [0,1].
///
/// Matches the ML1 Python reference: cartoon / blurry backgrounds score ~0.12;
/// dense code slides or forest scenes score ~0.85.
const LAPLACIAN_NORM_DENOM: f64 = 1400.0;

/// Normalized complexity score for a chunk, clamped to [0,1].
///
/// Returns 0.0 for empty input. Raw mean of the spatial-energy samples is
/// divided by [`LAPLACIAN_NORM_DENOM`] and clamped.
pub fn complexity_score(spatial_energy: &[f64]) -> f64 {
    if spatial_energy.is_empty() {
        return 0.0;
    }
    let mean = spatial_energy.iter().sum::<f64>() / spatial_energy.len() as f64;
    (mean / LAPLACIAN_NORM_DENOM).clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_is_zero() {
        assert_eq!(complexity_score(&[]), 0.0);
    }

    #[test]
    fn clamps_to_unit_range() {
        assert!((complexity_score(&[5.0]) - (5.0 / LAPLACIAN_NORM_DENOM)).abs() < 1e-12);
        assert_eq!(complexity_score(&[LAPLACIAN_NORM_DENOM * 2.0]), 1.0);
    }

    #[test]
    fn matches_normalization_denominator() {
        assert!((complexity_score(&[LAPLACIAN_NORM_DENOM]) - 1.0).abs() < 1e-12);
        assert!((complexity_score(&[LAPLACIAN_NORM_DENOM / 2.0]) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn monotonic_in_spatial_energy() {
        let low = complexity_score(&[100.0, 100.0]);
        let high = complexity_score(&[900.0, 900.0]);
        assert!(low < high);
    }
}
