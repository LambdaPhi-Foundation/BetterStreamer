"""Manifest schema definitions for DC contract."""
import logging
from typing import TypedDict, List
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


class FeaturesDict(TypedDict):
    motion: float
    complexity: float
    saliency: float
    scene_tag: str
    audio_class: str


class VideoQualityDict(TypedDict):
    sizes_bytes: List[int]
    vmaf_tv: List[float]
    vmaf_phone: List[float]
    ssim: List[float]


class AudioQualityDict(TypedDict):
    sizes_bytes: List[int]
    quality: List[float]


class SegmentDict(TypedDict):
    id: int
    features: FeaturesDict
    video: VideoQualityDict
    audio: AudioQualityDict


class ManifestDict(TypedDict):
    video_id: str
    genre: str
    segment_duration_s: float
    video_ladder_kbps: List[int]
    audio_ladder_kbps: List[int]
    segments: List[SegmentDict]


def validate_manifest(manifest: dict) -> bool:
    """Validate manifest against schema requirements."""
    required_keys = [
        'video_id', 'genre', 'segment_duration_s',
        'video_ladder_kbps', 'audio_ladder_kbps', 'segments'
    ]
    for key in required_keys:
        if key not in manifest:
            raise ValueError(f"Missing required key: {key}")

    if not isinstance(manifest['segments'], list):
        raise ValueError("segments must be a list")

    if not manifest['segments']:
        raise ValueError("segments cannot be empty")

    # Check segment IDs are contiguous from 0
    segment_ids = [s['id'] for s in manifest['segments']]
    if segment_ids != list(range(len(segment_ids))):
        raise ValueError("segment IDs must be contiguous from 0")

    # Check all arrays have correct length (5 rungs)
    num_rungs = len(manifest['video_ladder_kbps'])
    for i, seg in enumerate(manifest['segments']):
        for field in ['sizes_bytes', 'vmaf_tv', 'vmaf_phone', 'ssim']:
            if len(seg['video'][field]) != num_rungs:
                raise ValueError(f"Segment {i} video.{field} length != {num_rungs}")

        if len(seg['audio']['sizes_bytes']) != len(manifest['audio_ladder_kbps']):
            raise ValueError(f"Segment {i} audio.sizes_bytes length != audio ladder")

        if len(seg['audio']['quality']) != len(manifest['audio_ladder_kbps']):
            raise ValueError(f"Segment {i} audio.quality length != audio ladder")

        # Check sizes are increasing (allow small decreases < 1% for short clips)
        for field in ['sizes_bytes']:
            sizes = seg['video'][field]
            for j in range(1, len(sizes)):
                if sizes[j] <= sizes[j-1]:
                    # Allow small decreases up to 1% (encoding overhead for short clips)
                    if sizes[j-1] > 0 and (sizes[j-1] - sizes[j]) / sizes[j-1] <= 0.01:
                        logger.warning(f"Segment {i} video.{field}[{j}] decreased by {(sizes[j-1]-sizes[j])/sizes[j-1]*100:.2f}% (allowed)")
                    else:
                        raise ValueError(f"Segment {i} video.{field} not increasing: {sizes[j-1]} -> {sizes[j]}")

        # Check audio sizes increasing
        audio_sizes = seg['audio']['sizes_bytes']
        for j in range(1, len(audio_sizes)):
            if audio_sizes[j] <= audio_sizes[j-1]:
                if audio_sizes[j-1] > 0 and (audio_sizes[j-1] - audio_sizes[j]) / audio_sizes[j-1] <= 0.01:
                    logger.warning(f"Segment {i} audio.sizes_bytes[{j}] decreased by {(audio_sizes[j-1]-audio_sizes[j])/audio_sizes[j-1]*100:.2f}% (allowed)")
                else:
                    raise ValueError(f"Segment {i} audio.sizes_bytes not increasing: {audio_sizes[j-1]} -> {audio_sizes[j]}")

        # Check scores in valid ranges
        for vmaf in seg['video']['vmaf_tv']:
            if not (0 <= vmaf <= 100):
                raise ValueError(f"VMAF out of range: {vmaf}")
        for vmaf in seg['video']['vmaf_phone']:
            if not (0 <= vmaf <= 100):
                raise ValueError(f"Phone VMAF out of range: {vmaf}")
        for ssim in seg['video']['ssim']:
            if not (0 <= ssim <= 1):
                raise ValueError(f"SSIM out of range: {ssim}")

    return True


def create_manifest(
    video_id: str,
    genre: str,
    segment_duration_s: float,
    video_ladder_kbps: list,
    audio_ladder_kbps: list,
    segments: list
) -> ManifestDict:
    """Create a manifest dict from components."""
    manifest = {
        'video_id': video_id,
        'genre': genre,
        'segment_duration_s': segment_duration_s,
        'video_ladder_kbps': video_ladder_kbps,
        'audio_ladder_kbps': audio_ladder_kbps,
        'segments': segments
    }
    validate_manifest(manifest)
    return manifest