"""Encode video chunks across 5-rung H.264 ladder."""
import logging
import yaml
import os
from pathlib import Path
from typing import List, Dict
from ..utils.ffmpeg import run_ffmpeg, validate_decodable

logger = logging.getLogger(__name__)


def load_encoding_config(config_path: str = "config/encoding.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def encode_chunk_rung(
    chunk_path: Path,
    output_path: Path,
    rung_config: dict,
    gop_size: int,
    chunk_duration_s: float
) -> int:
    """
    Encode single chunk at single rung using 2-pass.
    Returns file size in bytes.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    resolution = rung_config['resolution']
    target_kbps = rung_config['target_kbps']
    maxrate_kbps = rung_config['maxrate_kbps']
    bufsize_kbps = rung_config['bufsize_kbps']
    profile = rung_config['profile']
    level = rung_config['level']
    preset = rung_config['preset']

    # Use simple log file name in current directory (avoids path issues with passlogfile)
    log_name = f"passlog_{output_path.parent.name}_{output_path.stem}"

    # Pass 1 - use setpts to reset timestamps to start at 0
    vf = f"setpts=PTS-STARTPTS,scale={resolution}:flags=lanczos,format=yuv420p"
    pass1 = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(chunk_path), "-an",
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset,
        "-b:v", f"{target_kbps}k", "-maxrate", f"{maxrate_kbps}k",
        "-bufsize", f"{bufsize_kbps}k",
        "-profile:v", profile, "-level:v", level,
        "-g", str(gop_size), "-keyint_min", str(gop_size),
        "-sc_threshold", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{chunk_duration_s})",
        "-pass", "1", "-passlogfile", log_name,
        "-f", "mp4", os.devnull
    ]
    run_ffmpeg(pass1)

    # Pass 2 - encode directly to fMP4 (avoids timestamp issues with raw h264 remux)
    pass2 = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(chunk_path), "-an",
        "-vf", vf,
        "-c:v", "libx264", "-preset", preset,
        "-b:v", f"{target_kbps}k", "-maxrate", f"{maxrate_kbps}k",
        "-bufsize", f"{bufsize_kbps}k",
        "-profile:v", profile, "-level:v", level,
        "-g", str(gop_size), "-keyint_min", str(gop_size),
        "-sc_threshold", "0",
        "-force_key_frames", f"expr:gte(t,n_forced*{chunk_duration_s})",
        "-pass", "2", "-passlogfile", log_name,
        "-f", "mp4", "-movflags", "+faststart",
        str(output_path)
    ]
    run_ffmpeg(pass2)

    # Cleanup
    for logf in Path.cwd().glob(f"{log_name}*.log"):
        logf.unlink(missing_ok=True)

    if not validate_decodable(output_path):
        raise RuntimeError(f"Encoded chunk not decodable: {output_path}")

    size = output_path.stat().st_size
    logger.debug(f"Encoded {output_path.name}: {size} bytes ({size/1024:.1f} KB)")
    return size


def encode_video_ladder(
    video_id: str,
    source_chunks: List[Path],
    chunks_dir: Path,
    encoding_config: dict
) -> Dict[int, List[int]]:
    """
    Encode all chunks across all rungs.
    Returns: {rung: [sizes_bytes_per_chunk]}
    """
    video_ladder = encoding_config['video_ladder']
    chunk_duration = encoding_config['chunk_duration_s']
    fps = encoding_config['fps']
    gop_size = int(chunk_duration * fps)  # 60

    all_sizes = {r['rung']: [] for r in video_ladder}

    for rung_config in video_ladder:
        rung = rung_config['rung']
        rung_dir = chunks_dir / video_id / f"rung_{rung}"

        for i, chunk_path in enumerate(source_chunks):
            output_path = rung_dir / f"chunk_{i:03d}.m4s"

            if output_path.exists():
                size = output_path.stat().st_size
                logger.info(f"Skipping {video_id} rung {rung} chunk {i} (exists, {size} bytes)")
            else:
                size = encode_chunk_rung(chunk_path, output_path, rung_config, gop_size, chunk_duration)

            all_sizes[rung].append(size)

    # Verify monotonic sizes per chunk (warn only, not error for short clips)
    num_chunks = len(source_chunks)
    for chunk_idx in range(num_chunks):
        sizes = [all_sizes[r][chunk_idx] for r in sorted(all_sizes.keys())]
        for i in range(1, len(sizes)):
            if sizes[i] <= sizes[i-1]:
                logger.warning(f"Chunk {chunk_idx}: size not increasing at rung {i} ({sizes[i-1]} -> {sizes[i]})")

    logger.info(f"Video ladder complete for {video_id}")
    return all_sizes


def process_all_videos(config: dict, chunk_results: Dict[str, List[Path]]) -> Dict[str, Dict[int, List[int]]]:
    """Encode video ladder for all videos."""
    chunks_dir = Path(config['chunks_dir'])
    encoding_config = load_encoding_config()

    results = {}
    for video_id, source_chunks in chunk_results.items():
        sizes = encode_video_ladder(video_id, source_chunks, chunks_dir, encoding_config)
        results[video_id] = sizes

    return results