"""Audio quality placeholder (ViSQOL deferred)."""
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def compute_audio_quality(
    reference_path: Path,
    distorted_path: Path
) -> Dict[str, float]:
    """
    Placeholder for audio quality (ViSQOL deferred).
    Returns dummy score for now.
    """
    logger.warning("Audio quality (ViSQOL) deferred - returning dummy score")
    return {'mean': 3.5}


def compute_audio_quality_per_chunk_rung(
    video_id: str,
    chunk_dir: Path,
    audio_ladder: list
) -> Dict[int, List[Dict]]:
    """
    Placeholder for audio quality per chunk/rung.
    Returns {rung: [{mean} per chunk]}.
    """
    results = {}

    for rung_config in audio_ladder:
        rung = rung_config['rung']
        rung_path = chunk_dir / video_id / f"audio_rung_{rung}"

        quality_scores = []

        chunks = sorted(rung_path.glob("chunk_*.m4s"))
        logger.info(f"Audio quality placeholder for {video_id} rung {rung} ({len(chunks)} chunks)...")

        for i, chunk_path in enumerate(chunks):
            quality = compute_audio_quality(chunk_path, chunk_path)  # Self-reference dummy
            quality_scores.append(quality)
            logger.debug(f"  Chunk {i}: Quality={quality['mean']:.2f}")

        results[rung] = quality_scores

    return results