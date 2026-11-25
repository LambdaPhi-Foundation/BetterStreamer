"""SSIM computation for ground truth quality assessment."""
import logging
import subprocess
from pathlib import Path
from typing import List, Dict
from ..utils.ffmpeg import run_ffmpeg

logger = logging.getLogger(__name__)


def compute_ssim(
    reference_path: Path,
    distorted_path: Path
) -> Dict[str, float]:
    """
    Compute SSIM score between reference and distorted video.
    Returns dict with mean SSIM.
    Scale reference to match distorted resolution.
    """
    # Get distorted video resolution
    import subprocess
    import json
    probe_cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-select_streams", "v", str(distorted_path)
    ]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    probe_data = json.loads(probe_result.stdout)
    stream = probe_data['streams'][0]
    width = stream['width']
    height = stream['height']

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(distorted_path),
        "-i", str(reference_path),
        "-lavfi", f"[1:v]scale={width}:{height}:flags=lanczos[ref];[0:v][ref]ssim=stats_file=-",
        "-f", "null", "-"
    ]

    result = run_ffmpeg(cmd)
    return parse_ssim_output(result.stderr)


def parse_ssim_output(stderr: str) -> Dict[str, float]:
    """Parse SSIM output from ffmpeg stderr."""
    lines = stderr.strip().split('\n')
    for line in lines:
        if 'All:' in line and 'SSIM' in line:
            # Format: All: Y:0.99 U:0.99 V:0.99 All:0.99
            parts = line.split()
            for part in parts:
                if part.startswith('All:'):
                    try:
                        return {'mean': float(part.split(':')[1])}
                    except (IndexError, ValueError):
                        pass
    return {'mean': 0.0}


def compute_ssim_per_chunk_rung(
    video_id: str,
    chunk_dir: Path,
    source_normalized: Path,
    video_ladder: list
) -> Dict[int, List[Dict]]:
    """
    Compute SSIM for all chunks and rungs of a video.
    Returns {rung: [{mean} per chunk]}.
    """
    results = {}

    for rung_config in video_ladder:
        rung = rung_config['rung']
        rung_path = chunk_dir / video_id / f"rung_{rung}"

        ssim_scores = []

        chunks = sorted(rung_path.glob("chunk_*.m4s"))
        logger.info(f"Computing SSIM for {video_id} rung {rung} ({len(chunks)} chunks)...")

        for i, chunk_path in enumerate(chunks):
            ssim = compute_ssim(source_normalized, chunk_path)
            ssim_scores.append(ssim)
            logger.debug(f"  Chunk {i}: SSIM={ssim['mean']:.4f}")

        results[rung] = ssim_scores

    return results