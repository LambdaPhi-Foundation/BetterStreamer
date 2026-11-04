//! Typed errors for BetterStreamer.
//!
//! Phase 0: central error type so later phases never resort to stringly errors.

use thiserror::Error;

/// Crate-wide error type.
#[derive(Debug, Error)]
pub enum Error {
    /// Configuration or input validation failed.
    #[error("invalid config: {0}")]
    InvalidConfig(String),

    /// CSV / trace parsing failed.
    #[error("trace error: {0}")]
    Trace(String),

    /// Generic I/O failure with context.
    #[error("io error: {0}")]
    Io(String),

    /// JSON (report / video descriptor) failure.
    #[error("json error: {0}")]
    Json(String),
}

/// Crate-wide result alias.
pub type Result<T> = std::result::Result<T, Error>;

impl From<std::io::Error> for Error {
    fn from(e: std::io::Error) -> Self {
        Self::Io(e.to_string())
    }
}

impl From<serde_json::Error> for Error {
    fn from(e: serde_json::Error) -> Self {
        Self::Json(e.to_string())
    }
}
