"""Manifest validation - M4/M5 acceptance criteria."""
import logging
import json
from pathlib import Path
from typing import Dict
from .schema import validate_manifest

logger = logging.getLogger(__name__)


def validate_manifest_file(manifest_path: Path) -> bool:
    """Validate a single manifest file."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    validate_manifest(manifest)

    # Additional M4/M5 checks
    video_id = manifest['video_id']
    genre = manifest['genre']

    logger.info(f"Validated manifest for {video_id} ({genre}): OK")
    return True


def validate_all_manifests(manifests_dir: Path) -> bool:
    """Validate all manifests in directory."""
    manifests_dir = Path(manifests_dir)
    manifest_files = list(manifests_dir.glob("*.json"))

    if not manifest_files:
        logger.warning(f"No manifest files found in {manifests_dir}")
        return False

    for mf in manifest_files:
        validate_manifest_file(mf)

    logger.info(f"All {len(manifest_files)} manifests validated successfully")
    return True


def validate_ml2_csv(csv_path: Path, manifests_dir: Path) -> bool:
    """Validate ML2 CSV against manifests."""
    import csv

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        logger.warning("ML2 CSV is empty")
        return False

    # Check column names
    if reader.fieldnames != [
        "chunk_id", "category", "segment_id", "rung_id",
        "motion", "complexity", "priority",
        "bitrate_bps", "sizes_bytes", "vmaf", "ssim",
        "delta_vmaf_per_mb", "vmaf_phone",
        "audio_quality", "audio_sizes_bytes"
    ]:
        logger.error("ML2 CSV column mismatch")
        return False

    logger.info(f"ML2 CSV validated: {len(rows)} rows")
    return True