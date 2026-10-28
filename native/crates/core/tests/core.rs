use mbdyn_studio_core::{BackendClient, BackendService, Error, ProjectDocument, ProjectSession, SaveMode, MAX_PROJECT_BYTES};
use serde_json::json;
use std::{fs, io::{Read, Write}, net::TcpListener, path::PathBuf, sync::atomic::{AtomicU64, Ordering}, thread, time::{SystemTime, UNIX_EPOCH}};

static NEXT: AtomicU64 = AtomicU64::new(0);
struct Directory(PathBuf);
impl Directory {
    fn new() -> Self {
        let tick = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let path = std::env::temp_dir().join(format!("mbdyn-core-test-{}-{tick}-{}",std::process::id(),NEXT.fetch_add(1,Ordering::Relaxed)));
        fs::create_dir(&path).unwrap(); Self(path)
    }
}
impl Drop for Directory { fn drop(&mut self) { let _ = fs::remove_dir_all(&self.0); } }

fn model() -> serde_json::Value { json!({"kind":"pendulum","name":"Saved mechanism","parameters":{"mass":1,"length":1,"angle":30,"gravity":9.81},"simulation":{"duration":5,"step":0.005}}) }

#[test]
fn safe_save_roundtrip_backup_and_external_conflict() {
    let directory = Directory::new(); let path = directory.0.join("Mechanism Ω.json");
    let mut document = ProjectDocument::new(model()).unwrap();
    document.result = Some(json!({"source":"MBDyn","runId":"original","samples":[{"time":0,"nodes":[{"id":42,"z":1.2}]}],"rawCsv":"time_s,z_m\n0,1.2\n","provenance":{"license":"GPL-2.0"}}));
    document.extra.insert("customView".into(),json!({"camera":[1,2,3]}));
    let mut session = ProjectSession::new(document.clone()).unwrap();
    assert!(session.is_dirty());
    assert!(session.save_as(&path,SaveMode::CreateNew).unwrap().backup.is_none());
    assert!(!session.is_dirty());
    assert_eq!(ProjectSession::open(&path).unwrap().document(),&document);
    let first = fs::read(&path).unwrap();
    let mut changed = document.clone(); changed.model["name"] = json!("Edited");
    session.replace_document(changed.clone()).unwrap();
    assert!(session.is_dirty());
    let saved = session.save().unwrap();
    assert_eq!(fs::read(saved.backup.unwrap()).unwrap(),first);
    assert_eq!(ProjectSession::open(&path).unwrap().document(),&changed);
    fs::write(&path,b"external edit must survive").unwrap();
    assert!(matches!(session.save(),Err(Error::Conflict(_))));
    assert_eq!(fs::read(&path).unwrap(),b"external edit must survive");
    assert!(ProjectSession::new(document).unwrap().save_as(&path,SaveMode::CreateNew).is_err());
    assert_eq!(fs::read(&path).unwrap(),b"external edit must survive");
}

#[test]
fn save_as_hardlink_alias_preserves_external_changes_and_new_target_still_works() {
    let directory = Directory::new();
    let path = directory.0.join("source.mbdyn-studio");
    let alias = directory.0.join("hardlink.mbdyn-studio");
    let fresh = directory.0.join("new.mbdyn-studio");
    let mut seed = ProjectSession::new(ProjectDocument::new(model()).unwrap()).unwrap();
    seed.save_as(&path, SaveMode::CreateNew).unwrap();
    fs::hard_link(&path, &alias).unwrap();
    let mut session = ProjectSession::open(&path).unwrap();
    fs::write(&path, b"external edit").unwrap();
    assert!(matches!(session.save_as(&alias, SaveMode::ReplaceExisting), Err(Error::Conflict(_))));
    assert_eq!(fs::read(&path).unwrap(), b"external edit");
    assert_eq!(fs::read(&alias).unwrap(), b"external edit");
    session.save_as(&fresh, SaveMode::CreateNew).unwrap();
    assert_eq!(fs::read(&path).unwrap(), b"external edit");
    assert_eq!(ProjectSession::open(&fresh).unwrap().document().model, model());
}

#[cfg(windows)]
#[test]
fn save_as_windows_case_alias_checks_external_change_and_missing_original() {
    let directory = Directory::new();
    let path = directory.0.join("Mechanism.mbdyn-studio");
    let alias = directory.0.join("mechanism.MBDYN-STUDIO");
    let mut seed = ProjectSession::new(ProjectDocument::new(model()).unwrap()).unwrap();
    seed.save_as(&path, SaveMode::CreateNew).unwrap();
    if !alias.exists() { eprintln!("Case-sensitive directory: Windows case-alias fixture not applicable."); return; }
    let mut session = ProjectSession::open(&path).unwrap();
    fs::write(&path, b"external edit").unwrap();
    assert!(matches!(session.save_as(&alias, SaveMode::ReplaceExisting), Err(Error::Conflict(_))));
    assert_eq!(fs::read(&path).unwrap(), b"external edit");
    fs::remove_file(&path).unwrap();
    assert!(matches!(session.save_as(&alias, SaveMode::CreateNew), Err(Error::Conflict(_))));
    assert!(!alias.exists(), "A removed original must not be silently recreated through a case alias.");
}

#[cfg(any(windows, unix))]
#[test]
fn save_as_never_follows_a_symbolic_link() {
    let directory = Directory::new();
    let source = directory.0.join("source.mbdyn-studio");
    let target = directory.0.join("target.mbdyn-studio");
    let link = directory.0.join("link.mbdyn-studio");
    let mut session = ProjectSession::new(ProjectDocument::new(model()).unwrap()).unwrap();
    session.save_as(&source, SaveMode::CreateNew).unwrap();
    fs::write(&target, b"keep target").unwrap();
    #[cfg(windows)]
    let created = std::os::windows::fs::symlink_file(&target, &link);
    #[cfg(unix)]
    let created = std::os::unix::fs::symlink(&target, &link);
    if let Err(error) = created {
        if error.kind() == std::io::ErrorKind::PermissionDenied || (cfg!(windows) && error.raw_os_error() == Some(1314)) { eprintln!("Symlink creation is not permitted for this user."); return; }
        panic!("Could not create symlink fixture: {error}");
    }
    assert!(matches!(session.save_as(&link, SaveMode::ReplaceExisting), Err(Error::InvalidProject(_))));
    assert_eq!(fs::read(target).unwrap(), b"keep target");
    assert_eq!(ProjectSession::open(&source).unwrap().document().model, model());
}

#[test]
fn save_as_a_different_existing_file_remains_possible_after_original_changed() {
    let directory = Directory::new();
    let path = directory.0.join("source.mbdyn-studio");
    let target = directory.0.join("other.mbdyn-studio");
    let mut seed = ProjectSession::new(ProjectDocument::new(model()).unwrap()).unwrap();
    seed.save_as(&path, SaveMode::CreateNew).unwrap();
    fs::write(&target, b"other file").unwrap();
    let mut session = ProjectSession::open(&path).unwrap();
    fs::write(&path, b"external edit").unwrap();
    let outcome = session.save_as(&target, SaveMode::ReplaceExisting).unwrap();
    assert_eq!(fs::read(&path).unwrap(), b"external edit");
    assert_eq!(fs::read(outcome.backup.unwrap()).unwrap(), b"other file");
    assert_eq!(ProjectSession::open(&target).unwrap().document().model, model());
}

#[test]
fn source_projects_and_legacy_envelopes_preserve_unknown_data() {
    let directory = Directory::new(); let path = directory.0.join("source.json");
    let raw = json!({"format":"mbdyn-studio/1","model":{"kind":"source-example","name":"Upstream mechanism","sourceExampleId":"triangle","parameters":{},"simulation":{"duration":4,"step":0.002}},"origin":{"revision":"abc","licenses":["GPL-2.0"]}});
    fs::write(&path,serde_json::to_vec(&raw).unwrap()).unwrap();
    let session = ProjectSession::open(&path).unwrap();
    assert!(!session.is_dirty());
    assert_eq!(session.document().model,raw["model"]);
    assert_eq!(session.document().extra["origin"],raw["origin"]);
    fs::write(&path,serde_json::to_vec(&model()).unwrap()).unwrap();
    assert_eq!(ProjectSession::open(&path).unwrap().document().model,model());
}

#[test]
fn scientific_numbers_roundtrip_without_losing_native_output_precision() {
    let directory=Directory::new();let path=directory.0.join("precision.json");
    let mut document=ProjectDocument::new(model()).unwrap();
    let exact="{\"samples\":[{\"x\":-4.7845970000000004e-27,\"y\":5.0193969999999996e-26,\"z\":-0.0,\"large\":123456789012345678901234567890}]}";
    document.result=Some(serde_json::from_str(exact).unwrap());
    ProjectSession::new(document.clone()).unwrap().save_as(&path,SaveMode::CreateNew).unwrap();
    assert_eq!(ProjectSession::open(&path).unwrap().document(),&document);
}

#[test]
fn invalid_and_oversized_files_do_not_change_a_live_session() {
    let directory = Directory::new(); let path = directory.0.join("invalid.json");
    let original = ProjectDocument::new(model()).unwrap();
    let mut session = ProjectSession::new(original.clone()).unwrap();
    fs::write(&path,b"{broken").unwrap();
    assert!(ProjectSession::open(&path).is_err());
    let mut invalid = original.clone(); invalid.format = "unknown/9".into();
    assert!(session.replace_document(invalid).is_err());
    assert_eq!(session.document(),&original);
    let file = fs::File::create(&path).unwrap(); file.set_len(MAX_PROJECT_BYTES+1).unwrap(); drop(file);
    assert!(matches!(ProjectSession::open(&path),Err(Error::InvalidProject(_))));
    let mut large = original; large.result=Some(json!({"rawCsv":"x".repeat(16*1024*1024)}));
    session.replace_document(large).unwrap();
    session.save_as(&directory.0.join("large.json"),SaveMode::CreateNew).unwrap();
}

fn fixture(status: u16, value: serde_json::Value) -> (BackendClient, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let client = BackendClient::new(listener.local_addr().unwrap().port()).unwrap();
    let task = thread::spawn(move || {
        let (mut socket,_) = listener.accept().unwrap();
        let mut request = Vec::new();
        while !request.ends_with(b"\r\n\r\n") { let mut byte=[0];socket.read_exact(&mut byte).unwrap();request.push(byte[0]); }
        let headers=String::from_utf8(request).unwrap();
        let length=headers.lines().find_map(|line|line.strip_prefix("Content-Length: ")).unwrap().parse::<usize>().unwrap();
        let mut body=vec![0;length];socket.read_exact(&mut body).unwrap();
        let response=serde_json::to_vec(&value).unwrap();
        write!(socket,"HTTP/1.0 {status} Status\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",response.len()).unwrap();socket.write_all(&response).unwrap();
        format!("{headers}{}",String::from_utf8(body).unwrap())
    });
    (client,task)
}

#[test]
fn loopback_api_preserves_failure_payload_and_checks_identity() {
    let payload=json!({"ok":false,"error":"time limit","runId":"retained","exitCode":124,"log":"partial state","files":{"log":"/api/runs/retained/solver.log"}});
    let (client,task)=fixture(422,payload.clone());
    match client.run_source("triangle") { Err(Error::Backend{status,payload:actual})=>{assert_eq!(status,422);assert_eq!(actual,payload);}, other=>panic!("unexpected result: {other:?}") }
    let request=task.join().unwrap();
    assert!(request.contains("POST /api/source-run HTTP/1.0"));
    assert!(request.contains("Host: 127.0.0.1:"));
    assert!(request.ends_with("{\"id\":\"triangle\"}"));
    let (client,task)=fixture(200,json!({"application":"different-app","version":"1"}));
    assert!(matches!(client.health(),Err(Error::Protocol(_)))); task.join().unwrap();
}

#[test]
fn source_result_samples_and_provenance_are_not_narrowed() {
    let result=json!({"ok":true,"source":"MBDyn","runId":"abc","model":{"kind":"source-example"},"samples":[{"time":0,"nodes":[{"id":8,"x":2.0,"z":3.0}]}],"metrics":{"sampleCount":1},"upstream":{"revision":"123","files":["driver.mbd"]}});
    let (client,task)=fixture(200,result.clone());
    let actual=client.run_source("triangle").unwrap();
    assert_eq!(actual.samples,result["samples"].as_array().unwrap().clone());
    assert_eq!(actual.extra["upstream"],result["upstream"]);
    task.join().unwrap();
    assert!(matches!(client.download("/api/runs/../../backend/solver.json"),Err(Error::Protocol(_))));
}

#[test]
fn authored_assembly_runs_preserve_the_model_and_solver_output() {
    let models = [
        json!({
            "kind":"planar-assembly", "name":"Planar", "parameters":{"gravity":9.81},
            "simulation":{"duration":1.0,"step":0.001},
            "bodies":[{"id":"arm","name":"Arm","mass":1.0,"inertia":{"xx":0.1,"yy":0.1,"zz":0.1},"pose":{"x":0.0,"z":-0.5,"angleDeg":0.0},"velocity":{"vx":0.0,"vz":0.0,"omega":0.0}}],
            "joints":[{"id":"hinge","type":"revolute","parent":"ground","child":"arm","parentAnchor":{"x":0.0,"z":0.0},"childAnchor":{"x":0.0,"z":0.5}}],
            "rotationalElements":[{"id":"spring","joint":"hinge","stiffness":10.0,"damping":0.5,"restAngleDeg":0.0}]
        }),
        json!({
            "kind":"spatial-assembly", "name":"Spatial", "parameters":{"gravity":{"x":0.0,"y":0.0,"z":-9.81}},
            "simulation":{"duration":1.0,"step":0.002},
            "bodies":[{"id":"bob","name":"Bob","mass":1.0,"inertia":{"xx":0.1,"yy":0.1,"zz":0.1},"pose":{"x":0.5,"y":0.0,"z":-0.8660254037844386,"rx":0.0,"ry":0.0,"rz":0.0},"velocity":{"vx":0.0,"vy":0.0,"vz":0.0,"wx":0.0,"wy":0.0,"wz":0.0}}],
            "joints":[{"id":"ball","type":"spherical","a":"ground","b":"bob","anchorA":{"x":0.0,"y":0.0,"z":0.0},"anchorB":{"x":-0.5,"y":0.0,"z":0.8660254037844386}}]
        }),
    ];
    for model in models {
        let response=json!({"ok":true,"source":"MBDyn","runId":"0123456789abcdef0123456789abcdef","model":model,
            "samples":[{"time":0.0,"nodes":[{"id":"bob","x":0.5}],"rotationalStates":[{"id":"spring","torque":1.0}]}],
            "metrics":{"maxConstraintError":1e-12},"solver":{"available":true,"version":"1.7.3","path":"mbdyn","mode":"native","detail":"ready"},
            "nodeLabels":{"bob":1},"deckSha256":"abc"});
        let (client,task)=fixture(200,response.clone());
        let actual=client.run_model(&model).unwrap();
        assert_eq!(actual.model.as_ref(),Some(&model));
        assert_eq!(actual.samples,response["samples"].as_array().unwrap().clone());
        assert_eq!(actual.extra["nodeLabels"],response["nodeLabels"]);
        let request=task.join().unwrap();
        let (headers,body)=request.split_once("\r\n\r\n").unwrap();
        assert!(headers.starts_with("POST /api/run HTTP/1.0\r\n"));
        assert_eq!(serde_json::from_str::<serde_json::Value>(body).unwrap(),json!({"model":model}));
    }
}

#[test]
fn authored_run_preserves_backend_validation_and_execution_errors() {
    let model=json!({"kind":"spatial-assembly","parameters":{"gravity":{"x":0,"y":0,"z":-9.81}},"bodies":[],"joints":[]});
    let failures=[
        (422,json!({"ok":false,"error":"Model validation failed.","issues":[{"field":"bodies","level":"error","message":"Supply 1–16 rigid bodies."}]})),
        (503,json!({"ok":false,"error":"MBDyn is unavailable. No solver result was generated.","solver":{"available":false,"detail":"not configured"}})),
    ];
    for (status,payload) in failures {
        let (client,task)=fixture(status,payload.clone());
        match client.run_model(&model) {
            Err(Error::Backend{status:actual_status,payload:actual})=>{assert_eq!(actual_status,status);assert_eq!(actual,payload);},
            other=>panic!("unexpected result: {other:?}"),
        }
        let request=task.join().unwrap();
        let (headers,body)=request.split_once("\r\n\r\n").unwrap();
        assert!(headers.starts_with("POST /api/run HTTP/1.0\r\n"));
        assert_eq!(serde_json::from_str::<serde_json::Value>(body).unwrap(),json!({"model":model}));
    }
    let (client,task)=fixture(200,json!({"ok":true,"source":"Reference preview","runId":"wrong","samples":[{"time":0}]}));
    assert!(matches!(client.run_model(&model),Err(Error::Protocol(_))));
    task.join().unwrap();
}

#[test]
fn owned_python_service_uses_command_line_bytecode_suppression() {
    use std::process::Command;
    if !Command::new("python").arg("--version").output().is_ok_and(|value| value.status.success()) {
        eprintln!("Python is unavailable; owned service launch fixture was not run.");
        return;
    }
    let directory=Directory::new();
    let root=directory.0.join("read only resources"); let backend=root.join("backend"); let data=directory.0.join("separate data");
    fs::create_dir_all(&backend).unwrap();fs::create_dir(&data).unwrap();
    fs::write(backend.join("bytecode_probe.py"),"VALUE = 1\n").unwrap();
    fs::write(backend.join("server.py"),r#"import argparse,json,sys
assert '-B' in sys.orig_argv and sys.dont_write_bytecode
import bytecode_probe
from http.server import BaseHTTPRequestHandler,HTTPServer
p=argparse.ArgumentParser();p.add_argument('--port',type=int);p.add_argument('--startup-nonce');args=p.parse_args()
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  value=json.dumps({'application':'mbdyn-studio','version':'test','startupNonce':args.startup_nonce}).encode()
  self.send_response(200);self.send_header('Content-Length',str(len(value)));self.end_headers();self.wfile.write(value)
 def log_message(self,*args):pass
HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
"#).unwrap();
    let mut service=BackendService::start_with_data_dir(&root,&PathBuf::from("python"),&data).unwrap();
    assert!(service.is_running().unwrap());service.stop().unwrap();
    assert!(!backend.join("__pycache__").exists(),"Service import created cache files in immutable resources");
}

#[test]
fn backend_reports_unusable_user_data_path_before_launch() {
    let directory=Directory::new();
    let data_file=directory.0.join("not-a-directory");
    fs::write(&data_file,b"retain me").unwrap();
    let result=BackendService::start_with_data_dir(&directory.0,&PathBuf::from("python"),&data_file);
    match result { Err(Error::Protocol(message)) => assert!(message.contains("writable data folder")), _ => panic!("Expected an actionable user-data error") }
    assert_eq!(fs::read(data_file).unwrap(),b"retain me");
}
