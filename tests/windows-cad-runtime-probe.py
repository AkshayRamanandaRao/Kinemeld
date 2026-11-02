"""Diagnostic only: compare the exact nose-gear STEP on two installed CAD runtimes."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

repo = Path(__file__).resolve().parents[1]
output = repo / "tests/evidence/windows-cad-runtime-probe"
output.mkdir(parents=True)
project = json.loads((repo / "examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio").read_text())
asset = project["assets"]["step"]["files"][0]
data = base64.b64decode(asset["data"], validate=True)
assert len(data) == asset["byteLength"] and hashlib.sha256(data).hexdigest() == asset["sha256"]
source = output / "source.step"
source.write_bytes(data)
worker = repo / "backend/step_geometry.py"
wrapper = "import faulthandler,runpy,sys;from pathlib import Path;faulthandler.dump_traceback_later(75);script=sys.argv.pop(1);sys.path.insert(0,str(Path(script).parent));runpy.run_path(script,run_name='__main__')"
report = {"scope": "Diagnostic comparison only; no packaged/native GUI qualification", "stepSha256": asset["sha256"], "workerSha256": hashlib.sha256(worker.read_bytes()).hexdigest(), "runs": []}
for name, python in zip(("ocp8", "ocp79"), sys.argv[1:], strict=True):
    version = subprocess.check_output([python, "-c", "import importlib.metadata as m;print(m.version('cadquery-ocp'))"], text=True, timeout=20).strip()
    for index in range(2):
        mesh = output / f"{name}-{index}.json"
        record = {"runtime": name, "version": version, "repeat": index}
        started = time.monotonic()
        with (output / f"{name}-{index}.log").open("wb") as log:
            try:
                completed = subprocess.run([python, "-B", "-X", "importtime", "-c", wrapper, str(worker), "--worker", str(source), str(mesh)], stdout=log, stderr=log, timeout=90)
                record["exit"] = completed.returncode
            except subprocess.TimeoutExpired:
                record["timedOut"] = True
        record["elapsedSeconds"] = time.monotonic() - started
        if mesh.is_file():
            result = json.loads(mesh.read_text())
            record.update({"parts": len(result.get("parts", [])), "error": result.get("error"), "meshBytes": mesh.stat().st_size})
        report["runs"].append(record)
        (output / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(record), flush=True)
