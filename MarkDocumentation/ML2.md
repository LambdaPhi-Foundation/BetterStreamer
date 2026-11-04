# ML2.md — AI Decision Intelligence, Predictive Networking & Policy Optimization

> **Owner**: ML2 (Machine Learning Engineer 2 — Decision Modeling, Predictive Networking & AI Policy)  
> **Project**: Content-Aware Adaptive Bitrate Streaming (`BetterStreamer`)  
> **Core Stack**: Python 3.11+, PyTorch, Scikit-Learn, LightGBM, ONNX, `ort` (Rust bindings)  
> **Document Status**: Authoritative Work Breakdown & Integration Contract  
> **Process Model**: ML2 works **concurrently and independently** of ML1 and DC; integration happens only through versioned file contracts (`tests/fixtures/ml_training_dataset.csv`, `media/manifests/`) and the frozen Rust `AbrPolicy` trait. ML2 never modifies core Rust simulation logic.

---

## 1. Executive Summary & Role Mission

ML2 owns the **Decision Intelligence, Predictive Modeling, and AI-Enhanced ABR Policies** of BetterStreamer. While ML1 extracts visual features from raw video and DC builds the deterministic simulation harness and heuristic allocator, ML2 **replaces static heuristics with learning-based intelligence**:

1. **Learn optimal feature weights** $(w_m, w_c)$ from measured VMAF data.
2. **Predict marginal perceptual gain** $\widehat{\Delta}(c, r) = \mathbb{E}[\Delta\text{VMAF}/\Delta\text{MB}]$ per (chunk, rung).
3. **Forecast near-future network throughput** for proactive cliff avoidance.
4. **Train a learned ABR policy** (RL / contextual bandit) selecting rungs under buffer pressure.

ML2's models are **embeddable into DC's Rust engine** via the `AbrPolicy` trait (§4.2) with a deterministic heuristic fallback. ML2 writes Python training/export code and ONNX weight files; it does **not** edit `src/abr/` simulation internals.

---

## 2. Core Responsibilities & Domain Ownership

```
                        ┌──────────────────────────────────────┐
                        │      ML2: AI Decision Intelligence   │
                        │  (Prediction, RL, Policy, Deployment)│
                        └──────────────┬───────────────────────┘
                                       │
        ┌──────────────────────────────┴──────────────────────────────┐
        │ Trained Models + ONNX Weights                             │ Policy Benchmarks
        ▼                                                            ▼
 ┌──────────────┐                                          ┌──────────────┐
 │   DC (Rust)  │                                          │   WB (Web)   │
 │Embedded ONNX │                                          │Model telemetry│
 │runtime       │                                          │+ explanations│
 └──────────────┘                                          └──────────────┘
```

### 2.1 Workstream A — Learning Optimal Feature Weights (§6, §11-P8)

**Goal**: replace the fixed heuristic $w_m=0.60, w_c=0.40$ with data-driven weights.

1. Ingest `tests/fixtures/ml_training_dataset.csv` (produced by ML1).
2. Fit a regressor mapping `(motion, complexity, category) → optimal weight pair` that maximizes total delivered VMAF under each bandwidth budget.
3. Export `models/learned_weights.json`:
   ```json
   {
     "talking_head": { "w_m": 0.45, "w_c": 0.55 },
     "sports": { "w_m": 0.70, "w_c": 0.30 },
     "text_lecture": { "w_m": 0.20, "w_c": 0.80 },
     "default": { "w_m": 0.60, "w_c": 0.40 }
   }
   ```
4. DC reads this JSON (via `SimulatorConfig` or a dedicated loader) to parameterize `priority_score` at runtime — no model file needed for inference, just two floats.

### 2.2 Workstream B — Marginal Perceptual Gain Predictor ($\Delta\text{VMAF}/\Delta\text{MB}$) (§6 core target)

**Goal**: predict $\widehat{\Delta}(c, r)$ so DC's greedy allocator always spends the next byte where VMAF-per-MB is highest.

1. Build tabular dataset from ML1: features `(motion, complexity, priority, rung_id, bitrate_bps, size_bytes)` → target `delta_vmaf_per_mb`.
2. Train a lightweight regressor: LightGBM / CatBoost / compact MLP.
   - Target: continuous, ≥ 0.
   - Handle cold start: unseen categories → fall back to priority-based heuristic gain.
3. Export to ONNX: `models/marginal_vmaf_predictor.onnx`.
4. **Latency constraint**: single-chunk inference **< 1.0 ms** on CPU (quantized INT8/FP16).

**Integration**: DC's `allocate_greedy_marginal` accepts `marginal_gains: &[Vec<f64>]`. ML2's ONNX runtime fills that table per segment before calling the allocator (≤1 ms budget, PIPELINE.md §8).

### 2.3 Workstream C — Predictive Network Bandwidth Modeling

**Goal**: proactive rather than reactive ABR; detect throughput cliffs 3–5s ahead.

1. Training data: `traces/*.csv` + live telemetry beacons (WB).
2. Features: last-N throughput samples, RTT, loss rate, buffer level, time-of-chunk.
3. Model: 1D-CNN / TCN / GRU / Holt-Winters autoregressive.
4. Output: $\widehat{T}_{t+1}, \dots, \widehat{T}_{t+k}$ (k upcoming chunks).
5. Export: `models/bandwidth_forecaster.onnx`.

**Usage**: DC's simulator passes forecasted bandwidth into `PlayerCtx.estimated_throughput_bps` for upcoming segments; the policy shifts low-priority chunks down before the buffer empties.

### 2.4 Workstream D — Learned ABR Policy (RL / Contextual Bandit)

**Goal**: end-to-end learned policy $r_t = \pi(S_t)$.

**State vector** $S_t$:
$$[\text{BufferLevel}_t,\ \text{PastThroughput}_{t-k:t},\ \text{ChunkFeatures}(c_t),\ \text{CandidateSizes}_{t},\ \text{RemainingBudget}]$$

**Action**: rung id $r_t \in \{0,1,2,3,4\}$.

**Reward**:
$$\mathcal{R}_t = \text{VMAF}(c_t, r_t) - \alpha\cdot\text{RebufferTime}_t - \beta\cdot|\text{VMAF}_t - \text{VMAF}_{t-1}| - \gamma\cdot\text{BitrateWaste}$$

Train with PPO/DQN (stable-baselines3) or a contextual bandit (LinUCB / Thompson). Evaluate hold-out vs. heuristic on Q/MB with zero rebuffer regression.

### 2.5 Workstream E — Personalization & Viewer Preference (extension)

Profiles:
- **Smoothness-sensitive**: penalize resolution shifts + rebuffering; stable medium quality.
- **Quality-sensitive**: penalize blur in complex scenes; accept buffer risk for 1080p.
- **Device-specific**: mobile (spatial detail less visible) vs 4K TV (artifacts highly visible).

Export per-profile weight overrides in `models/personalization/`.

---

## 3. Key Deliverables & Artifacts

| Artifact | Path | Owner | Format |
|----------|------|-------|--------|
| Training script (marginal gain) | `scripts/training/train_marginal_gain.py` | ML2 | Python |
| Training script (throughput) | `scripts/training/train_throughput_predictor.py` | ML2 | Python |
| Training script (weights) | `scripts/training/train_weights.py` | ML2 | Python |
| Evaluation script | `scripts/training/evaluate_policy.py` | ML2 | Python |
| Marginal gain model | `models/marginal_vmaf_predictor.onnx` | ML2 | ONNX |
| Bandwidth forecaster | `models/bandwidth_forecaster.onnx` | ML2 | ONNX |
| Learned weights | `models/learned_weights.json` | ML2 | JSON |
| Personalization overrides | `models/personalization/*.json` | ML2 | JSON |
| Hold-out validation report | `tests/model_validation/holdout_report.json` | ML2 | JSON |

---

## 4. Cross-Team Technical Interfaces & Contracts (FROZEN)

### 4.1 Interface to ML1 (Feature Input)

- **Data ingestion**: read `tests/fixtures/ml_training_dataset.csv` (ML1-owned). One row per chunk × rung.
- **Feature normalization**: ML1 emits raw [0,1] features; ML2 applies Z-score/MinMax at training time. **Never** re-scale in the inference path without versioning.
- **Schema changes**: ML1 owns the CSV schema; ML2 pins a schema version and fails fast on mismatch (clear error message, no silent mis-training).

### 4.2 Interface to DC (Rust Engine Deployment)

DC defines the trait; ML2 provides a conforming implementation behind an inference boundary. ML2 does **not** edit `src/abr/mod.rs` or `src/simulation/`.

**Trait** (frozen in `src/abr/mod.rs`):
```rust
pub trait AbrPolicy {
    fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId;
}
```

**ML2 conforming struct** (owned by ML2, placed in a separate crate or feature-gated module):
```rust
pub struct MlPerceptualAbr {
    session: ort::Session,                 // ONNX Runtime
    lookahead_chunks: usize,
    fallback: PerceptualAbr,               // deterministic heuristic fallback
}

impl AbrPolicy for MlPerceptualAbr {
    fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId {
        // 1. Run ONNX marginal-gain predictor -> gains table
        // 2. Run ONNX bandwidth forecaster -> predicted bps
        // 3. Call DC's allocate_greedy_marginal(segments, budget, gains)
        // 4. On any inference error / OOD input -> fallback.select()
    }
}
```

**Fallback guarantee**: if ONNX session fails, input is out-of-distribution, or latency > 1 ms, fall back to DC's `PerceptualAbr` (heuristic). Simulation must never panic or hang waiting for ML2.

**Onboarding path**: ML2 exports ONNX weights → DC adds an optional `ml` feature gate + `ort` dependency → `MlPerceptualAbr` implements `AbrPolicy` → CLI gains `--policy ml` option. Until then, `perceptual` remains the content-aware policy.

### 4.3 Interface to WB (Web Platform)

- Model explanation telemetry: SHAP values / feature importances for "why this rung".
- Predicted throughput curves for WB's live chart overlay.
- Model confidence + decision breakdown JSON per chunk.

---

## 5. Tools, Tech Stack & Environment

- **Python 3.11+**: `torch`, `scikit-learn`, `lightgbm`, `xgboost`, `pandas`, `numpy`, `onnx`, `onnxruntime`.
- **Time-Series / RL**: `statsmodels`, `stable-baselines3` (optional PPO/DQN).
- **ONNX export**: `torch.onnx.export`, `skl2onnx`, `onnxmltools`.
- **Analysis**: `jupyterlab`, `matplotlib`, `seaborn`.
- **Rust binding** (DC-owned, ML2 provides weights only): `ort` (ONNX Runtime Rust).

---

## 6. Execution Roadmap & Milestones

| Milestone | Deliverable | Exit Criteria |
|-----------|-------------|---------------|
| M1 | Dataset exploration | Baseline $R^2$ via linear regression on ML1's CSV |
| M2 | Weight optimization | `learned_weights.json` with per-category $(w_m, w_c)$ |
| M3 | Marginal gain model | `marginal_vmaf_predictor.onnx`, $R^2 \ge 0.82$ hold-out, inference < 1 ms |
| M4 | Throughput predictor | `bandwidth_forecaster.onnx`, proactive cliff detection on `sudden-degradation.csv` |
| M5 | Rust integration | `MlPerceptualAbr` implements `AbrPolicy`; fallback works; `cargo test` green |
| M6 | Hold-out comparison | ML policy ≥ heuristic Q/MB, zero rebuffer regression across 4 traces |

---

## 7. Verification & Acceptance Criteria

1. **Prediction accuracy**: marginal gain predictor $R^2 \ge 0.82$ on unseen hold-out clips.
2. **Inference latency**: single-chunk prediction < 1.0 ms on standard CPU.
3. **Comparative superiority (§11-P8)**: ML-enhanced policy matches or exceeds heuristic Quality/MB with **zero rebuffering regressions** across `traces/*.csv`.
4. **Deterministic reproducibility**: fixed inputs → identical ONNX outputs across repeated runs (fixed seed, no GPU nondeterminism).
5. **Fallback correctness**: corrupted / missing ONNX → `PerceptualAbr` heuristic selected; simulation continues without panic.
6. **Contract stability**: ML2 does not modify `src/`; any new Rust integration goes through DC review + `AbrPolicy` trait conformance.

---

## 8. Concurrency / Independence Rules

- ML2 owns `scripts/training/`, `models/`, `tests/model_validation/`. **No edits to `src/` without DC review.**
- ML2 reads ML1's `tests/fixtures/ml_training_dataset.csv` and `media/manifests/*.json`; treats them as immutable inputs pinned to a schema version.
- ML2 never blocks on ML1: if a category's manifest is missing, ML2 trains on available categories and marks the rest as "fallback to default weights."
- ML2 never blocks on DC: ONNX export and Python training are fully offline; Rust integration (`ort` + `MlPerceptualAbr`) is a separate, optional milestone (M5) gated behind a Cargo feature flag.
- All three teams synchronize only at the **contract version** (schema version in the training CSV / manifest header).
