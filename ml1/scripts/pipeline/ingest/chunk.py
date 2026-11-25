"""Split normalized video into 2s chunks."""
import logging
from pathlib import Path
from typing import List, Dict
from ..utils.ffmpeg import run_ffmpeg, validate_decodable, get_video_duration

logger = logging.getLogger(__name__)


def chunk_video(
    normalized_path: Path,
    output_dir: Path,
    chunk_duration_s: float = 2.0,
    fps: int = 30
) -> List[Path]:
    """
    Split into 2s chunks using segment muxer (stream copy).
    Source chunks don't require forced keyframes - encoded rungs handle that.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(normalized_path),
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(chunk_duration_s),
        "-reset_timestamps", "1",
        "-segment_format", "mp4",
        str(output_dir / "chunk_%03d.mp4")
    ]
    run_ffmpeg(cmd)

    # Collect chunk paths
    chunks = sorted(output_dir.glob("chunk_*.mp4"))

    if not chunks:
        raise RuntimeError(f"No chunks created in {output_dir}")

    # Validate each chunk (decodable + duration check only)
    for i, chunk in enumerate(chunks):
        if not validate_decodable(chunk):
            raise RuntimeError(f"Chunk {i} not independently decodable: {chunk}")

        # Verify duration ≈ chunk_duration_s
        duration = get_video_duration(chunk)
        if abs(duration - chunk_duration_s) > 0.5:  # Allow more tolerance for stream copy
            logger.warning(f"Chunk {i} duration {duration:.3f}s != {chunk_duration_s}s")

    logger.info(f"Created {len(chunks)} chunks in {output_dir}")
    return chunks


def process_all_videos(config: dict, normalized_results: Dict[str, Path]) -> Dict[str, List[Path]]:
    """Chunk all normalized videos."""
    chunks_dir = Path(config['chunks_dir'])
    chunk_duration = config.get('chunk_duration_s', 2.0)
    fps = config.get('target_fps', 30)

    results = {}
    for video_id, normalized_path in normalized_results.items():
        chunk_dir = chunks_dir / video_id / "source"
        existing_chunks = sorted(chunk_dir.glob("chunk_*.mp4"))

        if existing_chunks:
            logger.info(f"Skipping {video_id} (already chunked, {len(existing_chunks)} chunks)")
            chunks = existing_chunks
        else:
            chunks = chunk_video(normalized_path, chunk_dir, chunk_duration, fps)

        results[video_id] = chunks

    return results