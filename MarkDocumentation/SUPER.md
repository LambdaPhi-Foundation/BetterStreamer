# SUPER.md — Content-Aware Adaptive Bitrate Streaming in Rust (BetterStreamer)

> Master plan and build log index. Source of truth for *what we are building, why, and in what order*.
> Original requirements: `Content_Aware_ABR_Project_Document.docx` (C++ prototype proposal).
> This repo re-targets the identical system to **Rust** (`BetterStreamer`, edition 2024).
> All markdown docs live in `MarkDocumentation/`. Per-phase build evidence lives in `PHASE0.md … PHASE8.md`.

---

## 1. What We Are Trying To Build

### 1.1 One-sentence objective

Build a **Rust content-aware ABR simulator** that demonstrates whether allocating limited
bandwidth according to video-content perceptual importance achieves **better objective
perceptual quality per megabyte** than a conventional HLS/DASH-style baseline.

Minimum viable contribution (§13 of Word doc): **the content-aware bitrate allocator**.
AI / personalization / predictive networking are extensions, not prerequisites.

### 1.2 Formal view (from §14 of Word doc)

```text
priority = λc. f(motion(c), complexity(c))
allocate = λB. λC. argmax Σ quality(cᵣ, bitrateᵣ)  subject to Σ bitrateᵣ ≤ B
```

In plain terms: given a set of chunks and a finite bandwidth budget, select bitrate
levels that maximize total perceptual value delivered to the viewer.

First prototype priority (deterministic, §5.2):

```text
Priority(c) = w_m · Motion(c) + w_c · Complexity(c),  normalized to [0, 1]
  0.00–0.33 → Low    → lower bitrate
  0.34–0.66 → Medium → moderate bitrate
  0.67–1.00 → High   → higher bitrate
```

Allocator objective (§5.3):

```text
Maximize Σ Quality(chunkᵣ)  subject to  Σ Bits(chunkᵣ) ≤ Available Budget
```

A particularly useful future ML target (§6): predicted marginal gain `ΔVMAF / ΔMB`
— prioritize the chunk where the next unit of bandwidth yields the largest
perceptual improvement.

### 1.3 Research question (narrowed per §8 — do NOT overclaim)

> Can network-aware adaptive streaming improve perceptual quality per delivered byte
> by explicitly incorporating content-dependent perceptual importance into bitrate allocation?

We do NOT claim HLS/DASH are unaware of content or that ABR research does not exist.
Contribution = **a content-aware bandwidth-allocation policy evaluated against a
conventional ABR baseline under identical conditions**.

### 1.4 System pipeline (§3)

```text
Video → Chunking → Content Analysis → Priority Score → Bandwidth-Aware Allocation
      → Streaming (Network Simulator) → Quality Evaluation (VMAF/SSIM)
```

| Component (§3.1) | Purpose | Rust home (this repo) |
|---|---|---|
| Segment model | Represent chunks + quality representations | `src/media.rs` |
| Content analyzer | Motion + visual complexity per chunk | `src/analysis/` |
| Priority engine | Features → `0..1` score (weighted heuristic first) | `src/analysis/priority.rs` |
| Bitrate allocator | Distribute bandwidth budget (greedy / knapsack) | `src/abr/allocator.rs` |
| Network simulator | Replay stable / degraded traces | `src/network.rs` + `traces/*.csv` |
| Baseline ABR | Throughput + buffer policy (EWMA + BOLA-lite) | `src/abr/baseline.rs` |
| Proposed ABR | Content-aware policy | `src/abr/perceptual.rs` |
| Player + Simulator | Deterministic event loop, both policies reproducibly | `src/simulation/` |
| Quality evaluator | VMAF (primary), SSIM (support), Q/MB, rebuffer, startup | `src/metrics.rs` |
| CLI entry | Thin binary; all logic in lib for testability | `src/main.rs` + `src/lib.rs` |
| Shared config | Seed, segment duration, ladder, weights, paths | `src/config.rs` |
| Shared errors | Typed errors, no stringly failures | `src/error.rs` |

C++ → Rust mapping note: `Segment.hpp / Representation.hpp / Video.hpp` → `media.rs`
structs; `Motion.hpp / Complexity.hpp` → pure functions `&[f32] -> f64`; `ABR.hpp`
→ `trait AbrPolicy`; `NetworkTrace.hpp` → CSV-backed `NetworkTrace`; `Player.hpp /
Simulator.hpp` → deterministic simulator; `Metrics.hpp` → `metrics.rs`.

### 1.5 Baseline vs proposed (§4–§5)

Baseline (conventional): `throughput estimate + buffer state → representation selection`.
Models segmented HTTP ABR behaviour. No full HLS/DASH player required — simulate the
common abstraction (§4, §7).

Proposed: adds content features (§5.1: motion = temporal change; complexity = spatial
detail / texture / encoding difficulty; future: saliency, faces/text, scene type,
viewer preference) and spends extra bits where perceptual benefit is greatest.

### 1.6 HLS/DASH context (§7)

HLS and MPEG-DASH are segmented HTTP approaches with multiple representations and
client-side switching. The standards are NOT the research target. We simulate their
common segmented-ABR abstraction.

### 1.7 Role of AI (§6 — enhancement, not prerequisite)

Order: deterministic heuristic works FIRST so ML effect is measurable separately.
Later:

1. Learn `w_m, w_c` from content→quality data instead of fixed weights.
2. Predict marginal VMAF gain per candidate rung.
3. Predict near-future throughput for proactive decisions.
4. Model viewer preferences for personalization.

### 1.8 Evaluation contract (§9 — binding for all phases)

Same video set + same network traces for BOTH algorithms. No exceptions.

Test content (§9.1): talking-head/static, sports/dynamic, action/camera-motion,
text/lecture/news, mixed-complexity.

Network profiles (§9.2): stable-high, moderate, sudden-degradation, highly-variable.

Metrics (§9.3):

| Metric | Role | Goal |
|---|---|---|
| VMAF | Primary perceptual quality | Higher |
| SSIM | Supporting quality metric | Higher |
| Quality / MB | Primary efficiency metric | Higher |
| Rebuffering ratio | Secondary UX | Lower |
| Startup latency | Secondary UX | Lower |
| Total data delivered | Bandwidth consumption | Lower at equal quality |

Key risks (§12): motion-only misclassifies static-but-complex scenes; over-prioritizing
dynamic chunks wastes bits; Q/MB misleading if conditions differ; must use identical
clips/encodes/traces; report across multiple content types, not one favorable clip.

---

## 2. Repository Conventions (binding from Phase 0 on)

```text
BetterStreamer/
  src/
    main.rs            # thin CLI (clap), calls into lib
    lib.rs             # crate root, re-exports
    config.rs          # SimulatorConfig, RepresentationLadder presets
    error.rs           # thiserror typed errors
    media.rs           # Representation, SegmentFeatures, Segment, Video
    analysis/
      mod.rs           # re-exports + feature-vector types
      motion.rs        # motion(c) pure function
      complexity.rs    # complexity(c) pure function
      priority.rs      # priority score + Priority::{Low,Medium,High}
    abr/
      mod.rs           # AbrPolicy trait + PlayerCtx + shared types
      baseline.rs      # conventional policy
      perceptual.rs    # content-aware policy
      allocator.rs     # budget-constrained allocation (greedy/knapsack)
    network.rs         # NetworkTrace, CSV replay, built-in profiles
    simulation/
      mod.rs
      player.rs        # buffer / state machine
      simulator.rs     # deterministic run() -> SimulationReport
    metrics.rs         # quality + efficiency aggregation
  media/               # sample / generated video descriptors (not binaries)
  traces/              # network trace CSVs: time_s,bandwidth_mbps
  tests/
    fixtures/          # deterministic CSVs / JSON for tests
    integration_* .rs  # (from Phase 6) end-to-end determinism tests
  MarkDocumentation/
    SUPER.md           # this file
    PHASE0.md … PHASE8.md
  Cargo.toml
```

Rules:

- `src/main.rs` stays thin. All logic importable from library crate (`better_streamer`)
  so `cargo test` covers it.
- Core simulation (`media, analysis, abr, network, simulation`) prefers **no extra
  I/O deps**; I/O deps (`csv, serde_json`) live at boundaries (`config, network, metrics`).
- Every phase adds unit tests + updates its `PHASEX.md`. No phase is "done" without
  `cargo test`, `cargo clippy -- -D warnings`, `cargo fmt --check` green.
- Determinism: every stochastic choice takes `seed` from `SimulatorConfig`. Same
  seed + same inputs = byte-identical `SimulationReport`.
- Budgets are hard constraints: `total_bits <= budget` is a property test from Phase 4 on.
- Docs: `SUPER.md` = plan (this file, updated rarely). `PHASEX.md` = what was ACTUALLY
  built in phase X, with file list, API, tests, deviations, verification log.

Crates (phased in):

| Phase | New deps |
|---|---|
| 0 | `clap(derive), serde(+derive), serde_json, csv, thiserror` |
| 1–5 | none new (pure logic) — keeps core testable |
| 6 | `tracing` (optional, sim logging) |
| 7 | `image` (SSIM helper, optional) + external `ffmpeg+libvmaf` ingestion via CSV (no Rust VMAF reimpl) |
| 8 | `smartcore` or `linreg` (regression), later `burn`/`onnxruntime` if needed; `criterion` benches, `proptest` invariants |

---

## 3. Phase-by-Phase Roadmap

### Phase 0 — Skeleton + determinism harness [CURRENT]

Goal: fixed layout so Phases 1–8 never require reorganization.
Work: `lib.rs`, thin `main.rs` (`run --policy --trace --video --out`), `config.rs`
(`SimulatorConfig{seed, segment_duration_s, ladder, weights, buffer_capacity_s}`),
`error.rs`, stub modules with doc comments, `media/`, `traces/`, `tests/fixtures/`
dirs, sample trace CSVs, README-style crate docs.
Success: `cargo test` constructs `Video` with N segments × M rungs; clippy + fmt clean.
Doc: `PHASE0.md`.

### Phase 1 — Segment / representation model (§11-P1, §10.1)

Work: full `Representation{id,width,height,bitrate_bps}`, `SegmentFeatures`,
`Segment{id,duration_s,features,representations}`, `Video{segments}`, ladder presets
(e.g. 400k/800k/1500k/3000k/6000k), synthetic `Video::synthetic(kind, n)` for §9.1
categories, validation (non-empty ladder, sorted bitrates, positive durations).
Success: video representable as chunks × quality levels; `serde` round-trip.
Tests: construction, validation rejects, JSON round-trip, ladder ordering.

### Phase 2 — Motion + complexity analysis (§11-P2, §5.1)

Work: `motion::score(&[frame_diff]) -> f64`, `complexity::score(&[spatial_energy]) -> f64`,
both normalized `[0,1]`, pure + deterministic. Feature-vector abstraction so real
decoders (`ffmpeg-sidecar`, `image`, `opencv`) can plug in later without API break.
Success: each chunk gets a motion score (+ complexity proxy).
Tests: zeros→0, max→1, empty→error/0 contract, monotonicity.

### Phase 3 — Priority model (§11-P3, §5.2)

Work: `priority::score(motion, complexity, weights)`, clamp `[0,1]`,
`Priority::bucket() -> Low/Medium/High` per `0.00–0.33 / 0.34–0.66 / 0.67–1.00`.
Weights from config for sweeps. Explicit static-but-complex unit case (§12).
Success: continuous `0..1` priority + bucket mapping.
Tests: weighting, clamping, bucket boundaries, determinism.

### Phase 4 — Bandwidth allocator (§11-P4, §5.3, §14)

Work: (a) equal-quality baseline, (b) priority-weighted greedy by marginal gain
`ΔQuality/ΔBits` (quality = log-saturating `f(priority, bitrate)` until real VMAF
tables land), (c) offline DP-knapsack optimal as upper bound. Hard budget enforcement.
Success: allocation respects budget; high-priority gets higher rungs under contention.
Tests: `total_bits <= budget` property, monotonicity (bigger budget ⇒ ≥ quality),
high-priority favoritism fixture.

### Phase 5 — Baseline ABR (§11-P5, §4)

Work: `ThroughputEstimator` (EWMA + harmonic mean over last-k), `BufferRule`
(BOLA-lite: low buffer → downshift, high → upshift), `BaselineAbr: AbrPolicy` as
`min(throughput_choice, buffer_choice)` with safety margin. Stateful across segments.
Success: conventional policy runs under same traces; no panics on gaps/spikes.
Tests: estimator math, buffer thresholds, trace-gap robustness, statefulness.

### Phase 6 — Simulation harness (§11-P6)

Work: `Player` (buffer, rebuffer, startup tracking), `Simulator::run(policy, video,
trace, config) -> SimulationReport`, `NetworkTrace::from_csv`, 4 built-in profiles
(§9.2), seeded jitter, `compare` CLI emitting `results.json`, integration tests for
byte-identical reruns.
Success: BOTH policies run reproducibly; comparable reports.
Tests: determinism (same seed ⇒ identical report), rebuffer accounting, CSV parsing.

### Phase 7 — Quality evaluation (§11-P7, §9.3)

Work: `metrics.rs` aggregation (VMAF primary via ingested CSV from `ffmpeg+libvmaf`,
synthetic VMAF model until then; SSIM supporting; Q/MB; rebuffer; startup; total
bytes), per-content-type × per-network reporting matrix, `compare` table output.
Success: quality + bandwidth recorded and comparable across arms.
Tests: metric math, Q/MB edge (zero bytes), report schema stability.

### Phase 8 — AI enhancement (§11-P8, §6)

Work (strictly after heuristic works): (1) regress `w_m,w_c` from measured VMAF,
(2) predict `ΔVMAF/ΔMB` per (chunk, rung) for allocator, (3) throughput predictor,
(4) personalization weights. Hold-out evaluation ML-vs-heuristic.
Success: ML policy compared against heuristic on Q/MB without rebuffer regression.
Tests: train/predict round-trip, hold-out comparison fixture.

---

## 4. Build Order & Verification Matrix

| Order | Doc | Gate |
|---|---|---|
| 0 | `PHASE0.md` | `cargo test + clippy + fmt` green; `Video` N×M test |
| 1 | `PHASE1.md` | model tests + serde round-trip |
| 2 | `PHASE2.md` | motion/complexity unit tests |
| 3 | `PHASE3.md` | priority + bucket tests |
| 4 | `PHASE4.md` | budget property test |
| 5 | `PHASE5.md` | estimator + robustness tests |
| 6 | `PHASE6.md` | determinism integration test |
| 7 | `PHASE7.md` | metrics + report matrix test |
| 8 | `PHASE8.md` | hold-out comparison test |

Each `PHASEX.md` MUST contain: goal, files added/changed, key APIs (signatures),
algorithms, tests added, verification log (exact commands + output), deviations from
this plan, and next-phase hooks.

---

## 5. Decisions Deferred (need owner input when reached)

1. V1 features: synthetic + CSV-ingested VMAF vs live decode? (Recommend synthetic first.)
2. Ground truth: shell out to `ffmpeg + libvmaf` or pure-Rust SSIM only?
3. Fixed ladder + segment duration for comparability (propose 4 s, 5 rungs)?
4. AI crate choice at Phase 8 (`smartcore` vs `burn` vs `onnxruntime`)?

---

## 6. Phase Log

| Phase | Status | Doc | Notes |
|---|---|---|---|
| 0 | completed | `PHASE0.md` | skeleton + harness; 21 unit + 4 integration green; csv deferred, see PHASE0 §7 |
| 1 | planned | `PHASE1.md` | segment model |
| 2 | planned | `PHASE2.md` | motion analysis |
| 3 | planned | `PHASE3.md` | priority model |
| 4 | planned | `PHASE4.md` | allocator |
| 5 | planned | `PHASE5.md` | baseline ABR |
| 6 | planned | `PHASE6.md` | simulation |
| 7 | planned | `PHASE7.md` | VMAF/SSIM |
| 8 | planned | `PHASE8.md` | AI enhancement |
