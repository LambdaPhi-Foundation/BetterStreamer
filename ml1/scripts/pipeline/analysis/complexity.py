"""Spatial complexity feature extraction (optimized)."""
import logging
import cv2
import numpy as np
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def compute_laplacian_variance(frame: np.ndarray) -> float:
    """Compute Laplacian variance (edge density) for a frame."""
    lap = cv2.Laplacian(frame, cv2.CV_32F)
    return float(lap.var())


def compute_complexity(frame: np.ndarray) -> float:
    """
    Compute spatial complexity using Laplacian variance only.
    Fast and correlates well with spatial complexity.
    """
    lap_var = compute_laplacian_variance(frame)
    # Normalize approximately (will be calibrated later)
    return min(lap_var / 1400.0, 1.0)


def extract_complexity(chunk_path: Path, sample_every: int = 5) -> float:
    """
    Extract complexity feature from a chunk.
    Samples every Nth frame for speed (default: every 5th frame).
    """
    cap = cv2.VideoCapture(str(chunk_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {chunk_path}")

    complexities = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % sample_every == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            c = compute_complexity(gray)
            complexities.append(c)
        frame_idx += 1

    cap.release()

    if not complexities:
        return 0.0

    return float(np.mean(complexities))


def process_video_chunks(chunk_dir: Path, sample_every: int = 5) -> List[float]:
    """Extract complexity for all chunks in a video."""
    chunks = sorted(chunk_dir.glob("chunk_*.mp4"))
    complexities = []

    for chunk_path in chunks:
        c = extract_complexity(chunk_path, sample_every)
        complexities.append(c)
        logger.debug(f"Complexity for {chunk_path.name}: {c:.4f}")

    return complexities