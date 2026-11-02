use mbdyn_studio_core::ProjectSession;
use std::path::PathBuf;

struct PreviousProject {
    session: Option<ProjectSession>,
    dirty: bool,
    edited: bool,
    token: String,
}

/// Holds both project sessions until the frontend has applied the candidate.
#[derive(Default)]
pub(crate) struct ProjectOpenState {
    pub(crate) session: Option<ProjectSession>,
    pub(crate) dirty: bool,
    pub(crate) recovered_from: Option<PathBuf>,
    pub(crate) pending_recovered_from: Option<PathBuf>,
    pending: Option<ProjectSession>,
    previous: Option<PreviousProject>,
    next_token: u64,
    last_finalized: Option<String>,
    dirty_revision: u64,
}

impl ProjectOpenState {
    pub(crate) fn is_opening(&self) -> bool {
        self.pending.is_some() || self.previous.is_some()
    }

    pub(crate) fn ensure_idle(&self) -> Result<(), &'static str> {
        if self.is_opening() { Err("A project open is already in progress.") } else { Ok(()) }
    }

    pub(crate) fn mark_dirty(&mut self) {
        self.dirty_revision = self.dirty_revision.saturating_add(1);
        self.dirty = true;
        if let Some(previous) = self.previous.as_mut() { previous.edited = true; }
    }

    pub(crate) fn set_pending(&mut self, candidate: ProjectSession) -> Result<(), &'static str> {
        self.ensure_idle()?;
        self.pending = Some(candidate);
        self.pending_recovered_from = None;
        Ok(())
    }

    pub(crate) fn discard_pending(&mut self) {
        self.pending = None;
        self.pending_recovered_from = None;
    }

    pub(crate) fn accept(&mut self) -> Result<String, &'static str> {
        if self.previous.is_some() { return Err("Another project open is awaiting finalization."); }
        if self.pending.is_none() { return Err("No project is awaiting confirmation."); }
        let sequence = self.next_token.checked_add(1).ok_or("Project transaction sequence exhausted.")?;
        let token = sequence.to_string();
        let candidate = self.pending.take().ok_or("No project is awaiting confirmation.")?;
        self.next_token = sequence;
        self.previous = Some(PreviousProject { session: self.session.take(), dirty: self.dirty, edited: false, token:token.clone() });
        self.session = Some(candidate);
        self.dirty_revision = self.dirty_revision.saturating_add(1);
        self.dirty = true;
        Ok(token)
    }

    pub(crate) fn finalize(&mut self, token: &str) -> Result<(), &'static str> {
        if let Some(previous) = self.previous.as_ref() {
            if previous.token != token { return Err("Project transaction does not match the accepted open."); }
            self.previous = None;
            self.recovered_from = self.pending_recovered_from.take();
            self.last_finalized = Some(token.to_owned());
            return Ok(());
        }
        if self.last_finalized.as_deref() == Some(token) { return Ok(()); }
        Err("No matching project open is awaiting finalization.")
    }

    pub(crate) fn dirty_revision(&self) -> String { self.dirty_revision.to_string() }

    pub(crate) fn confirm_clean(&mut self, token: &str, expected_revision: &str) -> Result<bool, &'static str> {
        if self.previous.is_some() || self.last_finalized.as_deref() != Some(token) {
            return Err("No matching finalized project can be marked clean.");
        }
        let revision = expected_revision.parse::<u64>().map_err(|_| "Invalid project dirty revision.")?;
        if revision != self.dirty_revision || revision == u64::MAX { return Ok(false); }
        self.dirty = false;
        Ok(true)
    }

    pub(crate) fn rollback(&mut self, token: &str) -> Result<(), &'static str> {
        if self.previous.as_ref().map(|previous| previous.token.as_str()) != Some(token) {
            return Err("No matching project open is awaiting rollback.");
        }
        let previous = self.previous.take().ok_or("No opened project is awaiting rollback.")?;
        self.session = previous.session;
        self.dirty = previous.dirty || previous.edited;
        self.pending_recovered_from = None;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use mbdyn_studio_core::ProjectDocument;
    use serde_json::json;

    fn session(name: &str) -> ProjectSession {
        ProjectSession::new(ProjectDocument::new(json!({"kind":"pendulum","name":name})).unwrap()).unwrap()
    }
    fn name(state: &ProjectOpenState) -> Option<&str> {
        state.session.as_ref().and_then(|session| session.document().model["name"].as_str())
    }

    #[test]
    fn rollback_restores_session_and_dirty_state() {
        for dirty in [false, true] {
            let mut state = ProjectOpenState { session:Some(session("old")), dirty, ..Default::default() };
            state.set_pending(session("new")).unwrap();
            let token=state.accept().unwrap();
            assert_eq!(name(&state),Some("new"));
            assert!(state.dirty);
            state.rollback(&token).unwrap();
            assert_eq!(name(&state),Some("old"));
            assert_eq!(state.dirty,dirty);
            assert!(!state.is_opening());
        }
    }

    #[test]
    fn rollback_without_prior_session_preserves_unsaved_edits() {
        let mut state = ProjectOpenState::default();
        state.mark_dirty();
        state.set_pending(session("new")).unwrap();
        let token=state.accept().unwrap();
        state.rollback(&token).unwrap();
        assert!(state.session.is_none());
        assert!(state.dirty);
    }

    #[test]
    fn edits_during_provisional_open_remain_dirty_on_rollback_or_finalize() {
        for finalize in [false,true] {
            let mut state = ProjectOpenState { session:Some(session("old")), ..Default::default() };
            state.set_pending(session("new")).unwrap();
            let token=state.accept().unwrap();
            state.mark_dirty();
            if finalize { state.finalize(&token).unwrap(); assert_eq!(name(&state),Some("new")); }
            else { state.rollback(&token).unwrap(); assert_eq!(name(&state),Some("old")); }
            assert!(state.dirty);
        }
    }

    #[test]
    fn rollback_keeps_original_file_identity_and_external_change_detection() {
        use mbdyn_studio_core::{Error, SaveMode};
        use std::{fs, time::{SystemTime, UNIX_EPOCH}};
        let suffix=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let directory=std::env::temp_dir().join(format!("mbdyn-open-{}-{suffix}",std::process::id()));
        fs::create_dir(&directory).unwrap();
        let path=directory.join("original.mbdyn-studio");
        let mut original=session("old");
        original.save_as(&path,SaveMode::CreateNew).unwrap();
        let mut state=ProjectOpenState { session:Some(original), dirty:true, ..Default::default() };
        state.set_pending(session("candidate")).unwrap();
        let token=state.accept().unwrap();
        fs::write(&path,b"externally changed").unwrap();
        state.rollback(&token).unwrap();
        let restored=state.session.as_mut().unwrap();
        assert_eq!(restored.path(),Some(fs::canonicalize(&path).unwrap().as_path()));
        assert!(matches!(restored.save(),Err(Error::Conflict(_))));
        assert_eq!(fs::read(&path).unwrap(),b"externally changed");
        assert!(state.dirty);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn new_project_stays_pathless_and_rollback_restores_the_previous_file() {
        use mbdyn_studio_core::SaveMode;
        use std::{fs, time::{SystemTime, UNIX_EPOCH}};
        let suffix=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let directory=std::env::temp_dir().join(format!("mbdyn-new-{}-{suffix}",std::process::id()));
        fs::create_dir(&directory).unwrap();
        let path=directory.join("original.mbdyn-studio");
        let mut original=session("old");
        original.save_as(&path,SaveMode::CreateNew).unwrap();
        let bytes=fs::read(&path).unwrap();
        let mut state=ProjectOpenState { session:Some(original), ..Default::default() };
        state.set_pending(session("new")).unwrap();
        let token=state.accept().unwrap();
        assert!(state.session.as_ref().unwrap().path().is_none());
        state.rollback(&token).unwrap();
        assert_eq!(state.session.as_ref().unwrap().path(),Some(fs::canonicalize(&path).unwrap().as_path()));
        state.set_pending(session("new")).unwrap();
        let token=state.accept().unwrap();
        state.finalize(&token).unwrap();
        assert!(state.session.as_ref().unwrap().path().is_none());
        assert!(state.session.as_mut().unwrap().save().is_err());
        assert!(state.dirty);
        assert_eq!(fs::read(&path).unwrap(),bytes);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn recovery_origin_changes_only_when_its_project_is_finalized() {
        let old=PathBuf::from("old.mbdyn-studio");
        let recovered=PathBuf::from("recovered.mbdyn-studio");
        let mut state=ProjectOpenState { session:Some(session("old")), recovered_from:Some(old.clone()), ..Default::default() };
        state.set_pending(session("discarded")).unwrap();
        state.pending_recovered_from=Some(recovered.clone());
        state.discard_pending();
        assert_eq!(state.recovered_from,Some(old.clone()));
        state.set_pending(session("rolled back")).unwrap();
        let token=state.accept().unwrap();
        state.rollback(&token).unwrap();
        assert_eq!(state.recovered_from,Some(old));
        state.set_pending(session("recovered")).unwrap();
        state.pending_recovered_from=Some(recovered.clone());
        let token=state.accept().unwrap();
        state.finalize(&token).unwrap();
        state.finalize(&token).unwrap();
        assert_eq!(state.recovered_from,Some(recovered));
        state.set_pending(session("new")).unwrap();
        let token=state.accept().unwrap();
        state.finalize(&token).unwrap();
        assert!(state.recovered_from.is_none());
    }

    #[test]
    fn finalize_is_idempotent_only_for_the_matching_transaction() {
        let mut state=ProjectOpenState { session:Some(session("old")), dirty:true, ..Default::default() };
        state.set_pending(session("first")).unwrap();
        let first=state.accept().unwrap();
        assert!(state.finalize("wrong").is_err());
        assert!(state.rollback("wrong").is_err());
        assert_eq!(name(&state),Some("first"));
        state.mark_dirty();
        state.finalize(&first).unwrap();
        state.finalize(&first).unwrap();
        assert!(state.dirty);
        assert!(state.rollback(&first).is_err());
        state.set_pending(session("second")).unwrap();
        let second=state.accept().unwrap();
        assert_ne!(first,second);
        assert!(state.finalize(&first).is_err());
        assert!(state.rollback(&first).is_err());
        assert_eq!(name(&state),Some("second"));
        state.rollback(&second).unwrap();
        assert_eq!(name(&state),Some("first"));
        assert!(state.dirty);
    }

    #[test]
    fn clean_handshake_is_scoped_to_the_finalized_token_and_dirty_revision() {
        let mut state=ProjectOpenState { session:Some(session("old")), ..Default::default() };
        state.set_pending(session("new")).unwrap();
        let token=state.accept().unwrap();
        let initial=state.dirty_revision();
        assert!(state.dirty);
        assert!(state.confirm_clean(&token,&initial).is_err());
        state.finalize(&token).unwrap();
        assert!(state.dirty, "lost finalize replies must leave close protection enabled");
        assert!(state.confirm_clean("wrong",&initial).is_err());
        state.mark_dirty();
        assert!(!state.confirm_clean(&token,&initial).unwrap());
        assert!(state.dirty, "an edit before the clean handshake must remain dirty");
        let current=state.dirty_revision();
        assert!(state.confirm_clean(&token,&current).unwrap());
        assert!(!state.dirty);
        state.mark_dirty();
        assert!(state.dirty, "an edit after clean must restore close protection");
        assert!(!state.confirm_clean(&token,&current).unwrap());
        assert!(state.dirty);
    }

    #[test]
    fn invalid_transitions_do_not_discard_pending_or_prior_sessions() {
        let mut state = ProjectOpenState { session:Some(session("old")), ..Default::default() };
        assert!(state.accept().is_err());
        assert!(state.finalize("1").is_err());
        assert!(state.rollback("1").is_err());
        state.set_pending(session("first")).unwrap();
        assert!(state.set_pending(session("second")).is_err());
        assert!(state.ensure_idle().is_err());
        let token=state.accept().unwrap();
        assert!(state.accept().is_err());
        assert!(state.set_pending(session("second")).is_err());
        assert!(state.ensure_idle().is_err());
        state.rollback(&token).unwrap();
        assert_eq!(name(&state),Some("old"));
        assert!(state.ensure_idle().is_ok());
        state.set_pending(session("discard")).unwrap();
        state.discard_pending();
        assert_eq!(name(&state),Some("old"));
        assert!(state.ensure_idle().is_ok());
    }
}
