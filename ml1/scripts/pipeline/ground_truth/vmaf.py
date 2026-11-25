"""VMAF computation for ground truth quality assessment."""
import logging
import json
import tempfile
from pathlib import Path
from typing import Dict, List
from ..utils.ffmpeg import run_ffmpeg

logger = logging.getLogger(__name__)


def compute_vmaf(
    reference_path: Path,
    distorted_path: Path,
    model: str = "default"
) -> Dict[str, float]:
    """
    Compute VMAF score between reference and distorted video.
    Returns dict with mean, harmonic_mean, min, max.
    """
    # Scale distorted to display resolution (1080p) if needed
    vmaf_filter = f"libvmaf=log_fmt=json"
    if model != "default":
        vmaf_filter += f":model={model}"

    import uuid
    log_filename = f"vmaf_{uuid.uuid4().hex}.json"

    try:
        # Use relative filename - ffmpeg will write to CWD
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            "-i", str(distorted_path),
            "-i", str(reference_path),
            "-lavfi", f"[0:v]scale=1920:1080:flags=lanczos[dist];[1:v][dist]{vmaf_filter}:log_path={log_filename}",
            "-f", "null", "-"
        ]
        run_ffmpeg(cmd)

        # Parse JSON output from CWD
        log_path = Path.cwd() / log_filename
        with open(log_path, 'r') as f:
            data = json.load(f)

        return parse_vmaf_json(data)

    except Exception as e:
        logger.error(f"VMAF computation failed: {e}")
        return {'mean': 0.0, 'harmonic_mean': 0.0, 'min': 0.0, 'max': 0.0}
    finally:
        Path.cwd().joinpath(log_filename).unlink(missing_ok=True)


def parse_vmaf_json(data: dict) -> Dict[str, float]:
    """Parse VMAF JSON output from ffmpeg."""
    # Extract from pooled_metrics
    if 'pooled_metrics' in data and 'vmaf' in data['pooled_metrics']:
        vmaf_data = data['pooled_metrics']['vmaf']
        return {
            'mean': float(vmaf_data.get('mean', 0)),
            'harmonic_mean': float(vmaf_data.get('harmonic_mean', 0)),
            'min': float(vmaf_data.get('min', 0)),
            'max': float(vmaf_data.get('max', 0)),
        }

    # Fallback: try aggregate_metrics
    if 'aggregate_metrics' in data and 'vmaf' in data['aggregate_metrics']:
        vmaf_data = data['aggregate_metrics']['vmaf']
        return {
            'mean': float(vmaf_data.get('mean', 0)),
            'harmonic_mean': float(vmaf_data.get('harmonic_mean', 0)),
            'min': float(vmaf_data.get('min', 0)),
            'max': float(vmaf_data.get('max', 0)),
        }

    # Last resort: compute from per-frame
    frames = data.get('frames', [])
    scores = [f.get('metrics', {}).get('vmaf', 0) for f in frames if 'vmaf' in f.get('metrics', {})]
    if scores:
        import numpy as np
        return {
            'mean': float(np.mean(scores)),
            'harmonic_mean': float(len(scores) / np.sum(1.0 / np.array(scores))) if np.all(np.array(scores) > 0) else 0,
            'min': float(np.min(scores)),
            'max': float(np.max(scores)),
        }

    return {'mean': 0.0, 'harmonic_mean': 0.0, 'min': 0.0, 'max': 0.0}


def compute_vmaf_per_chunk_rung(
    video_id: str,
    chunk_dir: Path,
    source_normalized: Path,
    video_ladder: list
) -> Dict[int, List[Dict]]:
    """
    Compute VMAF for all chunks and rungs of a video.
    Returns {rung: [{mean, harmonic_mean, min, max} per chunk]}.
    Compares each encoded chunk with the corresponding source chunk.
    """
    results = {}

    # Get source chunks
    source_chunks = sorted((chunk_dir / video_id / "source").glob("chunk_*.mp4"))
    logger.info(f"Found {len(source_chunks)} source chunks for {video_id}")

    for rung_config in video_ladder:
        rung = rung_config['rung']
        rung_path = chunk_dir / video_id / f"rung_{rung}"

        vmaf_scores = []

        encoded_chunks = sorted(rung_path.glob("chunk_*.m4s"))
        logger.info(f"Computing VMAF for {video_id} rung {rung} ({len(encoded_chunks)} chunks)...")

        for i, chunk_path in enumerate(encoded_chunks):
            # Use corresponding source chunk as reference
            if i < len(source_chunks):
                ref_chunk = source_chunks[i]
            else:
                logger.warning(f"Chunk index {i} exceeds source chunks, using last source chunk")
                ref_chunk = source_chunks[-1]

            # Use default model (phone/NEG not available in this FFmpeg build)
            vmaf = compute_vmaf(ref_chunk, chunk_path, "default")
            vmaf_scores.append(vmaf)
            logger.debug(f"  Chunk {i}: VMAF={vmaf['mean']:.2f}")

        results[rung] = {
            'vmaf_tv': vmaf_scores,  # Using default model for both
            'vmaf_phone': vmaf_scores,  # Fallback to default
            'vmaf_neg': vmaf_scores,  # Fallback to default
        }

    return results