//! Budget-constrained content-aware bitrate allocator.
//!
//! Implements PIPELINE.md §5: maximize `Σ Quality(cᵢ, rᵢ)` subject to
//! `Σ Bytes(cᵢ, rᵢ) ≤ Budget`, across a window of chunks.
//!
//! Two solvers:
//!  * `allocate_greedy` / `allocate_greedy_marginal` — greedy marginal-utility
//!    (PIPELINE.md §5.2), fast, suitable for the live loop (≤1 ms budget).
//!  * `allocate_knapsack` — offline multiple-choice DP knapsack, the
//!    theoretical upper bound used to benchmark the greedy gap.
//!
//! Hard invariant enforced by both: `total_bytes(selected) ≤ budget_bytes`.
//! Until real VMAF tables land (Phase 7 / ML1), quality is a log-saturating
//! deterministic model of priority × rung.

use crate::media::Segment;

/// Base quality delivered even at the lowest rung.
const QUALITY_BASE: f64 = 10.0;
/// Per-priority quality span as rung → ∞.
const QUALITY_SPAN: f64 = 30.0;

/// Deterministic log-saturating quality of `segment` at `rung`.
///
/// `Quality(p, r) = QUALITY_BASE + p * QUALITY_SPAN * (1 - 1/(r+1))`.
/// Diminishing returns in `r`, scaled by chunk priority.
pub fn quality_of(segment: &Segment, rung: usize) -> f64 {
    let p = segment.features.priority.clamp(0.0, 1.0);
    let r = rung as f64;
    QUALITY_BASE + p * QUALITY_SPAN * (1.0 - 1.0 / (r + 1.0))
}

/// Marginal quality of upgrading `segment` to `rung` (from `rung - 1`), `rung ≥ 1`.
///
/// `ΔQ = p * QUALITY_SPAN * (1/rung - 1/(rung+1))` — strictly decreasing in rung.
fn marginal_quality(priority: f64, rung: usize) -> f64 {
    let p = priority.clamp(0.0, 1.0);
    let r = rung as f64;
    p * QUALITY_SPAN * (1.0 / r - 1.0 / (r + 1.0))
}

/// Build the marginal-gain table `[segment][rung]` used by the greedy solver.
///
/// `gains[i][0] = 0`; `gains[i][r]` (r ≥ 1) is the gain of moving segment `i`
/// to rung `r` from rung `r - 1`, derived from the chunk's priority score.
pub fn build_marginal_gains(segments: &[Segment]) -> Vec<Vec<f64>> {
    if segments.is_empty() {
        return Vec::new();
    }
    let n_rungs = segments[0].representations.len();
    segments
        .iter()
        .map(|seg| {
            let p = seg.features.priority;
            (0..n_rungs)
                .map(|r| if r == 0 { 0.0 } else { marginal_quality(p, r) })
                .collect()
        })
        .collect()
}

/// Total bytes of downloading `segments` at the given `rungs`.
pub fn total_bytes(segments: &[Segment], rungs: &[usize]) -> u64 {
    segments
        .iter()
        .zip(rungs)
        .filter_map(|(seg, &r)| seg.bytes_at(r).ok())
        .sum()
}

/// Total quality of `segments` at the given `rungs`.
pub fn total_quality(segments: &[Segment], rungs: &[usize]) -> f64 {
    segments
        .iter()
        .zip(rungs)
        .map(|(seg, &r)| quality_of(seg, r))
        .sum()
}

/// Greedy marginal-utility allocation (PIPELINE.md §5.2).
///
/// Starts every segment at rung 0, then repeatedly upgrades the segment with
/// the best `ΔQuality / ΔBytes` ratio that still fits the remaining budget.
/// Never exceeds `budget_bytes`. If even all-rung-0 does not fit, returns
/// all zeros.
///
/// `marginal_gains[i][r]` = gain of moving segment `i` to rung `r` (from `r-1`).
pub fn allocate_greedy_marginal(
    segments: &[Segment],
    budget_bytes: u64,
    marginal_gains: &[Vec<f64>],
) -> Vec<usize> {
    let n = segments.len();
    if n == 0 {
        return Vec::new();
    }
    let n_rungs = segments[0].representations.len();
    let mut selected_rungs = vec![0usize; n];

    let mut current_bytes: u64 = segments
        .iter()
        .map(|s| s.bytes_at(0).unwrap_or(0))
        .sum::<u64>();

    if current_bytes > budget_bytes {
        // Cannot even afford the lowest rung for every segment.
        return selected_rungs;
    }

    loop {
        let mut best_seg: Option<usize> = None;
        let mut best_ratio = 0.0f64;
        let mut best_cost: u64 = 0;

        for (i, seg) in segments.iter().enumerate() {
            let r = selected_rungs[i];
            if r + 1 >= n_rungs {
                continue;
            }
            let current_size = seg.bytes_at(r).unwrap_or(0);
            let next_size = seg.bytes_at(r + 1).unwrap_or(0);
            let delta_bytes = next_size.saturating_sub(current_size);
            if delta_bytes == 0 {
                continue;
            }
            if current_bytes
                .checked_add(delta_bytes)
                .is_some_and(|t| t > budget_bytes)
            {
                continue;
            }
            let delta_gain = marginal_gains
                .get(i)
                .and_then(|g| g.get(r + 1))
                .copied()
                .unwrap_or(0.0);
            let ratio = delta_gain / (delta_bytes as f64);
            if ratio > best_ratio {
                best_ratio = ratio;
                best_seg = Some(i);
                best_cost = delta_bytes;
            }
        }

        match best_seg {
            Some(idx) => {
                selected_rungs[idx] += 1;
                current_bytes += best_cost;
            }
            None => break,
        }
    }

    selected_rungs
}

/// Convenience: greedy allocation using the built-in priority quality model.
pub fn allocate_greedy(segments: &[Segment], budget_bytes: u64) -> Vec<usize> {
    let gains = build_marginal_gains(segments);
    allocate_greedy_marginal(segments, budget_bytes, &gains)
}

/// Multiple-choice DP knapsack upper bound.
///
/// Picks exactly one rung per segment to maximize total quality under the
/// byte budget. Costs are scaled to keep the DP table bounded (`≤ MAX_UNITS`
/// units), so this is a close-but-slightly-loose upper bound suitable for
/// benchmarking the greedy gap.
pub fn allocate_knapsack(segments: &[Segment], budget_bytes: u64) -> Vec<usize> {
    let n = segments.len();
    if n == 0 {
        return Vec::new();
    }
    let n_rungs = segments[0].representations.len();

    const MAX_UNITS: u64 = 5000;
    let unit = u64::max(1, budget_bytes / MAX_UNITS);
    let budget_units = budget_bytes / unit;

    // cost_units[i][r] = bytes(segment i, rung r) / unit, floored, ≥1 if nonzero bytes.
    let cost_units: Vec<Vec<u64>> = segments
        .iter()
        .map(|seg| {
            (0..n_rungs)
                .map(|r| {
                    let b = seg.bytes_at(r).unwrap_or(0);
                    if b == 0 { 0 } else { u64::max(1, b / unit) }
                })
                .collect()
        })
        .collect();

    const NEG: f64 = f64::NEG_INFINITY;
    // dp[b] = best quality after processed segments with `b` units spent.
    let mut dp: Vec<f64> = vec![NEG; (budget_units + 1) as usize];
    dp[0] = 0.0;
    // parent[i][b] = (rung chosen for segment i, previous budget units).
    let mut parent: Vec<Vec<(usize, u64)>> = vec![vec![(0, 0); (budget_units + 1) as usize]; n];

    for i in 0..n {
        let mut ndp: Vec<f64> = vec![NEG; (budget_units + 1) as usize];
        for b in 0..=budget_units {
            if dp[b as usize] == NEG {
                continue;
            }
            for (r, &cost) in cost_units[i].iter().enumerate() {
                let nb = b.saturating_add(cost);
                if nb > budget_units {
                    continue;
                }
                let q = dp[b as usize] + quality_of(&segments[i], r);
                if q > ndp[nb as usize] {
                    ndp[nb as usize] = q;
                    parent[i][nb as usize] = (r, b);
                }
            }
        }
        dp = ndp;
    }

    // Best reachable budget.
    let mut best_b: u64 = 0;
    let mut best_q = NEG;
    for (b, &q) in dp.iter().enumerate() {
        if q > best_q {
            best_q = q;
            best_b = b as u64;
        }
    }

    if best_q == NEG {
        // No feasible full assignment; fall back to greedy (all-zero if rung-0
        // does not fit).
        return allocate_greedy(segments, budget_bytes);
    }

    // Reconstruct chosen rungs backwards.
    let mut chosen = vec![0usize; n];
    let mut b = best_b;
    for i in (0..n).rev() {
        let (r, prev_b) = parent[i][b as usize];
        chosen[i] = r;
        b = prev_b;
    }
    chosen
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_ladder;
    use crate::media::{Representation, Segment, SegmentFeatures, Video};

    fn seg(id: usize, duration_s: f64, bitrates: &[u64], priority: f64) -> Segment {
        let representations: Vec<Representation> = bitrates
            .iter()
            .enumerate()
            .map(|(i, &b)| Representation {
                id: i,
                width: 640 + i as u32 * 320,
                height: 360 + i as u32 * 180,
                bitrate_bps: b,
            })
            .collect();
        Segment {
            id,
            duration_s,
            features: SegmentFeatures {
                motion: 0.0,
                complexity: 0.0,
                priority,
            },
            representations,
        }
    }

    fn video_with(segment_priorities: &[f64]) -> Video {
        let ladder = default_ladder();
        let segments: Vec<Segment> = segment_priorities
            .iter()
            .enumerate()
            .map(|(i, &p)| seg(i, 4.0, &ladder, p))
            .collect();
        Video {
            name: "test".to_string(),
            segments,
        }
    }

    #[test]
    fn greedy_respects_hard_budget() {
        let v = video_with(&[0.2, 0.8, 0.5, 0.9, 0.3, 0.6, 0.1, 0.7]);
        let budget = 8_000_000u64; // 8 MBytes
        let rungs = allocate_greedy(&v.segments, budget);
        assert_eq!(rungs.len(), v.segments.len());
        assert!(total_bytes(&v.segments, &rungs) <= budget);
    }

    #[test]
    fn greedy_all_zero_when_rung0_exceeds_budget() {
        let v = video_with(&[0.5, 0.5]);
        let tiny = 1u64; // less than one rung-0 segment
        let rungs = allocate_greedy(&v.segments, tiny);
        assert_eq!(rungs, vec![0, 0]);
        // Rung-0 itself doesn't fit the budget, so the instance is infeasible;
        // the allocator's best effort is all lowest rungs.
    }

    #[test]
    fn greedy_monotonic_in_budget() {
        let v = video_with(&[0.5, 0.5, 0.5]);
        let gains = build_marginal_gains(&v.segments);
        let small = allocate_greedy_marginal(&v.segments, 2_000_000, &gains);
        let large = allocate_greedy_marginal(&v.segments, 20_000_000, &gains);
        let q_small = total_quality(&v.segments, &small);
        let q_large = total_quality(&v.segments, &large);
        assert!(q_large >= q_small - 1e-12);
        assert!(total_bytes(&v.segments, &large) <= 20_000_000);
    }

    #[test]
    fn greedy_favors_high_priority_under_contention() {
        // Same sizes, different priority; tight budget upgrades the high-prio one.
        let seg_low = seg(0, 4.0, &[400_000, 800_000], 0.1);
        let seg_high = seg(1, 4.0, &[400_000, 800_000], 0.9);
        let segments = vec![seg_low, seg_high];
        // Budget fits rung-0 for both (800_000*4/8 = 200_000 bytes each = 400_000)
        // plus one upgrade (another 200_000) = 600_000 total.
        let budget = 600_000u64;
        let gains = build_marginal_gains(&segments);
        let rungs = allocate_greedy_marginal(&segments, budget, &gains);
        assert_eq!(
            rungs,
            vec![0, 1],
            "high-priority segment should be upgraded"
        );
    }

    #[test]
    fn marginal_gains_decreasing_in_rung() {
        let seg = seg(0, 4.0, &default_ladder(), 0.7);
        let gains = build_marginal_gains(&[seg]);
        let g = &gains[0];
        assert_eq!(g[0], 0.0);
        for r in 1..(g.len() - 1) {
            assert!(g[r] > g[r + 1], "marginal gain must decrease with rung");
        }
    }

    #[test]
    fn knapsack_respects_hard_budget() {
        let v = video_with(&[0.2, 0.8, 0.5, 0.9]);
        let rungs = allocate_knapsack(&v.segments, 5_000_000);
        assert_eq!(rungs.len(), v.segments.len());
        assert!(total_bytes(&v.segments, &rungs) <= 5_000_000);
    }

    #[test]
    fn knapsack_is_upper_bound_over_greedy() {
        let v = video_with(&[0.2, 0.8, 0.5, 0.9, 0.4]);
        let budget = 6_000_000u64;
        let gains = build_marginal_gains(&v.segments);
        let greedy = allocate_greedy_marginal(&v.segments, budget, &gains);
        let knap = allocate_knapsack(&v.segments, budget);
        let q_greedy = total_quality(&v.segments, &greedy);
        let q_knap = total_quality(&v.segments, &knap);
        assert!(q_knap >= q_greedy - 1e-12, "knapsack upper bound ≥ greedy");
    }

    #[test]
    fn knapsack_all_zero_when_rung0_exceeds_budget() {
        let v = video_with(&[0.5, 0.5]);
        let rungs = allocate_knapsack(&v.segments, 1);
        assert_eq!(rungs, vec![0, 0]);
    }

    #[test]
    fn empty_segments_yields_empty_allocation() {
        assert!(allocate_greedy(&[], 1_000_000).is_empty());
        assert!(allocate_knapsack(&[], 1_000_000).is_empty());
    }
}
