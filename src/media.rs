//! Segment / representation data model (Phase 0 minimal, Phase 1 full).
//!
//! Word-doc §10.1 maps to these structs. Phase 0 provides the minimal validated
//! model needed for the determinism harness; Phase 1 adds ladder presets,
//! synthetic catalog kinds (§9.1), and richer validation.

use serde::{Deserialize, Serialize};

use crate::{Error, Result};

/// One encodable quality level.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Representation {
    /// Index into the ladder (0 = lowest).
    pub id: usize,
    /// Display width in px.
    pub width: u32,
    /// Display height in px.
    pub height: u32,
    /// Average bitrate in bits per second.
    pub bitrate_bps: u64,
}

/// Lightweight per-chunk content features.
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq)]
pub struct SegmentFeatures {
    /// Temporal change, normalized [0,1]. Phase 2 computes for real.
    pub motion: f64,
    /// Spatial detail / encoding difficulty, normalized [0,1].
    pub complexity: f64,
    /// `w_m*motion + w_c*complexity`, normalized [0,1]. Phase 3 computes.
    pub priority: f64,
}

/// One independently downloadable video chunk.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Segment {
    /// Zero-based chunk index.
    pub id: usize,
    /// Chunk duration in seconds.
    pub duration_s: f64,
    /// Content features (synthetic until Phase 2/3).
    pub features: SegmentFeatures,
    /// Available quality representations (shared ladder copy per segment).
    pub representations: Vec<Representation>,
}

impl Segment {
    /// Size in bytes of downloading this segment at the given representation.
    pub fn bytes_at(&self, representation_id: usize) -> Result<u64> {
        let r = self
            .representations
            .iter()
            .find(|r| r.id == representation_id)
            .ok_or_else(|| {
                Error::InvalidConfig(format!("unknown representation {representation_id}"))
            })?;
        Ok((r.bitrate_bps as f64 * self.duration_s / 8.0) as u64)
    }
}

/// A chunked video: ordered segments sharing one ladder.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Video {
    /// Human-readable catalog name (e.g. "mixed", "talking-head").
    pub name: String,
    /// Ordered chunks.
    pub segments: Vec<Segment>,
}

impl Video {
    /// Build a synthetic video: `num_segments` chunks × `ladder_bps` rungs.
    ///
    /// Features are deterministic placeholders (all zeros); Phases 2–3 fill them.
    /// Used by Phase 0 harness + CLI before real analysis exists.
    pub fn synthetic(
        name: &str,
        num_segments: usize,
        segment_duration_s: f64,
        ladder_bps: &[u64],
    ) -> Result<Self> {
        if num_segments == 0 {
            return Err(Error::InvalidConfig("num_segments must be > 0".to_string()));
        }
        if segment_duration_s <= 0.0 {
            return Err(Error::InvalidConfig(
                "segment_duration_s must be > 0".to_string(),
            ));
        }
        if ladder_bps.is_empty() {
            return Err(Error::InvalidConfig("ladder must not be empty".to_string()));
        }
        let representations: Vec<Representation> = ladder_bps
            .iter()
            .enumerate()
            .map(|(id, &bitrate_bps)| Representation {
                id,
                // Placeholder 16:9 ladder widths; Phase 1 refines.
                width: 640 + id as u32 * 320,
                height: 360 + id as u32 * 180,
                bitrate_bps,
            })
            .collect();
        let segments = (0..num_segments)
            .map(|id| Segment {
                id,
                duration_s: segment_duration_s,
                features: SegmentFeatures::default(),
                representations: representations.clone(),
            })
            .collect();
        Ok(Self {
            name: name.to_string(),
            segments,
        })
    }

    /// Number of segments.
    pub fn len(&self) -> usize {
        self.segments.len()
    }

    /// Build a synthetic video with deterministic, varying content features so
    /// the content-aware policy has signal to act on. Features cycle through
    /// deterministic motion/complexity values per segment index.
    pub fn synthetic_with_features(
        name: &str,
        num_segments: usize,
        segment_duration_s: f64,
        ladder_bps: &[u64],
    ) -> Result<Self> {
        let mut base = Self::synthetic(name, num_segments, segment_duration_s, ladder_bps)?;
        for (i, seg) in base.segments.iter_mut().enumerate() {
            let motion = ((i * 7) % 10) as f64 / 10.0;
            let complexity = ((i * 13) % 10) as f64 / 10.0;
            let priority = (0.6 * motion + 0.4 * complexity).clamp(0.0, 1.0);
            seg.features = SegmentFeatures {
                motion,
                complexity,
                priority,
            };
        }
        Ok(base)
    }

    /// True if the video has no segments.
    pub fn is_empty(&self) -> bool {
        self.segments.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::default_ladder;

    #[test]
    fn synthetic_video_is_n_segments_by_m_representations() {
        let ladder = default_ladder();
        let v = Video::synthetic("mixed", 8, 4.0, &ladder).unwrap();
        assert_eq!(v.len(), 8);
        for s in &v.segments {
            assert_eq!(s.representations.len(), ladder.len());
        }
    }

    #[test]
    fn rejects_empty_inputs() {
        assert!(Video::synthetic("x", 0, 4.0, &default_ladder()).is_err());
        assert!(Video::synthetic("x", 4, 0.0, &default_ladder()).is_err());
        assert!(Video::synthetic("x", 4, 4.0, &[]).is_err());
    }

    #[test]
    fn bytes_at_scales_with_bitrate() {
        let v = Video::synthetic("x", 1, 4.0, &[400_000, 800_000]).unwrap();
        let lo = v.segments[0].bytes_at(0).unwrap();
        let hi = v.segments[0].bytes_at(1).unwrap();
        assert_eq!(hi, lo * 2);
    }

    #[test]
    fn json_round_trip() {
        let v = Video::synthetic("mixed", 2, 4.0, &default_ladder()).unwrap();
        let s = serde_json::to_string(&v).unwrap();
        let back: Video = serde_json::from_str(&s).unwrap();
        assert_eq!(v, back);
    }
}
