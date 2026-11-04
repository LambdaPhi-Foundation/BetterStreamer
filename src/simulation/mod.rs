//! Deterministic player + simulator (full: Phase 6).
//!
//! Phase 0: stable module paths + report shape so the CLI can already emit
//! comparable JSON. Event loop + buffer accounting land in Phase 6.

pub mod player;
pub mod simulator;

pub use player::PlayerState;
pub use simulator::{SimPolicy, SimulationReport, Simulator};
