"""Phase 4: Manifest Builder & ML2 CSV Export (M4/M5)."""
import argparse
import logging
import yaml
import sys
from pathlib import Path

from .manifest.builder import build_manifest, save_manifest
from .manifest.export_ml2 import export_ml2_csv
from .manifest.validator import validate_all_manifests, validate_ml2_csv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_encoding_config(config_path: str = "config/encoding.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="BetterStreamer ML1 Pipeline - Phase 4: Manifest & Contracts")
    parser.add_argument("--config", default="config/ml1_pipeline.yaml", help="Pipeline config")
    parser.add_argument("--input-dir", help="Override input directory")
    parser.add_argument("--video-id", help="Process single video")
    parser.add_argument("--skip-build", action="store_true", help="Skip manifest building")
    parser.add_argument("--skip-export", action="store_true", help="Skip ML2 CSV export")
    parser.add_argument("--validate-only", action="store_true", help="Run validation only")
    args = parser.parse_args()

    config = load_config(args.config)
    encoding_config = load_encoding_config()

    chunks_dir = Path(config['chunks_dir'])
    manifests_dir = Path(config['manifests_dir'])
    reports_dir = Path(config['reports_dir'])

    if args.input_dir:
        config['input_dir'] = args.input_dir

    video_ladder_kbps = [r['target_kbps'] for r in encoding_config['video_ladder']]
    audio_ladder_kbps = [r['bitrate_kbps'] for r in encoding_config['audio_ladder']]

    logger.info("=" * 60)
    logger.info("PHASE 4: MANIFEST & CONTRACTS")
    logger.info("=" * 60)

    if args.validate_only:
        logger.info("Running validation only...")
        validate_all_manifests(manifests_dir)
        validate_ml2_csv(Path("tests/fixtures/ml_training_dataset.csv"), manifests_dir)
        logger.info("All validations passed!")
        return

    # Discover videos
    if args.video_id:
        video_ids = [args.video_id]
    else:
        video_dirs = [d for d in chunks_dir.iterdir() if d.is_dir()]
        video_ids = [d.name for d in video_dirs]

    if not video_ids:
        logger.error("No videos found in chunks directory. Run Phase 1 first.")
        sys.exit(1)

    logger.info(f"Found videos: {video_ids}")

    # Step 1: Build manifests
    if not args.skip_build:
        logger.info("Step 1/2: Building manifests...")
        for vid in video_ids:
            # Determine genre from video_id (simple heuristic)
            if 'talking' in vid.lower():
                genre = 'talking_head'
            elif 'sport' in vid.lower():
                genre = 'sports'
            elif 'action' in vid.lower():
                genre = 'action'
            elif 'text' in vid.lower() or 'lecture' in vid.lower():
                genre = 'text'
            else:
                genre = 'mixed'

            manifest = build_manifest(
                vid, genre, 2.0,
                video_ladder_kbps, audio_ladder_kbps,
                Path(config['chunks_dir'])
            )
            save_manifest(manifest, manifests_dir / f"{vid}.json")

    # Step 2: Export ML2 CSV
    if not args.skip_export:
        logger.info("Step 2/2: Exporting ML2 training CSV...")
        export_ml2_csv(manifests_dir, Path("tests/fixtures/ml_training_dataset.csv"))

    # Validation
    logger.info("Running validation...")
    validate_all_manifests(manifests_dir)
    validate_ml2_csv(Path("tests/fixtures/ml_training_dataset.csv"), manifests_dir)

    logger.info("Phase 4 COMPLETE")
    logger.info(f"Manifests saved to {manifests_dir}")
    logger.info(f"ML2 CSV saved to tests/fixtures/ml_training_dataset.csv")


if __name__ == "__main__":
    main()