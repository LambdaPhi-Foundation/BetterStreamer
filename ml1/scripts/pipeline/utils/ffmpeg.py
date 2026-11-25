"""FFmpeg wrapper utilities."""
import subprocess
import shlex
import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def run_ffmpeg(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run ffmpeg command with logging."""
    logger.debug(f"FFmpeg: {' '.join(shlex.quote(c) for c in cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed (exit {result.returncode}): {result.stderr}")
    return result


def probe_video(path: Path) -> Dict[str, Any]:
    """Get video info via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path)
    ]
    result = run_ffmpeg(cmd)
    return json.loads(result.stdout)


def validate_decodable(path: Path) -> bool:
    """Check if chunk decodes without errors."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"]
    result = run_ffmpeg(cmd, check=False)
    return result.returncode == 0


def get_keyframe_times(path: Path) -> List[float]:
    """Get keyframe timestamps."""
    cmd = [
        "ffprobe", "-v", "quiet", "-select_streams", "v",
        "-show_frames", "-show_entries", "frame=key_frame,pkt_pts_time",
        "-of", "json", str(path)
    ]
    result = run_ffmpeg(cmd)
    import json
    data = json.loads(result.stdout)
    keyframes = []
    for i, frame in enumerate(data.get('frames', [])):
        if frame.get('key_frame') == 1:
            pts = frame.get('pkt_pts_time')
            if pts:
                try:
                    keyframes.append(float(pts))
                except (ValueError, TypeError):
                    continue
            else:
                # pkt_pts_time missing - compute from frame index
                # Get frame rate from video stream
                try:
                    info = probe_video(path)
                    for stream in info.get('streams', []):
                        if stream.get('codec_type') == 'video':
                            r_frame_rate = stream.get('r_frame_rate', '30/1')
                            num, den = map(int, r_frame_rate.split('/'))
                            fps = num / den
                            keyframes.append(i / fps)
                            break
                except Exception:
                    pass
    return keyframes


def get_video_duration(path: Path) -> float:
    """Get video duration in seconds."""
    info = probe_video(path)
    format_info = info.get('format', {})
    return float(format_info.get('duration', 0))


def get_video_stream_info(path: Path) -> Dict[str, Any]:
    """Get primary video stream info."""
    info = probe_video(path)
    for stream in info.get('streams', []):
        if stream.get('codec_type') == 'video':
            return stream
    return {}