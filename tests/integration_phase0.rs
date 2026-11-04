//! Phase 0 integration: determinism harness.
//!
//! Locks: default config validates + JSON round-trips through the fixture,
//! synthetic video is N segments x M rungs, fixture trace parses, stub
//! simulator report serializes.

use better_streamer::{
    SimulatorConfig, media::Video, network::NetworkTrace, simulation::Simulator,
};
use std::path::PathBuf;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join(name)
}

#[test]
fn default_config_fixture_validates() {
    let text = std::fs::read_to_string(fixture("default-config.json")).unwrap();
    let cfg: SimulatorConfig = serde_json::from_str(&text).unwrap();
    assert_eq!(cfg, SimulatorConfig::default());
    cfg.validate().unwrap();
}

#[test]
fn synthetic_video_is_n_by_m() {
    let cfg = SimulatorConfig::default();
    let video = Video::synthetic("mixed", 8, cfg.segment_duration_s, &cfg.ladder_bps).unwrap();
    assert_eq!(video.len(), 8);
    assert_eq!(video.segments.len(), 8);
    for s in &video.segments {
        assert_eq!(s.representations.len(), cfg.ladder_bps.len());
    }
}

#[test]
fn fixture_trace_parses() {
    let trace = NetworkTrace::from_csv_file("min", &fixture("min-trace.csv")).unwrap();
    assert_eq!(trace.samples.len(), 3);
}

#[test]
fn stub_report_json_round_trip() {
    let r = Simulator::run_stub("baseline", "mixed", "stable-high");
    let s = serde_json::to_string(&r).unwrap();
    let back: better_streamer::simulation::SimulationReport = serde_json::from_str(&s).unwrap();
    assert_eq!(r, back);
}
