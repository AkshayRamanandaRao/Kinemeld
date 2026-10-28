//! Native project persistence and an explicit local bridge to the verified solver service.

mod backend;
mod error;
mod project;

pub use backend::{BackendClient, BackendService, BackendStatus, DeckResponse, Example, Health, Model, Simulation, SimulationResult, SolverStatus, Validation, ValidationIssue};
pub use error::{Error, Result};
pub use project::{ProjectDocument, ProjectSession, SaveMode, SaveOutcome, MAX_PROJECT_BYTES};
