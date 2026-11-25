"""Manifest builder - assembles final DC contract manifest."""
import logging
import json
from pathlib import Path
from typing import Dict, List
from .schema import create_manifest, validate_manifest

logger = logging.getLogger(__name__)


def build_manifest(
    video_id: str,
    genre: str,
    segment_duration_s: float,
    video_ladder_kbps: list,
    audio_ladder_kbps: list,
    chunks_dir: Path
) -> dict:
    """
    Build complete manifest by assembling all computed data.
    """
    logger.info(f"Building manifest for {video_id}...")

    # Load all component data
    source_chunks = sorted((chunks_dir / video_id / "source").glob("chunk_*.mp4"))
    num_chunks = len(source_chunks)

    # Load features
    with open(chunks_dir / video_id / "features_normalized.json") as f:
        features_data = json.load(f)

    # Load VMAF results
    with open(chunks_dir / video_id / "vmaf_results.json") as f:
        vmaf_results = json.load(f)

    # Load SSIM results
    with open(chunks_dir / video_id / "ssim_results.json") as f:
        ssim_results = json.load(f)

    # Load audio results
    with open(chunks_dir / video_id / "audio_results.json") as f:
        audio_results = json.load(f)

    # Load chunk sizes per rung
    chunk_sizes = {}
    for rung in range(5):
        rung_path = chunks_dir / video_id / f"rung_{rung}"
        chunk_files = sorted(rung_path.glob("chunk_*.m4s"))
        chunk_sizes[rung] = [f.stat().st_size for f in chunk_files]

    # Load audio chunk sizes
    audio_chunk_sizes = {}
    for rung in range(5):
        rung_path = chunks_dir / video_id / f"audio_rung_{rung}"
        chunk_files = sorted(rung_path.glob("chunk_*.m4s"))
        audio_chunk_sizes[rung] = [f.stat().st_size for f in chunk_files]

    # Build segments
    segments = []
    for i in range(num_chunks):
        segment = {
            "id": i,
            "features": {
                "motion": features_data["segments"][i]["features"]["motion"],
                "complexity": features_data["segments"][i]["features"]["complexity"],
                "saliency": features_data["segments"][i]["features"]["mv_magnitude"],
                "scene_tag": genre,  # Use genre as scene_tag for now
                "audio_class": "speech"  # Placeholder
            },
            "video": {
                "sizes_bytes": [chunk_sizes[r][i] for r in range(5)],
                "vmaf_tv": [vmaf_results[str(r)]["vmaf_tv"][i]["mean"] for r in range(5)],
                "vmaf_phone": [vmaf_results[str(r)]["vmaf_phone"][i]["mean"] for r in range(5)],
                "ssim": [ssim_results[str(r)][i]["mean"] for r in range(5)]
            },
            "audio": {
                "sizes_bytes": [audio_chunk_sizes[r][i] for r in range(5)],
                "quality": [audio_results[str(r)][i]["mean"] for r in range(5)]
            }
        }
        segments.append(segment)

    manifest = {
        "video_id": video_id,
        "genre": genre,
        "segment_duration_s": 2.0,  # 2-second chunks
        "video_ladder_kbps": [400, 800, 1500, 3000, 6000],
        "audio_ladder_kbps": [24, 48, 64, 96, 128],
        "segments": segments
    }

    # Validate
    validate_manifest(manifest)

    logger.info(f"Manifest built for {video_id}: {len(segments)} segments")
    return manifest


def save_manifest(manifest: dict, output_path: Path) -> None:
    """Save manifest to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"Manifest saved to {output_path}")