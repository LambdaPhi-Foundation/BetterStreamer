//! Content analysis: motion, complexity, priority.
//!
//! Phase 0: stable module paths + pure-function signatures so later phases
//! never reorganize imports. Real algorithms land in Phases 2–3.

pub mod complexity;
pub mod motion;
pub mod priority;

pub use complexity::complexity_score;
pub use motion::motion_score;
pub use priority::{Priority, priority_score};
