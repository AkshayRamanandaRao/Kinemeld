use serde_json::Value;
use std::{fmt, io};

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug)]
pub enum Error {
    Io(io::Error),
    Json(serde_json::Error),
    InvalidProject(String),
    Conflict(String),
    Protocol(String),
    Backend { status: u16, payload: Value },
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(f, "{error}"),
            Self::Json(error) => write!(f, "Invalid JSON: {error}"),
            Self::InvalidProject(message) | Self::Conflict(message) | Self::Protocol(message) => f.write_str(message),
            Self::Backend { status, payload } => write!(f, "Backend HTTP {status}: {}", payload.get("error").and_then(Value::as_str).unwrap_or("Inspect the preserved response payload")),
        }
    }
}

impl std::error::Error for Error {}
impl From<io::Error> for Error { fn from(error: io::Error) -> Self { Self::Io(error) } }
impl From<serde_json::Error> for Error { fn from(error: serde_json::Error) -> Self { Self::Json(error) } }
