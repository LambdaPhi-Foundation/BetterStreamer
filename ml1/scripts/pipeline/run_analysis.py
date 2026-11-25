"""Phase 2: Feature Extraction (Motion, Complexity, Calibration, Priority)."""
import argparse
import logging
import yaml
import json
from pathlib import Path
import sys

from .analysis.motion import extract_motion, extract_motion_vectors, process_video_chunks as process_motion
from .analysis.complexity import extract_complexity, process_video_chunks as process_complexity
from .analysis.priority import compute_priority, process_video_priorities, DEFAULT_MOTION_WEIGHT, DEFAULT_COMPLEXITY_WEIGHT
from .utils.calibration import calibrate_corpus, save_calibration, load_calibration, apply_calibration

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


def load_features_config(config_path: str = "config/features.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def extract_features_for_video(
    video_id: str,
    source_chunks: list,
    chunks_dir: Path
) -> dict:
    """Extract motion and complexity for a single video."""
    logger.info(f"Extracting features for {video_id}...")

    # Extract motion
    motions = process_motion(chunks_dir / video_id / "source")

    # Extract complexity
    complexities = process_complexity(chunks_dir / video_id / "source")

    # Extract motion vectors (optional, supporting feature)
    mv_magnitudes = []
    for chunk_path in sorted((chunks_dir / video_id / "source").glob("chunk_*.mp4")):
        mv = extract_motion_vectors(chunk_path)
        mv_magnitudes.append(mv)

    return {
        "motions": motions,
        "complexities": complexities,
        "mv_magnitudes": mv_magnitudes
    }


def main():
    parser = argparse.ArgumentParser(description="BetterStreamer ML1 Pipeline - Phase 2: Feature Extraction")
    parser.add_argument("--config", default="config/ml1_pipeline.yaml", help="Pipeline config")
    parser.add_argument("--input-dir", help="Override input directory")
    parser.add_argument("--skip-extract", action="store_true", help="Skip feature extraction, use cached")
    parser.add_argument("--skip-calibrate", action="store_true", help="Skip calibration, use existing")
    args = parser.parse_args()

    config = load_config(args.config)
    features_config = load_features_config()
    chunks_dir = Path(config['chunks_dir'])
    calibration_dir = Path(config['calibration_dir'])
    motion_weight = features_config.get('motion_weight', DEFAULT_MOTION_WEIGHT)
    complexity_weight = features_config.get('complexity_weight', DEFAULT_COMPLEXITY_WEIGHT)

    if args.input_dir:
        config['input_dir'] = args.input_dir

    logger.info("=" * 60)
    logger.info("PHASE 2: FEATURE EXTRACTION")
    logger.info("=" * 60)

    # Discover videos from chunks directory
    video_dirs = [d for d in chunks_dir.iterdir() if d.is_dir()]
    if not video_dirs:
        logger.error("No videos found in chunks directory. Run Phase 1 first.")
        sys.exit(1)

    video_ids = [d.name for d in video_dirs]
    logger.info(f"Found videos: {video_ids}")

    # Step 1: Extract features for all videos
    if not args.skip_extract:
        logger.info("Step 1/3: Extracting motion and complexity...")
        all_features = {}
        all_motions = []
        all_complexities = []
        all_mv_magnitudes = []

        for video_id in video_ids:
            features = extract_features_for_video(video_id, None, chunks_dir)
            all_features[video_id] = features
            all_motions.extend(features["motions"])
            all_complexities.extend(features["complexities"])
            all_mv_magnitudes.extend(features["mv_magnitudes"])

        # Save raw features per video
        for video_id, features in all_features.items():
            out_path = chunks_dir / video_id / "features_raw.json"
            with open(out_path, 'w') as f:
                json.dump(features, f, indent=2)

        logger.info(f"Extracted features for {len(video_ids)} videos")
    else:
        # Load cached features
        all_features = {}
        all_motions = []
        all_complexities = []
        all_mv_magnitudes = []
        for video_id in video_ids:
            feat_path = chunks_dir / video_id / "features_raw.json"
            if feat_path.exists():
                with open(feat_path) as f:
                    features = json.load(f)
                all_features[video_id] = features
                all_motions.extend(features["motions"])
                all_complexities.extend(features["complexities"])
                all_mv_magnitudes.extend(features["mv_magnitudes"])

    # Step 2: Compute calibration on corpus
    if not args.skip_calibrate:
        logger.info("Step 2/3: Computing corpus calibration...")
        calibration = calibrate_corpus(
            all_motions,
            all_complexities,
            all_mv_magnitudes if all_mv_magnitudes else None,
            percentiles=[5, 95]
        )
        save_calibration(calibration, calibration_dir / "calibration.json")
    else:
        calibration = load_calibration(calibration_dir / "calibration.json")

    # Step 3: Apply calibration and compute priorities
    logger.info("Step 3/3: Applying calibration and computing priorities...")
    for video_id, features in all_features.items():
        motions = features["motions"]
        complexities = features["complexities"]
        mv_magnitudes = features["mv_magnitudes"]

        normalized = []
        priorities = []

        for i in range(len(motions)):
            cal_result = apply_calibration(
                motions[i], complexities[i], mv_magnitudes[i], calibration
            )
            motion_norm = cal_result["motion"]
            complexity_norm = cal_result["complexity"]
            mv_norm = cal_result.get("mv_magnitude", 0.0)

            priority = compute_priority(
                motion_norm, complexity_norm,
                motion_weight, complexity_weight
            )

            normalized.append({
                "motion": motion_norm,
                "complexity": complexity_norm,
                "mv_magnitude": mv_norm
            })
            priorities.append(priority)

        # Save normalized features + priorities
        out_data = {
            "segments": [
                {
                    "segment_id": i,
                    "features": {
                        "motion": normalized[i]["motion"],
                        "complexity": normalized[i]["complexity"],
                        "mv_magnitude": normalized[i]["mv_magnitude"],
                        "priority_heuristic": priorities[i]
                    }
                }
                for i in range(len(normalized))
            ]
        }
        out_path = chunks_dir / video_id / "features_normalized.json"
        with open(out_path, 'w') as f:
            json.dump(out_data, f, indent=2)

        logger.info(f"  {video_id}: {len(priorities)} segments, priority range [{min(priorities):.3f}, {max(priorities):.3f}]")

    logger.info("Phase 2 COMPLETE")
    logger.info(f"Calibration saved to {calibration_dir}/calibration.json")
    logger.info(f"Per-video normalized features saved to data/chunks/<video_id>/features_normalized.json")


if __name__ == "__main__":
    main()