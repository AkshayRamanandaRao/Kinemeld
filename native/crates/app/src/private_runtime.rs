use std::{ffi::OsString, path::{Path, PathBuf}};

/// Select an explicit override, the application-local interpreter, or PATH.
pub(crate) fn python_for(root: &Path, explicit: Option<OsString>) -> Result<PathBuf, String> {
    if let Some(value) = explicit {
        if value.is_empty() { return Err("MBDYN_STUDIO_PYTHON is empty; specify an interpreter or unset it.".into()); }
        return Ok(PathBuf::from(value));
    }
    let runtime = root.join("runtime").join("python");
    let present = match std::fs::symlink_metadata(&runtime) {
        Ok(_) => true,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(format!("Cannot inspect application-local Python runtime at {}: {error}", runtime.display())),
    };
    if present {
        let interpreter = if cfg!(windows) { runtime.join("python.exe") } else { runtime.join("bin").join("python3") };
        if !runtime.is_dir() || !interpreter.is_file() || !runtime.join("runtime-manifest.json").is_file() {
            return Err(format!("The application-local Python runtime at {} is incomplete. Repair it or set MBDYN_STUDIO_PYTHON to another interpreter.", runtime.display()));
        }
        return Ok(interpreter);
    }
    Ok(PathBuf::from(if cfg!(windows) { "python" } else { "python3" }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{fs, time::{SystemTime,UNIX_EPOCH}};

    #[test]
    fn explicit_local_and_path_precedence_and_incomplete_runtime() {
        let dir=std::env::temp_dir().join(format!("mbdyn-runtime-{}-{}",std::process::id(),SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()));
        fs::create_dir(&dir).unwrap();
        let interpreter=if cfg!(windows) { PathBuf::from("python.exe") } else { PathBuf::from("bin").join("python3") };
        assert_eq!(python_for(&dir,None).unwrap(),PathBuf::from(if cfg!(windows) { "python" } else { "python3" }));
        assert!(python_for(&dir,Some(OsString::new())).is_err());
        assert_eq!(python_for(&dir,Some(OsString::from("custom-python"))).unwrap(),PathBuf::from("custom-python"));
        let runtime=dir.join("runtime").join("python");fs::create_dir_all(&runtime).unwrap();
        assert!(python_for(&dir,None).unwrap_err().contains("incomplete"));
        fs::create_dir_all(runtime.join(&interpreter).parent().unwrap()).unwrap();
        fs::write(runtime.join(&interpreter),b"test fixture").unwrap();
        assert!(python_for(&dir,None).is_err());
        fs::write(runtime.join("runtime-manifest.json"),b"test fixture").unwrap();
        assert_eq!(python_for(&dir,None).unwrap(),runtime.join(&interpreter));
        assert_eq!(python_for(&dir,Some(OsString::from("custom-python"))).unwrap(),PathBuf::from("custom-python"));
        fs::remove_dir_all(dir).unwrap();
    }
}
