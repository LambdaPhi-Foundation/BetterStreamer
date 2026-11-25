"""Feature calibration - compute corpus percentiles for normalization."""
import logging
import json
import numpy as np
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def compute_percentiles(values: List[float], percentiles: List[int] = None) -> Dict[int, float]:
    """Compute percentiles for a list of values."""
    if percentiles is None:
        percentiles = [5, 95]
    if not values:
        return {p: 0.0 for p in percentiles}
    arr = np.array(values)
    result = {}
    for p in percentiles:
        result[p] = float(np.percentile(arr, p))
    return result


def normalize(raw: float, p_low: float, p_high: float) -> float:
    """
    Calibrated min-max normalization using corpus percentiles.
    Clamps to [0, 1].
    """
    if p_high <= p_low:
        return 0.0
    normalized = (raw - p_low) / (p_high - p_low)
    return float(np.clip(normalized, 0.0, 1.0))


def calibrate_corpus(
    all_motions: List[float],
    all_complexities: List[float],
    all_mv_magnitudes: List[float] = None,
    percentiles: List[int] = None
) -> Dict:
    """
    Compute calibration parameters from corpus statistics.
    Returns dict with p_low, p_high for each feature.
    """
    if percentiles is None:
        percentiles = [5, 95]

    p_low = percentiles[0]
    p_high = percentiles[1]

    cal = {
        "motion": {
            "p_low": float(np.percentile(all_motions, p_low)),
            "p_high": float(np.percentile(all_motions, p_high)),
        },
        "complexity": {
            "p_low": float(np.percentile(all_complexities, p_low)),
            "p_high": float(np.percentile(all_complexities, p_high)),
        }
    }

    if all_mv_magnitudes:
        cal["mv_magnitude"] = {
            "p_low": float(np.percentile(all_mv_magnitudes, p_low)),
            "p_high": float(np.percentile(all_mv_magnitudes, p_high)),
        }

    logger.info(f"Calibration computed:")
    logger.info(f"  motion: p{p_low}={cal['motion']['p_low']:.4f}, p{p_high}={cal['motion']['p_high']:.4f}")
    logger.info(f"  complexity: p{p_low}={cal['complexity']['p_low']:.4f}, p{p_high}={cal['complexity']['p_high']:.4f}")

    return cal


def save_calibration(calibration: Dict, output_path: Path) -> None:
    """Save calibration to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(calibration, f, indent=2)
    logger.info(f"Calibration saved to {output_path}")


def load_calibration(calibration_path: Path) -> Dict:
    """Load calibration from JSON file."""
    with open(calibration_path, 'r') as f:
        return json.load(f)


def apply_calibration(
    motion: float,
    complexity: float,
    mv_magnitude: float = None,
    calibration: Dict = None
) -> Dict[str, float]:
    """
    Apply calibration to raw features.
    Returns normalized features in [0, 1].
    """
    if calibration is None:
        raise ValueError("Calibration required")

    motion_norm = normalize(motion, calibration["motion"]["p_low"], calibration["motion"]["p_high"])
    complexity_norm = normalize(complexity, calibration["complexity"]["p_low"], calibration["complexity"]["p_high"])

    result = {
        "motion": motion_norm,
        "complexity": complexity_norm,
    }

    if mv_magnitude is not None and "mv_magnitude" in calibration:
        mv_norm = normalize(mv_magnitude, calibration["mv_magnitude"]["p_low"], calibration["mv_magnitude"]["p_high"])
        result["mv_magnitude"] = mv_norm

    return result