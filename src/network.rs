//! Network trace replay (Phase 0 minimal, Phase 6 full).
//!
//! CSV schema: `time_s,bandwidth_mbps` with strictly increasing `time_s`.
//! Built-in synthetic profiles cover the four §9.2 cases until real traces land.

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

/// One throughput sample.
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct NetworkSample {
    /// Timestamp in seconds.
    pub time_s: f64,
    /// Available bandwidth in megabits per second.
    pub bandwidth_mbps: f64,
}

/// Replayable bandwidth trace.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NetworkTrace {
    /// Human-readable profile name.
    pub name: String,
    /// Time-ordered samples.
    pub samples: Vec<NetworkSample>,
}

impl NetworkTrace {
    /// Parse a `time_s,bandwidth_mbps` CSV string (header required).
    ///
    /// Phase 0 uses a small std-only parser (no `csv` crate) so the harness
    /// builds offline. Phase 6 may adopt the `csv` crate without API change.
    pub fn from_csv_str(name: &str, csv_text: &str) -> Result<Self> {
        let mut lines = csv_text.lines();
        let header = lines
            .next()
            .ok_or_else(|| Error::Trace("empty csv".to_string()))?;
        if header.trim() != "time_s,bandwidth_mbps" {
            return Err(Error::Trace(format!("bad header: {header:?}")));
        }
        let mut samples = Vec::new();
        for (lineno, line) in lines.enumerate() {
            let line = line.trim();
            if line.is_empty() {
                continue;
            }
            let (a, b) = line.split_once(',').ok_or_else(|| {
                Error::Trace(format!("line {}: expected two columns", lineno + 2))
            })?;
            let time_s: f64 = a
                .trim()
                .parse()
                .map_err(|_| Error::Trace(format!("line {}: bad time_s {a:?}", lineno + 2)))?;
            let bandwidth_mbps: f64 = b
                .trim()
                .parse()
                .map_err(|_| Error::Trace(format!("line {}: bad bandwidth {b:?}", lineno + 2)))?;
            let s = NetworkSample {
                time_s,
                bandwidth_mbps,
            };
            if s.time_s < 0.0 || s.bandwidth_mbps <= 0.0 {
                return Err(Error::Trace(format!("bad sample: {s:?}")));
            }
            samples.push(s);
        }
        if samples.is_empty() {
            return Err(Error::Trace("trace has no samples".to_string()));
        }
        if !samples.windows(2).all(|w| w[1].time_s > w[0].time_s) {
            return Err(Error::Trace(
                "time_s must be strictly increasing".to_string(),
            ));
        }
        Ok(Self {
            name: name.to_string(),
            samples,
        })
    }

    /// Read a trace CSV from disk.
    pub fn from_csv_file(name: &str, path: &std::path::Path) -> Result<Self> {
        let text = std::fs::read_to_string(path)?;
        Self::from_csv_str(name, &text)
    }

    /// Available bandwidth (bps) at `time_s`, using a step-function hold of the
    /// most recent sample at or before `time_s`. Returns 0.0 for an empty trace.
    pub fn bandwidth_at(&self, time_s: f64) -> f64 {
        if self.samples.is_empty() {
            return 0.0;
        }
        let mut best = self.samples[0];
        for s in &self.samples {
            if s.time_s <= time_s {
                best = *s;
            } else {
                break;
            }
        }
        best.bandwidth_mbps * 1_000_000.0 // Mbps → bps
    }

    /// Constant-bandwidth synthetic profile (covers "stable-high" / "moderate").
    pub fn constant(name: &str, bandwidth_mbps: f64, duration_s: f64, step_s: f64) -> Result<Self> {
        if bandwidth_mbps <= 0.0 || duration_s <= 0.0 || step_s <= 0.0 {
            return Err(Error::InvalidConfig(
                "profile params must be > 0".to_string(),
            ));
        }
        let mut samples = Vec::new();
        let mut t = 0.0;
        while t <= duration_s {
            samples.push(NetworkSample {
                time_s: t,
                bandwidth_mbps,
            });
            t += step_s;
        }
        Ok(Self {
            name: name.to_string(),
            samples,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CSV: &str = "time_s,bandwidth_mbps\n0.0,5.0\n4.0,4.5\n8.0,6.0\n";

    #[test]
    fn parses_valid_csv() {
        let t = NetworkTrace::from_csv_str("stable", CSV).unwrap();
        assert_eq!(t.samples.len(), 3);
        assert_eq!(t.samples[0].bandwidth_mbps, 5.0);
    }

    #[test]
    fn rejects_non_increasing_time() {
        let bad = "time_s,bandwidth_mbps\n0.0,5.0\n0.0,4.0\n";
        assert!(NetworkTrace::from_csv_str("bad", bad).is_err());
    }

    #[test]
    fn rejects_empty() {
        let empty = "time_s,bandwidth_mbps\n";
        assert!(NetworkTrace::from_csv_str("empty", empty).is_err());
    }

    #[test]
    fn constant_profile_is_monotone() {
        let t = NetworkTrace::constant("stable-high", 8.0, 20.0, 4.0).unwrap();
        assert!(t.samples.windows(2).all(|w| w[1].time_s > w[0].time_s));
    }
}
