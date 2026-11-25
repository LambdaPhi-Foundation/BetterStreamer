# BetterStreamer — ML1 Pipeline

Content-, Device- and Audio-Aware Adaptive Streaming — ML1 Implementation (Visual Feature Intelligence & Ground Truth)

## Overview

This repository implements the **ML1 (Machine Learning Engineer 1)** offline pipeline for the BetterStreamer project. ML1 owns the **Computer Vision, Video Processing, and Perceptual Ground Truth** pipeline — extracting quantitative motion and spatial complexity metrics from raw video, curating the benchmark corpus, encoding multi-bitrate ladders, and computing ground-truth perceptual quality scores (VMAF, SSIM).

**Deliverables flow into:**
- **DC (Rust Engine)**: Feature vectors + VMAF/size lookup tables via JSON manifests
- **ML2 (Decision Intelligence)**: Tabular training datasets for marginal-gain and weight-regression models
- **WB (Web & Demo)**: Encoded chunks + manifests for dashboard visualization

---

## Project Structure

```
BetterStreamer/
├── config/                 # Configuration files
│   ├── ml1_pipeline.yaml   # Main pipeline paths, 2s chunks, 30fps
│   ├── encoding.yaml       # Video/audio ladder (5 rungs each)
│   ├── features.yaml       # Feature extraction params, calibration percentiles
│   └── vmaf.yaml           # VMAF model paths
├── data/                   # Generated data (git-ignored)
│   ├── input/              # USER: Place test videos here (.mp4)
│   ├── chunks/             # Encoded chunks per video
│   │   └── <video_id>/
│   │       ├── source_normalized.mp4
│   │       ├── source/                 # 2s source chunks
│   │       ├── rung_0/ .. rung_4/      # 5-rung H.264 video (fMP4)
│   │       ├── audio_rung_0/ .. 4/     # 5-rung Opus audio (fMP4)
│   │       ├── features_raw.json
│   │       ├── features_normalized.json
│   │       ├── vmaf_results.json
│   │       ├── ssim_results.json
│   │       └── audio_results.json
│   ├── calibration/        # Corpus calibration (p5/p95)
│   ├── manifests/          # DC contract manifests
│   ├── reports/            # R-D curves (PNG + CSV)
│   └── temp/               # Temporary artifacts
├── scripts/
│   └── pipeline/
│       ├── ingest/         # Phase 1: Ingest & Encode
│       │   ├── normalize.py
│       │   ├── chunk.py
│       │   ├── encode_video.py
│       │   └── encode_audio.py
│       ├── analysis/       # Phase 2: Feature Extraction
│       │   ├── motion.py
│       │   ├── complexity.py
│       │   └── priority.py
│       ├── ground_truth/   # Phase 3: Ground Truth
│       │   ├── vmaf.py
│       │   ├── ssim.py
│       │   ├── audio_quality.py
│       │   └── rd_curves.py
│       ├── manifest/       # Phase 4: Manifests & Contracts
│       │   ├── builder.py
│       │   ├── export_ml2.py
│       │   ├── schema.py
│       │   └── validator.py
│       ├── utils/          # Shared utilities
│       │   ├── calibration.py
│       │   └── ffmpeg.py
│       ├── run_all.py      # Phase 1 entry point
│       ├── run_analysis.py # Phase 2 entry point
│       ├── run_ground_truth.py # Phase 3 entry point
│       ├── run_manifest.py # Phase 4 entry point
│       └── validate.py     # Validation gates
├── tests/
│   └── fixtures/
│       └── ml_training_dataset.csv  # ML2 training data
├── PIPELINE.md             # End-to-end project specification
├── ML1.md                  # ML1 role specification
├── requirements.txt
└── pyproject.toml
```

---

## Pipeline Phases

### Phase 1: Ingest & Encode
**Entry point:** `python -m scripts.pipeline.run_all`

Transforms raw input video into a normalized, chunked, multi-bitrate ladder.

| Step | Script | Description |
|------|--------|-------------|
| **Normalize** | `ingest/normalize.py` | 1080p30 yuv420p, constant fps, CRF 18 |
| **Chunk** | `ingest/chunk.py` | 2s segments, stream-copy segmentation |
| **Encode Video** | `ingest/encode_video.py` | 5-rung H.264 ladder (2-pass, forced keyframes) |
| **Encode Audio** | `ingest/encode_audio.py` | 5-rung Opus ladder (fMP4) |

**Video Ladder:**
| Rung | Resolution | Target Bitrate |
|------|------------|----------------|
| 0 | 640×360 | 400 kbps |
| 1 | 854×480 | 800 kbps |
| 2 | 1280×720 | 1500 kbps |
| 3 | 1920×1080 | 3000 kbps |
| 4 | 1920×1080 | 6000 kbps |

**Audio Ladder:** Opus at 24, 48, 64, 96, 128 kbps

**Validation Gates (M1):**
- All chunks exist (5 video + 5 audio rungs × N chunks)
- All chunks decodable (`ffmpeg -v error -i chunk.m4s -f null -`)
- Keyframe at frame 0, then every 60 frames (2s @ 30fps)
- Sizes strictly increasing per chunk across rungs

---

### Phase 2: Feature Extraction
**Entry point:** `python -m scripts.pipeline.run_analysis`

Extracts per-chunk visual features and computes corpus calibration.

| Feature | Method | Normalization |
|---------|--------|---------------|
| **Motion** | Median MSFD on 360p grayscale | Corpus p5/p95 |
| **Complexity** | Laplacian variance (sampled frames) | Corpus p5/p95 |
| **Motion Vectors** | Mean MV magnitude from H.264 bitstream | Corpus p5/p95 (optional) |
| **Priority** | `clamp(0.6 × motion + 0.4 × complexity, 0, 1)` | — |

**Outputs:**
- `features_raw.json` — Raw motion, complexity, mv_magnitude per chunk
- `features_normalized.json` — Calibrated [0,1] features + priority per chunk
- `calibration.json` — Corpus p5/p95 percentiles for all features

---

### Phase 3: Ground Truth
**Entry point:** `python -m scripts.pipeline.run_ground_truth`

Computes perceptual quality metrics and rate-distortion curves.

| Metric | Method | Output |
|--------|--------|--------|
| **VMAF (TV)** | libvmaf default model, upscaled to 1080p | Mean, harmonic mean, min, max per chunk×rung |
| **VMAF (Phone)** | libvmaf phone model (fallback to default) | Same structure |
| **VMAF NEG** | Enhancement gaming guard (fallback to default) | Same structure |
| **SSIM** | Dynamic resolution matching | Mean per chunk×rung |
| **Audio Quality** | Placeholder (ViSQOL deferred) | Dummy 3.5 |

**R-D Curves:**
- Per-video: VMAF TV, VMAF Phone, SSIM vs. Size (PNG + CSV)
- Marginal gains: ΔVMAF/ΔMB per rung step per chunk
- Category aggregate: Mean curves across videos by genre

**Outputs:**
- `vmaf_results.json`, `ssim_results.json`, `audio_results.json`
- `rd_curves_<video_id>.png`, `rd_data_<video_id>.csv`
- `rd_curves_<category>.png` (aggregate)

---

### Phase 4: Manifests & Contracts
**Entry point:** `python -m scripts.pipeline.run_manifest`

Assembles frozen contracts for downstream consumers.

| Contract | Consumer | Format | Schema |
|----------|----------|--------|--------|
| **DC Manifest** | DC (Rust Engine) | JSON | `manifest/schema.py` — PIPELINE.md §6.1 |
| **ML2 CSV** | ML2 (Decision Models) | CSV | `manifest/export_ml2.py` — PIPELINE.md §4.2 |

**DC Manifest** (`data/manifests/<video_id>.json`):
- Video metadata: genre, segment duration, ladder bitrates
- Per-segment: features (motion, complexity, saliency, scene_tag, audio_class), video (sizes, VMAF TV/phone, SSIM), audio (sizes, quality)

**ML2 CSV** (`tests/fixtures/ml_training_dataset.csv`):
- One row per segment × rung (14 columns): chunk_id, category, segment_id, rung_id, motion, complexity, priority, bitrate_bps, sizes_bytes, vmaf, ssim, delta_vmaf_per_mb, vmaf_phone, audio_quality, audio_sizes_bytes

**Validation (M4/M5):**
- Manifest schema: required keys, array lengths, contiguous segment IDs, increasing sizes (1% tolerance), score ranges
- ML2 CSV: column match, row completeness

---

## Quick Start

### 1. Setup Environment
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Verify FFmpeg
```bash
ffmpeg -version
# Must have: libx264, libopus, libvmaf
```

### 3. Add Test Videos
Place your test videos in `data/input/` (any .mp4 files):
```
data/input/
├── your_video_1.mp4
├── your_video_2.mp4
└── ...
```

### 4. Run Full Pipeline
```bash
# Phase 1: Ingest & Encode
python -m scripts.pipeline.run_all

# Phase 2: Feature Extraction
python -m scripts.pipeline.run_analysis

# Phase 3: Ground Truth
python -m scripts.pipeline.run_ground_truth

# Phase 4: Manifests & ML2 Export
python -m scripts.pipeline.run_manifest
```

### 5. Validate
```bash
# Phase 1 validation
python -m scripts.pipeline.run_all --validate-only

# Phase 4 validation
python -m scripts.pipeline.run_manifest --validate-only
```

---

## Configuration

| File | Purpose |
|------|---------|
| `config/ml1_pipeline.yaml` | Paths, 2s chunks, 30fps, 1080p30 |
| `config/encoding.yaml` | Video/audio ladder, 2-pass, presets |
| `config/features.yaml` | Downscale (640×360), weights (0.6/0.4), percentiles (5/95) |
| `config/vmaf.yaml` | VMAF model directory |

---

## Requirements

- **Python** 3.10+
- **FFmpeg** 9.0+ with libx264, libopus, libvmaf
- **Dependencies:** numpy, scipy, pandas, opencv-python, scikit-image, av (PyAV), pyyaml, matplotlib

Install via `pip install -r requirements.txt`

---

## Output Contracts

### DC Manifest Schema
```json
{
  "video_id": "string",
  "genre": "talking_head|sports|action|text|mixed",
  "segment_duration_s": 2.0,
  "video_ladder_kbps": [400, 800, 1500, 3000, 6000],
  "audio_ladder_kbps": [24, 48, 64, 96, 128],
  "segments": [
    {
      "id": 0,
      "features": {"motion": 0.0, "complexity": 0.0, "saliency": 0.0, "scene_tag": "mixed", "audio_class": "speech"},
      "video": {"sizes_bytes": [...], "vmaf_tv": [...], "vmaf_phone": [...], "ssim": [...]},
      "audio": {"sizes_bytes": [...], "quality": [...]}
    }
  ]
}
```

### ML2 CSV Columns
```
chunk_id,category,segment_id,rung_id,motion,complexity,priority,bitrate_bps,sizes_bytes,vmaf,ssim,delta_vmaf_per_mb,vmaf_phone,audio_quality,audio_sizes_bytes
```

---

## License

Research project — see PIPELINE.md for scope.