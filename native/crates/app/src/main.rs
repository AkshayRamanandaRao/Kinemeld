#![cfg_attr(windows, windows_subsystem = "windows")]

mod project_open;
mod private_runtime;

use project_open::ProjectOpenState;

use mbdyn_studio_core::{
    BackendService, ProjectDocument, ProjectSession, RecoveryStore, SaveMode, MAX_PROJECT_BYTES,
};
use rfd::{FileDialog, MessageButtons, MessageDialog, MessageDialogResult, MessageLevel};
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    env, fs,
    io::Write,
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tao::{
    dpi::LogicalSize,
    event::{Event, WindowEvent},
    event_loop::{ControlFlow, EventLoopBuilder},
    window::WindowBuilder,
};
use wry::{NewWindowResponse, WebContext, WebViewBuilder};

#[derive(Deserialize)]
struct Request {
    id: u64,
    op: String,
    #[serde(default)]
    payload: Value,
}

fn workspace() -> Result<PathBuf, String> {
    if let Some(path) = env::var_os("MBDYN_STUDIO_WORKSPACE") {
        let path = PathBuf::from(path);
        return if path.join("backend/server.py").is_file() {
            Ok(path)
        } else {
            Err("MBDYN_STUDIO_WORKSPACE must point to the Kinemeld folder containing backend/server.py.".into())
        };
    }
    let exe = env::current_exe().map_err(|e| e.to_string())?;
    // A macOS bundle keeps resources in Contents/Resources/app next to Contents/MacOS.
    let bundled = exe.parent().and_then(Path::parent).map(|contents| contents.join("Resources").join("app"));
    exe.ancestors().map(Path::to_path_buf).chain(bundled).find(|path| path.join("backend/server.py").is_file())
        .ok_or_else(|| "Could not locate the workspace. Place the executable inside the Kinemeld folder or set MBDYN_STUDIO_WORKSPACE.".into())
}

fn data_directory(_workspace: &Path) -> Result<PathBuf, String> {
    let configured = env::var_os("MBDYN_STUDIO_DATA_DIR");
    let data = if let Some(path) = configured {
        PathBuf::from(path)
    } else {
        #[cfg(windows)]
        { PathBuf::from(env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA is unavailable; set MBDYN_STUDIO_DATA_DIR to a writable folder.")?).join("MBDynStudio") }
        #[cfg(target_os = "macos")]
        { PathBuf::from(env::var_os("HOME").ok_or("HOME is unavailable; set MBDYN_STUDIO_DATA_DIR to a writable folder.")?).join("Library/Application Support/Kinemeld") }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            match env::var_os("XDG_DATA_HOME").filter(|value| !value.is_empty()) {
                Some(base) => PathBuf::from(base).join("kinemeld"),
                None => PathBuf::from(env::var_os("HOME").ok_or("HOME is unavailable; set MBDYN_STUDIO_DATA_DIR to a writable folder.")?).join(".local/share/kinemeld"),
            }
        }
    };
    if !data.is_absolute() { return Err("MBDYN_STUDIO_DATA_DIR must be an absolute writable folder.".into()); }
    fs::create_dir_all(data.join("runs")).map_err(|error| format!("Cannot create writable data folder {}: {error}", data.display()))?;
    Ok(data)
}

fn question(title: &str, description: &str) -> bool {
    MessageDialog::new()
        .set_level(MessageLevel::Warning)
        .set_title(title)
        .set_description(description)
        .set_buttons(MessageButtons::YesNo)
        .show()
        == MessageDialogResult::Yes
}

/// The project as the frontend last showed it, on top of the open session's document.
fn document_from(session: Option<&ProjectSession>, payload: &Value) -> Result<ProjectDocument, String> {
    let model = payload.get("model").cloned().ok_or("Missing project model.")?;
    let mut document = match session { Some(s) => s.document().clone(), None => ProjectDocument::new(model.clone()).map_err(|e| e.to_string())? };
    document.model = model;
    document.result = payload.get("result").filter(|value| !value.is_null()).cloned();
    document.view = payload.get("view").cloned().unwrap_or(Value::Null);
    if let Some(assets) = payload.get("assets").filter(|value| !value.is_null()) { document.extra.insert("assets".into(), assets.clone()); }
    else { document.extra.remove("assets"); }
    document.check().map_err(|e| e.to_string())?;
    Ok(document)
}

fn smoke_report(root: &Path, value: &Value) -> Result<(), String> {
    let path = root
        .join("runs")
        .join(format!("native-smoke-report-{}.json", std::process::id()));
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)
        .map_err(|e| e.to_string())?;
    file.write_all(
        serde_json::to_string_pretty(value)
            .map_err(|e| e.to_string())?
            .as_bytes(),
    )
    .map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())
}

fn smoke_save(root: &Path, data: &Path, payload: &Value) -> Result<Value, String> {
    let result = payload
        .get("result")
        .ok_or("No solver result in native smoke test.")?;
    if result.get("ok") != Some(&Value::Bool(true))
        || result.get("source").and_then(Value::as_str) != Some("MBDyn")
        || result
            .get("samples")
            .and_then(Value::as_array)
            .is_none_or(Vec::is_empty)
        || payload.get("hasCanvas") != Some(&Value::Bool(true))
    {
        return Err("Embedded viewer or actual MBDyn result failed the smoke checks.".into());
    }
    let model = payload
        .get("model")
        .cloned()
        .ok_or("No model in native smoke test.")?;
    let mut document = ProjectDocument::new(model.clone()).map_err(|e| e.to_string())?;
    document.result = Some(result.clone());
    let mut session = ProjectSession::new(document).map_err(|e| e.to_string())?;
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    let project = data.join("runs").join(format!(
        "native-smoke-{}-{stamp}.mbdyn-studio",
        std::process::id()
    ));
    session
        .save_as(&project, SaveMode::CreateNew)
        .map_err(|e| e.to_string())?;
    let reopened = ProjectSession::open(&project).map_err(|e| e.to_string())?;
    if reopened.document().model != model || reopened.document().result.as_ref() != Some(result) {
        return Err("Native saved-project round trip did not preserve model and result.".into());
    }
    Ok(
        json!({"ok":true,"workspace":root,"project":project,"source":"MBDyn","runId":result["runId"],"samples":result["samples"].as_array().map_or(0,Vec::len),"hasCanvas":true,"examples":payload["exampleCount"],"sourceExamples":payload["sourceCount"]}),
    )
}

fn run() -> Result<(), String> {
    let smoke = env::args().any(|arg| arg == "--smoke");
    let root = workspace()?;
    let data = data_directory(&root)?;
    let recovery = RecoveryStore::new(data.join("recovery")).map_err(|error| format!("Cannot prepare the recovery folder in {}: {error}", data.display()))?;
    // A snapshot from a session that ended without saving waits for the user's decision;
    // until then autosave must not replace it.
    let mut recovery_pending = !matches!(recovery.read(), Ok(None));
    let python = private_runtime::python_for(&root, env::var_os("MBDYN_STUDIO_PYTHON"))?;
    let service = BackendService::start_with_data_dir(&root, &python, &data).map_err(|error| format!("Cannot start the local Python solver service: {error}. Repair the application-local Python runtime, install Python 3.10+, or set MBDYN_STUDIO_PYTHON to its executable."))?;
    let base = service.client().base_url();
    // The event loop initialises the native toolkit (GTK on Linux) before any web context exists.
    let event_loop = EventLoopBuilder::<String>::with_user_event().build();
    let mut context = WebContext::new(Some(data.join("runs").join("desktop-webview")));
    let proxy = event_loop.create_proxy();
    if smoke {
        let timeout_proxy = proxy.clone();
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(180));
            let _ =
                timeout_proxy.send_event(r#"{"id":0,"op":"smoke-timeout","payload":{}}"#.into());
        });
    }
    let window = WindowBuilder::new()
        .with_title("Kinemeld")
        .with_inner_size(LogicalSize::new(1440.0, 960.0))
        .with_min_inner_size(LogicalSize::new(800.0, 600.0))
        .with_visible(!smoke)
        .build(&event_loop)
        .map_err(|e| e.to_string())?;
    let allowed = format!("{base}/");
    let ipc_origin = allowed.clone();
    let nav_origin = allowed.clone();
    let mut builder = WebViewBuilder::new_with_web_context(&mut context)
        .with_url(&allowed)
        .with_initialization_script(include_str!("bridge.js"))
        .with_navigation_handler(move |url| url.starts_with(&nav_origin))
        .with_new_window_req_handler(|_, _| NewWindowResponse::Deny)
        .with_ipc_handler(move |request| {
            if request.uri().to_string().starts_with(&ipc_origin)
                && request.body().len() <= MAX_PROJECT_BYTES as usize + 1024 * 1024
            {
                let _ = proxy.send_event(request.body().clone());
            }
        });
    if smoke {
        builder = builder.with_initialization_script(include_str!("smoke.js"));
    }
    #[cfg(target_os = "linux")]
    let webview = {
        use tao::platform::unix::WindowExtUnix;
        use wry::WebViewBuilderExtUnix;
        let container = window.default_vbox().ok_or("The GTK window has no content container.")?;
        builder.build_gtk(container)
    }
    .map_err(|e| format!("Cannot create the WebKitGTK viewer: {e}. Install WebKitGTK 4.1 (libwebkit2gtk-4.1) and retry."))?;
    #[cfg(not(target_os = "linux"))]
    let webview = builder.build(&window).map_err(|e| {
        if cfg!(windows) { format!("Cannot create the WebView2 viewer: {e}. Install the Microsoft WebView2 Runtime and retry.") }
        else { format!("Cannot create the system web viewer: {e}.") }
    })?;
    let mut service = Some(service);
    let mut projects = ProjectOpenState::default();
    let mut busy = false;
    let mut agent_busy = false;
    let mut exiting = false;
    event_loop.run(move |event, _, flow| {
        let _keep_context = &context;
        *flow = if exiting { ControlFlow::Exit } else { ControlFlow::Wait };
        if exiting && !matches!(&event, Event::LoopDestroyed) { return; }
        match event {
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                if busy || agent_busy || projects.is_opening() { MessageDialog::new().set_level(MessageLevel::Info).set_title("Work in progress").set_description("Wait for the current simulation, agent request or project open to finish before closing the application.").show(); }
                else if !projects.dirty || question("Unsaved project", "Discard unsaved changes and close Kinemeld?") {
                    // A clean close leaves nothing to recover; an undecided earlier snapshot is kept.
                    if !recovery_pending { let _ = recovery.clear(); }
                    exiting = true;
                    *flow = ControlFlow::Exit;
                }
            }
            Event::UserEvent(body) => {
                let Ok(request) = serde_json::from_str::<Request>(&body) else { return; };
                let mut exit_after = false;
                let result: Result<Value, String> = (|| match request.op.as_str() {
                    "dirty" => { projects.mark_dirty(); Ok(json!({})) }
                    "busy" => { busy = true; Ok(json!({})) }
                    "idle" => { busy = false; Ok(json!({})) }
                    "agent-busy" => { agent_busy = true; Ok(json!({})) }
                    "agent-idle" => { agent_busy = false; Ok(json!({})) }
                    "discard-open" => { projects.discard_pending(); Ok(json!({})) }
                    "finalize-open" => {
                        let token = request.payload.get("token").and_then(Value::as_str).ok_or("Missing project transaction identity.")?;
                        projects.finalize(token)?; Ok(json!({"token":token,"dirtyRevision":projects.dirty_revision()}))
                    }
                    "clean-open" => {
                        let token = request.payload.get("token").and_then(Value::as_str).ok_or("Missing project transaction identity.")?;
                        let revision = request.payload.get("dirtyRevision").and_then(Value::as_str).ok_or("Missing project dirty revision.")?;
                        let clean = projects.confirm_clean(token,revision)?;
                        Ok(json!({"token":token,"dirtyRevision":revision,"clean":clean}))
                    }
                    "rollback-open" => {
                        let token = request.payload.get("token").and_then(Value::as_str).ok_or("Missing project transaction identity.")?;
                        projects.rollback(token)?; Ok(json!({"token":token}))
                    }
                    "open" => {
                        if busy { return Err("Wait for the active simulation before opening a project.".into()); }
                        projects.ensure_idle()?;
                        if projects.dirty && !question("Unsaved project", "Discard unsaved changes and open another project?") { return Ok(json!({"cancelled":true})); }
                        let Some(path) = FileDialog::new().add_filter("Kinemeld project", &["mbdyn-studio", "json"]).pick_file() else { return Ok(json!({"cancelled":true})); };
                        let candidate = ProjectSession::open(&path).map_err(|e| e.to_string())?;
                        let value = json!({"project":candidate.document(),"path":path});
                        projects.set_pending(candidate)?; Ok(value)
                    }
                    "accept-open" => { let token=projects.accept()?; Ok(json!({"token":token})) }
                    "new-project" => {
                        if busy { return Err("Wait for the active simulation before opening a project.".into()); }
                        projects.ensure_idle()?;
                        if projects.dirty && !question("Unsaved project", "Discard unsaved changes and open an unsaved copy?") { return Ok(json!({"cancelled":true})); }
                        let document: ProjectDocument = serde_json::from_value(request.payload.get("project").cloned().ok_or("Missing project document.")?).map_err(|e| e.to_string())?;
                        let candidate = ProjectSession::new(document).map_err(|e| e.to_string())?;
                        let value = json!({"project":candidate.document()});
                        projects.set_pending(candidate)?; Ok(value)
                    }
                    "save" => {
                        if busy { return Err("Wait for the active simulation before saving.".into()); }
                        projects.ensure_idle()?;
                        let document = document_from(projects.session.as_ref(), &request.payload)?;
                        match projects.session.as_mut() { Some(s) => s.replace_document(document).map_err(|e| e.to_string())?, None => projects.session = Some(ProjectSession::new(document).map_err(|e| e.to_string())?) }
                        let session = projects.session.as_mut().ok_or("Project session unavailable.")?;
                        let save_as = request.payload.get("saveAs").and_then(Value::as_bool).unwrap_or(false) || session.path().is_none();
                        let outcome = if save_as {
                            // A recovered project suggests the file it came from.
                            let mut dialog = FileDialog::new().add_filter("Kinemeld project", &["mbdyn-studio"]);
                            match projects.recovered_from.as_ref().and_then(|path| Some((path.parent()?, path.file_name()?.to_str()?))) {
                                Some((folder, name)) => { dialog = dialog.set_directory(folder).set_file_name(name); }
                                None => { dialog = dialog.set_file_name("project.mbdyn-studio"); }
                            }
                            let Some(path) = dialog.save_file() else { return Ok(json!({"cancelled":true})); };
                            let mode = if path.exists() { SaveMode::ReplaceExisting } else { SaveMode::CreateNew };
                            session.save_as(&path, mode)
                        } else { session.save() }.map_err(|e| e.to_string())?;
                        projects.dirty = false;
                        projects.recovered_from = None;
                        // The saved file now holds this work; a failed removal only means a stale prompt later.
                        let _ = recovery.clear();
                        Ok(json!({"path":outcome.path,"backup":outcome.backup}))
                    }
                    "autosave" => {
                        if recovery_pending || busy || !projects.dirty || projects.is_opening() { return Ok(json!({"skipped":true})); }
                        let document = document_from(projects.session.as_ref(), &request.payload)?;
                        let path = projects.session.as_ref().and_then(ProjectSession::path).map(Path::to_path_buf).or_else(|| projects.recovered_from.clone());
                        let snapshot = recovery.write(&document, path.as_deref()).map_err(|e| e.to_string())?;
                        Ok(json!({"savedAt":snapshot.saved_at}))
                    }
                    "recovery" => match recovery.read() {
                        Ok(Some(snapshot)) => Ok(json!({"savedAt":snapshot.saved_at,"path":snapshot.project_path,"name":snapshot.document.model["name"]})),
                        Ok(None) => { recovery_pending = false; Ok(json!({})) }
                        Err(error) => {
                            let aside = recovery.set_aside().map_err(|e| e.to_string())?;
                            recovery_pending = false;
                            Ok(json!({"damaged":error.to_string(),"setAside":aside}))
                        }
                    },
                    "recovery-open" => {
                        if busy { return Err("Wait for the active simulation before recovering a project.".into()); }
                        projects.ensure_idle()?;
                        if projects.dirty && !question("Unsaved project", "Discard unsaved changes and recover the autosaved project?") { return Ok(json!({"cancelled":true})); }
                        let snapshot = recovery.read().map_err(|e| e.to_string())?.ok_or("No autosaved project is waiting for recovery.")?;
                        // Recovered work opens untitled, so Save asks where to write it instead of
                        // overwriting a file that may have changed since.
                        let candidate = ProjectSession::new(snapshot.document.clone()).map_err(|e| e.to_string())?;
                        let value = json!({"project":candidate.document(),"path":snapshot.project_path,"savedAt":snapshot.saved_at,"recovered":true});
                        projects.set_pending(candidate)?;
                        projects.pending_recovered_from = snapshot.project_path;
                        Ok(value)
                    }
                    // The frontend shows the recovered project; autosave may now replace the snapshot.
                    "recovery-adopted" => { recovery_pending = false; Ok(json!({})) }
                    "recovery-discard" => {
                        let aside = recovery.set_aside().map_err(|e| e.to_string())?;
                        recovery_pending = false;
                        projects.recovered_from = None;
                        Ok(json!({"setAside":aside}))
                    }
                    "smoke" if smoke => {
                        let report = smoke_save(&root, &data, &request.payload)?;
                        smoke_report(&data, &report)?; exit_after = true; Ok(json!({}))
                    }
                    "smoke-fail" | "smoke-timeout" if smoke => {
                        smoke_report(&data, &json!({"ok":false,"error":request.payload.get("error").and_then(Value::as_str).unwrap_or("Native smoke test timed out.")}))?;
                        exit_after = true; Ok(json!({}))
                    }
                    _ => Err("Unsupported desktop operation.".into()),
                })();
                if request.id != 0 {
                    let response = match result { Ok(value) => json!({"ok":true,"value":value}), Err(error) => json!({"ok":false,"error":error}) };
                    let script = format!("window.__mbdynNativeResolve({}, {});", request.id, response);
                    let _ = webview.evaluate_script(&script);
                }
                if exit_after { exiting = true; *flow = ControlFlow::Exit; }
            }
            Event::LoopDestroyed => { if let Some(mut owned) = service.take() { let _ = owned.stop(); } }
            _ => {}
        }
    });
}

fn main() {
    if let Err(error) = run() {
        if env::args().any(|arg| arg == "--smoke") {
            if let Ok(data) = workspace().and_then(|root| data_directory(&root)) {
                let _ = smoke_report(&data, &json!({"ok":false,"error":error}));
            }
        } else {
            MessageDialog::new()
                .set_level(MessageLevel::Error)
                .set_title("Kinemeld could not start")
                .set_description(error)
                .show();
        }
    }
}
