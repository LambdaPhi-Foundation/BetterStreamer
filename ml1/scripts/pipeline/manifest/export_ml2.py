"""ML2 training CSV export - frozen contract for ML2."""
import logging
import csv
import json
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


ML2_CSV_COLUMNS = [
    "chunk_id", "category", "segment_id", "rung_id",
    "motion", "complexity", "priority",
    "bitrate_bps", "sizes_bytes", "vmaf", "ssim",
    "delta_vmaf_per_mb", "vmaf_phone",
    "audio_quality", "audio_sizes_bytes"
]


def export_ml2_csv(
    manifests_dir: Path,
    output_path: Path,
    categories: List[str] = None
) -> int:
    """
    Export ML2 training CSV from all manifests.
    Returns number of rows written.
    """
    manifests_dir = Path(manifests_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest_files = list(manifests_dir.glob("*.json"))
    if not manifest_files:
        logger.warning(f"No manifest files found in {manifests_dir}")
        return 0

    rows_written = 0

    with open(output_path, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(ML2_CSV_COLUMNS)

        for manifest_file in manifest_files:
            with open(manifest_file) as f:
                manifest = json.load(f)

            video_id = manifest['video_id']
            category = manifest['genre']
            video_ladder_kbps = manifest['video_ladder_kbps']
            audio_ladder_kbps = manifest['audio_ladder_kbps']

            for segment in manifest['segments']:
                segment_id = segment['id']
                motion = segment['features']['motion']
                complexity = segment['features']['complexity']
                priority = segment['features'].get('priority_heuristic', 0.0)

                for rung_id in range(len(video_ladder_kbps)):
                    bitrate_bps = video_ladder_kbps[rung_id] * 1000
                    sizes_bytes = segment['video']['sizes_bytes'][rung_id]
                    vmaf = segment['video']['vmaf_tv'][rung_id]
                    ssim = segment['video']['ssim'][rung_id]
                    vmaf_phone = segment['video']['vmaf_phone'][rung_id]

                    # Compute delta_vmaf_per_mb
                    if rung_id == 0:
                        delta_vmaf_per_mb = 0.0
                    else:
                        prev_sizes = segment['video']['sizes_bytes'][rung_id - 1]
                        delta_mb = (sizes_bytes - prev_sizes) / 1_000_000
                        delta_vmaf = vmaf - segment['video']['vmaf_tv'][rung_id - 1]
                        delta_vmaf_per_mb = delta_vmaf / delta_mb if delta_mb > 0 else 0.0

                    audio_quality = segment['audio']['quality'][rung_id]
                    audio_sizes_bytes = segment['audio']['sizes_bytes'][rung_id]

                    writer.writerow([
                        video_id, category, segment_id, rung_id,
                        motion, complexity, priority,
                        bitrate_bps, sizes_bytes, vmaf, ssim,
                        delta_vmaf_per_mb, vmaf_phone,
                        audio_quality, audio_sizes_bytes
                    ])
                    rows_written += 1

    logger.info(f"ML2 training CSV exported to {output_path}: {rows_written} rows")
    return rows_written