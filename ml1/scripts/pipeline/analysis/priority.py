"""Priority heuristic computation."""
import logging
from typing import Dict

logger = logging.getLogger(__name__)


DEFAULT_MOTION_WEIGHT = 0.6
DEFAULT_COMPLEXITY_WEIGHT = 0.4


def compute_priority(
    motion: float,
    complexity: float,
    motion_weight: float = DEFAULT_MOTION_WEIGHT,
    complexity_weight: float = DEFAULT_COMPLEXITY_WEIGHT
) -> float:
    """
    Compute priority score: clamp(w_m * motion + w_c * complexity, 0, 1).
    Both inputs should be normalized to [0, 1].
    """
    priority = motion_weight * motion + complexity_weight * complexity
    return float(max(0.0, min(1.0, priority)))


def priority_bucket(priority: float) -> str:
    """Bucket priority into Low/Medium/High."""
    if priority < 0.34:
        return "Low"
    elif priority < 0.67:
        return "Medium"
    return "High"


def process_video_priorities(
    motions: list,
    complexities: list,
    motion_weight: float = DEFAULT_MOTION_WEIGHT,
    complexity_weight: float = DEFAULT_COMPLEXITY_WEIGHT
) -> list:
    """Compute priorities for all chunks in a video."""
    priorities = []
    for m, c in zip(motions, complexities):
        p = compute_priority(m, c, motion_weight, complexity_weight)
        priorities.append(p)
    return priorities