"""Source normalization to 1080p30 yuv420p."""
import logging
from pathlib import Path
from typing import Dict, Optional
from ..utils.ffmpeg import run_ffmpeg, probe_video, get_video_stream_info

logger = logging.getLogger(__name__)


def normalize_video(
    input_path: Path,
    output_path: Path,
    target_fps: int = 30,
    target_resolution: str = "1920x1080",
    target_pix_fmt: str = "yuv420p",
    crf: int = 18,
    preset: str = "medium"
) -> Path:
    """
    Normalize source video to constant fps, resolution, pixel format.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(input_path),
        "-vf", f"fps={target_fps},scale={target_resolution}:flags=lanczos,format={target_pix_fmt}",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-c:a", "pcm_s16le", "-ar", "48000",
        "-movflags", "+faststart",
        str(output_path)
    ]
    run_ffmpeg(cmd)

    # Validate output
    info = probe_video(output_path)
    video_stream = None
    for s in info.get('streams', []):
        if s.get('codec_type') == 'video':
            video_stream = s
            break

    if video_stream is None:
        raise RuntimeError(f"No video stream found in {output_path}")

    # Check constant fps
    r_frame_rate = video_stream.get('r_frame_rate', '')
    expected_rate = f"{target_fps}/1"
    if r_frame_rate != expected_rate:
        logger.warning(f"FPS mismatch: got {r_frame_rate}, expected {expected_rate}")

    # Check resolution
    width = video_stream.get('width', 0)
    height = video_stream.get('height', 0)
    if width != 1920 or height != 1080:
        raise RuntimeError(f"Resolution mismatch: got {width}x{height}, expected 1920x1080")

    # Check pix_fmt
    pix_fmt = video_stream.get('pix_fmt', '')
    if pix_fmt != 'yuv420p':
        raise RuntimeError(f"Pixel format mismatch: got {pix_fmt}, expected yuv420p")

    logger.info(f"Normalized: {input_path.name} -> {output_path.name}")
    return output_path


def process_all_inputs(config: dict) -> Dict[str, Path]:
    """Process all videos in input_dir."""
    input_dir = Path(config['input_dir'])
    chunks_dir = Path(config['chunks_dir'])
    target_fps = config.get('target_fps', 30)
    target_resolution = config.get('target_resolution', '1920x1080')
    target_pix_fmt = config.get('target_pix_fmt', 'yuv420p')

    results = {}
    video_files = sorted(input_dir.glob("*.mp4"))

    if not video_files:
        logger.warning(f"No MP4 files found in {input_dir}")
        return results

    for video_file in video_files:
        video_id = video_file.stem
        normalized = chunks_dir / video_id / "source_normalized.mp4"

        if normalized.exists():
            logger.info(f"Skipping {video_id} (already normalized)")
        else:
            normalize_video(
                video_file, normalized,
                target_fps=target_fps,
                target_resolution=target_resolution,
                target_pix_fmt=target_pix_fmt
            )
        results[video_id] = normalized

    return results