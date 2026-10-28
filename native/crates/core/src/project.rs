use crate::{Error, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{collections::BTreeMap, fs::{self, File, OpenOptions}, io::{Read, Write}, path::{Path, PathBuf}, sync::atomic::{AtomicU64, Ordering}, time::{SystemTime, UNIX_EPOCH}};

pub const MAX_PROJECT_BYTES: u64 = 32 * 1024 * 1024;
static NEXT_FILE: AtomicU64 = AtomicU64::new(0);

fn version() -> u32 { 1 }

/// Portable project envelope. Model, result, raw CSV and provenance remain lossless JSON.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectDocument {
    pub format: String,
    #[serde(default = "version")]
    pub schema_version: u32,
    pub model: Value,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(default)]
    pub view: Value,
    #[serde(flatten)]
    pub extra: BTreeMap<String, Value>,
}

impl ProjectDocument {
    pub fn new(model: Value) -> Result<Self> {
        let result = Self { format: "mbdyn-studio/1".into(), schema_version: 1, model, result: None, view: Value::Null, extra: BTreeMap::new() };
        result.check()?;
        Ok(result)
    }

    /// Structural validation only: the backend validates physics before solving.
    pub fn check(&self) -> Result<()> {
        if self.format != "mbdyn-studio/1" || self.schema_version != 1 {
            return Err(Error::InvalidProject("Unsupported project format or schema version; the file was not modified.".into()));
        }
        let model = self.model.as_object().ok_or_else(|| Error::InvalidProject("Project model must be an object.".into()))?;
        for field in ["kind", "name"] {
            let text = model.get(field).and_then(Value::as_str).ok_or_else(|| Error::InvalidProject(format!("Project model.{field} must be text.")))?;
            if text.trim().is_empty() || text.len() > 512 || text.chars().any(char::is_control) {
                return Err(Error::InvalidProject(format!("Project model.{field} must contain 1–512 printable bytes.")));
            }
        }
        if self.result.as_ref().is_some_and(|value| !value.is_object()) {
            return Err(Error::InvalidProject("A stored result must be a JSON object.".into()));
        }
        Ok(())
    }

    fn bytes(&self) -> Result<Vec<u8>> {
        self.check()?;
        let mut bytes = serde_json::to_vec_pretty(self)?;
        bytes.push(b'\n');
        if bytes.len() as u64 > MAX_PROJECT_BYTES {
            return Err(Error::InvalidProject("Project exceeds the 32 MiB limit. Export very large raw results separately.".into()));
        }
        Ok(bytes)
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SaveMode { CreateNew, ReplaceExisting }

#[derive(Clone, Debug)]
pub struct SaveOutcome { pub path: PathBuf, pub backup: Option<PathBuf> }

/// A loaded file snapshot prevents ordinary Save from overwriting external edits.
pub struct ProjectSession {
    document: ProjectDocument,
    path: Option<PathBuf>,
    saved_document: Option<ProjectDocument>,
    saved_bytes: Option<Vec<u8>>,
}

impl ProjectSession {
    pub fn new(document: ProjectDocument) -> Result<Self> {
        document.bytes()?;
        Ok(Self { document, path: None, saved_document: None, saved_bytes: None })
    }
    pub fn open(path: &Path) -> Result<Self> {
        let path = absolute_target(path)?;
        reject_symlink(&path)?;
        let bytes = read_bounded(&path)?;
        let raw: Value = serde_json::from_slice(&bytes)?;
        let document: ProjectDocument = if raw.get("format").is_some() { serde_json::from_value(raw)? } else { ProjectDocument::new(raw)? };
        document.check()?;
        Ok(Self { saved_document: Some(document.clone()), document, path: Some(path), saved_bytes: Some(bytes) })
    }
    pub fn document(&self) -> &ProjectDocument { &self.document }
    pub fn path(&self) -> Option<&Path> { self.path.as_deref() }
    pub fn is_dirty(&self) -> bool { self.saved_document.as_ref() != Some(&self.document) }
    pub fn replace_document(&mut self, document: ProjectDocument) -> Result<()> {
        document.bytes()?;
        self.document = document;
        Ok(())
    }
    pub fn save(&mut self) -> Result<SaveOutcome> {
        let path = self.path.clone().ok_or_else(|| Error::InvalidProject("Choose a project path with Save As first.".into()))?;
        self.write(&path, SaveMode::ReplaceExisting, true)
    }
    pub fn save_as(&mut self, path: &Path, mode: SaveMode) -> Result<SaveOutcome> {
        let path = absolute_target(path)?;
        let check_snapshot = match self.path.as_ref() {
            Some(current) => same_destination(current, &path)?,
            None => false,
        };
        self.write(&path, mode, check_snapshot)
    }
    fn write(&mut self, path: &Path, mode: SaveMode, check_snapshot: bool) -> Result<SaveOutcome> {
        let bytes = self.document.bytes()?;
        let _lock = SaveLock::acquire(path)?;
        reject_symlink(path)?;
        let exists = path.try_exists()?;
        if check_snapshot {
            let current = read_bounded(path).map_err(|_| Error::Conflict("The project was removed or cannot be read. Save As to a new file; the current file was not modified.".into()))?;
            if self.saved_bytes.as_ref() != Some(&current) {
                return Err(Error::Conflict("The project changed on disk after it was opened/saved. Reload it or Save As a new file; external edits were not overwritten.".into()));
            }
        }
        if exists && mode == SaveMode::CreateNew {
            return Err(Error::Conflict("That file already exists. Choose another name or explicitly replace it.".into()));
        }
        let temporary = sibling(path, "new");
        let mut file = OpenOptions::new().write(true).create_new(true).open(&temporary)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        let backup = if exists {
            let backup = sibling(path, "backup");
            if let Err(error) = replace_with_backup(path, &temporary, &backup) {
                // Leave both recovery candidates intact if replacement fails.
                return Err(Error::Conflict(format!("Project replacement failed: {error}. Recovery files, if created, are {} and {}.", temporary.display(), backup.display())));
            }
            Some(backup)
        } else {
            // Hard-link creation never replaces a competing writer's new file.
            if let Err(error) = fs::hard_link(&temporary, path) {
                let _ = fs::remove_file(&temporary);
                return Err(Error::Io(error));
            }
            fs::remove_file(&temporary)?;
            None
        };
        self.path = Some(path.to_path_buf());
        self.saved_bytes = Some(bytes);
        self.saved_document = Some(self.document.clone());
        Ok(SaveOutcome { path: path.to_path_buf(), backup })
    }
}

fn read_bounded(path: &Path) -> Result<Vec<u8>> {
    let file = File::open(path)?;
    if file.metadata()?.len() > MAX_PROJECT_BYTES { return Err(Error::InvalidProject("Project exceeds the 32 MiB limit.".into())); }
    let mut bytes = Vec::new();
    file.take(MAX_PROJECT_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_PROJECT_BYTES { return Err(Error::InvalidProject("Project grew beyond the 32 MiB limit while reading.".into())); }
    Ok(bytes)
}

fn absolute_target(path: &Path) -> Result<PathBuf> {
    let name = path.file_name().ok_or_else(|| Error::InvalidProject("Choose a project filename.".into()))?;
    let parent = path.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or_else(|| Path::new("."));
    Ok(fs::canonicalize(parent)?.join(name))
}

fn reject_symlink(path: &Path) -> Result<()> {
    match fs::symlink_metadata(path) {
        Ok(meta) if meta.file_type().is_symlink() || !meta.is_file() => Err(Error::InvalidProject("Choose a regular project file, not a symlink or directory.".into())),
        Ok(_) => Ok(()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
    }
}

/// Detect aliases of an open project before allowing Save As to replace them.
fn same_destination(current: &Path, target: &Path) -> Result<bool> {
    reject_symlink(target)?;
    if current == target { return Ok(true); }
    let metadata = |path: &Path| match fs::symlink_metadata(path) {
        Ok(value) => Ok(Some(value)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error),
    };
    let current_info = metadata(current)?;
    let target_info = metadata(target)?;
    match (current_info, target_info) {
        (Some(a), Some(b)) if a.is_file() && !a.file_type().is_symlink() && b.is_file() && !b.file_type().is_symlink() => same_file(current, target),
        (None, None) => missing_path_alias(current, target),
        _ => Ok(false),
    }
}

#[cfg(windows)]
fn same_file(a: &Path, b: &Path) -> Result<bool> {
    use std::os::windows::io::AsRawHandle;
    #[repr(C)]
    #[derive(Default)]
    struct FileInformation {
        attributes: u32,
        creation_time: [u32; 2],
        access_time: [u32; 2],
        write_time: [u32; 2],
        volume_serial: u32,
        size_high: u32,
        size_low: u32,
        links: u32,
        index_high: u32,
        index_low: u32,
    }
    #[link(name = "kernel32")]
    extern "system" { fn GetFileInformationByHandle(handle: std::os::windows::io::RawHandle, info: *mut FileInformation) -> i32; }
    fn identity(path: &Path) -> Result<(u32, u32, u32)> {
        let file = File::open(path)?;
        let mut info = FileInformation::default();
        // The file handle and output struct remain valid for this synchronous call.
        if unsafe { GetFileInformationByHandle(file.as_raw_handle(), &mut info) } == 0 { return Err(std::io::Error::last_os_error().into()); }
        if info.index_high == 0 && info.index_low == 0 {
            return Err(Error::Conflict("Cannot verify the identity of this file on its filesystem; choose a new Save As filename.".into()));
        }
        Ok((info.volume_serial, info.index_high, info.index_low))
    }
    Ok(identity(a)? == identity(b)?)
}

#[cfg(unix)]
fn same_file(a: &Path, b: &Path) -> Result<bool> {
    use std::os::unix::fs::MetadataExt;
    let left = File::open(a)?.metadata()?;
    let right = File::open(b)?.metadata()?;
    Ok(left.dev() == right.dev() && left.ino() == right.ino())
}

#[cfg(not(any(windows, unix)))]
fn same_file(a: &Path, b: &Path) -> Result<bool> {
    Ok(fs::canonicalize(a)? == fs::canonicalize(b)?)
}

#[cfg(windows)]
fn missing_path_alias(a: &Path, b: &Path) -> Result<bool> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" { fn CompareStringOrdinal(a: *const u16, a_len: i32, b: *const u16, b_len: i32, ignore_case: i32) -> i32; }
    let left = a.as_os_str().encode_wide().collect::<Vec<_>>();
    let right = b.as_os_str().encode_wide().collect::<Vec<_>>();
    let left_len = i32::try_from(left.len()).map_err(|_| Error::InvalidProject("Project path is too long.".into()))?;
    let right_len = i32::try_from(right.len()).map_err(|_| Error::InvalidProject("Project path is too long.".into()))?;
    // No file exists to inspect; compare the normalized paths conservatively.
    match unsafe { CompareStringOrdinal(left.as_ptr(), left_len, right.as_ptr(), right_len, 1) } {
        0 => Err(std::io::Error::last_os_error().into()),
        2 => Ok(true),
        _ => Ok(false),
    }
}

#[cfg(not(windows))]
fn missing_path_alias(_a: &Path, _b: &Path) -> Result<bool> { Ok(false) }

fn sibling(path: &Path, purpose: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |time| time.as_nanos());
    let suffix = NEXT_FILE.fetch_add(1, Ordering::Relaxed);
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    path.with_file_name(format!(".{name}.mbdyn-{purpose}-{}-{nanos}-{suffix}", std::process::id()))
}

struct SaveLock { path: PathBuf, file: Option<File> }
impl SaveLock {
    fn acquire(path: &Path) -> Result<Self> {
        let name = path.file_name().unwrap_or_default().to_string_lossy();
        let lock = path.with_file_name(format!(".{name}.mbdyn-save-lock"));
        let file = OpenOptions::new().write(true).create_new(true).open(&lock).map_err(|error| {
            if error.kind() == std::io::ErrorKind::AlreadyExists { Error::Conflict(format!("A save lock exists at {}. Another window may be saving; after a crash, inspect the project/recovery files before removing a stale lock.", lock.display())) } else { error.into() }
        })?;
        Ok(Self { path: lock, file: Some(file) })
    }
}
impl Drop for SaveLock { fn drop(&mut self) { drop(self.file.take()); let _ = fs::remove_file(&self.path); } }

#[cfg(windows)]
fn replace_with_backup(target: &Path, temporary: &Path, backup: &Path) -> std::io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    #[link(name = "kernel32")]
    extern "system" { fn ReplaceFileW(target: *const u16, replacement: *const u16, backup: *const u16, flags: u32, exclude: *mut std::ffi::c_void, reserved: *mut std::ffi::c_void) -> i32; }
    let wide = |path: &Path| path.as_os_str().encode_wide().chain(Some(0)).collect::<Vec<_>>();
    let target = wide(target); let temporary = wide(temporary); let backup = wide(backup);
    // All UTF-16 buffers live through the call; optional pointer parameters are null.
    let result = unsafe { ReplaceFileW(target.as_ptr(), temporary.as_ptr(), backup.as_ptr(), 0, std::ptr::null_mut(), std::ptr::null_mut()) };
    if result == 0 { Err(std::io::Error::last_os_error()) } else { Ok(()) }
}

#[cfg(not(windows))]
fn replace_with_backup(target: &Path, temporary: &Path, backup: &Path) -> std::io::Result<()> {
    fs::copy(target, backup)?;
    fs::rename(temporary, target)
}
