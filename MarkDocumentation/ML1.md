# ML1.md — AI-Based Content Assessment & Visual Feature Intelligence

> **Owner**: ML1 (Machine Learning Engineer 1 — Visual Feature Intelligence & Ground Truth)  
> **Project**: Content-Aware Adaptive Bitrate Streaming (`BetterStreamer`)  
> **Core Stack**: Python 3.11+, OpenCV, FFmpeg, libvmaf, PyAV, NumPy, SciPy, pandas  
> **Document Status**: Authoritative Work Breakdown & Integration Contract  
> **Process Model**: ML1 works **concurrently and independently** of ML2 and DC; integration happens only through versioned file contracts in `media/manifests/` and `tests/fixtures/`. ML1 never touches Rust code.

---

## 1. Executive Summary & Role Mission

ML1 owns the **Computer Vision, Video Processing, and Perceptual Ground Truth** pipeline of BetterStreamer. The core thesis: traditional ABR is blind to visual dynamics, treating every chunk as equally demanding. ML1 provides the **content awareness** — extracting quantitative motion and spatial complexity metrics from raw video frames, curating the benchmark video corpus, encoding multi-bitrate ladders, and computing ground-truth perceptual quality scores (VMAF, SSIM).

**Deliverables flow into**:
- **DC (Rust Engine)**: feature vectors + VMAF/size lookup tables via JSON manifests consumed by `src/media.rs` and `src/network.rs`.
- **ML2 (Decision Models)**: tabular training datasets for marginal-gain and weight-regression models.

ML1 does **not** write Rust, does **not** modify `src/`, and does **not** depend on ML2's output. Both teams work in parallel against the frozen interface contract in §4.

---

## 2. Core Responsibilities & Domain Ownership

```
                        ┌───────────────────────────────┐
                        │     ML1: Video & Vision CI    │
                        └──────────────┬────────────────┘
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        │ Feature Vectors + VMAF Tables│ Transcoded Media (chunks)    │
        ▼                              ▼                              ▼
 ┌──────────────┐              ┌──────────────┐              ┌──────────────┐
 │   DC (Rust)  │              │   WB (Web)   │              │   ML2 (AI)   │
 │Ingestion /   │              │Player chunks │              │Training data │
 │Allocator     │              │+ manifests   │              │+ models      │
 └──────────────┘              └──────────────┘              └──────────────┘
```

### 2.1 Workstream A — Video Corpus Curation (§9.1)

Curate and standardize the benchmark corpus representing **5 mandatory categories**:

| # | Category | Example content | Motion | Complexity |
|---|----------|-----------------|--------|------------|
| 1 | Talking Head / Low Dynamics | Interviews, video podcasts, newscasts | Low | Low-Med |
| 2 | Sports / High Dynamics | Football, basketball, racing | High | Med-High |
| 3 | Action / Heavy Camera Motion | Drone footage, cinematic cuts, handheld | High | High |
| 4 | Text / Screen Capture / Lecture | Slides, coding screencasts, diagrams | Low | High |
| 5 | Mixed-Complexity Footage | Transitions between interview, b-roll, action | Mixed | Mixed |

**Requirements**:
- Normalize all sources to **1080p30** (or 60fps), YUV420p, MP4 container.
- Constant frame rate; strictly monotonic PTS/DTS.
- Known duration; no container-level duration drift.
- Store masters under `media/raw/` (do not commit binaries; commit descriptors + scripts only).

### 2.2 Workstream B — Transcoding Ladder & Chunking Pipeline

Implement `scripts/pipeline/chunk_and_encode.py`:

- Split each source into **4.0-second** independent, keyframe-aligned chunks (closed GOP).
- Enforce closed GOPs: `-g 120 -keyint_min 120 -sc_threshold 0` (30 fps → 120-frame GOP).
- Encode every chunk across the **5-rung BetterStreamer ladder**:

| Rung | Resolution | Target Bitrate | Codec Profile |
|------|------------|----------------|---------------|
| 0 | 640×360 | 400 kbps | H.264 Main L3.0 |
| 1 | 854×480 | 800 kbps | H.264 Main L3.1 |
| 2 | 1280×720 | 1500 kbps | H.264 High L3.2 |
| 3 | 1920×1080 | 3000 kbps | H.264 High L4.0 |
| 4 | 1920×1080 | 6000 kbps | H.264 High L4.1 |

- Use 2-pass `libx264` for exact bitrate conformity.
- Output to `media/chunks/<category>/<chunk_id>/rung_<r>/chunk.mp4`.
- Emit a per-video manifest (JSON, schema in §4.1).

### 2.3 Workstream C — Computer Vision Feature Extraction

Implement `scripts/pipeline/extract_features.py`. Per chunk, compute normalized scores in **[0.0, 1.0]** on downsampled grayscale luminance (360p):

**A. Motion (`motion_score`)** — mirrors `src/analysis/motion.rs`
- Mean Squared Frame Difference (MSFD) over adjacent frame pairs.
- Motion-vector magnitude from H.264 macroblocks via PyAV/FFmpeg (optional cross-check).
- Normalization: `norm_motion = min(1.0, raw_msfd / 450.0)`.
- Static podcast ≈ 0.04; soccer / auto-racing ≈ 0.88.

**B. Spatial Complexity (`complexity_score`)** — mirrors `src/analysis/complexity.rs`
- Laplacian variance per frame, averaged.
- High-frequency 2D-DCT energy ratio (8×8 blocks).
- Texture entropy (Shannon) of grayscale histogram.
- Normalization: `norm_complexity = min(1.0, raw_energy / 1400.0)`.
- Blurry background ≈ 0.12; dense code slides / forest ≈ 0.85.

**C. Saliency / RoI (extension, Phase 3+)**
- Face detection (Haar / RetinaFace), text regions (CRAFT / contour).
- Boost complexity when high-detail overlaps attention zones.

**Output contract**: one JSON row per chunk appended to the video manifest:
```json
{
  "segment_id": 0,
  "motion": 0.82,
  "complexity": 0.65,
  "priority_heuristic": 0.752
}
```

### 2.4 Workstream D — Perceptual Ground Truth (VMAF & SSIM)

Implement `scripts/pipeline/compute_vmaf.py`:

- Per-chunk VMAF via `ffmpeg -i degraded.mp4 -i reference.mp4 -lavfi libvmaf=... -f null -`.
- Compute arithmetic + harmonic mean VMAF per chunk across all 5 rungs.
- Frame-level SSIM as supporting metric (`ssim` ffmpeg filter or scikit-image).
- Generate rate-distortion (R-D) curve: `VMAF(c, rung)` per chunk.
- Compute marginal perceptual gain:
  $$\frac{\Delta \text{VMAF}}{\Delta \text{MB}} =
  \frac{\text{VMAF}(c, r) - \text{VMAF}(c, r-1)}
  {\text{SizeMB}(c, r) - \text{SizeMB}(c, r-1)}$$

**Acceptance criteria** (§7):
1. Zero NaN; all scores strictly in [0,1].
2. Every chunk starts with an IDR frame; decodes in isolation: `ffmpeg -v error -i chunk.mp4 -f null -`.
3. File size strictly increases across rungs: `S₀ < S₁ < S₂ < S₃ < S₄`.
4. 100% of chunks have verified VMAF against the uncompressed source.

---

## 3. Key Deliverables & Artifacts

| Artifact | Path | Owner | Format |
|----------|------|-------|--------|
| Chunk + encode script | `scripts/pipeline/chunk_and_encode.py` | ML1 | Python |
| Feature extraction script | `scripts/pipeline/extract_features.py` | ML1 | Python |
| VMAF/SSIM compute script | `scripts/pipeline/compute_vmaf.py` | ML1 | Python |
| Video manifests | `media/manifests/<category>_<id>.json` | ML1 | JSON (§4.1) |
| Transcoded chunks | `media/chunks/<category>/<id>/rung_<r>/` | ML1 | `.mp4` / `.m4s` |
| R-D / feature report | `media/reports/rd_curves_<category>.png` | ML1 | PNG + CSV |

---

## 4. Cross-Team Technical Interfaces & Contracts (FROZEN)

These contracts are **versioned and frozen**; ML1, ML2, and DC implement against them without coordinating day-to-day.

### 4.1 Interface to DC (Rust Engine) — Feature Import

DC defines the schema; ML1 produces files matching it exactly. DC parses without requiring heavy deps.

**File**: `media/manifests/<video_id>.json`

```json
{
  "video_id": "sports_dynamic_01",
  "category": "sports",
  "segment_duration_s": 4.0,
  "ladder_bps": [400000, 800000, 1500000, 3000000, 6000000],
  "segments": [
    {
      "segment_id": 0,
      "features": {
        "motion": 0.82,
        "complexity": 0.65,
        "priority_heuristic": 0.752
      },
      "vmaf_scores": [62.4, 76.1, 88.5, 94.2, 97.8],
      "ssim_scores": [0.89, 0.93, 0.96, 0.98, 0.99],
      "sizes_bytes": [200000, 400000, 750000, 1500000, 3000000],
      "chunk_path": "media/chunks/sports_dynamic_01/0/rung_3/chunk.mp4"
    }
  ]
}
```

**Parser contract** (DC side, read-only for ML1): DC reads this JSON into `Video` structs via `serde`. ML1 must ensure:
- `segment_id` is contiguous from 0.
- `vmaf_scores` / `sizes_bytes` length == ladder length (5).
- All floats finite, no NaN/Inf.
- `sizes_bytes` strictly increasing.

### 4.2 Interface to ML2 (Decision Intelligence) — Training Data Hand-Off

**File**: `tests/fixtures/ml_training_dataset.csv`

Columns (one row per chunk × rung):
```
chunk_id,category,segment_id,rung_id,motion,complexity,priority,bitrate_bps,sizes_bytes,vmaf,ssim,delta_vmaf_per_mb
```

ML2 consumes this CSV directly (no Rust dependency). ML1 regenerates it whenever the corpus changes; ML2 pulls the latest commit.

**Normalization agreement**: ML1 emits raw 0–1 features; ML2 applies its own Z-score/MinMax scaling at training time. ML1 does **not** pre-scale.

---

## 5. Tools, Tech Stack & Environment

- **Python 3.11+**: `numpy`, `scipy`, `pandas`, `opencv-python`, `scikit-image`, `av` (PyAV).
- **FFmpeg**: compiled with `--enable-libvmaf --enable-libx264`.
- **Quality**: `libvmaf` v3.0+ (or `vmaf` Python package).
- **Visualization**: `matplotlib`, `seaborn` for R-D curve plots.
- **Git**: feature branch per video category; merge to `main` after §7 acceptance.

---

## 6. Execution Roadmap & Milestones

| Milestone | Deliverable | Exit Criteria |
|-----------|-------------|---------------|
| M1 | Corpus + chunking | 5 reference clips, 4s chunks × 5 rungs, closed-GOP verified |
| M2 | Feature extraction | `motion` ∈ [0,1], `complexity` ∈ [0,1], no NaN |
| M3 | VMAF ground truth | Full VMAF matrix, R-D curves, marginal gain computed |
| M4 | Integration delivery | Manifests in `media/manifests/`, training CSV in `tests/fixtures/`, parser round-trip verified by DC's unit tests |
| M5 | Refinement | Saliency / face weighting on text-lecture category |

---

## 7. Verification & Acceptance Criteria

1. **Zero NaN / bounded scores**: `0.0 ≤ motion, complexity ≤ 1.0` for every chunk.
2. **Independent chunk decodability**: `ffmpeg -v error -i chunk.mp4 -f null -` exits 0 for every chunk.
3. **Monotonic bitrate**: `S₀ < S₁ < S₂ < S₃ < S₄` per chunk.
4. **VMAF completeness**: 100% of chunks have VMAF vs. reference.
5. **Manifest schema validity**: `python -m json.tool` parses; DC's `Video` serde round-trip test passes on a sample manifest.
6. **Determinism**: same source + same ffmpeg params → byte-identical chunk hashes across runs.

---

## 8. Concurrency / Independence Rules

- ML1 owns `scripts/pipeline/`, `media/manifests/`, `media/chunks/`, `media/reports/`. **No Rust edits.**
- ML1 publishes to `main` via PR; DC's CI runs `cargo test` which includes a manifest round-trip test — if ML1 breaks the schema, CI fails fast without blocking ML2.
- ML2 reads only `tests/fixtures/ml_training_dataset.csv`; never waits on ML1 for code changes.
- All three teams synchronize only at the **contract version** (bump a `contract_version` field in the manifest when the schema changes).
