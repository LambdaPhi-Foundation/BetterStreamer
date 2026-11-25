"""Encode audio chunks across 5-rung Opus ladder."""
import logging
import yaml
from pathlib import Path
from typing import List, Dict
from ..utils.ffmpeg import run_ffmpeg, validate_decodable

logger = logging.getLogger(__name__)


def load_encoding_config(config_path: str = "config/encoding.yaml") -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def extract_audio(normalized_path: Path, output_wav: Path) -> Path:
    """Extract PCM audio from normalized video."""
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(normalized_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2",
        str(output_wav)
    ]
    run_ffmpeg(cmd)
    return output_wav


def chunk_audio(wav_path: Path, output_dir: Path, chunk_duration_s: float = 2.0) -> List[Path]:
    """Split audio into 2s chunks."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(wav_path),
        "-f", "segment", "-segment_time", str(chunk_duration_s),
        "-reset_timestamps", "1", "-c", "copy",
        str(output_dir / "chunk_%03d.wav")
    ]
    run_ffmpeg(cmd)
    return sorted(output_dir.glob("chunk_*.wav"))


def encode_audio_chunk(
    chunk_wav: Path,
    output_path: Path,
    bitrate_kbps: int,
    codec: str = "libopus"
) -> int:
    """Encode single audio chunk to Opus in fMP4 container."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        "-i", str(chunk_wav),
        "-c:a", codec, "-b:a", f"{bitrate_kbps}k",
        "-application", "audio",
        "-f", "mp4", "-movflags", "+faststart",
        str(output_path)
    ]
    run_ffmpeg(cmd)
    if not validate_decodable(output_path):
        raise RuntimeError(f"Audio chunk not decodable: {output_path}")
    return output_path.stat().st_size


def encode_audio_ladder(
    video_id: str,
    normalized_path: Path,
    num_chunks: int,
    chunks_dir: Path,
    encoding_config: dict
) -> Dict[int, List[int]]:
    """Encode audio across 5 rungs."""
    audio_ladder = encoding_config['audio_ladder']
    chunk_duration = encoding_config.get('audio_chunk_duration_s', 2.0)
    codec = encoding_config.get('audio_codec', 'libopus')

    # Extract and chunk audio once
    wav_path = chunks_dir / video_id / "source_audio.wav"
    if not wav_path.exists():
        extract_audio(normalized_path, wav_path)

    audio_chunks_dir = chunks_dir / video_id / "audio_chunks"
    if not list(audio_chunks_dir.glob("chunk_*.wav")):
        chunk_audio(wav_path, audio_chunks_dir, chunk_duration)

    audio_chunks = sorted(audio_chunks_dir.glob("chunk_*.wav"))
    if len(audio_chunks) != num_chunks:
        logger.warning(f"Audio chunks mismatch: {len(audio_chunks)} vs {num_chunks}")

    all_sizes = {r['rung']: [] for r in audio_ladder}

    for rung_config in audio_ladder:
        rung = rung_config['rung']
        bitrate = rung_config['bitrate_kbps']
        rung_dir = chunks_dir / video_id / f"audio_rung_{rung}"

        for i, chunk_wav in enumerate(audio_chunks):
            output_path = rung_dir / f"chunk_{i:03d}.m4s"

            if output_path.exists():
                size = output_path.stat().st_size
            else:
                size = encode_audio_chunk(chunk_wav, output_path, bitrate, codec)

            all_sizes[rung].append(size)

    # Verify monotonic (warn only)
    for chunk_idx in range(min(num_chunks, len(audio_chunks))):
        sizes = [all_sizes[r][chunk_idx] for r in sorted(all_sizes.keys())]
        for i in range(1, len(sizes)):
            if sizes[i] <= sizes[i-1]:
                logger.warning(f"Audio chunk {chunk_idx}: size not increasing at rung {i} ({sizes[i-1]} -> {sizes[i]})")

    logger.info(f"Audio ladder complete for {video_id}")
    return all_sizes


def process_all_videos(config: dict, chunk_results: Dict[str, List[Path]], normalized_results: Dict[str, Path]) -> Dict[str, Dict[int, List[int]]]:
    """Encode audio ladder for all videos."""
    chunks_dir = Path(config['chunks_dir'])
    encoding_config = load_encoding_config()

    results = {}
    for video_id, source_chunks in chunk_results.items():
        normalized_path = normalized_results[video_id]
        num_chunks = len(source_chunks)
        sizes = encode_audio_ladder(video_id, normalized_path, num_chunks, chunks_dir, encoding_config)
        results[video_id] = sizes

    return results