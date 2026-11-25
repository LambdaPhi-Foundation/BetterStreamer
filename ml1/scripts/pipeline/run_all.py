"""ML1 Pipeline - Phase 1: Ingest & Encode."""
import argparse
import logging
import yaml
import sys
from pathlib import Path

from .ingest.normalize import process_all_inputs as normalize_all
from .ingest.chunk import process_all_videos as chunk_all
from .ingest.encode_video import process_all_videos as encode_video_all
from .ingest.encode_audio import process_all_videos as encode_audio_all
from .validate import validate_phase1, load_encoding_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="BetterStreamer ML1 Pipeline - Phase 1")
    parser.add_argument("--config", default="config/ml1_pipeline.yaml", help="Pipeline config")
    parser.add_argument("--input-dir", help="Override input directory")
    parser.add_argument("--skip-normalize", action="store_true", help="Skip normalization")
    parser.add_argument("--skip-chunk", action="store_true", help="Skip chunking")
    parser.add_argument("--skip-encode-video", action="store_true", help="Skip video encoding")
    parser.add_argument("--skip-encode-audio", action="store_true", help="Skip audio encoding")
    parser.add_argument("--validate-only", action="store_true", help="Run validation only")
    args = parser.parse_args()

    config = load_config(args.config)
    encoding_config = load_encoding_config()
    chunks_dir = Path(config['chunks_dir'])

    if args.input_dir:
        config['input_dir'] = args.input_dir

    if args.validate_only:
        logger.info("Running validation only...")
        validate_all_videos(chunks_dir, encoding_config)
        logger.info("All validations passed!")
        return

    logger.info("=" * 60)
    logger.info("PHASE 1: INGEST & ENCODE")
    logger.info("=" * 60)

    # Step 1: Normalize
    if not args.skip_normalize:
        logger.info("Step 1/4: Normalizing sources...")
        normalized = normalize_all(config)
    else:
        normalized = {}
        for video_dir in chunks_dir.iterdir():
            if video_dir.is_dir():
                norm = video_dir / "source_normalized.mp4"
                if norm.exists():
                    normalized[video_dir.name] = norm

    if not normalized:
        logger.error("No normalized videos found. Run without --skip-normalize first.")
        sys.exit(1)

    # Step 2: Chunk
    if not args.skip_chunk:
        logger.info("Step 2/4: Chunking into 2s segments...")
        chunked = chunk_all(config, normalized)
    else:
        chunked = {}
        for video_dir in chunks_dir.iterdir():
            if video_dir.is_dir():
                source_chunks = sorted((video_dir / "source").glob("chunk_*.mp4"))
                if source_chunks:
                    chunked[video_dir.name] = source_chunks

    if not chunked:
        logger.error("No chunked videos found. Run without --skip-chunk first.")
        sys.exit(1)

    # Step 3: Encode video
    if not args.skip_encode_video:
        logger.info("Step 3/4: Encoding video ladder (5 rungs)...")
        video_sizes = encode_video_all(config, chunked)
    else:
        video_sizes = {}

    # Step 4: Encode audio
    if not args.skip_encode_audio:
        logger.info("Step 4/4: Encoding audio ladder (5 rungs)...")
        audio_sizes = encode_audio_all(config, chunked, normalized)
    else:
        audio_sizes = {}

    # Validation
    logger.info("Running Phase 1 validation...")
    for video_id in chunked.keys():
        validate_phase1(video_id, chunks_dir, encoding_config)

    logger.info("Phase 1 COMPLETE")
    logger.info(f"Processed videos: {list(chunked.keys())}")


def validate_all_videos(chunks_dir: Path, encoding_config: dict) -> bool:
    """Validate all videos in chunks_dir."""
    from .validate import validate_all_videos as _validate_all
    return _validate_all(chunks_dir, encoding_config)


if __name__ == "__main__":
    main()