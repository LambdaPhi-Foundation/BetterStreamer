//! BetterStreamer library crate.
//!
//! Content-aware adaptive bitrate (ABR) simulator.
//! See `MarkDocumentation/SUPER.md` for the master plan.
//!
//! Pipeline: Video → Content Analysis → Priority → Allocation → Simulation → Metrics.
//! Phase 0 establishes module layout and determinism harness; later phases fill in
//! algorithms. All shared configuration lives in [`config::SimulatorConfig`].

pub mod abr;
pub mod analysis;
pub mod config;
pub mod error;
pub mod media;
pub mod metrics;
pub mod network;
pub mod simulation;

pub use config::SimulatorConfig;
pub use error::{Error, Result};
