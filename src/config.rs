//! Shared deterministic simulation configuration.
//!
//! Phase 0: every stochastic or environment-dependent choice must derive from
//! [`SimulatorConfig`], so reruns with the same config are byte-identical.
//! Later phases read ladder / weights / buffer limits from here.

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

/// Top-level deterministic configuration for a simulation run.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SimulatorConfig {
    /// RNG seed for any jitter / synthetic generation.
    pub seed: u64,
    /// Segment (chunk) duration in seconds. Proposed default: 4.0.
    pub segment_duration_s: f64,
    /// Bitrate ladder in bps, ascending. E.g. [400k, 800k, 1500k, 3000k, 6000k].
    pub ladder_bps: Vec<u64>,
    /// Weight for motion in `priority = w_m*motion + w_c*complexity`.
    pub weight_motion: f64,
    /// Weight for complexity in priority score.
    pub weight_complexity: f64,
    /// Player buffer capacity in seconds.
    pub buffer_capacity_s: f64,
}

impl Default for SimulatorConfig {
    fn default() -> Self {
        Self {
            seed: 42,
            segment_duration_s: 4.0,
            ladder_bps: default_ladder(),
            weight_motion: 0.5,
            weight_complexity: 0.5,
            buffer_capacity_s: 30.0,
        }
    }
}

/// Default 5-rung ladder proposed in SUPER.md.
pub fn default_ladder() -> Vec<u64> {
    vec![400_000, 800_000, 1_500_000, 3_000_000, 6_000_000]
}

impl SimulatorConfig {
    /// Validate invariants; called by simulator and CLI before a run.
    pub fn validate(&self) -> Result<()> {
        if self.segment_duration_s <= 0.0 {
            return Err(Error::InvalidConfig(
                "segment_duration_s must be > 0".to_string(),
            ));
        }
        if self.ladder_bps.is_empty() {
            return Err(Error::InvalidConfig(
                "ladder_bps must not be empty".to_string(),
            ));
        }
        if !self.ladder_bps.windows(2).all(|w| w[0] < w[1]) {
            return Err(Error::InvalidConfig(
                "ladder_bps must be strictly ascending".to_string(),
            ));
        }
        if !(0.0..=1.0).contains(&self.weight_motion)
            || !(0.0..=1.0).contains(&self.weight_complexity)
        {
            return Err(Error::InvalidConfig("weights must be in [0,1]".to_string()));
        }
        if (self.weight_motion + self.weight_complexity - 1.0).abs() > 1e-9 {
            return Err(Error::InvalidConfig("weights must sum to 1.0".to_string()));
        }
        if self.buffer_capacity_s <= 0.0 {
            return Err(Error::InvalidConfig(
                "buffer_capacity_s must be > 0".to_string(),
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_validates() {
        SimulatorConfig::default().validate().unwrap();
    }

    #[test]
    fn rejects_empty_ladder() {
        let mut c = SimulatorConfig::default();
        c.ladder_bps.clear();
        assert!(c.validate().is_err());
    }

    #[test]
    fn rejects_unsorted_ladder() {
        let c = SimulatorConfig {
            ladder_bps: vec![800_000, 400_000],
            ..SimulatorConfig::default()
        };
        assert!(c.validate().is_err());
    }

    #[test]
    fn rejects_bad_weights() {
        let c = SimulatorConfig {
            weight_motion: 0.8,
            weight_complexity: 0.8,
            ..SimulatorConfig::default()
        };
        assert!(c.validate().is_err());
    }

    #[test]
    fn json_round_trip() {
        let c = SimulatorConfig::default();
        let s = serde_json::to_string(&c).unwrap();
        let back: SimulatorConfig = serde_json::from_str(&s).unwrap();
        assert_eq!(c, back);
    }
}
