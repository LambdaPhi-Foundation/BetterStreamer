//! Priority engine: motion + complexity -> [0,1] score + Low/Medium/High bucket.
//!
//! Word-doc §5.2: `Priority(c) = clamp(w_m·Motion(c) + w_c·Complexity(c), 0, 1)`,
//! bucketed Low 0.00–0.33 / Medium 0.34–0.66 / High 0.67–1.00.
//!
//! Phase 3: weights come from [`crate::config::SimulatorConfig`]. Formula and
//! bucket thresholds are frozen.

use crate::media::SegmentFeatures;

/// Priority bucket for bitrate allocation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Priority {
    /// 0.00–0.33 → lower bitrate.
    Low,
    /// 0.34–0.66 → moderate bitrate.
    Medium,
    /// 0.67–1.00 → higher bitrate.
    High,
}

impl Priority {
    /// Bucket a normalized score.
    pub fn bucket(score: f64) -> Self {
        if score < 0.34 {
            Self::Low
        } else if score < 0.67 {
            Self::Medium
        } else {
            Self::High
        }
    }
}

/// Deterministic weighted priority score, clamped to [0,1].
pub fn priority_score(motion: f64, complexity: f64, w_motion: f64, w_complexity: f64) -> f64 {
    (w_motion * motion + w_complexity * complexity).clamp(0.0, 1.0)
}

/// Build a [`SegmentFeatures`] from motion and complexity using the configured
/// weights. Used to fill chunk features before allocation.
pub fn segment_features(
    motion: f64,
    complexity: f64,
    w_motion: f64,
    w_complexity: f64,
) -> SegmentFeatures {
    let priority = priority_score(motion, complexity, w_motion, w_complexity);
    SegmentFeatures {
        motion,
        complexity,
        priority,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weighted_sum() {
        assert!((priority_score(1.0, 0.0, 0.5, 0.5) - 0.5).abs() < 1e-12);
    }

    #[test]
    fn bucket_boundaries() {
        assert_eq!(Priority::bucket(0.0), Priority::Low);
        assert_eq!(Priority::bucket(0.33), Priority::Low);
        assert_eq!(Priority::bucket(0.34), Priority::Medium);
        assert_eq!(Priority::bucket(0.66), Priority::Medium);
        assert_eq!(Priority::bucket(0.67), Priority::High);
        assert_eq!(Priority::bucket(1.0), Priority::High);
    }

    #[test]
    fn priority_clamps_to_unit_range() {
        assert_eq!(priority_score(1.0, 1.0, 1.0, 1.0), 1.0);
        assert_eq!(priority_score(-1.0, -1.0, 0.5, 0.5), 0.0);
    }

    #[test]
    fn segment_features_matches_score() {
        let f = segment_features(0.8, 0.6, 0.6, 0.4);
        assert!((f.motion - 0.8).abs() < 1e-12);
        assert!((f.complexity - 0.6).abs() < 1e-12);
        assert!((f.priority - 0.72).abs() < 1e-12);
    }

    #[test]
    fn static_but_complex_not_starved() {
        // A static lecture slide: near-zero motion, high complexity.
        let f = segment_features(0.05, 0.9, 0.6, 0.4);
        let expected = 0.6 * 0.05 + 0.4 * 0.9;
        assert!((f.priority - expected).abs() < 1e-12);
        assert_eq!(Priority::bucket(f.priority), Priority::Medium);
    }

    #[test]
    fn weight_sweep_changes_bucket() {
        // High complexity, moderate motion: bucket depends on weights.
        let high_w_c = segment_features(0.2, 0.9, 0.3, 0.7);
        assert_eq!(Priority::bucket(high_w_c.priority), Priority::High);
        let low_w_c = segment_features(0.2, 0.9, 0.9, 0.1);
        assert_eq!(Priority::bucket(low_w_c.priority), Priority::Low);
    }
}
