"""Phase 3: Ground Truth (VMAF, SSIM, R-D curves)."""
import argparse
import logging
import yaml
import json
import sys
from pathlib import Path

from .ground_truth.vmaf import compute_vmaf_per_chunk_rung
from .ground_truth.ssim import compute_ssim_per_chunk_rung
from .ground_truth.audio_quality import compute_audio_quality_per_chunk_rung
from .ground_truth.rd_curves import generate_rd_curves, generate_category_report

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


def load_vmaf_config(config_path: str = "config/vmaf.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="BetterStreamer ML1 Pipeline - Phase 3: Ground Truth")
    parser.add_argument("--config", default="config/ml1_pipeline.yaml", help="Pipeline config")
    parser.add_argument("--input-dir", help="Override input directory")
    parser.add_argument("--skip-vmaf", action="store_true", help="Skip VMAF computation")
    parser.add_argument("--skip-ssim", action="store_true", help="Skip SSIM computation")
    parser.add_argument("--video-id", help="Process single video")
    args = parser.parse_args()

    config = load_config(args.config)
    encoding_config = load_encoding_config()
    vmaf_config = load_vmaf_config()

    chunks_dir = Path(config['chunks_dir'])
    reports_dir = Path(config['reports_dir'])
    model_dir = Path(vmaf_config['model_dir'])

    if args.input_dir:
        config['input_dir'] = args.input_dir

    video_ladder = encoding_config['video_ladder']
    audio_ladder = encoding_config['audio_ladder']

    logger.info("=" * 60)
    logger.info("PHASE 3: GROUND TRUTH")
    logger.info("=" * 60)

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

    # Load source normalized paths
    source_normalized = {}
    for vid in video_ids:
        norm_path = chunks_dir / vid / "source_normalized.mp4"
        if norm_path.exists():
            source_normalized[vid] = norm_path
        else:
            logger.warning(f"Missing source_normalized for {vid}")

    # Compute chunk sizes per rung
    logger.info("Loading chunk sizes...")
    chunk_sizes = {}
    for vid in video_ids:
        sizes = {}
        for rung_config in video_ladder:
            rung = rung_config['rung']
            rung_path = chunks_dir / vid / f"rung_{rung}"
            chunk_files = sorted(rung_path.glob("chunk_*.m4s"))
            sizes[str(rung)] = [f.stat().st_size for f in chunk_files]
        chunk_sizes[vid] = sizes

    # Compute VMAF
    vmaf_results = {}
    if not args.skip_vmaf:
        logger.info("Step 1/4: Computing VMAF (TV, Phone, NEG)...")
        for vid in video_ids:
            if vid in source_normalized:
                vmaf_results[vid] = compute_vmaf_per_chunk_rung(
                    vid, chunks_dir, source_normalized[vid], video_ladder
                )
                # Save per-video VMAF results
                out_path = chunks_dir / vid / "vmaf_results.json"
                with open(out_path, 'w') as f:
                    json.dump(vmaf_results[vid], f, indent=2)
            else:
                logger.warning(f"Skipping VMAF for {vid} (no source_normalized)")

    # Compute SSIM
    ssim_results = {}
    if not args.skip_ssim:
        logger.info("Step 2/4: Computing SSIM...")
        for vid in video_ids:
            if vid in source_normalized:
                ssim_results[vid] = compute_ssim_per_chunk_rung(
                    vid, chunks_dir, source_normalized[vid], video_ladder
                )
                out_path = chunks_dir / vid / "ssim_results.json"
                with open(out_path, 'w') as f:
                    json.dump(ssim_results[vid], f, indent=2)

    # Audio quality (placeholder)
    logger.info("Step 3/4: Audio quality (placeholder)...")
    audio_results = {}
    for vid in video_ids:
        audio_results[vid] = compute_audio_quality_per_chunk_rung(vid, chunks_dir, audio_ladder)
        out_path = chunks_dir / vid / "audio_results.json"
        with open(out_path, 'w') as f:
            json.dump(audio_results[vid], f, indent=2)

    # Generate R-D curves
    logger.info("Step 4/4: Generating R-D curves...")
    video_summaries = []
    for vid in video_ids:
        if vid in vmaf_results and vid in ssim_results:
            summary = generate_rd_curves(
                vid, video_ladder,
                vmaf_results[vid], ssim_results[vid],
                chunk_sizes[vid], reports_dir
            )
            video_summaries.append(summary)

    # Generate category reports (by genre if available)
    # For now, group all as "mixed"
    if video_summaries:
        generate_category_report("mixed", video_summaries, reports_dir)

    logger.info("Phase 3 COMPLETE")
    logger.info(f"VMAF/SSIM results saved to data/chunks/<video_id>/")
    logger.info(f"R-D curves saved to {reports_dir}/")


if __name__ == "__main__":
    main()