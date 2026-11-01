//! Explicit opt-in test instrumentation. Production dialog operations remain unchanged.
use mbdyn_studio_core::MAX_PROJECT_BYTES;
use serde_json::{json, Value};
use std::{env, fs, path::{Component, Path, PathBuf}};

pub struct GuiTest { root: PathBuf, config: Value }

impl GuiTest {
    pub fn from_args(data: &Path, smoke: bool) -> Result<Option<Self>, String> {
        let args: Vec<_> = env::args_os().collect();
        let Some(index) = args.iter().position(|arg| arg == "--native-gui-test") else { return Ok(None); };
        if smoke { return Err("GUI tests and smoke tests cannot run together.".into()); }
        let file = args.get(index + 1).ok_or("--native-gui-test requires a configuration file.")?;
        Self::from_config(Path::new(file), data).map(Some)
    }

    fn from_config(file: &Path, data: &Path) -> Result<Self, String> {
        let config: Value = serde_json::from_slice(&fs::read(file).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        let root = PathBuf::from(config["root"].as_str().ok_or("Missing GUI-test root.")?).canonicalize().map_err(|e| e.to_string())?;
        if !root.join(".kinemeld-native-gui-test").is_file() || data.canonicalize().map_err(|e| e.to_string())? != root.join("user-data").canonicalize().map_err(|e| e.to_string())? {
            return Err("GUI tests require their own marked root and isolated user-data folder.".into());
        }
        if !matches!(config["phase"].as_str(), Some("initial" | "recovery")) { return Err("Invalid GUI-test phase.".into()); }
        Ok(Self { root, config })
    }

    pub fn script(&self) -> String {
        format!("window.__kinemeldGuiTest={};\n{}", self.config, include_str!("gui_test.js"))
    }

    fn path(&self, name: &str) -> Result<PathBuf, String> {
        let relative = Path::new(name);
        if relative.as_os_str().is_empty() || relative.components().any(|part| !matches!(part, Component::Normal(_))) {
            return Err("GUI-test files must be inside the test root.".into());
        }
        let path = self.root.join(relative);
        let resolved = if path.exists() { path.canonicalize() } else { path.parent().unwrap().canonicalize() }.map_err(|e| e.to_string())?;
        if !resolved.starts_with(&self.root) { return Err("GUI-test path escapes its root.".into()); }
        Ok(path)
    }

    pub fn call(&self, payload: &Value) -> Result<Value, String> {
        match payload["command"].as_str().ok_or("Missing GUI-test command.")? {
            "read" => {
                let path = self.path(payload["name"].as_str().ok_or("Missing GUI-test file.")?)?;
                if !path.exists() { return Ok(json!({"text":null})); }
                if fs::metadata(&path).map_err(|e| e.to_string())?.len() > MAX_PROJECT_BYTES + 1024 * 1024 { return Err("GUI-test read exceeds project size limit.".into()); }
                Ok(json!({"text":fs::read_to_string(path).map_err(|e| e.to_string())?}))
            }
            "list" => Ok(json!(fs::read_dir(&self.root).map_err(|e| e.to_string())?.map(|entry| entry.map(|e| e.file_name().to_string_lossy().into_owned())).collect::<Result<Vec<_>, _>>().map_err(|e| e.to_string())?)),
            "write" => {
                let name = payload["name"].as_str().ok_or("Missing GUI-test file.")?;
                // Never alter configuration, scripts, driver plans, or recovery through this helper.
                if !matches!(Path::new(name).extension().and_then(|s| s.to_str()), Some("mbdyn-studio" | "json")) || name.contains('/') || name.contains('\\') || matches!(name, "config.json" | "action.json" | "action-result.json" | "viewer-report.json") {
                    return Err("GUI-test writes are limited to project snapshots.".into());
                }
                let text = payload["text"].as_str().ok_or("Missing GUI-test text.")?;
                if text.len() as u64 > MAX_PROJECT_BYTES { return Err("GUI-test write exceeds project size limit.".into()); }
                fs::write(self.path(name)?, text).map_err(|e| e.to_string())?;
                Ok(json!({}))
            }
            "action" => {
                let actions = payload["actions"].as_array().ok_or("Missing GUI actions.")?;
                if actions.is_empty() || actions.len() > 4 { return Err("Expected one to four native GUI actions.".into()); }
                for action in actions {
                    if !matches!(action["kind"].as_str(), Some("open" | "save" | "button" | "cancel" | "close")) { return Err("Unknown native GUI action.".into()); }
                    if let Some(path) = action["path"].as_str() {
                        let candidate = Path::new(path);
                        let resolved = if candidate.exists() { candidate.canonicalize() } else { candidate.parent().ok_or("Missing GUI action parent.")?.canonicalize() }.map_err(|e| e.to_string())?;
                        if !resolved.starts_with(&self.root) { return Err("Native GUI actions must stay in the test root.".into()); }
                    }
                }
                self.atomic("action.json", payload)?;
                Ok(json!({}))
            }
            "status" => {
                let path = self.root.join("action-result.json");
                if !path.exists() { return Ok(Value::Null); }
                serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?).map_err(|e| e.to_string())
            }
            "report" => { self.atomic("viewer-report.json", &payload["report"])?; Ok(json!({})) }
            _ => Err("Unsupported GUI-test command.".into()),
        }
    }

    fn atomic(&self, name: &str, value: &Value) -> Result<(), String> {
        let temp = self.root.join(format!(".{name}.tmp"));
        fs::write(&temp, serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
        fs::rename(temp, self.root.join(name)).map_err(|e| e.to_string())
    }

    #[cfg(target_os = "macos")]
    pub fn start_driver(&self) -> Result<(), String> {
        use std::ffi::CString;
        unsafe extern "C" { fn kinemeld_gui_test_start(root: *const std::ffi::c_char); }
        let path = CString::new(self.root.to_string_lossy().as_bytes()).map_err(|e| e.to_string())?;
        unsafe { kinemeld_gui_test_start(path.as_ptr()); }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gui_test_helpers_require_isolated_data_and_reject_path_escapes() {
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root = env::temp_dir().join(format!("kinemeld-gui-guard-{}-{stamp}", std::process::id()));
        fs::create_dir_all(root.join("user-data")).unwrap();
        let config = root.join("config.json");
        fs::write(&config, json!({"root":root,"phase":"initial"}).to_string()).unwrap();
        assert!(GuiTest::from_config(&config, &root.join("user-data")).is_err());
        fs::write(root.join(".kinemeld-native-gui-test"), "").unwrap();
        assert!(GuiTest::from_config(&config, &root).is_err());
        let test = GuiTest::from_config(&config, &root.join("user-data")).unwrap();
        for name in ["../outside.json", "/outside.json", "user-data/../outside.json"] {
            assert!(test.call(&json!({"command":"read","name":name})).is_err());
        }
        for name in ["config.json", "action.json", "viewer-report.json", "user-data/solver.json", "script.js"] {
            assert!(test.call(&json!({"command":"write","name":name,"text":"{}"})).is_err());
        }
        test.call(&json!({"command":"write","name":"saved.mbdyn-studio","text":"{}"})).unwrap();
        assert_eq!(test.call(&json!({"command":"read","name":"saved.mbdyn-studio"})).unwrap(), json!({"text":"{}"}));
        assert!(test.call(&json!({"command":"action","id":1,"actions":[{"kind":"open","path":root.parent().unwrap().join("outside.json") }]})).is_err());
        assert!(test.call(&json!({"command":"action","id":1,"actions":[{"kind":"replace-result"}]})).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
