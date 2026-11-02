"""Check a Kinemeld release archive the way a clean machine sees it.

Unpacks the archive into an empty folder, verifies its checksum and every file against
package-manifest.json, starts the packaged Python service with a fresh user-data folder, and
checks the interface, the solver status and, when MBDyn is bundled, real solver runs whose
files land in the data folder rather than the application folder. With --native-smoke it also
runs the desktop executable's own self-check (on Linux without a display, through xvfb-run).

    python scripts/check_package.py dist/Kinemeld-0.6.0-linux-x86_64.tar.gz --version 0.6.0 [--expect-solver] [--native-smoke]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

from check_asset_notices import verify as verify_assets, unique_keys
from collect_rust_notices import check_bundle as verify_rust
from prepare_solver_sources import verify as verify_solver, verify_license_texts, child

MACOS_APP_ROOT = "Kinemeld.app/Contents/Resources/app"


def ok(message):
    print(f"ok    {message}", flush=True)


def fail(message):
    raise SystemExit(f"FAIL  {message}")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(archive, target):
    def safe_name(name):
        relative = PurePosixPath(name)
        if not name or "\\" in name or ":" in name or relative.is_absolute() or ".." in relative.parts:
            fail(f"unsafe archive path: {name}")
        return relative.as_posix()

    if archive.name.endswith(".tar.gz"):
        with tarfile.open(archive) as tar:
            names = set()
            for member in tar.getmembers():
                name = safe_name(member.name)
                if name in names or not (member.isfile() or member.isdir()):
                    fail(f"duplicate or non-regular archive entry: {member.name}")
                names.add(name)
            tar.extractall(target, filter="data")
        return
    with zipfile.ZipFile(archive) as bundle:
        names = set()
        for info in bundle.infolist():
            name = safe_name(info.filename)
            if name in names or (info.external_attr >> 16) & 0o170000 == 0o120000:
                fail(f"duplicate or linked archive entry: {info.filename}")
            names.add(name)
            path = Path(bundle.extract(info, target))
            # zipfile drops Unix modes; restore them as an unzip tool would.
            mode = (info.external_attr >> 16) & 0o777
            if mode and not info.is_dir():
                path.chmod(mode)


def verify_files(archive, target, version):
    expected = archive.with_name(archive.name + ".sha256")
    if expected.is_file():
        if expected.read_text(encoding="utf-8").split()[0] != sha256(archive):
            fail(f"{archive.name} does not match {expected.name}")
        ok(f"archive checksum matches {expected.name}")
    unpack(archive, target)
    manifests = list(target.rglob("package-manifest.json"))
    if len(manifests) != 1:
        fail(f"expected one package-manifest.json, found {len(manifests)}")
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    if manifest.get("format") != "kinemeld-desktop-package/2":
        fail("package lacks the current dependency/source inventory; rebuild it with the audited packager")
    if version and manifest.get("version") != version:
        fail(f"manifest version {manifest.get('version')} is not {version}")
    root = manifests[0].parent
    if "appRoot" in manifest:
        if manifest["platform"] != "macos" or manifest["appRoot"] != MACOS_APP_ROOT or root != target:
            fail("package appRoot must name the fixed macOS bundle from an archive-root manifest")
        root = target / MACOS_APP_ROOT
        signed_files = {"Kinemeld.app/Contents/MacOS/kinemeld", "Kinemeld.app/Contents/_CodeSignature/CodeResources"}
        if not signed_files <= set(manifest["archiveFiles"]) or any(not (target / name).is_file() for name in signed_files):
            fail("macOS signed host or bundle resource signature is missing from the inventory")
    elif manifest["platform"] == "macos" and root != target / MACOS_APP_ROOT:
        fail("legacy macOS manifest is not inside the fixed application resource folder")
    for relative, digest in manifest["files"].items():
        path = child(root, relative)
        if not path.is_file():
            fail(f"{relative} is listed in the manifest but missing")
        if sha256(path) != digest:
            fail(f"{relative} does not match its manifest hash")
    ok(f"{len(manifest['files'])} files match the manifest of {manifest['application']} {manifest['version']} ({manifest['platform']})")
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file() and p != manifests[0]}
    if actual != set(manifest["archiveFiles"]):
        fail("archive contains unlisted files or omits inventoried files")
    for relative, expected_digest in manifest["archiveFiles"].items():
        if sha256(child(target, relative)) != expected_digest:
            fail(f"archive file does not match its manifest: {relative}")
    if manifest.get("appRoot") and sys.platform == "darwin":
        subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(target / "Kinemeld.app")], check=True)
        ok("macOS application bundle signature and sealed resources verified")
    verify_assets(root)
    verify_license_texts(root / "notices/solver")
    verify_rust(root / "notices/rust", target=manifest["rustTarget"])
    if manifest["bundledSolver"]:
        record = manifest.get("solverSources") or {}
        name = record.get("file", "")
        if not name or Path(name).name != name or "\\" in name:
            fail("solver corresponding-source companion is missing or has an unsafe filename")
        sources_archive = child(archive.parent, name)
        if not sources_archive.is_file() or sha256(sources_archive) != record.get("sha256"):
            fail(f"missing or changed solver corresponding-source companion: {name}")
        sources_target = target.parent / "sources"
        unpack(sources_archive, sources_target)
        metadata = verify_solver(root / "solver", sources_target / "solver-sources")
        if metadata["platform"] != manifest["platform"]:
            fail("solver source inventory belongs to a different platform")
    elif manifest.get("solverSources") or (root / "solver").exists():
        fail("solver payload disagrees with the package manifest")
    ok("asset and Rust notices, full archive inventory and solver corresponding source verified offline")
    return root, manifest


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class Service:
    """The packaged backend, started as the desktop host or start.py would start it."""

    def __init__(self, root, data, log):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "PYTHONHOME")}
        env["MBDYN_STUDIO_DATA_DIR"] = str(data)
        self.process = subprocess.Popen([sys.executable, "-B", str(root / "backend" / "server.py"), "--port", str(self.port)],
                                        cwd=data, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 60
        while True:
            if self.process.poll() is not None:
                fail(f"the packaged service exited with status {self.process.returncode}; see {log.name}")
            try:
                self.get("/api/status")
                return
            except (OSError, urllib.error.URLError):
                if time.monotonic() > deadline:
                    fail("the packaged service did not answer within 60 s")
                time.sleep(0.5)

    def request(self, path, body=None, timeout=120):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"} if data else {})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def get(self, path):
        status, content = self.request(path)
        if status != 200:
            fail(f"GET {path} returned HTTP {status}")
        return content

    def json(self, path, body=None):
        status, content = self.request(path, body)
        value = json.loads(content)
        if status != 200:
            fail(f"{'POST' if body is not None else 'GET'} {path} returned HTTP {status}: {value.get('error')}")
        return value

    def stop(self):
        self.process.terminate()
        try:
            self.process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            self.process.kill()


def check_service(root, manifest, data, log):
    service = Service(root, data, log)
    try:
        version = manifest["version"]
        page = service.get("/").decode("utf-8")
        short = ".".join(version.split(".")[:2])
        if f'id="appVersion">{short}<' not in page:
            fail(f"the interface does not show version {short}")
        for asset in ("/app.js", "/viewport.js", "/styles.css", "/vendor/three.module.js"):
            service.get(asset)
        ok(f"interface {short} and its scripts are served")
        examples = service.json("/api/examples")["examples"]
        studies = service.json("/api/featured")["studies"]
        if not examples or not studies:
            fail("the example catalog or the featured studies are empty")
        ok(f"{len(examples)} examples and {len(studies)} featured studies are listed")
        solver = service.json("/api/status")["solver"]
        if not manifest["bundledSolver"]:
            if not isinstance(solver.get("detail"), str):
                fail("solver status lacks an explanation")
            ok(f"no bundled solver; status explains: {solver['detail']}")
            return
        executable = Path(solver.get("path") or "")
        if not solver.get("available") or root.resolve() not in executable.resolve().parents:
            fail(f"the bundled MBDyn is not the active solver: {solver}")
        ok(f"bundled MBDyn {solver.get('version')} answers its version probe")
        pendulum = next(item for item in examples if item["id"] == "pendulum")["model"]
        pendulum["simulation"] = {"duration": 0.1, "step": 0.005}
        study = next((item for item in studies if item["id"] == "robot-arm"), studies[0])
        spatial = service.json(f"/api/featured/{study['id']}")["model"]
        spatial["simulation"]["duration"] = min(spatial["simulation"]["duration"], 10 * spatial["simulation"]["step"])
        for name, model in (("pendulum", pendulum), (study["id"], spatial)):
            result = service.json("/api/run", {"model": model})
            if not result.get("ok") or result.get("source") != "MBDyn" or not result.get("samples"):
                fail(f"{name} run failed: {result.get('error')}")
            run = data / "runs" / result["runId"]
            if not (run / "results.csv").is_file():
                fail(f"{name} run files are not in the user-data folder")
            csv = service.get(f"/api/runs/{result['runId']}/results.csv").decode("utf-8").splitlines()
            ok(f"{name}: MBDyn solved {len(result['samples'])} samples; full CSV has {len(csv)} lines")
        if (root / "runs").exists():
            fail("the service wrote into the application folder")
        ok("run files stay in the user-data folder; the application folder is untouched")
    finally:
        service.stop()


def native_executable(root, platform):
    if platform == "macos":
        return root.parents[1] / "MacOS" / "kinemeld"
    return root / ("Kinemeld.exe" if platform == "windows" else "kinemeld")


def check_native(root, manifest, data):
    executable = native_executable(root, manifest["platform"])
    if not executable.is_file():
        fail(f"desktop executable {executable} is missing")
    command = [str(executable), "--smoke"]
    if manifest["platform"] == "linux" and not os.environ.get("DISPLAY"):
        if not shutil.which("xvfb-run"):
            fail("xvfb-run is needed for the desktop self-check without a display")
        command = ["xvfb-run", "-a", *command]
    env = {key: value for key, value in os.environ.items() if key not in ("MBDYN_STUDIO_WORKSPACE", "PYTHONPATH", "PYTHONHOME")}
    env["MBDYN_STUDIO_DATA_DIR"] = str(data)
    env["MBDYN_STUDIO_PYTHON"] = sys.executable
    completed = subprocess.run(command, cwd=data, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=300, check=False)
    reports = sorted((data / "runs").glob("native-smoke-report-*.json"))
    if not reports:
        fail(f"the desktop self-check wrote no report (exit {completed.returncode}): {completed.stderr[-2000:]}")
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    if not report.get("ok"):
        fail(f"desktop self-check failed: {report.get('error')}")
    if Path(report["workspace"]).resolve() != root.resolve():
        fail(f"the desktop host used resources from {report['workspace']}, not the package")
    leftovers = list((data / "recovery").glob("*")) if (data / "recovery").is_dir() else []
    if leftovers:
        fail(f"a clean exit left recovery files: {leftovers}")
    ok(f"desktop self-check: embedded viewer with WebGL2, MBDyn run of {report['samples']} samples, project saved and reopened")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--version", help="expected application version, e.g. 0.6.0")
    parser.add_argument("--expect-solver", action="store_true", help="fail unless MBDyn is bundled")
    parser.add_argument("--native-smoke", action="store_true", help="also run the desktop executable's self-check")
    parser.add_argument("--keep", action="store_true", help="keep the unpacked folder for inspection")
    parser.add_argument("--files-only", action="store_true", help="verify notices/source/inventory without executing a different platform's binaries")
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="kinemeld-package-check-"))
    try:
        root, manifest = verify_files(args.archive.resolve(), work / "unpacked", args.version)
        if args.expect_solver and not manifest["bundledSolver"]:
            fail("MBDyn is not bundled in this package")
        if args.files_only:
            print(f"PASS  {args.archive.name} (files, notices and sources only)", flush=True)
            return
        (work / "data").mkdir()
        with (work / "service.log").open("w", encoding="utf-8") as log:
            check_service(root, manifest, work / "data", log)
        if args.native_smoke:
            (work / "native-data").mkdir()
            check_native(root, manifest, work / "native-data")
        print(f"PASS  {args.archive.name}", flush=True)
    finally:
        if args.keep:
            print(f"kept {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
