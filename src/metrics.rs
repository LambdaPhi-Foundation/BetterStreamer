//! Quality / efficiency metrics stub (full: Phase 7).
//!
//! Word-doc §9.3: VMAF primary, SSIM supporting, Quality/MB primary-efficiency,
//! rebuffer + startup + total bytes secondary.

/// Placeholder mean quality until the Phase 7 evaluator lands.
pub fn mean_quality_placeholder(scores: &[f64]) -> f64 {
    if scores.is_empty() {
        return 0.0;
    }
    scores.iter().sum::<f64>() / scores.len() as f64
}

/// Placeholder quality-per-MB until real VMAF tables land.
///
/// Returns 0 when no bytes were delivered (avoids divide-by-zero).
pub fn quality_per_mb_placeholder(mean_quality: f64, total_bytes: u64) -> f64 {
    if total_bytes == 0 {
        return 0.0;
    }
    let mb = total_bytes as f64 / 1_000_000.0;
    mean_quality / mb
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mean_of_empty_is_zero() {
        assert_eq!(mean_quality_placeholder(&[]), 0.0);
    }

    #[test]
    fn q_per_mb_guards_zero_bytes() {
        assert_eq!(quality_per_mb_placeholder(90.0, 0), 0.0);
    }
}
