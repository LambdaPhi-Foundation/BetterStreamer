"""Motion feature extraction (median MSFD on 360p grayscale)."""
import logging
import cv2
import numpy as np
from pathlib import Path
from typing import Tuple, List
from ..utils.ffmpeg import get_video_stream_info

logger = logging.getLogger(__name__)


def load_frames_gray_360p(chunk_path: Path) -> List[np.ndarray]:
    """
    Load video frames as grayscale 360p arrays.
    Returns list of (360, 640) uint8 frames.
    """
    cap = cv2.VideoCapture(str(chunk_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {chunk_path}")

    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Convert to grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Downscale to 360p (640x360)
        small = cv2.resize(gray, (640, 360), interpolation=cv2.INTER_LANCZOS4)
        frames.append(small.astype(np.uint8))

    cap.release()
    return frames


def compute_motion_msfd(frames: List[np.ndarray]) -> float:
    """
    Compute Median of Mean Squared Frame Difference (MSFD).
    Robust to scene cuts - uses median instead of mean.
    """
    if len(frames) < 2:
        return 0.0

    # Convert to float32 to avoid uint8 wraparound
    frames_f32 = [f.astype(np.float32) for f in frames]
    frames_arr = np.stack(frames_f32)  # (N, H, W)

    # Mean squared difference between consecutive frames
    diffs = np.mean((frames_arr[1:] - frames_arr[:-1]) ** 2, axis=(1, 2))

    # Median is robust to scene cuts within chunk
    motion = float(np.median(diffs))
    return motion


def extract_motion(chunk_path: Path) -> float:
    """Extract motion feature from a chunk."""
    frames = load_frames_gray_360p(chunk_path)
    motion = compute_motion_msfd(frames)
    return motion


def extract_motion_vectors(chunk_path: Path) -> float:
    """
    Optional: Extract mean motion vector magnitude from H.264 bitstream.
    Uses PyAV to decode motion vectors.
    """
    try:
        import av
        container = av.open(str(chunk_path))
        stream = container.streams.video[0]

        mv_magnitudes = []
        for packet in container.demux(stream):
            for frame in packet.decode():
                if frame.motion_vectors is not None:
                    for mv in frame.motion_vectors:
                        magnitude = np.sqrt(mv.mv_x ** 2 + mv.mv_y ** 2)
                        mv_magnitudes.append(magnitude)

        container.close()

        if mv_magnitudes:
            return float(np.mean(mv_magnitudes))
        return 0.0
    except Exception as e:
        logger.warning(f"Motion vector extraction failed for {chunk_path}: {e}")
        return 0.0


def process_video_chunks(chunk_dir: Path) -> List[float]:
    """Extract motion for all chunks in a video."""
    chunks = sorted(chunk_dir.glob("chunk_*.mp4"))
    motions = []

    for chunk_path in chunks:
        motion = extract_motion(chunk_path)
        motions.append(motion)
        logger.debug(f"Motion for {chunk_path.name}: {motion:.4f}")

    return motions