# PIPELINE.md — End-to-End System Pipeline Architecture

> **Project**: Content-Aware Adaptive Bitrate Streaming (`BetterStreamer`)  
> **Location**: `MarkDocumentation/PIPELINE.md`  
> **Scope**: Complete Pipeline from Video Ingestion and Segmentation to AI Chunk Analysis, Bandwidth Allocation, and Low-Latency Livestream Reprocessing  
> **Authors & Roles**: DC (Systems & Computing), ML1 (Vision & Features), ML2 (AI & Decision), WB (Web & Delivery)  

---

## 1. High-Level Architectural Blueprint

The **BetterStreamer** pipeline transforms continuous video streams into intelligent, content-aware adaptive media. Traditional Adaptive Bitrate (ABR) streaming (HLS / MPEG-DASH) treats every chunk uniformly: representation switching decisions depend strictly on estimated client throughput and buffer fill levels. 

BetterStreamer introduces **Content Awareness** into the streaming pipeline:
1. Chunks are ingested and split into strictly aligned, independent segments.
2. Lightweight Computer Vision and AI extract temporal motion and spatial complexity metrics.
3. Machine learning models predict marginal perceptual gain ($\Delta\text{VMAF}/\Delta\text{MB}$) and forecast near-future network throughput.
4. A constrained optimization allocator in Rust distributes the available bandwidth budget so visually complex chunks receive higher bitrates while visually simple chunks receive fewer bits.
5. In live streaming mode, the stream is reprocessed using low-latency packaging (LL-HLS / CMAF), smart manifest tagging, or server-side dynamic rate control to deliver superior perceptual quality per megabyte with zero rebuffering regressions.

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   END-TO-END SYSTEM PIPELINE                                           │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘

 ┌───────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
 │ 1. INGESTION  │ ───► │   2. SEGMENTATION      │ ───► │  3. CONTENT ANALYSIS   │
 │   & DEMUX     │      │   & LADDER ENCODE      │      │     (AI / CV ENGINE)   │
 └───────────────┘      └────────────────────────┘      └────────────────────────┘
  RTMP / SRT / File      Closed GOP (2s / 4s)            Motion (MSFD / Vectors)
  Video Normalization    Multi-Rung Ladder (360p-1080p)  Spatial Energy (Laplacian)
  Timestamp Sync (PTS)   IDR Keyframe Alignment          Saliency / RoI Attention
                                                                    │
                                                                    ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ 4. AI INFERENCE & DECISION INTELLIGENCE                                               │
 │    • Deterministic Priority Score: Priority(c) = w_m · Motion(c) + w_c · Complex(c)   │
 │    • Marginal Gain Model: Predict ΔVMAF / ΔMB per candidate rung                     │
 │    • Throughput Forecaster: Time-series prediction (T_{t+1}) for early cliff warning  │
 └───────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ 5. CONTENT-AWARE BITRATE ALLOCATION (CORE RUST ENGINE)                                │
 │    • Constrained Optimization: Maximize Σ Quality(c_i) subject to Σ Bits(c_i) ≤ Budget │
 │    • Greedy Marginal Allocation / Dynamic Programming Knapsack                        │
 │    • Buffer Safety Governor (BOLA-lite / Rebuffer Prevention)                         │
 └───────────────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
 ┌────────────────────────┐      ┌────────────────────────┐      ┌───────────────────────┐
 │  6. LIVE REPROCESSING  │ ───► │ 7. PACKAGING & MANIFEST│ ───► │ 8. CLIENT PLAYBACK    │
 │    & STREAM PIPELINE   │      │    (LL-HLS / CMAF)     │      │    & TELEMETRY LOOP   │
 └────────────────────────┘      └────────────────────────┘      └───────────────────────┘
  Sliding Window Ingestion        Dynamic .m3u8 / .mpd            Synchronized Player
  Chunked Transfer (CTE)          Metadata Enrichment             Real-time Buffer & QoE
  Low-Latency Transcoding         Preload Hints (#EXT-X)          Feedback to ML2 & Sim
```

---

## 2. Stage 1: Video Ingestion & Chunking ("Breaking the Video")

### 2.1 Ingest Protocol & Demuxing
The ingestion stage accepts raw or compressed continuous media from two sources:
- **VOD / Benchmark Suite**: High-bitrate master files (ProRes, DNxHR, or uncompressed YUV420p raw video) ingested via filesystem.
- **Livestream Broadcast**: Real-time broadcast feeds ingested over **RTMP** (`rtmp://origin:1935/live`), **SRT** (Secure Reliable Transport with Caller/Listener ARQ packet recovery), or **WebRTC / WHIP** for sub-second contribution feeds.

During ingestion, the video and audio tracks are demuxed. Video frames are normalized:
- **Color Format**: `YUV420p` (planar 8-bit).
- **Frame Rate**: Fixed frame cadence (e.g., 30.0 fps or 60.0 fps) with strictly monotonically increasing Presentation Time Stamps (`PTS`) and Decode Time Stamps (`DTS`).

### 2.2 GOP Structure & Independent Chunking
For adaptive bitrate streaming, segments must be **completely self-contained** and aligned across representations:
1. **Closed GOP (Group of Pictures)**:
   - Every chunk begins with an **IDR-frame (Instantaneous Decoder Refresh)**.
   - No frame in chunk $N$ can use motion prediction from chunk $N-1$ or chunk $N+1$.
2. **Strict Time Cadence Alignment**:
   - VOD / Standard Streaming: **4.0 seconds per segment** (120 frames at 30 fps).
   - Low-Latency Livestreaming: **2.0 seconds per segment** (60 frames at 30 fps), with **500 ms sub-chunks** for CMAF chunked transfer.
   - Scene change detection must not insert arbitrary unaligned keyframes (`-sc_threshold 0`), ensuring every representation switches at identical PTS timestamps.

### 2.3 Multi-Bitrate Representation Ladder
Each chunk is encoded into 5 discrete representation rungs matching the BetterStreamer ladder specification:

| Rung | Resolution | Target Bitrate | Max Bitrate | VBV Buffer | Codec Profile | Primary Use Case |
|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **0** | $640 \times 360$ | 400 kbps | 440 kbps | 800 kbps | H.264 Main L3.0 | Emergency fallback / low bandwidth |
| **1** | $854 \times 480$ | 800 kbps | 880 kbps | 1600 kbps | H.264 Main L3.1 | Cellular edge / simple scenes |
| **2** | $1280 \times 720$ | 1500 kbps | 1650 kbps | 3000 kbps | H.264 High L3.2 | Standard mobile / moderate scenes |
| **3** | $1920 \times 1080$ | 3000 kbps | 3300 kbps | 6000 kbps | H.264 High L4.0 | High definition / complex scenes |
| **4** | $1920 \times 1080$ | 6000 kbps | 6600 kbps | 12000 kbps | H.264 High L4.1 | Premium quality / dynamic action |

### 2.4 Production Transcode Command (FFmpeg)
```bash
ffmpeg -hide_banner -y -i input_source.mp4 \
  -filter_complex "[0:v]split=5[v0][v1][v2][v3][v4]" \
  -map "[v0]" -s:v 640x360   -c:v:0 libx264 -b:v:0 400k  -maxrate:v:0 440k  -bufsize:v:0 800k \
  -map "[v1]" -s:v 854x480   -c:v:1 libx264 -b:v:1 800k  -maxrate:v:1 880k  -bufsize:v:1 1600k \
  -map "[v2]" -s:v 1280x720  -c:v:2 libx264 -b:v:2 1500k -maxrate:v:2 1650k -bufsize:v:2 3000k \
  -map "[v3]" -s:v 1920x1080 -c:v:3 libx264 -b:v:3 3000k -maxrate:v:3 3300k -bufsize:v:3 6000k \
  -map "[v4]" -s:v 1920x1080 -c:v:4 libx264 -b:v:4 6000k -maxrate:v:4 6600k -bufsize:v:4 12000k \
  -g 120 -keyint_min 120 -sc_threshold 0 \
  -force_key_frames "expr:gte(t,n_forced*4)" \
  -preset veryfast -tune zerolatency \
  -f hls -hls_time 4 -hls_playlist_type vod \
  -hls_segment_type fmp4 \
  -hls_segment_filename "media/chunks/rung_%v/chunk_%03d.m4s" \
  media/manifests/manifest_%v.m3u8
```

---

## 3. Stage 2: Content Analysis & Feature Extraction

Every chunk undergoes lightweight computer vision analysis to compute continuous visual characteristics. To meet live processing budgets, feature extraction runs on downsampled grayscale luminance frames ($360\text{p}$) or extracts motion vectors directly from the encoder's bitstream.

```
                  ┌────────────────────────────────────────┐
                  │          Raw Video Chunk (c)           │
                  └──────────────────┬─────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │ Y-Plane Downscaled (360p) │ H.264 Bitstream           │ Saliency / Attention
         ▼                           ▼                           ▼
 ┌───────────────┐           ┌───────────────┐           ┌───────────────┐
 │ Frame Diffs   │           │ Motion Vector │           │ Face / Text   │
 │ & Laplacians  │           │ Macroblocks   │           │ Detection     │
 └───────┬───────┘           └───────┬───────┘           └───────┬───────┘
         │                           │                           │
         ▼                           ▼                           ▼
 ┌───────────────────────────────────────────────────────────────────────┐
 │ Continuous Normalized Features: Motion M(c) ∈ [0,1], Complex C(c) ∈ [0,1]│
 └───────────────────────────────────────────────────────────────────────┘
```

### 3.1 Temporal Motion Estimation ($M$)
Captures the magnitude and velocity of temporal changes between consecutive frames:
1. **Mean Squared Frame Difference (MSFD)**:
   $$\text{MSFD}(c) = \frac{1}{(T-1) \cdot W \cdot H} \sum_{t=1}^{T-1} \sum_{x=1}^{W} \sum_{y=1}^{H} \left( Y_t(x, y) - Y_{t-1}(x, y) \right)^2$$
2. **Motion Vector Velocity from Macroblocks**:
   Extracted without decoding via FFmpeg / PyAV:
   $$\text{MV\_Mag}(c) = \frac{1}{N_{MB}} \sum_{i=1}^{N_{MB}} \sqrt{dx_i^2 + dy_i^2}$$
3. **Normalization**:
   Normalized to $M(c) \in [0.0, 1.0]$. A static podcast interview scores $M \approx 0.04$; soccer or auto-racing scores $M \approx 0.88$.

### 3.2 Spatial Complexity Estimation ($C$)
Measures high-frequency detail, edge sharpness, and texture entropy:
1. **Laplacian Variance**:
   $$\sigma^2_{\text{Laplacian}}(c) = \frac{1}{T} \sum_{t=1}^T \text{Var}\left( \nabla^2 Y_t \right)$$
2. **High-Frequency 2D-DCT Energy**:
   Measures energy concentration in high-frequency AC coefficients of $8 \times 8$ blocks.
3. **Normalization**:
   Mapped to $C(c) \in [0.0, 1.0]$. Cartoon or blurry background scenes score $C \approx 0.12$; high-density code slides or dense forest scenes score $C \approx 0.85$.

### 3.3 Visual Saliency & Perceptual Attention (Extension)
- Employs lightweight Region-of-Interest (RoI) weighting: detects human faces and text regions.
- When spatial detail is concentrated within an active face bounding box or slide text, the complexity score is boosted to avoid visible blur where the viewer's gaze is focused.

---

## 4. Stage 3: AI Inference & Decision Intelligence

### 4.1 Deterministic Priority Scoring Engine
The deterministic foundation calculates a priority score combining motion and complexity:
$$\text{Priority}(c) = \text{clamp}\left(w_m \cdot M(c) + w_c \cdot C(c), 0.0, 1.0\right)$$

- Default configuration: $w_m = 0.60$, $w_c = 0.40$.
- **Classification Tiers**:
  - **Low ($0.00 - 0.33$)**: Simple scenes. Quality saturates at low bitrates; extra bits produce negligible VMAF improvements.
  - **Medium ($0.34 - 0.66$)**: Standard visual dynamics. Allocated nominal ladder rungs.
  - **High ($0.67 - 1.00$)**: Complex / dynamic action. Vulnerable to macroblocking; prioritized for top bitrates.

### 4.2 Machine Learning: Marginal Perceptual Gain Predictor ($\Delta\text{VMAF} / \Delta\text{MB}$)
Rather than relying solely on static weights, ML2 trains a supervised model (CatBoost / lightweight MLP) predicting the exact rate-distortion slope:
$$\widehat{\Delta}(c, r) = \mathbb{E}\left[\frac{\text{VMAF}(c, r) - \text{VMAF}(c, r-1)}{\text{SizeMB}(c, r) - \text{SizeMB}(c, r-1)}\right]$$

- **The Rate-Distortion Asymmetry**:
  - *Talking Head*: Upgrading from 800 kbps to 3000 kbps yields $+1.5$ VMAF points ($\Delta\text{VMAF}/\Delta\text{MB} \approx 1.2$).
  - *Action / Sports*: Upgrading from 800 kbps to 3000 kbps yields $+14.2$ VMAF points ($\Delta\text{VMAF}/\Delta\text{MB} \approx 11.8$).
  - The model guides the allocator to spend bits where human visual perception reaps the highest return.

### 4.3 Predictive Network Throughput Forecaster
Standard ABR is reactive: it detects throughput collapse only after a chunk download stalls. ML2 introduces an autoregressive time-series predictor (TCN / GRU):
$$\widehat{T}_{t+1}, \dots, \widehat{T}_{t+k} = \text{Model}\left(\{T_{t-i}\}_{i=0}^N, \{\text{RTT}_{t-i}\}_{i=0}^N, \text{LossRate}_t\right)$$

- When a sudden degradation is predicted 3–5 seconds ahead, the system proactively shifts upcoming low-priority chunks to lower bitrates, preserving buffer headroom and **completely eliminating rebuffering stalls**.

---

## 5. Stage 4: Bandwidth-Aware Bitrate Allocation Engine (Rust Core)

The core allocation engine in `src/abr/allocator.rs` distributes the available bandwidth budget across a sliding window of $K$ chunks ($K=8$ in VOD, $K=2$ in low-latency live).

```
Network Bandwidth Budget B ───┐
Predicted Throughput Curve ───┼──► Constrained Allocator (Rust) ──► Selected Rung IDs [r_0, r_1, ..., r_K]
Chunk Priority & Marginal VMAF│     (Greedy Marginal Utility)
Player Buffer Level b(t) ─────┘
```

### 5.1 Optimization Formulation
$$\max_{\{r_1, \dots, r_K\}} \sum_{i=1}^K \text{Quality}(c_i, r_i) \quad \text{subject to} \quad \sum_{i=1}^K \text{Bytes}(c_i, r_i) \le B_{\text{budget}}$$

### 5.2 Greedy Marginal Utility Allocation Algorithm
1. **Initialization**: Assign all $K$ chunks to the lowest representation rung: $r_i \leftarrow 0$.
2. **Budget Verification**:
   $$B_{\text{consumed}} = \sum_{i=1}^K \text{Bytes}(c_i, 0), \quad B_{\text{remaining}} = B_{\text{budget}} - B_{\text{consumed}}$$
3. **Iterative Step**:
   - While $B_{\text{remaining}} > 0$:
     - For every chunk $i$ where $r_i < r_{\max}$:
       $$\text{Gain}_i = \frac{\widehat{\Delta}(c_i, r_i + 1)}{\Delta\text{Bytes}(c_i, r_i \to r_i + 1)}$$
     - Find chunk $i^* = \arg\max \text{Gain}_i$.
     - If $\Delta\text{Bytes}(c_{i^*}, r_{i^*} \to r_{i^*} + 1) \le B_{\text{remaining}}$:
       - Upgrade rung: $r_{i^*} \leftarrow r_{i^*} + 1$.
       - Deduct bytes: $B_{\text{remaining}} \leftarrow B_{\text{remaining}} - \Delta\text{Bytes}$.
     - Else: break or evaluate next best candidate.

### 5.3 Buffer Safety Governor (BOLA-lite)
To guarantee zero rebuffering stalls under network volatility:
- **Critical Buffer Zone ($b(t) < 2.0\text{ s}$)**: Force lowest rung ($r = 0$) immediately, overriding content priority.
- **Depleted Buffer Zone ($2.0\text{ s} \le b(t) < 5.0\text{ s}$)**: Cap maximum allowed rung at $r = 2$ (720p).
- **Comfortable Buffer Zone ($b(t) \ge 5.0\text{ s}$)**: Allow unrestricted content-aware upgrades up to $r = 4$ (1080p high).

---

## 6. Stage 5: Live Streaming Reprocessing & Real-Time Delivery

Livestreaming introduces tight real-time constraints: chunks are produced continuously, playback buffers are small ($1.5\text{s} - 4.0\text{s}$), and the pipeline cannot look ahead minutes into the future.

```
Live Feed Ingest (RTMP/SRT)
          │
          ▼
 ┌──────────────────────────────────────────────┐
 │ Real-Time Multi-Bitrate Transcoder (NVENC)   │
 │ Encodes 5 rungs in parallel (Closed GOPs)    │
 └──────────────────────┬───────────────────────┘
                        │
                        ▼
 ┌──────────────────────────────────────────────┐
 │ Chunk Feature Extractor & AI Priority Engine │  ◄── Total Time Budget: < 50ms
 └──────────────────────┬───────────────────────┘
                        │
                        ▼
 ┌──────────────────────────────────────────────┐
 │ Real-Time Content-Aware Packager (Origin)    │
 │ Injects Priority Tags & Updates Manifest     │
 └──────────────────────┬───────────────────────┘
                        │
         ┌──────────────┴──────────────┐
         ▼                             ▼
   Mode A: Smart Manifest        Mode B: Server-Side
   Client-Driven Decision        Dynamic Bitrate Control
   (Hls.js Custom ABR)           (Transcoder Rate Modulator)
```

### 6.1 Adaptation Mode A: Client-Driven Smart Manifest (CDN-Compatible)
- The live origin transcode cluster encodes all 5 ladder rungs continuously.
- The AI analyzer computes chunk features in real time ($< 20\text{ ms}$) and injects priority metadata into the live HLS playlist (`.m3u8`):
  ```m3u8
  #EXTM3U
  #EXT-X-VERSION:7
  #EXT-X-TARGETDURATION:2
  #EXT-X-MEDIA-SEQUENCE:1042
  
  # Chunk 1042: High Motion Sports Action
  #EXT-X-CONTENT-PRIORITY: MOTION=0.88, COMPLEX=0.74, PRIORITY=0.82, SUGGESTED_RUNG=4
  #EXTINF:2.000,
  chunk_1042_r4.m4s
  
  # Chunk 1043: Static Replay Scoreboard
  #EXT-X-CONTENT-PRIORITY: MOTION=0.08, COMPLEX=0.22, PRIORITY=0.14, SUGGESTED_RUNG=1
  #EXTINF:2.000,
  chunk_1043_r1.m4s
  ```
- **Client Player Plugin**: A lightweight custom plugin in Hls.js / Dash.js reads the `#EXT-X-CONTENT-PRIORITY` tag and adjusts its representation selection threshold based on content urgency and current buffer state.

### 6.2 Adaptation Mode B: Server-Side Dynamic Rate Control (Bandwidth Saving)
- For broadcast origins or bandwidth-constrained live CDNs, the origin modulates target bitrate dynamically per chunk:
  - If incoming chunk priority is **Low**: Encoder caps target bitrate to 800 kbps even if the client's network profile permits 3000 kbps.
  - If incoming chunk priority is **High**: Encoder bursts up to 6000 kbps to preserve critical high-motion frames.
- **Result**: Yields **25%–38% overall bandwidth savings** while maintaining perceptual VMAF equivalence.

### 6.3 Low-Latency Protocol Stack (LL-HLS & CMAF)
- **CMAF Chunked Transfer Encoding (CTE)**: Chunks are split into 500 ms sub-chunks (`moof`/`mdat` pairs) and streamed to the CDN edge before the complete 2.0-second chunk is fully encoded.
- **LL-HLS Delta Playlists & Preload Hints**:
  ```m3u8
  #EXT-X-SERVER-CONTROL:CAN-BLOCK-RELOAD=YES,PART-HOLD-BACK=1.0
  #EXT-X-PART:DURATION=0.500,URI="chunk_1044_part1.m4s"
  #EXT-X-PART:DURATION=0.500,URI="chunk_1044_part2.m4s"
  #EXT-X-PRELOAD-HINT:TYPE=PART,URI="chunk_1044_part3.m4s"
  ```
- Eliminates HTTP round-trip latency, achieving **sub-2.5-second glass-to-glass latency**.

---

## 7. Stage 6: Client Playback & Real-Time Telemetry Feedback Loop

```
 Client Video Player (WB)
       │
       ├──► Synchronized Dual Player (Baseline vs Content-Aware)
       │
       ├──► Telemetry Harvester:
       │     • Buffer occupancy b(t)
       │     • Download throughput T_down
       │     • Dropped frames & stall events
       │
       └──► Beacon Transmission ──► Backend API / Edge Telemetry
                                           │
                                           ▼
                               Update Predictive Network Model
                               & Log Real-Time Benchmark
```

### 7.1 Synchronized Dual Playback (WB Showcase)
- **Side-by-Side Dual Canvas**: Left player renders Baseline ABR; right player renders BetterStreamer Content-Aware ABR.
- **Frame Sync Engine**: Locks presentation timestamps ($PTS$) to play both streams in lockstep.
- **Visual HUD Overlay**: Displays live resolution badge (`1080p @ 6000k`), instantaneous chunk VMAF score, buffer fill bar, and stall indicators.

### 7.2 Telemetry Beacon Payload
```json
{
  "session_id": "live_user_4492",
  "chunk_id": 1042,
  "policy": "content_aware",
  "chosen_rung": 4,
  "chunk_duration_s": 2.0,
  "download_time_ms": 482,
  "buffer_before_s": 3.8,
  "buffer_after_s": 5.3,
  "rebuffer_stall_s": 0.0,
  "estimated_throughput_mbps": 5.82,
  "vmaf_score": 94.6
}
```

---

## 8. Latency Budget for Live Reprocessing

In a live stream with a **2.0-second chunk duration** and a target glass-to-glass latency of **2.5 seconds**, execution times must stay strictly within the following limits:

| Stage | Operation | Target Duration | Technology Stack |
|:---:|:---|:---:|:---|
| **1** | Ingestion & Demuxing | $\le 10\text{ ms}$ | FFmpeg / GStreamer C-API |
| **2** | Hardware Multi-Rung Transcode | $\le 450\text{ ms}$ | NVIDIA NVENC / Intel QuickSync |
| **3** | Feature Extraction (Motion/Complexity) | $\le 20\text{ ms}$ | Downscaled Y-plane (PyAV / OpenCV) |
| **4** | AI Inference (Marginal Gain / Predictor) | $\le 2\text{ ms}$ | Quantized INT8 ONNX Runtime |
| **5** | Bitrate Allocation (Rust Core Engine) | $\le 1\text{ ms}$ | Rust Allocator (`better_streamer`) |
| **6** | Manifest Generation & CMAF Packaging | $\le 15\text{ ms}$ | Shaka Packager / mp4box / Rust Origin |
| **7** | CDN Edge Propagation | $\le 150\text{ ms}$ | HTTP/2 Chunked Transfer |
| **8** | Client Download & Buffer Ingestion | $\le 500\text{ ms}$ | HLS.js / Dash.js Player |
| **Total** | **Glass-to-Glass Processing Overhead** | **$\approx 1.15\text{ s}$** | **Sub-2.5s LL-HLS budget met** |

---

## 9. Concrete Implementation Recipes

### 9.1 Feature Extraction Module (`scripts/extract_features.py`)
```python
import cv2
import numpy as np

def extract_chunk_features(frames: list[np.ndarray]) -> tuple[float, float]:
    """Computes normalized motion and complexity scores from a sequence of frames."""
    if len(frames) < 2:
        return 0.0, 0.0

    # 1. Temporal Motion: Mean Squared Frame Difference (MSFD)
    diffs = [
        np.mean((frames[i] - frames[i - 1]) ** 2)
        for i in range(1, len(frames))
    ]
    raw_motion = float(np.mean(diffs))
    norm_motion = min(1.0, raw_motion / 450.0)

    # 2. Spatial Complexity: Laplacian Variance
    laplacian_vars = [
        cv2.Laplacian(frame, cv2.CV_64F).var()
        for frame in frames
    ]
    raw_complexity = float(np.mean(laplacian_vars))
    norm_complexity = min(1.0, raw_complexity / 1400.0)

    return norm_motion, norm_complexity
```

### 9.2 Rust Allocation Hook (`src/abr/allocator.rs`)
```rust
use crate::media::Segment;

pub fn allocate_greedy_marginal(
    segments: &[Segment],
    budget_bytes: u64,
    marginal_gains: &[Vec<f64>], // [segment_idx][rung_idx]
) -> Vec<usize> {
    let n = segments.len();
    let mut selected_rungs = vec![0; n];
    let mut current_bytes: u64 = segments
        .iter()
        .map(|s| s.bytes_at(0).unwrap_or(0))
        .sum();

    if current_bytes > budget_bytes {
        return selected_rungs;
    }

    loop {
        let mut best_seg = None;
        let mut best_ratio = 0.0;
        let mut best_cost = 0;

        for (i, seg) in segments.iter().enumerate() {
            let r = selected_rungs[i];
            if r + 1 < seg.representations.len() {
                let current_size = seg.bytes_at(r).unwrap_or(0);
                let next_size = seg.bytes_at(r + 1).unwrap_or(0);
                let delta_bytes = next_size.saturating_sub(current_size);

                if current_bytes + delta_bytes <= budget_bytes && delta_bytes > 0 {
                    let delta_gain = marginal_gains[i][r + 1];
                    let ratio = delta_gain / (delta_bytes as f64);
                    if ratio > best_ratio {
                        best_ratio = ratio;
                        best_seg = Some(i);
                        best_cost = delta_bytes;
                    }
                }
            }
        }

        match best_seg {
            Some(idx) => {
                selected_rungs[idx] += 1;
                current_bytes += best_cost;
            }
            None => break,
        }
    }

    selected_rungs
}
```

### 9.3 Client-Side Hls.js Plugin (`web/frontend/src/abr/ContentAwareAbrPlugin.ts`)
```typescript
export function computeContentAwareRung(
  bufferLevelS: number,
  measuredBandwidthBps: number,
  chunkPriority: number, // 0.0 to 1.0 from manifest tag
  bitrateLadderBps: number[]
): number {
  // Buffer safety override
  if (bufferLevelS < 2.0) {
    return 0; // Force lowest rung to prevent rebuffering
  }

  // Adjust effective spending budget based on chunk priority
  // High priority chunk -> allow spending up to 85% of measured bandwidth
  // Low priority chunk  -> cap at 50% of bandwidth to build buffer
  const multiplier = 0.50 + 0.35 * chunkPriority;
  const effectiveBudget = measuredBandwidthBps * multiplier;

  let chosenRung = 0;
  for (let i = bitrateLadderBps.length - 1; i >= 0; i--) {
    if (bitrateLadderBps[i] <= effectiveBudget) {
      chosenRung = i;
      break;
    }
  }
  return chosenRung;
}
```

---

## 10. Pipeline Verification & Quality Gate Checklist

| Component | Acceptance Criterion | Verification Command / Metric |
|---|---|---|
| **Segmentation** | Strictly aligned keyframes across all ladder rungs | `ffprobe -show_frames -select_streams v` |
| **Analysis** | Motion & Complexity normalized to $[0.0, 1.0]$ without NaNs | Unit test in `src/analysis/` |
| **Inference** | Marginal gain prediction finishes in $< 2\text{ ms}$ on CPU | Criterion benchmark test |
| **Allocation** | Hard bandwidth budget constraint never violated | `proptest` in `src/abr/allocator.rs` |
| **Live Reprocess** | Sub-50ms transcode-to-manifest processing turnaround | End-to-end latency timer |
| **Player QoE** | Statistically significant ($> 10\%$) gain in Quality/MB with equal/lower rebuffer | Compare report via `betterstreamer compare` |
