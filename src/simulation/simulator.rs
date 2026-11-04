//! Deterministic simulation event loop (SUPER.md §11-P6).
//!
//! Runs one ABR policy over one video × one network trace, producing a
//! comparable `SimulationReport`. Fully deterministic given the same config.

use serde::{Deserialize, Serialize};

use crate::abr::{AbrPolicy, PlayerCtx, baseline::BaselineAbr, perceptual::PerceptualAbr};
use crate::config::SimulatorConfig;
use crate::media::Video;
use crate::network::NetworkTrace;
use crate::simulation::player::Player;

/// Supported simulation policies.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SimPolicy {
    Baseline,
    Perceptual,
}

impl SimPolicy {
    pub fn name(&self) -> &'static str {
        match self {
            SimPolicy::Baseline => "baseline",
            SimPolicy::Perceptual => "perceptual",
        }
    }
}

/// Comparable output of one policy × video × trace run.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SimulationReport {
    /// Policy name ("baseline" / "perceptual").
    pub policy: String,
    /// Video catalog name.
    pub video: String,
    /// Trace profile name.
    pub trace: String,
    /// Per-segment chosen representation ids.
    pub chosen: Vec<usize>,
    /// Total bytes downloaded.
    pub total_bytes: u64,
    /// Rebuffer seconds.
    pub rebuffer_s: f64,
}

/// Deterministic simulator.
#[derive(Debug)]
pub struct Simulator;

impl Simulator {
    /// Stub run kept for Phase 0 compatibility.
    pub fn run_stub(policy: &str, video: &str, trace: &str) -> SimulationReport {
        SimulationReport {
            policy: policy.to_string(),
            video: video.to_string(),
            trace: trace.to_string(),
            chosen: Vec::new(),
            total_bytes: 0,
            rebuffer_s: 0.0,
        }
    }

    /// Full deterministic event loop: one policy over one video × trace.
    ///
    /// For each segment: sample bandwidth from the trace, ask the policy for a
    /// rung, simulate the download through the player, and account for
    /// rebuffering. `config` reserves the seed / jitter hook for later phases.
    pub fn run(
        policy: SimPolicy,
        video: &Video,
        trace: &NetworkTrace,
        config: &SimulatorConfig,
    ) -> SimulationReport {
        let _ = config; // reserved for seeded jitter in later phases
        let mut player = Player::new();
        let mut chosen = Vec::with_capacity(video.len());
        let mut baseline = BaselineAbr::new();
        let mut perceptual = PerceptualAbr::new();

        for (i, seg) in video.segments.iter().enumerate() {
            let bw_bps = trace.bandwidth_at(player.playback_time_s());
            let ctx = PlayerCtx {
                buffer_s: player.buffer_s(),
                estimated_throughput_bps: bw_bps,
                segment_index: i,
            };

            let rung: usize = match policy {
                SimPolicy::Baseline => baseline.select(&ctx, seg),
                SimPolicy::Perceptual => perceptual.select(&ctx, seg),
            };
            chosen.push(rung);

            let bytes = seg.bytes_at(rung).unwrap_or(0);
            let bps = bw_bps.max(1.0);
            let download_s = bytes as f64 / (bps / 8.0);
            player.step(download_s, seg.duration_s, bytes);
        }

        let state = player.state();
        SimulationReport {
            policy: policy.name().to_string(),
            video: video.name.clone(),
            trace: trace.name.clone(),
            chosen,
            total_bytes: state.total_bytes,
            rebuffer_s: state.rebuffer_s,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_ladder;
    use crate::media::Video;

    fn make_video() -> Video {
        Video::synthetic("mixed", 6, 4.0, &default_ladder()).unwrap()
    }

    fn make_trace() -> NetworkTrace {
        NetworkTrace::constant("stable-high", 8.0, 40.0, 4.0).unwrap()
    }

    #[test]
    fn run_baseline_produces_chosen_and_bytes() {
        let v = make_video();
        let t = make_trace();
        let cfg = SimulatorConfig::default();
        let r = Simulator::run(SimPolicy::Baseline, &v, &t, &cfg);
        assert_eq!(r.chosen.len(), v.len());
        assert!(r.total_bytes > 0);
        assert_eq!(r.policy, "baseline");
    }

    #[test]
    fn run_perceptual_produces_chosen_and_bytes() {
        let v = make_video();
        let t = make_trace();
        let cfg = SimulatorConfig::default();
        let r = Simulator::run(SimPolicy::Perceptual, &v, &t, &cfg);
        assert_eq!(r.chosen.len(), v.len());
        assert!(r.total_bytes > 0);
        assert_eq!(r.policy, "perceptual");
    }

    #[test]
    fn run_respects_budget_ish_no_rebuffer_on_stable_trace() {
        let v = make_video();
        let t = make_trace();
        let cfg = SimulatorConfig::default();
        for pol in [SimPolicy::Baseline, SimPolicy::Perceptual] {
            let r = Simulator::run(pol, &v, &t, &cfg);
            assert!(r.total_bytes > 0);
            // stable 8 Mbps trace over 24 s of video should not rebuffer.
            assert!(
                r.rebuffer_s < 1.0,
                "{:?} rebuffered {:?}s",
                pol.name(),
                r.rebuffer_s
            );
        }
    }

    #[test]
    fn stub_and_run_share_schema() {
        let s = Simulator::run_stub("baseline", "mixed", "stable-high");
        let json = serde_json::to_string(&s).unwrap();
        let back: SimulationReport = serde_json::from_str(&json).unwrap();
        assert_eq!(s, back);
    }
}
