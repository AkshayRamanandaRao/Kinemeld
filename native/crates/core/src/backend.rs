use crate::{Error, Result};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{collections::BTreeMap, fs::{self, File}, io::{BufReader, Read, Write}, net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream}, path::{Path, PathBuf}, process::{Child, Command, Stdio}, thread, time::{Duration, Instant, SystemTime, UNIX_EPOCH}};

const MAX_RESPONSE: usize = 64 * 1024 * 1024;
const MAX_REQUEST: usize = 65536;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Simulation { pub duration: f64, pub step: f64 }

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Model { pub kind: String, pub name: String, pub parameters: BTreeMap<String, f64>, pub simulation: Simulation }

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Health {
    pub application: String,
    pub version: String,
    #[serde(default, rename = "startupNonce", skip_serializing)]
    pub startup_nonce: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SolverStatus {
    pub available: bool,
    pub version: Option<String>,
    pub path: Option<String>,
    pub mode: Option<String>,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendStatus { pub solver: SolverStatus, pub capabilities: Vec<String>, pub local_only: bool, pub project_schema_version: u32 }

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Example {
    pub id: String, pub title: String, pub description: String, pub model: Value,
    #[serde(flatten)] pub extra: BTreeMap<String, Value>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ValidationIssue { pub level: String, pub field: String, pub message: String }

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Validation { pub valid: bool, pub issues: Vec<ValidationIssue>, pub summary: Value }

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DeckResponse { #[serde(flatten)] pub validation: Validation, pub deck: String, pub filename: String }

/// Typed result envelope with opaque samples/provenance for template and source models.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SimulationResult {
    pub ok: bool,
    pub source: Option<String>,
    pub model: Option<Value>,
    #[serde(default)] pub samples: Vec<Value>,
    #[serde(default)] pub metrics: Value,
    pub run_id: Option<String>,
    #[serde(default)] pub files: BTreeMap<String, String>,
    pub solver: Option<SolverStatus>,
    pub log: Option<String>,
    pub error: Option<String>,
    pub deck_sha256: Option<String>,
    #[serde(flatten)] pub extra: BTreeMap<String, Value>,
}

/// Loopback-only, blocking API. Call it on a UI worker thread for solver operations.
#[derive(Clone, Debug)]
pub struct BackendClient { port: u16 }

impl BackendClient {
    pub fn new(port: u16) -> Result<Self> {
        if port < 1024 { return Err(Error::Protocol("Choose a local backend port from 1024 to 65535.".into())); }
        Ok(Self { port })
    }
    pub fn port(&self) -> u16 { self.port }
    pub fn base_url(&self) -> String { format!("http://127.0.0.1:{}", self.port) }
    pub fn health(&self) -> Result<Health> {
        let health: Health = self.json("GET", "/api/health", None, 2)?;
        if health.application != "mbdyn-studio" { return Err(Error::Protocol("The selected port does not identify Kinemeld.".into())); }
        Ok(health)
    }
    pub fn status(&self) -> Result<BackendStatus> { self.json("GET", "/api/status", None, 15) }
    pub fn examples(&self) -> Result<Vec<Example>> {
        #[derive(Deserialize)] struct Examples { examples: Vec<Example> }
        Ok(self.json::<Examples>("GET", "/api/examples", None, 5)?.examples)
    }
    pub fn validate(&self, model: &Model) -> Result<Validation> { self.validate_model(&serde_json::to_value(model)?) }
    pub fn validate_model(&self, model: &Value) -> Result<Validation> { self.json("POST", "/api/validate", Some(json!({"model":model})), 10) }
    pub fn deck(&self, model: &Model) -> Result<DeckResponse> { self.json("POST", "/api/deck", Some(json!({"model":model})), 10) }
    pub fn deck_model(&self, model: &Value) -> Result<DeckResponse> { self.json("POST", "/api/deck", Some(json!({"model":model})), 10) }
    pub fn preview(&self, model: &Model) -> Result<SimulationResult> { self.json("POST", "/api/preview", Some(json!({"model":model})), 30) }
    pub fn run(&self, model: &Model) -> Result<SimulationResult> { self.checked_run("/api/run", json!({"model":model})) }
    pub fn source_catalog(&self) -> Result<Value> { self.json("GET", "/api/source-examples", None, 10) }
    pub fn run_source(&self, id: &str) -> Result<SimulationResult> { self.checked_run("/api/source-run", json!({"id":id})) }
    pub fn run_model(&self, model: &Value) -> Result<SimulationResult> {
        if model.get("kind").and_then(Value::as_str) == Some("source-example") {
            let validation = self.validate_model(model)?;
            if !validation.valid { return Err(Error::Backend { status:422, payload:serde_json::to_value(validation)? }); }
            let id = model.get("sourceExampleId").and_then(Value::as_str).ok_or_else(|| Error::Protocol("A source project must identify its catalog example.".into()))?;
            self.run_source(id)
        } else { self.checked_run("/api/run", json!({"model":model})) }
    }
    fn checked_run(&self, path: &str, body: Value) -> Result<SimulationResult> {
        let result: SimulationResult = self.json("POST", path, Some(body), 210)?;
        if !result.ok || result.source.as_deref() != Some("MBDyn") || result.samples.is_empty() || result.run_id.is_none() {
            return Err(Error::Protocol("Backend response did not establish a completed MBDyn run with samples and provenance.".into()));
        }
        Ok(result)
    }
    pub fn download(&self, path: &str) -> Result<Vec<u8>> {
        let pieces: Vec<_> = path.split('/').collect();
        if pieces.len() != 5 || pieces[1] != "api" || pieces[2] != "runs" || pieces[3].len() != 32 || !pieces[3].bytes().all(|c| c.is_ascii_hexdigit()) || !["model.mbd","solver.log","results.csv","project.json","summary.json","result.mov","result.out","result.log"].contains(&pieces[4]) {
            return Err(Error::Protocol("Only known run-artifact download paths are accepted.".into()));
        }
        self.request("GET", path, None, 30)
    }
    fn json<T: DeserializeOwned>(&self, method: &str, path: &str, body: Option<Value>, timeout: u64) -> Result<T> {
        let bytes = body.as_ref().map(serde_json::to_vec).transpose()?;
        Ok(serde_json::from_slice(&self.request(method,path,bytes.as_deref(),timeout)?)?)
    }
    fn request(&self, method: &str, path: &str, body: Option<&[u8]>, timeout: u64) -> Result<Vec<u8>> {
        if body.is_some_and(|bytes| bytes.len() > MAX_REQUEST) { return Err(Error::Protocol("Backend request exceeds 64 KiB.".into())); }
        let address = SocketAddr::from((Ipv4Addr::LOCALHOST,self.port));
        let mut stream = TcpStream::connect_timeout(&address,Duration::from_secs(2))?;
        stream.set_read_timeout(Some(Duration::from_secs(timeout)))?;
        stream.set_write_timeout(Some(Duration::from_secs(5)))?;
        write!(stream,"{method} {path} HTTP/1.0\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",self.port,body.map_or(0,<[u8]>::len))?;
        if let Some(body) = body { stream.write_all(body)?; }
        let mut reader = BufReader::new(stream);
        let mut headers = Vec::new();
        while !headers.ends_with(b"\r\n\r\n") {
            if headers.len() == 65536 { return Err(Error::Protocol("Backend response headers exceed 64 KiB.".into())); }
            let mut byte = [0]; reader.read_exact(&mut byte)?; headers.push(byte[0]);
        }
        let headers = std::str::from_utf8(&headers).map_err(|_| Error::Protocol("Backend returned non-text HTTP headers.".into()))?;
        let status = headers.lines().next().and_then(|line| line.split_whitespace().nth(1)).and_then(|word| word.parse::<u16>().ok()).ok_or_else(|| Error::Protocol("Backend returned an invalid HTTP status.".into()))?;
        let mut length = None;
        for line in headers.lines().skip(1) {
            if let Some((key,value)) = line.split_once(':') {
                if key.eq_ignore_ascii_case("content-length") {
                    if length.is_some() { return Err(Error::Protocol("Backend returned duplicate Content-Length headers.".into())); }
                    length = Some(value.trim().parse::<usize>().map_err(|_| Error::Protocol("Invalid backend Content-Length.".into()))?);
                }
                if key.eq_ignore_ascii_case("transfer-encoding") { return Err(Error::Protocol("The local bridge expects explicit Content-Length, not transfer encoding.".into())); }
            }
        }
        let length = length.ok_or_else(|| Error::Protocol("Backend omitted Content-Length.".into()))?;
        if length > MAX_RESPONSE { return Err(Error::Protocol("Backend response exceeds 64 MiB.".into())); }
        let mut bytes = vec![0;length]; reader.read_exact(&mut bytes)?;
        if !(200..300).contains(&status) {
            let payload = serde_json::from_slice(&bytes).unwrap_or_else(|_| json!({"error":String::from_utf8_lossy(&bytes)}));
            return Err(Error::Backend { status, payload });
        }
        Ok(bytes)
    }
}

/// Owns only the Python child started here. Existing services and other build jobs are untouched.
pub struct BackendService { client: BackendClient, child: Option<Child>, log_path: PathBuf }

impl BackendService {
    /// Starts a dedicated backend on an available loopback port; no existing server is reused.
    pub fn start(workspace: &Path, python: &Path) -> Result<Self> {
        Self::start_with_data_dir(workspace, python, workspace)
    }
    /// Start with immutable application resources and a separate writable user-data folder.
    pub fn start_with_data_dir(workspace: &Path, python: &Path, data_dir: &Path) -> Result<Self> {
        fs::create_dir_all(data_dir).map_err(|error| Error::Protocol(format!("Cannot create writable data folder {}: {error}", data_dir.display())))?;
        let data_dir = python_workspace_path(fs::canonicalize(data_dir)?);
        let workspace = python_workspace_path(fs::canonicalize(workspace)?);
        let server = workspace.join("backend/server.py");
        if !server.is_file() { return Err(Error::Protocol("The workspace does not contain backend/server.py.".into())); }
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST,0))?;
        let port = listener.local_addr()?.port();
        drop(listener);
        let client = BackendClient::new(port)?;
        let startup_nonce = startup_nonce()?;
        let logs = data_dir.join("runs/native-service"); fs::create_dir_all(&logs).map_err(|error| Error::Protocol(format!("Cannot write backend logs under {}: {error}", data_dir.display())))?;
        let stamp = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |value| value.as_nanos());
        let log_path = logs.join(format!("backend-{}-{stamp}.log",std::process::id()));
        let log = File::create(&log_path)?;
        let mut command = Command::new(python);
        command.arg("-B").arg(&server).arg("--port").arg(port.to_string()).arg("--startup-nonce").arg(&startup_nonce).env("MBDYN_STUDIO_DATA_DIR", &data_dir).env("PYTHONDONTWRITEBYTECODE", "1").current_dir(&workspace).stdin(Stdio::null()).stdout(Stdio::from(log.try_clone()?)).stderr(Stdio::from(log));
        #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
        let child = command.spawn()?;
        let mut service = Self { client, child:Some(child), log_path };
        let deadline = Instant::now()+Duration::from_secs(15);
        while Instant::now() < deadline {
            let child = service.child.as_mut().ok_or_else(|| Error::Protocol("Backend ownership was lost during startup.".into()))?;
            match startup_ready(&service.client, child, &startup_nonce) {
                Ok(true) => return Ok(service),
                Ok(false) => {},
                Err(error) => return Err(Error::Protocol(format!("{error} Inspect {}.", service.log_path.display()))),
            }
            thread::sleep(Duration::from_millis(75));
        }
        Err(Error::Protocol(format!("The Python backend did not become ready. Inspect {}.",service.log_path.display())))
    }
    pub fn client(&self) -> &BackendClient { &self.client }
    pub fn log_path(&self) -> &Path { &self.log_path }
    pub fn is_running(&mut self) -> Result<bool> {
        match self.child.as_mut() { Some(child) => Ok(child.try_wait()?.is_none()), None => Ok(false) }
    }
    /// Call after pending solver requests finish. An interrupted WSL solve retains its own deadline.
    pub fn stop(&mut self) -> Result<()> {
        if let Some(child) = self.child.as_mut() {
            if child.try_wait()?.is_none() { child.kill()?; }
            child.wait()?;
        }
        self.child = None;
        Ok(())
    }
}

impl Drop for BackendService { fn drop(&mut self) { let _ = self.stop(); } }

fn startup_nonce() -> Result<String> {
    let mut bytes = [0u8;32];
    getrandom::fill(&mut bytes).map_err(|error| Error::Protocol(format!("Cannot obtain secure randomness for backend startup: {error}")))?;
    Ok(bytes.iter().map(|byte|format!("{byte:02x}")).collect())
}

fn startup_ready(client: &BackendClient, child: &mut Child, expected_nonce: &str) -> Result<bool> {
    if let Some(exit) = child.try_wait()? {
        return Err(Error::Protocol(format!("The owned Python backend exited during startup ({exit}).")));
    }
    let health = match client.health() { Ok(health) => health, Err(_) => return Ok(false) };
    if health.startup_nonce.as_deref() != Some(expected_nonce) {
        return Err(Error::Protocol("Backend startup identity mismatch; untrusted content will not be loaded.".into()));
    }
    if let Some(exit) = child.try_wait()? {
        return Err(Error::Protocol(format!("The owned Python backend exited before readiness was established ({exit}).")));
    }
    Ok(true)
}

fn python_workspace_path(path: PathBuf) -> PathBuf {
    // Python's WSL drive mapper consumes ordinary drive paths, not Win32 verbatim prefixes.
    #[cfg(windows)] {
        use std::path::{Component,Prefix};
        if let Some(Component::Prefix(prefix)) = path.components().next() {
            if let Prefix::VerbatimDisk(drive) = prefix.kind() {
                let mut ordinary = PathBuf::from(format!("{}:\\",char::from(drive)));
                for component in path.components().skip(2) { ordinary.push(component.as_os_str()); }
                return ordinary;
            }
        }
    }
    path
}

#[cfg(test)]
mod startup_tests {
    use super::*;

    struct OwnedTestChild(Child);
    impl OwnedTestChild {
        fn start() -> Self {
            let mut command = Command::new(std::env::current_exe().unwrap());
            command.args(["--exact","backend::startup_tests::handshake_child","--ignored","--nocapture"])
                .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
            #[cfg(windows)] { use std::os::windows::process::CommandExt; command.creation_flags(0x08000000); }
            Self(command.spawn().unwrap())
        }
    }
    impl Drop for OwnedTestChild {
        fn drop(&mut self) { let _=self.0.kill(); let _=self.0.wait(); }
    }

    #[test]
    #[ignore = "Subprocess fixture; launched and reaped by startup tests"]
    fn handshake_child() {
        let mut byte=[0];
        std::io::stdin().read_exact(&mut byte).unwrap();
    }

    fn fake_health(value: Value, before_response: impl FnOnce()+Send+'static) -> (BackendClient,thread::JoinHandle<String>) {
        let listener=TcpListener::bind((Ipv4Addr::LOCALHOST,0)).unwrap();
        let client=BackendClient::new(listener.local_addr().unwrap().port()).unwrap();
        let task=thread::spawn(move || {
            let (mut socket,_)=listener.accept().unwrap();
            let mut request=Vec::new();
            while !request.ends_with(b"\r\n\r\n") { let mut byte=[0];socket.read_exact(&mut byte).unwrap();request.push(byte[0]); }
            before_response();
            let body=serde_json::to_vec(&value).unwrap();
            write!(socket,"HTTP/1.0 200 OK\r\nContent-Length: {}\r\n\r\n",body.len()).unwrap();
            socket.write_all(&body).unwrap();
            String::from_utf8(request).unwrap()
        });
        (client,task)
    }

    #[test]
    fn rogue_app_name_without_exact_nonce_cannot_establish_readiness() {
        let expected=startup_nonce().unwrap();
        let other=startup_nonce().unwrap();
        assert_eq!(expected.len(),64);
        assert!(expected.bytes().all(|byte|byte.is_ascii_hexdigit()));
        assert_ne!(expected,other);
        let mut child=OwnedTestChild::start();
        for nonce in [Value::Null,json!(other)] {
            let (client,task)=fake_health(json!({"application":"mbdyn-studio","version":"0.1.0","startupNonce":nonce}),||{});
            let error=startup_ready(&client,&mut child.0,&expected).unwrap_err();
            assert!(matches!(error,Error::Protocol(message) if message.contains("identity mismatch")));
            assert!(!task.join().unwrap().contains(&expected),"The client must not reveal its expected nonce to the responder");
            assert!(child.0.try_wait().unwrap().is_none());
        }
    }

    #[test]
    fn matching_nonce_is_rejected_if_owned_child_exits_during_health_request() {
        let expected=startup_nonce().unwrap();
        let mut child=OwnedTestChild::start();
        let mut input=child.0.stdin.take().unwrap();
        let mut output=child.0.stdout.take().unwrap();
        let (client,task)=fake_health(json!({"application":"mbdyn-studio","version":"0.1.0","startupNonce":expected}),move || {
            input.write_all(&[1]).unwrap();drop(input);
            let mut ignored=Vec::new();output.read_to_end(&mut ignored).unwrap();
            thread::sleep(Duration::from_millis(50));
        });
        let error=startup_ready(&client,&mut child.0,&expected).unwrap_err();
        assert!(matches!(error,Error::Protocol(message) if message.contains("exited before readiness")));
        task.join().unwrap();
        assert!(child.0.try_wait().unwrap().is_some());
    }
}
