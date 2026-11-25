"""Rate-Distortion curve generation and marginal gains computation."""
import logging
import json
import csv
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def compute_marginal_gains(
    qualities: List[float],
    sizes_bytes: List[int]
) -> List[float]:
    """
    Compute marginal quality gain per MB for each rung step.
    delta_quality / delta_MB for rung r vs r-1.
    """
    gains = [0.0]  # First rung has no previous

    for i in range(1, len(qualities)):
        delta_q = qualities[i] - qualities[i-1]
        delta_mb = (sizes_bytes[i] - sizes_bytes[i-1]) / 1_000_000
        if delta_mb > 0:
            gains.append(delta_q / delta_mb)
        else:
            gains.append(0.0)

    return gains


def generate_rd_curves(
    video_id: str,
    video_ladder: list,
    vmaf_results: Dict,
    ssim_results: Dict,
    chunk_sizes: Dict[int, List[int]],
    reports_dir: Path
) -> Dict:
    """
    Generate R-D curve plots and data for a video.
    Returns summary statistics.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Handle both string and int keys in results
    rungs = sorted(video_ladder, key=lambda x: x['rung'])
    rung_indices = [r['rung'] for r in rungs]
    rung_bitrates = [r['target_kbps'] for r in rungs]

    # Find the correct key format in the results
    sample_vmaf = vmaf_results
    first_rung = list(sample_vmaf.keys())[0] if sample_vmaf else 0
    use_int_keys = isinstance(first_rung, int)
    
    # Get number of chunks from the first rung
    first_rung_key = 0 if use_int_keys else '0'
    num_chunks = len(vmaf_results[first_rung_key]['vmaf_tv'])

    rung_indices = [r['rung'] for r in rungs]

    # Aggregate per-rung statistics across chunks
    mean_vmaf_tv = []
    mean_vmaf_phone = []
    mean_ssim = []
    mean_sizes_mb = []

    for rung in rung_indices:
        rung_key = rung if use_int_keys else str(rung)
        vmaf_tv_chunk = [vmaf_results[rung_key]['vmaf_tv'][i]['mean'] for i in range(num_chunks)]
        vmaf_phone_chunk = [vmaf_results[rung_key]['vmaf_phone'][i]['mean'] for i in range(num_chunks)]
        ssim_chunk = [ssim_results[rung_key][i]['mean'] for i in range(num_chunks)]
        sizes_chunk = chunk_sizes[rung if isinstance(list(chunk_sizes.keys())[0], int) else str(rung)]

        mean_vmaf_tv.append(float(np.mean(vmaf_tv_chunk)))
        mean_vmaf_phone.append(float(np.mean(vmaf_phone_chunk)))
        mean_ssim.append(float(np.mean(ssim_chunk)))
        mean_sizes_mb.append(float(np.mean(sizes_chunk)) / 1_000_000)

    # Plot R-D curves
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # VMAF TV
    axes[0].plot(mean_sizes_mb, mean_vmaf_tv, 'o-', label='Mean')
    axes[0].set_xlabel('Size (MB)')
    axes[0].set_ylabel('VMAF (TV)')
    axes[0].set_title(f'{video_id} - VMAF TV vs Size')
    axes[0].grid(True, alpha=0.3)

    # VMAF Phone
    axes[1].plot(mean_sizes_mb, mean_vmaf_phone, 'o-', color='orange', label='Mean')
    axes[1].set_xlabel('Size (MB)')
    axes[1].set_ylabel('VMAF (Phone)')
    axes[1].set_title(f'{video_id} - VMAF Phone vs Size')
    axes[1].grid(True, alpha=0.3)

    # SSIM
    axes[2].plot(mean_sizes_mb, mean_ssim, 'o-', color='green', label='Mean')
    axes[2].set_xlabel('Size (MB)')
    axes[2].set_ylabel('SSIM')
    axes[2].set_title(f'{video_id} - SSIM vs Size')
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(reports_dir / f"rd_curves_{video_id}.png", dpi=150)
    plt.close()

    # Save CSV data
    csv_path = reports_dir / f"rd_data_{video_id}.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['rung', 'bitrate_kbps', 'mean_vmaf_tv', 'mean_vmaf_phone', 'mean_ssim', 'mean_size_mb'])
        for i, rung in enumerate(rung_indices):
            writer.writerow([rung, rung_bitrates[i], mean_vmaf_tv[i], mean_vmaf_phone[i], mean_ssim[i], mean_sizes_mb[i]])

    # Compute marginal gains for each chunk
    # Determine key format for chunk_sizes
    first_size_key = list(chunk_sizes.keys())[0] if chunk_sizes else 0
    use_int_size_keys = isinstance(first_size_key, int)

    marginal_gains = {}
    for rung in rung_indices:
        rung_key = rung if use_int_keys else str(rung)
        size_key = rung if use_int_size_keys else str(rung)
        gains_per_chunk = []
        for i in range(num_chunks):
            chunk_qualities = [vmaf_results[r if use_int_keys else str(r)]['vmaf_tv'][i]['mean'] for r in rung_indices]
            chunk_sizes_list = [chunk_sizes[r if use_int_size_keys else str(r)][i] for r in rung_indices]
            gains = compute_marginal_gains(chunk_qualities, chunk_sizes_list)
            gains_per_chunk.append(gains)
        marginal_gains[rung_key] = gains_per_chunk

    summary = {
        'video_id': video_id,
        'num_chunks': num_chunks,
        'rungs': rung_indices,
        'bitrates_kbps': rung_bitrates,
        'mean_vmaf_tv': mean_vmaf_tv,
        'mean_vmaf_phone': mean_vmaf_phone,
        'mean_ssim': mean_ssim,
        'mean_sizes_mb': mean_sizes_mb,
        'marginal_gains': marginal_gains,
    }

    logger.info(f"R-D curves saved for {video_id}")
    return summary


def generate_category_report(
    category: str,
    video_summaries: List[Dict],
    reports_dir: Path
) -> None:
    """Generate aggregate R-D curve report for a category."""
    if not video_summaries:
        return

    # Aggregate mean VMAF across videos per rung
    rungs = video_summaries[0]['rungs']
    agg_vmaf_tv = {r: [] for r in rungs}
    agg_vmaf_phone = {r: [] for r in rungs}
    agg_ssim = {r: [] for r in rungs}
    agg_sizes = {r: [] for r in rungs}

    for summary in video_summaries:
        for i, rung in enumerate(rungs):
            agg_vmaf_tv[rung].append(summary['mean_vmaf_tv'][i])
            agg_vmaf_phone[rung].append(summary['mean_vmaf_phone'][i])
            agg_ssim[rung].append(summary['mean_ssim'][i])
            agg_sizes[rung].append(summary['mean_sizes_mb'][i])

    # Plot aggregate curves
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    for ax, data, label, color in [
        (axes[0], agg_vmaf_tv, 'VMAF (TV)', 'blue'),
        (axes[1], agg_vmaf_phone, 'VMAF (Phone)', 'orange'),
        (axes[2], agg_ssim, 'SSIM', 'green')
    ]:
        for rung in rungs:
            ax.plot(np.mean(data[rung]), np.mean(data[rung]), 'o', alpha=0.5)
        # Mean curve
        mean_sizes = [np.mean(agg_sizes[r]) for r in rungs]
        mean_data = [np.mean(data[r]) for r in rungs]
        ax.plot(mean_sizes, mean_data, 'o-', color=color, label='Category Mean')
        ax.set_xlabel('Size (MB)')
        ax.set_ylabel(label)
        ax.set_title(f'{category} - {label} vs Size')
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(reports_dir / f"rd_curves_{category}.png", dpi=150)
    plt.close()

    logger.info(f"Category report saved for {category}")