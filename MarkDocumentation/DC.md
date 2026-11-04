# DC.md — Core Computing, Research & Technical Implementation

> **Owner**: DC (Team Lead / Core Computing & Technical Implementation)  
> **Project**: Content-Aware Adaptive Bitrate Streaming (`BetterStreamer`)  
> **Core Stack**: Rust (Edition 2024), Systems Architecture, Mathematical Optimization, Simulation Harness  
> **Document Status**: Authoritative Work Breakdown & Responsibilities Guide  

---

## 1. Executive Summary & Role Mission

As the **Core Computing, Research, and Technical Implementation Lead (DC)**, you are responsible for the foundational computing infrastructure, mathematical modeling, simulation engine, and overarching architectural integrity of **BetterStreamer**. 

While initial design documents conceptualized the project in C++, the production system is targeted in **Rust** (`BetterStreamer`, Edition 2024) to guarantee zero memory-safety overhead, deterministic execution, and reproducible academic benchmarks. You own the core simulation runtime, the formalization of the content-aware bandwidth allocation problem, the baseline comparison harness, and the technical contracts that integrate ML1's feature pipelines, ML2's decision models, and WB's web platform.

---

## 2. Core Responsibilities & Domain Ownership

```
                        ┌─────────────────────────────────────┐
                        │      DC: Core Systems & Engine      │
                        │  (Rust Engine, Simulation, Alloc)   │
                        └──────────────┬───────────────┬──────┘
                                       │               │
                 Feature Vectors & CSV │               │ Integration API / JSON
                                       ▼               ▼
                       ┌──────────────────┐  ┌──────────────────┐
                       │   ML1 & ML2      │  │        WB        │
                       │ AI & Decision    │  │ Web Dashboard    │
                       └──────────────────┘  └──────────────────┘
```

### 2.1 Research Problem Framing & Academic Rigor
- **Formal Problem Formulation**: Formulate and enforce the formal optimization model (§14 of project spec):
  $$\text{allocate} = \arg\max \sum_{i} \text{Quality}(c_i, \text{bitrate}_i) \quad \text{subject to} \quad \sum_{i} \text{Bits}(c_i) \le B_{\text{available}}$$
- **Research Question Defense**: Keep the experimental methodology strictly focused on:
  > *"Can network-aware adaptive streaming improve perceptual quality per delivered byte by explicitly incorporating content-dependent perceptual importance into bitrate allocation?"*
- **Axiomatic Consistency**: Ensure baseline and proposed policies run under **strictly identical** inputs: identical video chunks, identical representations, and identical network trace replays. Never allow stochastic divergence between evaluation arms.

### 2.2 Rust Core Architecture & Systems Programming
- **Workspace Maintenance**: Maintain `Cargo.toml`, compiler settings, offline dependency caching, and clean compilation (`cargo clippy -- -D warnings`, `cargo fmt --check`).
- **Module Structure & Code Quality**: Own all core modules under `src/`:
  - `src/lib.rs` & `src/main.rs`: Library crate exports and thin CLI interface.
  - `src/config.rs`: Central configuration (`SimulatorConfig`), random seeds, ladder definitions, and validation logic.
  - `src/error.rs`: Typed, non-stringly error handling using `thiserror`.
  - `src/media.rs`: High-performance data models for `Representation`, `SegmentFeatures`, `Segment`, and `Video`.
  - `src/network.rs`: Network trace CSV parser, replay engine, and bandwidth step functions.
  - `src/abr/`: ABR policy abstraction traits, baseline ABR, perceptual ABR, and budget allocators.
  - `src/simulation/`: Event-driven deterministic player state machine and simulator runner.
  - `src/metrics.rs`: Perceptual quality, rebuffering, and efficiency aggregation.

### 2.3 Algorithm Design & Allocator Engineering
- **Baseline ABR Policy (`src/abr/baseline.rs`)**:
  - Implement a conventional throughput- and buffer-based ABR policy modeling standard HLS/DASH clients.
  - Combine EWMA / Harmonic Mean throughput estimation with a BOLA-lite buffer safety heuristic:
    $$\text{Rung} = \min\left(R_{\text{throughput}}, R_{\text{buffer}}\right)$$
  - Provide a stable baseline that does not panic or crash on sudden trace drops or spikes.
- **Content-Aware Heuristic & Allocator (`src/abr/allocator.rs`, `src/abr/perceptual.rs`)**:
  - Implement the deterministic priority score engine:
    $$\text{Priority}(c) = \text{clamp}\left(w_m \cdot \text{Motion}(c) + w_c \cdot \text{Complexity}(c), 0.0, 1.0\right)$$
  - Implement budget-constrained allocation algorithms:
    1. *Greedy Marginal-Gain Allocation*: Incrementally allocate bitrate steps to the segment offering the highest $\Delta\text{Quality} / \Delta\text{Bits}$.
    2. *Knapsack / Dynamic Programming Solver*: Offline bounded knapsack solver providing the theoretical upper bound for benchmarking.
  - Enforce the hard invariant: $\text{Total Bits Allocated} \le \text{Network Bandwidth Budget}$.

### 2.4 Simulation Engine & Determinism Harness
- **Event-Driven Player Simulator (`src/simulation/`)**:
  - Build the deterministic player model tracking playback time, buffer fill level ($s$), chunk download times, stalls/rebuffers ($s$), and quality shifts.
  - Ensure zero wall-clock dependencies; every simulation run must be 100% deterministic given a PRNG seed.
- **Automated Comparison & Reporting**:
  - Implement the `compare` command in the CLI to execute both Baseline and Content-Aware policies across traces and output clean `results.json` reports.

---

## 3. Phased Technical Roadmap & Deliverables

Mapped against the repository master plan (`MarkDocumentation/SUPER.md`):

| Phase | Milestone Name | DC Ownership & Specific Deliverables | Status |
|:---:|:---|:---|:---:|
| **Phase 0** | **Skeleton & Determinism Harness** | Pinned dependencies, library crate, CLI skeleton, stub modules, typed errors, sample traces. | **Completed** |
| **Phase 1** | **Segment & Representation Model** | Implement `media.rs` data model, representation ladders, synthetic video generator for §9.1 categories, unit tests & serde round-trips. | **Next** |
| **Phase 2** | **Motion & Complexity Engine Core** | Pure function interfaces for `motion_score(&[f64])` and `complexity_score(&[f64])`; boundary guards; integration hooks for ML1. | Planned |
| **Phase 3** | **Priority Engine** | Continuous `0.0..1.0` priority scoring, Low/Medium/High bucketing, weight parameter sweeping tests. | Planned |
| **Phase 4** | **Bandwidth Allocator** | Greedy marginal gain allocator, offline DP knapsack upper bound, budget-enforcement property tests (`proptest`). | Planned |
| **Phase 5** | **Baseline ABR Engine** | EWMA + harmonic mean throughput estimator, BOLA-lite buffer safety thresholding, stateful segment selection. | Planned |
| **Phase 6** | **Simulation Harness** | Deterministic `Player` state machine, full event-loop `Simulator::run()`, CSV trace replay, integration determinism tests. | Planned |
| **Phase 7** | **Quality Evaluation** | Real/Synthetic VMAF & SSIM metric aggregation, Quality/MB calculations, comparative JSON reporting. | Planned |
| **Phase 8** | **AI Integration & Systems Polish** | Integrate ML2's learned weights / ONNX runtime, finalize benchmark comparison reports and documentation. | Planned |

---

## 4. Cross-Team Technical Interfaces & Contracts

### 4.1 Interface to ML1 (Feature Extraction & Ground Truth)
- **Data Ingestion Contract**: DC defines and enforces the schema for ingested video features and VMAF tables:
  ```json
  {
    "video_name": "sports_dynamic_01",
    "segment_duration_s": 4.0,
    "segments": [
      {
        "segment_id": 0,
        "motion_score": 0.82,
        "complexity_score": 0.65,
        "vmaf_ladder": {
          "400k": 62.4,
          "800k": 76.1,
          "1500k": 88.5,
          "3000k": 94.2,
          "6000k": 97.8
        }
      }
    ]
  }
  ```
- **FFmpeg / VMAF Import**: Build a lightweight parser that ingests ML1's exported CSV/JSON files into `Video` structs without requiring heavy external dependencies in the core crate.

### 4.2 Interface to ML2 (Decision Models & AI Allocation)
- **Trait Definition for Policy**: Provide a clean, thread-safe Rust trait that ML2's models must satisfy:
  ```rust
  pub trait AbrPolicy {
      fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId;
  }
  ```
- **Inference Boundary**: Provide an FFI or crate boundary (`smartcore`, `linreg`, or ONNX Runtime bindings) where ML2's learned model can predict $\Delta\text{VMAF}/\Delta\text{MB}$ or priority weights without slowing down the simulation.

### 4.3 Interface to WB (Web Platform & Demonstration)
- **CLI & Simulation Output Schema**: DC guarantees a stable JSON output format for `betterstreamer run` and `betterstreamer compare`:
  ```json
  {
    "simulation_id": "sim_20261010_001",
    "config": { "seed": 42, "segment_duration_s": 4.0 },
    "trace_name": "sudden-degradation",
    "video_name": "mixed-complexity",
    "summary": {
      "baseline": { "avg_vmaf": 74.2, "quality_per_mb": 5.4, "rebuffer_s": 1.2, "total_mb": 13.7 },
      "content_aware": { "avg_vmaf": 82.6, "quality_per_mb": 7.1, "rebuffer_s": 0.0, "total_mb": 11.6 }
    },
    "timeline": [
      {
        "segment_id": 0,
        "playback_time_s": 0.0,
        "bandwidth_mbps": 5.0,
        "baseline_rung": 3,
        "content_aware_rung": 4,
        "buffer_baseline_s": 4.0,
        "buffer_ca_s": 4.0
      }
    ]
  }
  ```
- Provide clean CLI commands so WB can invoke runs on-demand via subprocess or ingest precomputed trace files.

---

## 5. Verification & Acceptance Criteria

1. **Compilation & Linting**: `cargo build`, `cargo test`, `cargo clippy --all-targets -- -D warnings`, and `cargo fmt --check` must pass on every commit.
2. **Determinism Guarantee**: Running the simulator twice with identical seeds, trace files, and video manifests must yield byte-identical `SimulationReport` JSON files.
3. **Hard Constraint Enforcement**: The allocator must never exceed the specified bandwidth budget ($\sum \text{bits} \le B$). Enforced via property tests using `proptest`.
4. **Reproducible Research Baseline**: When evaluated across the 4 standard network profiles (`traces/*.csv`), Content-Aware ABR must demonstrate measurable Quality/MB improvements over Baseline ABR on high-entropy and mixed clips without introducing rebuffering regressions.
