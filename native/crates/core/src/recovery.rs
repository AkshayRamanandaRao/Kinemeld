//! Crash recovery for the desktop app. Unsaved work is written to one snapshot in the user's data
//! folder, replaced atomically, and removed after an explicit save or a clean close; a snapshot
//! found at start-up therefore belongs to a session that ended without either.

use crate::{Error, ProjectDocument, Result, MAX_PROJECT_BYTES};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::{ErrorKind, Read, Write},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

const FORMAT: &str = "kinemeld-recovery/1";
const SNAPSHOT: &str = "autosave.json";
const SET_ASIDE_PREFIX: &str = "declined-";
const KEEP_SET_ASIDE: usize = 3;
/// Room for the envelope around a project at the project size limit.
const MAX_SNAPSHOT_BYTES: u64 = MAX_PROJECT_BYTES + 64 * 1024;

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RecoverySnapshot {
    pub format: String,
    /// Milliseconds since the Unix epoch when the snapshot was written.
    pub saved_at: u64,
    /// The project file the unsaved edits belong to, when it had been saved or opened.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub project_path: Option<PathBuf>,
    pub document: ProjectDocument,
}

pub struct RecoveryStore {
    directory: PathBuf,
}

impl RecoveryStore {
    /// Use `directory` for snapshots, removing temporary files left by a crash during a write.
    pub fn new(directory: impl Into<PathBuf>) -> Result<Self> {
        let directory = directory.into();
        fs::create_dir_all(&directory)?;
        for entry in fs::read_dir(&directory)?.flatten() {
            let name = entry.file_name();
            let name = name.to_string_lossy();
            if name.starts_with(&format!(".{SNAPSHOT}.")) && name.ends_with(".new") {
                let _ = fs::remove_file(entry.path());
            }
        }
        Ok(Self { directory })
    }

    pub fn snapshot_path(&self) -> PathBuf {
        self.directory.join(SNAPSHOT)
    }

    /// Replace the snapshot atomically: a crash mid-write leaves the previous snapshot intact.
    pub fn write(&self, document: &ProjectDocument, project_path: Option<&Path>) -> Result<RecoverySnapshot> {
        document.check()?;
        let snapshot = RecoverySnapshot { format: FORMAT.into(), saved_at: now_ms(), project_path: project_path.map(Path::to_path_buf), document: document.clone() };
        let bytes = serde_json::to_vec(&snapshot)?;
        if bytes.len() as u64 > MAX_SNAPSHOT_BYTES {
            return Err(Error::InvalidProject("The project exceeds the 32 MiB limit, so it cannot be kept for recovery; save it with a smaller result.".into()));
        }
        let temporary = self.directory.join(format!(".{SNAPSHOT}.{}-{}.new", std::process::id(), snapshot.saved_at));
        let mut file = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
        let written = file.write_all(&bytes).and_then(|()| file.sync_all());
        drop(file);
        if let Err(error) = written.and_then(|()| fs::rename(&temporary, self.snapshot_path())) {
            let _ = fs::remove_file(&temporary);
            return Err(error.into());
        }
        sync_directory(&self.directory);
        Ok(snapshot)
    }

    /// The snapshot left by an earlier session, if any. An unreadable snapshot is an error, so the
    /// caller can set it aside instead of losing it.
    pub fn read(&self) -> Result<Option<RecoverySnapshot>> {
        let file = match File::open(self.snapshot_path()) {
            Ok(file) => file,
            Err(error) if error.kind() == ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error.into()),
        };
        let mut bytes = Vec::new();
        file.take(MAX_SNAPSHOT_BYTES + 1).read_to_end(&mut bytes)?;
        if bytes.len() as u64 > MAX_SNAPSHOT_BYTES {
            return Err(Error::InvalidProject("The recovery snapshot exceeds the project size limit.".into()));
        }
        let snapshot: RecoverySnapshot = serde_json::from_slice(&bytes).map_err(|error| Error::InvalidProject(format!("The recovery snapshot is unreadable: {error}")))?;
        if snapshot.format != FORMAT {
            return Err(Error::InvalidProject("The recovery snapshot has an unsupported format.".into()));
        }
        snapshot.document.check()?;
        Ok(Some(snapshot))
    }

    /// Remove the snapshot once its work is saved or deliberately discarded.
    pub fn clear(&self) -> Result<()> {
        match fs::remove_file(self.snapshot_path()) {
            Err(error) if error.kind() != ErrorKind::NotFound => Err(error.into()),
            _ => Ok(()),
        }
    }

    /// Keep a declined or unreadable snapshot under a dated name; only the newest few are kept.
    pub fn set_aside(&self) -> Result<Option<PathBuf>> {
        let source = self.snapshot_path();
        if !source.try_exists()? {
            return Ok(None);
        }
        let target = self.directory.join(format!("{SET_ASIDE_PREFIX}{:020}.json", now_ms()));
        fs::rename(&source, &target)?;
        let mut aside: Vec<PathBuf> = fs::read_dir(&self.directory)?
            .flatten()
            .map(|entry| entry.path())
            .filter(|path| path.file_name().and_then(|name| name.to_str()).is_some_and(|name| name.starts_with(SET_ASIDE_PREFIX) && name.ends_with(".json")))
            .collect();
        // Zero-padded timestamps sort chronologically.
        aside.sort();
        let excess = aside.len().saturating_sub(KEEP_SET_ASIDE);
        for old in &aside[..excess] {
            fs::remove_file(old)?;
        }
        Ok(Some(target))
    }
}

fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |time| u64::try_from(time.as_millis()).unwrap_or(u64::MAX))
}

/// Persist the rename itself; Windows has no directory handle to flush.
#[cfg(unix)]
fn sync_directory(directory: &Path) {
    if let Ok(handle) = File::open(directory) {
        let _ = handle.sync_all();
    }
}

#[cfg(not(unix))]
fn sync_directory(_directory: &Path) {}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);

    fn folder() -> PathBuf {
        let path = std::env::temp_dir().join(format!("kinemeld-recovery-{}-{}-{}", std::process::id(), now_ms(), NEXT.fetch_add(1, Ordering::Relaxed)));
        fs::create_dir_all(&path).unwrap();
        path
    }
    fn document(name: &str) -> ProjectDocument {
        ProjectDocument::new(json!({"kind":"pendulum","name":name})).unwrap()
    }
    fn names(directory: &Path) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(directory).unwrap().flatten().map(|entry| entry.file_name().to_string_lossy().into_owned()).collect();
        names.sort();
        names
    }

    #[test]
    fn snapshot_round_trips_and_replaces_atomically() {
        let directory = folder();
        let store = RecoveryStore::new(&directory).unwrap();
        assert_eq!(store.read().unwrap(), None);
        store.write(&document("first"), None).unwrap();
        let original = directory.join("project.mbdyn-studio");
        let written = store.write(&document("second"), Some(&original)).unwrap();
        let read = store.read().unwrap().unwrap();
        assert_eq!(read, written);
        assert_eq!(read.document.model["name"], "second");
        assert_eq!(read.project_path.as_deref(), Some(original.as_path()));
        assert_eq!(names(&directory), vec![SNAPSHOT.to_string()], "no temporary files remain");
        store.clear().unwrap();
        store.clear().unwrap();
        assert_eq!(store.read().unwrap(), None);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn interrupted_writes_leave_the_previous_snapshot_and_are_cleaned_up() {
        let directory = folder();
        let store = RecoveryStore::new(&directory).unwrap();
        store.write(&document("kept"), None).unwrap();
        fs::write(directory.join(format!(".{SNAPSHOT}.123-456.new")), b"{\"partial").unwrap();
        let store = RecoveryStore::new(&directory).unwrap();
        assert_eq!(names(&directory), vec![SNAPSHOT.to_string()]);
        assert_eq!(store.read().unwrap().unwrap().document.model["name"], "kept");
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn oversized_projects_are_refused_without_touching_the_snapshot() {
        let directory = folder();
        let store = RecoveryStore::new(&directory).unwrap();
        store.write(&document("kept"), None).unwrap();
        let mut large = document("large");
        large.extra.insert("assets".into(), json!("x".repeat(MAX_SNAPSHOT_BYTES as usize)));
        assert!(matches!(store.write(&large, None), Err(Error::InvalidProject(_))));
        assert_eq!(store.read().unwrap().unwrap().document.model["name"], "kept");
        assert_eq!(names(&directory), vec![SNAPSHOT.to_string()]);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn damaged_snapshots_are_reported_and_can_be_set_aside() {
        let directory = folder();
        let store = RecoveryStore::new(&directory).unwrap();
        fs::write(store.snapshot_path(), b"{not json").unwrap();
        assert!(matches!(store.read(), Err(Error::InvalidProject(_))));
        let aside = store.set_aside().unwrap().unwrap();
        assert_eq!(fs::read(aside).unwrap(), b"{not json");
        assert_eq!(store.read().unwrap(), None);
        assert_eq!(store.set_aside().unwrap(), None);
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn only_the_newest_set_aside_snapshots_are_kept() {
        let directory = folder();
        let store = RecoveryStore::new(&directory).unwrap();
        for index in 0..5 {
            store.write(&document(&format!("run {index}")), None).unwrap();
            store.set_aside().unwrap();
            std::thread::sleep(std::time::Duration::from_millis(2));
        }
        let kept = names(&directory);
        assert_eq!(kept.len(), KEEP_SET_ASIDE);
        let newest: RecoverySnapshot = serde_json::from_slice(&fs::read(directory.join(kept.last().unwrap())).unwrap()).unwrap();
        assert_eq!(newest.document.model["name"], "run 4");
        fs::remove_dir_all(directory).unwrap();
    }
}
