# PIPELINE.md — BetterStreamer End-to-End Pipeline (v2, combined plan)

> **Project**: Content-, Device- and Audio-Aware Adaptive Streaming (`BetterStreamer`)
> **Scope**: Offline analysis and encoding, ground-truth quality tables, bandwidth allocation, deterministic network simulation, evaluation, and a demo dashboard. Live LL-HLS/CMAF is a stretch goal (Section 13).
> **Roles**: DC (Systems & Computing), ML1 (Vision, Audio & Ground Truth), ML2 (AI & Decision), WB (Web & Demo)

---

## 1. Point of view, question and scope

**Point of view.** One bandwidth budget, spent differently depending on what is on screen, which device is watching, and what the audio needs.

**What this is.** A decision layer for adaptive streaming plus a reproducible evaluation framework. It is not a full streaming platform: no accounts, catalogue, CDN or production player.

**Research question.** Can content-aware, device-aware and audio-aware bit allocation deliver more perceptual quality per delivered megabyte than a conventional ABR baseline under identical conditions?

**What we do not claim.** We do not claim that HLS/DASH or ABR research ignore content. The contribution is a measured comparison of an allocation policy against standard baselines.

**Primary metric.** VMAF (SSIM as support) per megabyte delivered, against an HLS/DASH-style baseline on a common clip set and network degradation profile. Secondary: rebuffering ratio and startup latency.

---

## 2. Evaluation contract (binding)

1. Every policy runs on **identical clips, identical encoded ladders and identical network trace replays**.
2. Every run takes a fixed **seed**. Same seed + same inputs gives a **byte-identical** report JSON.
3. **Clips**: 15 to 25 clips across 5 genres (talking head, sports, action/camera motion, text/lecture, mixed), several per genre.
4. **Network profiles**: `stable-high`, `moderate`, `sudden-degradation`, `highly-variable`, plus generated traces for training the forecaster.
5. **Policies compared**:
   - `baseline-ewma`: EWMA / harmonic-mean throughput + BOLA-lite buffer rule
   - `baseline-bola` (or MPC): one recognised published algorithm
   - `lowest-rung`: sanity check that exposes quality-per-MB gaming
   - `heuristic`: priority score + allocator
   - `ml-gain`: learned marginal-gain model + allocator
   - `oracle`: allocator using true VMAF values (the ceiling)
6. **No headline result is reported on synthetic quality.** Synthetic data is for unit tests only.
7. Report **VMAF-vs-MB curves** across several bandwidths, bytes saved at equal VMAF, a quality floor (e.g. 5th-percentile VMAF), quality-switch count, and audio quality per MB. A single ratio is never the only number.
8. **Train/test split by clip.** The forecaster is tested on held-out traces.
9. **Ablation**: baseline, heuristic, ML gain, ML gain + forecaster, oracle.

---

## 3. Architecture

```
 OFFLINE (encode time)                                          PLAYBACK (simulated)
┌────────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐   ┌────────────────┐
│ 1. INGEST  │─►│ 2. ANALYSIS  │─►│ 3. GROUND     │─►│ 4. MANIFEST│──►│ 5. DECISION    │
│  & ENCODE  │  │ motion,      │  │ TRUTH         │  │ (one frozen│   │ priority, gain │
│ video+audio│  │ complexity,  │  │ VMAF, SSIM,   │  │  schema)   │   │ model, forecast│
│  ladders   │  │ saliency, tags│ │ phone VMAF,   │  └────────────┘   │ + allocator    │
└────────────┘  └──────────────┘  │ audio score   │                   └───────┬────────┘
                                  └───────────────┘                           ▼
                                                              ┌────────────────────────┐
                                                              │ 6. DETERMINISTIC       │
                                                              │ SIMULATOR (trace replay│
                                                              │ buffer, stalls, startup)│
                                                              └───────────┬────────────┘
                                                                          ▼
                                                              ┌────────────────────────┐
                                                              │ 7. REPORT + DASHBOARD  │
                                                              └────────────────────────┘
```

**Key principle:** all heavy analysis (features, pretrained models, VMAF, model predictions) happens **offline and is stored in the manifest**. At playback the decision is a table lookup plus a small allocation, so AI adds no startup delay and runs stay deterministic.

---

## 4. Stage 1: Ingest and encode

### 4.1 Source normalisation
- 1080p, constant 30 fps (or 60 fps), `yuv420p`, monotonic PTS.
- Known duration; fixed frame rate.
- Audio is demuxed and handled separately (Section 4.4).

### 4.2 Chunking
- **4.0 s chunks (120 frames at 30 fps)**, closed GOP, every chunk starts with an IDR frame.
- No scene-cut keyframes (`-sc_threshold 0`) so all rungs switch at identical timestamps.
- First chunk may be shortened or forced to a low rung for fast startup (Section 7.6).

### 4.3 Video ladder

| Rung | Resolution | Target | Max | VBV buffer | Profile |
|:---:|:---:|:---:|:---:|:---:|:---|
| 0 | 640x360 | 400 kbps | 440 kbps | 800 kbps | H.264 Main |
| 1 | 854x480 | 800 kbps | 880 kbps | 1600 kbps | H.264 Main |
| 2 | 1280x720 | 1500 kbps | 1650 kbps | 3000 kbps | H.264 High |
| 3 | 1920x1080 | 3000 kbps | 3300 kbps | 6000 kbps | H.264 High |
| 4 | 1920x1080 | 6000 kbps | 6600 kbps | 12000 kbps | H.264 High |

Encode **each rung as its own run** (not one `-filter_complex` with shared `-s:v`), so scaling and rate control apply to the intended stream:

```bash
# encode_rung.sh  <input> <rung> <width> <height> <kbps>
IN=$1; R=$2; W=$3; H=$4; K=$5
ffmpeg -hide_banner -y -i "$IN" -an \
  -vf "scale=${W}:${H}:flags=lanczos,format=yuv420p" \
  -c:v libx264 -preset medium -b:v ${K}k -maxrate $((K*11/10))k -bufsize $((K*2))k \
  -g 120 -keyint_min 120 -sc_threshold 0 \
  -force_key_frames "expr:gte(t,n_forced*4)" \
  -f hls -hls_time 4 -hls_playlist_type vod -hls_segment_type fmp4 \
  -hls_segment_filename "media/chunks/rung_${R}/chunk_%03d.m4s" \
  "media/manifests/rung_${R}.m3u8"
```

Notes:
- Do **not** use `-tune zerolatency` for VOD (it disables lookahead and B-frames and lowers quality per MB).
- Two-pass or capped-CRF encoding may be used per rung; whichever is chosen is fixed for every policy.
- Real per-chunk file sizes are recorded, since actual sizes (not nominal bitrates) drive the allocator.

### 4.4 Audio ladder
- Opus rungs, for example 24, 48, 64, 96 and 128 kbps, cut into the same 4.0 s chunks.
- Silence/speech/music segments are tagged (Section 5.4) so silent stretches can use the lowest rung or DTX.
- The audio ladder is a second set of rungs in the same budget problem (Section 8.4).

---

## 5. Stage 2: Content analysis (offline)

Features are extracted per chunk on a downscaled grayscale (360p) luma plane, or from encoder motion vectors. Raw values are normalised to `[0, 1]` using **calibration percentiles computed on the corpus** (saved in `calibration.json`), not hard-coded constants.

### 5.1 Motion `M(c)`
- Median (not mean) of mean-squared frame differences across the chunk, so a single scene cut inside a chunk does not mark the whole chunk as high motion.
- Optional: mean motion-vector magnitude from the H.264 bitstream; optical-flow variance as a supporting feature.

### 5.2 Spatial complexity `C(c)`
- Mean Laplacian variance, high-frequency DCT energy ratio, and texture entropy.

### 5.3 Reference implementation (`scripts/extract_features.py`)

```python
import cv2
import numpy as np

def raw_chunk_features(frames_gray_360p):
    """frames_gray_360p: list of 2-D uint8 arrays (one chunk). Returns raw (motion, complexity)."""
    frames = np.asarray(frames_gray_360p, dtype=np.float32)   # cast first: uint8 subtraction wraps
    if len(frames) < 2:
        return 0.0, 0.0
    diffs = np.mean((frames[1:] - frames[:-1]) ** 2, axis=(1, 2))
    motion = float(np.median(diffs))                          # robust to scene cuts
    lap_vars = [cv2.Laplacian(f, cv2.CV_32F).var() for f in frames]
    complexity = float(np.mean(lap_vars))
    return motion, complexity

def normalise(raw, p_low, p_high):
    """Calibrated min-max using corpus percentiles (e.g. p5, p95)."""
    if p_high <= p_low:
        return 0.0
    return float(np.clip((raw - p_low) / (p_high - p_low), 0.0, 1.0))
```

### 5.4 Pretrained models (run offline, outputs stored in the manifest)
- **Scene tags** (CLIP/SigLIP-style) as extra features.
- **Faces and text regions** (a small detector) for saliency weighting, so complexity inside an attention region counts for more.
- **Audio class** (speech / music / silence) from a pretrained audio classifier.
- Each model's **revision and seed are pinned and recorded** in the report; licences are checked.
- Every pretrained feature is **ablated**. If it does not improve quality per MB, it is dropped.

---

## 6. Stage 3: Ground truth (offline)

- **VMAF** per chunk and rung, computed at **display resolution** (lower rungs upscaled to 1080p) with libvmaf, plus the **VMAF NEG** variant to guard against enhancement-style metric gaming.
- **Phone-model VMAF** (libvmaf phone model) as a second table for the device profile.
- **SSIM** per chunk and rung as supporting metric.
- **Audio quality** per chunk and audio rung with a perceptual audio metric (e.g. ViSQOL).
- **Real sizes** in bytes for every chunk and rung.

### 6.1 Frozen manifest schema (one file per clip)

```json
{
  "video_id": "sports_dynamic_01",
  "genre": "sports",
  "segment_duration_s": 4.0,
  "video_ladder_kbps": [400, 800, 1500, 3000, 6000],
  "audio_ladder_kbps": [24, 48, 64, 96, 128],
  "segments": [
    {
      "id": 0,
      "features": { "motion": 0.82, "complexity": 0.65, "saliency": 0.4,
                    "scene_tag": "sports", "audio_class": "speech" },
      "video": {
        "sizes_bytes": [200000, 400000, 750000, 1500000, 3000000],
        "vmaf_tv":     [62.4, 76.1, 88.5, 94.2, 97.8],
        "vmaf_phone":  [70.1, 82.0, 91.3, 95.0, 97.0],
        "ssim":        [0.90, 0.94, 0.97, 0.985, 0.992]
      },
      "audio": {
        "sizes_bytes": [12000, 24000, 32000, 48000, 64000],
        "quality":     [3.1, 3.6, 3.9, 4.2, 4.4]
      }
    }
  ]
}
```

### 6.2 Manifest validation
- Sizes strictly increase across rungs; scores in valid ranges; no NaN; no missing chunk.
- Every chunk decodes independently: `ffmpeg -v error -i chunk.m4s -f null -`.
- Keyframes align across rungs: `ffprobe -show_frames -select_streams v`.

---

## 7. Stage 4: Decision intelligence

### 7.1 Deterministic priority (the heuristic arm)
```
Priority(c) = clamp(w_m * Motion(c) + w_c * Complexity(c), 0, 1)
```
Defaults `w_m = 0.6`, `w_c = 0.4` (tuned per genre by ML2). Buckets: Low (<0.34), Medium (<0.67), High. A static-but-complex case (lecture slides) is an explicit unit test, since motion-only logic starves it.

### 7.2 Marginal-gain model (the `ml-gain` arm, trained by us)
A small gradient-boosted or MLP model predicts, for each chunk and each rung step, the **absolute quality gain** of moving from rung `r-1` to `r`:

```
gain(c, r) = Quality(c, r) - Quality(c, r-1)
```

Inputs: motion, complexity, saliency, scene tag, genre, rung, device profile. The allocator divides by the **byte cost** of the step (Section 8), so the model output is not divided twice. Targets: hold-out R² of at least 0.82 on unseen clips; inference under 1 ms per chunk; deterministic outputs; fallback to the heuristic on failure or out-of-distribution input.

### 7.3 Throughput forecaster
- Predicts throughput `T_{t+1..t+k}` from recent throughput, RTT and buffer state.
- Candidates: EWMA / Holt-Winters (simple baseline), a small TCN or GRU, and optionally a pretrained time-series model.
- Trained on many generated traces; **tested on the four held-out named profiles**.
- The simple forecaster is always reported alongside; if it is nearly as good, that is stated.

### 7.4 Device profile (viewer-aware signal)
- Profiles: `phone`, `tv` (optionally `laptop`).
- The profile selects the quality table (`vmaf_phone` vs `vmaf_tv`) and may cap the ladder (a phone does not need 1080p at 6000 kbps).
- The same clip and network therefore produce different allocations per device, which is the personalisation shown in the demo.

### 7.5 Viewer preference profiles (extension)
Smoothness-sensitive and quality-sensitive weightings of the reward (rebuffering and switch penalties vs. peak quality).

### 7.6 Startup and prefetch
- Start on a low rung with a short first chunk; use the forecaster to prefetch upcoming chunks and ramp up.
- Startup latency (time to first frame) is measured as a reported metric.

---

## 8. Stage 5: Bandwidth allocator (Rust core)

### 8.1 Problem
```
maximise   sum_i Quality(c_i, r_i)      subject to   sum_i Bytes(c_i, r_i) <= Budget
```

### 8.2 Windowed policy (how per-segment decisions connect to the allocator)
At each decision point the policy:
1. looks ahead `K` segments (`K = 8` for VOD),
2. sets `Budget = forecast_throughput * window_time - safety_margin`,
3. runs the allocator over the window,
4. **commits only the first segment's rung**,
5. repeats at the next segment.

### 8.3 Greedy marginal allocation (fixed math)
1. **Prune** each segment's rungs to the **convex hull** of (bytes, quality), removing rungs that are dominated or lie below the hull.
2. Start every segment at its lowest hull rung. If even this exceeds the budget, return an explicit infeasibility error (the budget invariant is never silently violated).
3. Repeatedly upgrade the segment with the highest
   `ratio = (Quality(next) - Quality(current)) / (Bytes(next) - Bytes(current))`
   that still fits in the remaining budget.
4. Offline **DP knapsack** gives the optimal upper bound for benchmarking.

```rust
pub enum AllocError { InfeasibleBudget }

/// sizes[i][r], quality[i][r]: strictly increasing sizes per segment.
fn hull(sizes: &[u64], q: &[f64]) -> Vec<usize> {
    let mut h: Vec<usize> = Vec::new();
    for i in 0..sizes.len() {
        if let Some(&l) = h.last() {
            if q[i] <= q[l] { continue; }            // no quality gain for more bytes
        }
        while h.len() >= 2 {
            let (a, b) = (h[h.len() - 2], h[h.len() - 1]);
            let s_ab = (q[b] - q[a]) / (sizes[b] - sizes[a]) as f64;
            let s_bi = (q[i] - q[b]) / (sizes[i] - sizes[b]) as f64;
            if s_ab <= s_bi { h.pop(); } else { break; }   // b is below the hull
        }
        h.push(i);
    }
    h
}

pub fn allocate_greedy(
    sizes: &[Vec<u64>],
    quality: &[Vec<f64>],
    budget: u64,
) -> Result<Vec<usize>, AllocError> {
    let hulls: Vec<Vec<usize>> = (0..sizes.len()).map(|i| hull(&sizes[i], &quality[i])).collect();
    let mut pos = vec![0usize; sizes.len()];
    let mut used: u64 = (0..sizes.len()).map(|i| sizes[i][hulls[i][0]]).sum();
    if used > budget { return Err(AllocError::InfeasibleBudget); }

    loop {
        let mut best: Option<(usize, f64, u64)> = None;     // (segment, ratio, cost)
        for i in 0..sizes.len() {
            if pos[i] + 1 >= hulls[i].len() { continue; }
            let (cur, nxt) = (hulls[i][pos[i]], hulls[i][pos[i] + 1]);
            let cost = sizes[i][nxt] - sizes[i][cur];
            if cost == 0 || used + cost > budget { continue; }
            let ratio = (quality[i][nxt] - quality[i][cur]) / cost as f64;
            if best.map_or(true, |(_, r, _)| ratio > r) { best = Some((i, ratio, cost)); }
        }
        match best {
            Some((i, _, cost)) => { pos[i] += 1; used += cost; }
            None => break,
        }
    }
    Ok((0..sizes.len()).map(|i| hulls[i][pos[i]]).collect())
}
```

The invariant `total bytes <= budget` is enforced with `proptest`, together with a monotonicity test (a larger budget never lowers total quality).

### 8.4 Joint audio and video budget
Audio rungs are additional upgrade steps in the same greedy loop, with their own quality table. The same ratio rule decides whether the next byte is better spent upgrading video or audio for that segment. Speech-heavy genres (talking head, lecture) naturally shift budget toward audio; action content shifts it toward video. Silent segments use the lowest audio rung.

### 8.5 Buffer safety governor
Applied after allocation and overriding content priority (buffer thresholds are tuned to the player's buffer capacity, e.g. 12 to 20 s):
- Critical (`b < 2 s`): force the lowest rung.
- Depleted (`2 s <= b < 6 s`): cap at rung 2.
- Comfortable (`b >= 6 s`): unrestricted content-aware choice.

---

## 9. Stage 6: Deterministic simulator (Rust)

- Replays CSV traces (`time_s,bandwidth_mbps`) as a step function; validated for positive values and strictly increasing time.
- **Download time** = chunk bytes divided by the integral of bandwidth over time, plus RTT.
- Event-driven player: buffer level, playback time, stalls, startup, quality switches. **No wall-clock dependence.**
- All randomness (e.g. jitter) is seeded from `SimulatorConfig`.
- `betterstreamer compare` runs every policy on every clip and trace and writes `results.json`.
- **Policy trait:**
  ```rust
  pub trait AbrPolicy {
      fn select(&mut self, ctx: &PlayerCtx, segment: &Segment) -> RepresentationId;
  }
  ```

---

## 10. Stage 7: Report and dashboard

### 10.1 Report schema (one shape for CLI, evaluation and dashboard)
```json
{
  "simulation_id": "sim_001",
  "config": { "seed": 42, "segment_duration_s": 4.0, "device": "phone" },
  "video": "sports_dynamic_01",
  "trace": "sudden-degradation",
  "summary": {
    "baseline-bola": { "mean_vmaf": 0, "vmaf_p5": 0, "total_mb": 0, "vmaf_per_mb": 0,
                       "rebuffer_ratio": 0, "startup_s": 0, "switches": 0, "audio_q_per_mb": 0 },
    "ml-gain":       { "mean_vmaf": 0, "vmaf_p5": 0, "total_mb": 0, "vmaf_per_mb": 0,
                       "rebuffer_ratio": 0, "startup_s": 0, "switches": 0, "audio_q_per_mb": 0 }
  },
  "timeline": [
    { "segment_id": 0, "bandwidth_mbps": 5.0, "chosen_video": {"baseline-bola": 3, "ml-gain": 4},
      "chosen_audio": {"baseline-bola": 2, "ml-gain": 1},
      "buffer_s": {"baseline-bola": 4.0, "ml-gain": 4.0} }
  ]
}
```
(Values above are placeholders; real numbers come only from runs.)

### 10.2 Dashboard (WB)
- Control bar: clip, network profile, device, weights, policy toggle, Run.
- Dual players (baseline vs content-aware) with a HUD for rung, VMAF and priority.
- Charts: bandwidth vs chosen bitrate, buffer level, VMAF per chunk, cumulative MB.
- Scorecard and an evaluation page (VMAF-vs-MB curves, ablation).
- The dashboard **only renders the report**; it never recomputes metrics, and it is labelled "simulated network".
- Export: JSON, CSV, printable PDF.

---

## 11. Latency and startup (VOD)

Everything expensive happens at encode time. On the playback path:

| Step | Cost | Note |
|:---|:---|:---|
| Manifest load | one fetch | features, sizes and quality tables already inside |
| Priority / gain lookup | table lookup | model outputs precomputed offline |
| Allocation over `K=8` window | target under 1 ms | measured in a benchmark |
| Governor | negligible | |
| First chunk | download time of a low-rung short chunk | dominates startup latency |

Report **decision time per chunk** and **startup latency** as measured numbers next to quality per MB. No latency figure is quoted until measured.

---

## 12. Verification checklist

| Component | Acceptance criterion | How |
|---|---|---|
| Segmentation | Aligned keyframes across rungs; chunks decode alone | `ffprobe`, `ffmpeg -f null` |
| Manifest | Sizes strictly increasing; no NaN; schema valid | validator test |
| Features | Scores in [0, 1]; scene-cut robust | unit tests |
| Allocator | Budget never exceeded; monotone in budget; DP bound >= greedy | `proptest` |
| Governor | Never selects above the zone cap | unit tests |
| Simulator | Byte-identical report on rerun | determinism integration test |
| Gain model | Hold-out R² >= 0.82; < 1 ms; deterministic | model validation suite |
| Forecaster | Beats or matches EWMA on held-out traces | evaluation script |
| Evaluation | Curves on all clips and traces; ablation complete | `betterstreamer compare` |
| Dashboard | Numbers equal report values exactly | UI test |

---

## 13. Stretch goals (only after the core is complete)

- **Live reprocessing with LL-HLS / CMAF** (2 s chunks, 500 ms parts, preload hints). Analysis would run on the source in parallel with encoding, per part, using only cheap deterministic features (no ML on the live path). Latency numbers must be re-derived and measured, not assumed.
- **Server-side dynamic rate control** (Mode B) and a client-side hls.js plugin reading `#EXT-X-DATERANGE` priority metadata.
- **Receiver-side super-resolution**: send a lower rung and upscale on the client, reported as a **separate, clearly labelled arm** with client compute cost counted, scored with VMAF NEG and SSIM.

---

## 14. Out of scope

- Age or demographic inference from frames. If ads are explored, selection is contextual (based on scene content), never based on guessing the viewer.
- Heavy frame-by-frame generative enhancement.
- Accounts, catalogues, recommendations, CDN operations.

---

## 15. Milestones and roles

| Phase | Deliverable | Owner | Gate |
|:---:|:---|:---:|:---|
| 1 | Clips, video/audio ladders, manifest loader | ML1, DC | Chunks decode alone; sizes monotonic |
| 2 | Features (motion, complexity, saliency) | ML1 | Bounded, no NaN |
| 3 | Baselines + deterministic simulator | DC | Deterministic rerun matches |
| 4 | Allocator + DP bound | DC | Budget property test passes |
| 5 | Real VMAF / phone / audio tables + evaluation | ML1, DC | Curves on all clips and traces |
| 6 | Gain model, forecaster, joint audio budget | ML2 | Hold-out R²; no rebuffer regression |
| 7 | Dashboard replay + export | WB | Matches report exactly |
| 8 | Stretch: live LL-HLS, super-resolution arm | all | Only if time remains |

**Ownership summary**
- **DC**: simulator, allocator, baselines, report schema, `compare` CLI.
- **ML1**: clips, encoding, features, VMAF/SSIM/audio tables, manifest.
- **ML2**: gain model, forecaster, weight tuning, pretrained-model integration.
- **WB**: backend runner, dashboard, evaluation page, export.
