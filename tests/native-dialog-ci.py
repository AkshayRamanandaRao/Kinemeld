"""Build a candidate with the release packager, extract it, then run real native GUI tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
platform = {"linux": "linux", "darwin": "macos", "win32": "windows"}[sys.platform]
arch = "arm64" if platform == "macos" else "x86_64"
binary = root / "native/target/release" / ("mbdyn-studio-desktop.exe" if platform == "windows" else "mbdyn-studio-desktop")
out = root / "build/native-gui"
out.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, str(root / "scripts/package_release.py"), "--platform", platform, "--arch", arch,
                "--binary", str(binary), "--version", "1.2.1-gui", "--solver", str(root / "build/solver"),
                "--solver-sources", str(root / "build/solver-sources"), "--out", str(out)], check=True)
extracted = out / "extracted"
extracted.mkdir()  # A stale candidate must never be silently reused.
stem = f"Kinemeld-1.2.1-gui-{platform}-{arch}"
if platform == "linux":
    with tarfile.open(out / (stem + ".tar.gz")) as archive:
        archive.extractall(extracted, filter="data")
else:
    with zipfile.ZipFile(out / (stem + ".zip")) as archive:
        archive.extractall(extracted)
if platform == "macos":
    exe = extracted / "Kinemeld.app/Contents/MacOS/kinemeld"
    resources = extracted / "Kinemeld.app/Contents/Resources/app"
else:
    resources = extracted / "Kinemeld-1.2.1-gui"
    exe = resources / ("Kinemeld.exe" if platform == "windows" else "kinemeld")
if platform != "windows":
    for path in [exe, *(resources / "solver/bin").iterdir()]:
        if path.is_file():
            path.chmod(path.stat().st_mode | 0o111)
solver = resources / "solver/bin" / ("mbdyn.exe" if platform == "windows" else "mbdyn")
config = out / "solver.json"
config.write_text(json.dumps({"mode": "native", "executable": str(solver)}), encoding="utf-8")
environment = os.environ.copy()
environment["MBDYN_STUDIO_PYTHON"] = sys.executable
environment.pop("MBDYN_STUDIO_WORKSPACE", None)
if platform == "windows":
    command = [sys.executable, str(root / "tests/native-dialog-platform.py"), "--exe", str(exe), "--solver-config", str(config)]
elif platform == "linux":
    # System Python has the runner's AT-SPI bindings; the service uses the CAD-enabled Python.
    command = ["dbus-run-session", "--", "xvfb-run", "-a", "-s", "-screen 0 1600x1000x24", "bash", str(root / "tests/native-dialog-linux-session.sh"), str(exe), str(config)]
else:
    command = [sys.executable, str(root / "tests/native-dialog-platform.py"), "--exe", str(exe), "--solver-config", str(config)]
subprocess.run(command, cwd=root, env=environment, check=True)
