"""Phase 1 validation gates."""
import logging
import yaml
from pathlib import Path
from typing import Dict
from .utils.ffmpeg import validate_decodable, get_keyframe_times

logger = logging.getLogger(__name__)


def load_encoding_config(config_path: str = "config/encoding.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def validate_phase1(video_id: str, chunks_dir: Path, encoding_config: dict) -> bool:
    """Run all M1 validation checks."""
    video_ladder = encoding_config['video_ladder']
    audio_ladder = encoding_config['audio_ladder']
    chunk_duration = encoding_config['chunk_duration_s']

    # 1. All video chunks exist
    for rung_config in video_ladder:
        rung_dir = chunks_dir / video_id / f"rung_{rung_config['rung']}"
        chunks = list(rung_dir.glob("chunk_*.m4s"))
        if not chunks:
            raise RuntimeError(f"No video chunks for rung {rung_config['rung']}")

    # Audio is optional - only validate if directories exist
    has_audio = (chunks_dir / video_id / "audio_rung_0").exists()

    # 2. All video chunks decodable
    for rung_config in video_ladder:
        rung_dir = chunks_dir / video_id / f"rung_{rung_config['rung']}"
        for chunk in rung_dir.glob("chunk_*.m4s"):
            if not validate_decodable(chunk):
                raise RuntimeError(f"Video chunk not decodable: {chunk}")

    if has_audio:
        for rung_config in audio_ladder:
            rung_dir = chunks_dir / video_id / f"audio_rung_{rung_config['rung']}"
            for chunk in rung_dir.glob("chunk_*.m4s"):
                if not validate_decodable(chunk):
                    raise RuntimeError(f"Audio chunk not decodable: {chunk}")

    # 3. Keyframe alignment (video rungs)
    for rung_config in video_ladder:
        rung_dir = chunks_dir / video_id / f"rung_{rung_config['rung']}"
        for chunk in rung_dir.glob("chunk_*.m4s"):
            keyframes = get_keyframe_times(chunk)
            if not keyframes:
                raise RuntimeError(f"No keyframes in {chunk}")
            if abs(keyframes[0] - 0.0) > 0.1:
                raise RuntimeError(f"First keyframe not at 0: {chunk} (at {keyframes[0]}s)")

    # 4. Monotonic sizes per chunk (warn if not strictly increasing)
    rung0_dir = chunks_dir / video_id / "rung_0"
    num_chunks = len(list(rung0_dir.glob("chunk_*.m4s")))

    for chunk_idx in range(num_chunks):
        video_sizes = []
        for rung_config in video_ladder:
            chunk_path = chunks_dir / video_id / f"rung_{rung_config['rung']}" / f"chunk_{chunk_idx:03d}.m4s"
            if not chunk_path.exists():
                raise RuntimeError(f"Missing video chunk: {chunk_path}")
            video_sizes.append(chunk_path.stat().st_size)

        for i in range(1, len(video_sizes)):
            if video_sizes[i] <= video_sizes[i-1]:
                logger.warning(f"Chunk {chunk_idx}: video sizes not increasing at rung {i} ({video_sizes[i-1]} -> {video_sizes[i]})")

    logger.info(f"Phase 1 validation PASSED for {video_id}")
    return True


def validate_all_videos(chunks_dir: Path, encoding_config: dict) -> bool:
    """Validate all videos in chunks_dir."""
    video_dirs = [d for d in chunks_dir.iterdir() if d.is_dir()]
    for video_dir in video_dirs:
        validate_phase1(video_dir.name, chunks_dir, encoding_config)
    return True