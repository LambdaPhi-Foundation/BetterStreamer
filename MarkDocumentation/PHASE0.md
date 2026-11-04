# PHASE0.md — Skeleton + Determinism Harness (Completed)

> Phase 0 of `MarkDocumentation/SUPER.md`. Layout is now frozen; Phases 1–8 fill
> algorithms without reorganizing imports.

## 1. Goal

Establish the Rust workspace so every later phase has a stable home:

- `src/main.rs` thin CLI, all logic in `better_streamer` lib (testable via `cargo test`).
- `SimulatorConfig` centralizes seed / segment duration / ladder / weights / buffer.
- Stub modules reserve every future path (`analysis::*`, `abr::*`, `network`,
  `simulation::*`, `metrics`) with compiling signatures + docs.
- `media/`, `traces/`, `tests/fixtures/` dirs + sample traces for the 4 §9.2 profiles.
- Gate: `cargo test` proves `Video` = N segments × M rungs; `clippy -D warnings`
  + `cargo fmt --check` clean; CLI emits a stub `SimulationReport` JSON.

## 2. Files Added / Changed

```text
Cargo.toml                    # lib+bin targets; pinned offline deps (see §6); csv deferred
src/lib.rs                    # crate root + re-exports (NEW)
src/main.rs                   # clap CLI: `run --policy --video --segments --trace --out` (REWRITTEN)
src/config.rs                 # SimulatorConfig + default_ladder + validation (NEW)
src/error.rs                  # thiserror Error::{InvalidConfig,Trace,Io,Json} (NEW)
src/media.rs                  # Representation/SegmentFeatures/Segment/Video + synthetic() (NEW)
src/analysis/mod.rs           # re-exports (NEW)
src/analysis/motion.rs        # motion_score() placeholder (NEW)
src/analysis/complexity.rs    # complexity_score() placeholder (NEW)
src/analysis/priority.rs      # priority_score() + Priority::{Low,Medium,High} (NEW)
src/abr/mod.rs                # AbrPolicy trait + PlayerCtx + RepresentationId (NEW)
src/abr/baseline.rs           # BaselineAbr stub: picks lowest rung (NEW)
src/abr/perceptual.rs         # PerceptualAbr stub: picks middle rung (NEW)
src/abr/allocator.rs          # allocate_equal() path reservation (NEW)
src/network.rs                # NetworkSample/Trace, std-only CSV, constant() (NEW)
src/simulation/mod.rs         # re-exports (NEW)
src/simulation/player.rs      # PlayerState{buffer_s} (NEW)
src/simulation/simulator.rs   # SimulationReport schema + run_stub() (NEW)
src/metrics.rs                # mean_quality + quality_per_mb placeholders (NEW)
tests/integration_phase0.rs   # harness integration tests (NEW)
media/.gitkeep                # keep empty media/ in git (NEW)
traces/*.csv                  # stable-high, moderate, sudden-degradation, highly-variable (NEW)
tests/fixtures/default-config.json  # == SimulatorConfig::default() (NEW)
tests/fixtures/min-trace.csv  # 3-sample minimal trace (NEW)
```

## 3. Key APIs (signatures frozen)

```rust
// config.rs
pub struct SimulatorConfig { seed: u64, segment_duration_s: f64, ladder_bps: Vec<u64>,
    weight_motion: f64, weight_complexity: f64, buffer_capacity_s: f64 }
impl SimulatorConfig { pub fn validate(&self) -> Result<()> }
pub fn default_ladder() -> Vec<u64> // [400k, 800k, 1500k, 3000k, 6000k]

// media.rs
impl Video { pub fn synthetic(name: &str, num_segments: usize, segment_duration_s: f64,
    ladder_bps: &[u64]) -> Result<Self> }
impl Segment { pub fn bytes_at(&self, representation_id: usize) -> Result<u64> }

// analysis
pub fn motion_score(frame_diffs: &[f64]) -> f64
pub fn complexity_score(spatial_energy: &[f64]) -> f64
pub fn priority_score(motion: f64, complexity: f64, w_m: f64, w_c: f64) -> f64
impl Priority { pub fn bucket(score: f64) -> Self } // <0.34 Low, <0.67 Med, else High

// abr
pub trait AbrPolicy { fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId; }

// network.rs
impl NetworkTrace {
    pub fn from_csv_str(name: &str, csv_text: &str) -> Result<Self>
    pub fn from_csv_file(name: &str, path: &Path) -> Result<Self>
    pub fn constant(name: &str, bandwidth_mbps: f64, duration_s: f64, step_s: f64) -> Result<Self>
}

// simulation
pub struct SimulationReport { policy: String, video: String, trace: String,
    chosen: Vec<usize>, total_bytes: u64, rebuffer_s: f64 }
```

CLI:

```text
betterstreamer run --policy baseline|perceptual --video mixed --segments 8
    [--trace traces/stable-high.csv] [--out -|results.json]
```

## 4. Algorithms (Phase 0 placeholders — real logic in noted phases)

- Motion/complexity: clamped mean of normalized samples; empty → 0.0 (Phase 2 real).
- Priority: `(w_m*motion + w_c*complexity).clamp(0,1)` + bucket thresholds (Phase 3 real).
- Baseline stub: lowest rung; Perceptual stub: middle rung (Phase 4–5 real).
- Allocator: path reserved only (Phase 4 real).
- Network: strict `time_s,bandwidth_mbps` header check, per-line `f64` parse,
  positivity + strictly-increasing-time validation (final CSV contract already).
- Metrics: mean + `mean/megabytes` with zero-bytes guard (Phase 7 real VMAF).

## 5. Tests Added

Unit (21): config validate/round-trip (5), media N×M/reject/bytes/round-trip (4),
motion/complexity clamp+empty (4), priority weight+buckets (2), network parse/reject/
constant (4), metrics empty/zero-guards (2).
Integration (`tests/integration_phase0.rs`, 4): default-config fixture == Default +
validates; synthetic 8×5; min-trace parses to 3 samples; stub report JSON round-trips.

## 6. Verification Log (exact)

```text
$ cargo test --offline
running 21 tests ... ok (lib) | 4 passed (integration) | 0 failed

$ cargo clippy --offline --all-targets -- -D warnings
Finished dev profile — 0 errors (1 incremental-cache hardlink notice, env-only)

$ cargo fmt --check
exit 0

$ cargo run --offline -- run --policy baseline --video mixed --segments 8 \
    --trace traces/stable-high.csv --out -
video 'mixed': 8 segments x 5 representations
trace 'custom': 9 samples
{ "policy": "baseline", "video": "mixed", "trace": "custom",
  "chosen": [], "total_bytes": 0, "rebuffer_s": 0.0 }
```

Toolchain: `rustc/cargo 1.96.0`. Deps resolve offline via local cache.

## 7. Deviations from SUPER.md (all intentional, API-compatible)

1. **`csv` crate deferred to Phase 6.** No network to crates.io in this environment
   and `csv` was absent from the cargo cache. `network.rs` implements an equivalent
   std-only parser with the identical `from_csv_str/file` signatures, so adopting
   `csv` later is a private-function change. `Cargo.toml` documents this.
2. **Dep versions pinned (`=`) to cache-available releases**
   (`anyhow 1.0.102, clap 4.6.6, serde 1.0.228, serde_json 1.0.149, thiserror 2.0.19`)
   for offline reproducibility. Unpin once registry access returns; no code impact.
3. **Phase 1 preview inside Phase 0:** minimal validated `media.rs` (not just a stub)
   because the Phase 0 gate itself requires the N×M construction test. Phase 1 still
   owns ladder presets, catalog kinds (§9.1), and richer validation.

## 8. Next-Phase Hooks

- Phase 1: extend `media.rs` (ladder presets, `Video::synthetic(kind)`, resolution
  mapping); keep `synthetic()` signature.
- Phase 2: replace bodies of `motion_score` / `complexity_score`; keep `&[f64] -> f64`.
- Phase 3: `priority_score` already final formula; add weight-sweep tests + feature fill.
- Phase 6: swap CSV internals for `csv` crate; add `Simulator::run()`; keep report schema.
