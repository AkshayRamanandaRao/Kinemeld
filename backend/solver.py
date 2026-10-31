"""Run generated decks only; preserve solver provenance and physical output."""

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid

from models import deck, metrics, sample, validate
import industry_models
import gear_deployment
import planar_assembly
import spatial_assembly
import app_paths

ROOT = app_paths.RESOURCE_ROOT
RUNS = app_paths.RUNS
CONFIG = app_paths.SOLVER_CONFIG
SOLVER_TIMEOUT_SECONDS = 180
PROCESS_TIMEOUT_SECONDS = 185


def linux_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("The configured WSL solver requires a local drive path.")
    return "/mnt/" + path.drive[0].lower() + "/" + "/".join(path.parts[1:])


def configuration():
    path = app_paths.existing_config(CONFIG, app_paths.SOLVER_CONFIG, app_paths.LEGACY_SOLVER_CONFIG)
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(config, dict) or config.get("mode") not in ("native", "wsl") or not isinstance(config.get("executable"), str) or not config["executable"]:
            raise ValueError(f"{path} must specify mode and executable.")
        if config["mode"] == "wsl" and not re.fullmatch(r"[A-Za-z0-9_.-]+", config.get("distribution", "")):
            raise ValueError("The WSL distribution name is invalid.")
        return config
    # Release packages may ship a solver next to the application; PATH is the final fallback.
    bundled = ROOT / "solver" / "bin" / ("mbdyn.exe" if os.name == "nt" else "mbdyn")
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return {"mode": "native", "executable": str(bundled)}
    binary = shutil.which("mbdyn")
    return {"mode": "native", "executable": binary} if binary else None


def command(config, args, directory=None, bounded=False, cancellable=False):
    if config["mode"] == "wsl":
        result = ["wsl.exe", "-d", config["distribution"]]
        if directory:
            result += ["--cd", linux_path(directory)]
        result += ["--exec"]
        if cancellable:
            result += ["/bin/sh", "-c", _WSL_SUPERVISOR, "mbdyn-cancel-supervisor"]
        if bounded:
            result += ["/usr/bin/timeout", "--signal=TERM", "--kill-after=3", f"{SOLVER_TIMEOUT_SECONDS}s"]
        return result + [config["executable"], *args]
    return [config["executable"], *args]


def status():
    try:
        config = configuration()
        if config is None:
            return {"available": False, "version": None, "path": None, "detail": "MBDyn is not configured. See docs/solver.md. Deck export and reference preview remain available."}
        # The first run of a newly installed solver can wait for an operating-system security scan.
        result = subprocess.run(command(config, ["-v"]), capture_output=True, timeout=30, text=True, errors="replace")
        output = (result.stdout + result.stderr).replace("\x00", "").strip()
        match = re.search(r"MBDyn\s*-\s*MultiBody Dynamics\s+([^\r\n]+)", output, re.I)
        available = result.returncode == 0 and match is not None
        return {"available": available, "version": match.group(1).strip() if match else None, "path": config["executable"], "mode": config["mode"], "detail": "Configured solver responds to its version probe." if available else output[-1500:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "version": None, "path": None, "detail": str(exc)}


class _WindowsProcessJob:
    """Own a Windows process tree, including descendants, until this handle closes."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [("per_process_time", ctypes.c_int64), ("per_job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
                        ("maximum_working_set", ctypes.c_size_t), ("active_process_limit", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in
                        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]
        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", IoCounters), ("process_memory", ctypes.c_size_t),
                        ("job_memory", ctypes.c_size_t), ("peak_process_memory", ctypes.c_size_t),
                        ("peak_job_memory", ctypes.c_size_t)]

        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._kernel.CreateJobObjectW.restype = wintypes.HANDLE
        self._kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self._kernel.SetInformationJobObject.restype = wintypes.BOOL
        self._kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        self._kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._kernel.TerminateJobObject.restype = wintypes.BOOL
        self._kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel.CloseHandle.restype = wintypes.BOOL
        self._handle = self._kernel.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._kernel.SetInformationJobObject(self._handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        import ctypes
        if not self._kernel.AssignProcessToJobObject(self._handle, int(process._handle)):
            error = ctypes.WinError(ctypes.get_last_error())
            raise OSError(f"Cannot isolate the solver process in a Windows job: {error}") from error

    def terminate(self):
        import ctypes
        if not self._kernel.TerminateJobObject(self._handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self._handle:
            self._kernel.CloseHandle(self._handle)
            self._handle = None


class RunControl:
    """A cancellation request associated with exactly one solver invocation."""
    def __init__(self):
        self._requested = threading.Event()

    def cancel(self):
        self._requested.set()

    @property
    def requested(self):
        return self._requested.is_set()


# The guest supervisor owns a fresh session. Its ready marker guarantees that
# cancellation cannot target a group before the child has created that session.
_WSL_SUPERVISOR = r"""set -u
if [ -e .cancel-request ]; then exit 125; fi
/usr/bin/setsid /bin/sh -c 'printf ready > .cancel-ready; exec "$@"' mbdyn-owned "$@" &
leader=$!
while [ ! -s .cancel-ready ]; do
    if ! kill -0 "$leader" 2>/dev/null; then wait "$leader"; exit $?; fi
    sleep .05
done
while kill -0 "$leader" 2>/dev/null; do
    if [ -e .cancel-request ]; then
        if kill -KILL -"$leader" 2>/dev/null; then
            wait "$leader" 2>/dev/null || :
            exit 125
        fi
        wait "$leader"
        exit $?
    fi
    sleep .1
done
wait "$leader"
"""


# The gate prevents the command from creating descendants before job assignment.
_WINDOWS_LAUNCHER = """import subprocess, sys
if sys.stdin.buffer.read(1) != b'1':
    sys.exit(125)
try:
    sys.exit(subprocess.run(sys.argv[1:], stdin=subprocess.DEVNULL).returncode)
except OSError as error:
    print(f'Could not start the configured solver: {error}', file=sys.stderr, flush=True)
    sys.exit(126)
"""


def execute(argv, directory, timeout=PROCESS_TIMEOUT_SECONDS, control=None, wsl=False):
    """Run an owned solver process tree with a deadline and retain partial output."""
    job = _WindowsProcessJob() if os.name == "nt" else None
    process = None
    try:
        with (directory / "solver.log").open("wb") as log:
            if control and control.requested:
                return {"cancelled": True, "error": "Simulation cancelled before solver launch. Partial artifacts are retained."}
            if job:
                process = subprocess.Popen([sys.executable, "-B", "-c", _WINDOWS_LAUNCHER, *argv], cwd=directory,
                                           stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    job.assign(process)
                    process.stdin.write(b"1")
                    process.stdin.close()
                except BaseException:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                    raise
            else:
                process = subprocess.Popen(argv, cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + timeout
            cancel_sent = False
            guest_deadline = None
            try:
                while process.poll() is None:
                    now = time.monotonic()
                    if control and control.requested and not cancel_sent:
                        if wsl:
                            (directory / ".cancel-request").touch()
                            guest_deadline = now + 8
                        elif job:
                            job.terminate()
                        else:
                            try: os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                        cancel_sent = True
                    if now >= deadline or (guest_deadline is not None and now >= guest_deadline):
                        if job: job.terminate()
                        else:
                            try: os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError: pass
                        process.wait()
                        if guest_deadline is not None:
                            return {"error": "The WSL cancellation supervisor did not confirm guest termination; the launcher was stopped. Inspect the retained log and guest processes."}
                        return {"error": f"MBDyn exceeded the {timeout:g}-second process deadline and was stopped. Partial output is retained; inspect the saved log and retry when system load is lower or shorten the study."}
                    try: process.wait(timeout=min(.1, max(.001, deadline-now)))
                    except subprocess.TimeoutExpired: pass
            except BaseException:
                if not job:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait()
                raise
        code = process.returncode
    finally:
        if job:
            job.close()
    if cancel_sent and ((wsl and code == 125) or (not wsl and code != 0)):
        return {"cancelled": True, "exitCode": code, "error": "Simulation cancelled. Partial output and the solver log are retained."}
    outcome = {"exitCode": code}
    if code == 124:
        outcome["error"] = f"MBDyn reached the {SOLVER_TIMEOUT_SECONDS}-second solver time limit (exit 124). Partial output is retained; retry when system load is lower or shorten the study. This exit does not establish a convergence failure."
    elif code == 137:
        outcome["error"] = f"MBDyn was forcibly stopped (exit 137): the {SOLVER_TIMEOUT_SECONDS}-second time limit plus 3-second shutdown grace may have expired, or an external SIGKILL occurred. Inspect the retained partial log; this exit does not establish a convergence failure."
    elif code == 126:
        outcome["error"] = "MBDyn could not be launched or returned exit 126. Inspect the saved solver log for the actual reason."
    elif code != 0:
        outcome["error"] = f"MBDyn did not complete successfully (exit {code}). Inspect the saved solver log."
    return outcome


def parse_output(directory, model):
    if model["kind"] == spatial_assembly.KIND:
        return spatial_assembly.parse_output(directory, model)
    if model["kind"] == planar_assembly.KIND:
        return planar_assembly.parse_output(directory, model)
    times = []
    for line in (directory / "result.out").read_text(errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 9 and fields[0] == "Step" and fields[8] == "1":
            times.append(float(fields[2]))
    kind = model["kind"]
    node = 2 if kind == "mass-spring" else 1
    labels = gear_deployment.NODE_LABELS if kind in gear_deployment.RANGES else ((1,2) if kind == "double-pendulum" or kind in industry_models.RANGES else (node,))
    rows = {label: [] for label in labels}
    for line in (directory / "result.mov").read_text().splitlines():
        fields = line.split()
        if not fields:
            continue
        label = int(fields[0])
        if label in rows:
            values = [float(v) for v in fields]
            if len(values) != 13 or not all(math.isfinite(v) for v in values):
                raise ValueError("Unexpected structural-node output representation.")
            rows[label].append(values)
    if len(times) < 2 or any(len(times) != len(records) for records in rows.values()):
        raise ValueError(f"Time/node output mismatch: {len(times)} times, node counts {[len(r) for r in rows.values()]}.")
    if any(not math.isfinite(t) for t in times) or any(b <= a for a,b in zip(times,times[1:])):
        raise ValueError("Solver output timestamps are not finite and increasing.")
    requested = model["simulation"]["duration"]
    if times[-1] < requested - model["simulation"]["step"]*0.1:
        raise ValueError("Solver stopped before the requested end time.")
    samples = []
    for index, (t, row) in enumerate(zip(times, rows[node])):
        if kind in gear_deployment.RANGES:
            samples.append(gear_deployment.parse_sample(model,t,{label:records[index] for label,records in rows.items()}))
            continue
        if kind in industry_models.RANGES:
            row2 = rows[2][index]
            if kind == "landing-gear-drop" and row[3]-row2[3] <= .2*model["parameters"]["strutLength"]:
                raise ValueError("The strut exceeded the supported 80% compression range.")
            samples.append(industry_models.sample(model,t,(row[3],row2[3],row[9],row2[9])))
            continue
        x,y,z = row[1:4]
        if kind != "mass-spring":
            if x*x+z*z < 1e-20:
                raise ValueError("Pendulum output collapsed to its pin position.")
            angle = math.degrees(math.atan2(x, -z))
            velocity = (-z*row[7]+x*row[9]) / (x*x+z*z)
        else:
            angle, velocity = 0, row[7]
        value = sample(kind, t, (x,y,z), velocity, angle)
        if kind == "double-pendulum":
            row2 = rows[2][index]
            x2,y2,z2 = row2[1:4]
            dx,dz = x2-x,z2-z
            if dx*dx+dz*dz < 1e-20:
                raise ValueError("The second pendulum link collapsed.")
            angle2 = math.degrees(math.atan2(dx,-dz))
            velocity2 = (-dz*(row2[7]-row[7])+dx*(row2[9]-row[9]))/(dx*dx+dz*dz)
            value.update(x2=x2,y2=y2,z2=z2,angle2=angle2,velocity2=velocity2,value2=angle2)
        samples.append(value)
    return samples


def run(model, control=None):
    check = validate(model)
    if not check["valid"]:
        return {"ok": False, "error": "Model validation failed.", "issues": check["issues"]}, 422
    if control and control.requested:
        return {"ok":False,"cancelled":True,"error":"Simulation cancelled before solver launch."}, 409
    info = status()
    if control and control.requested:
        return {"ok":False,"cancelled":True,"error":"Simulation cancelled before solver launch."}, 409
    if not info["available"]:
        return {"ok": False, "error": "MBDyn is unavailable. No solver result was generated.", "solver": info}, 503
    config = configuration()
    run_id = uuid.uuid4().hex
    directory = RUNS / run_id
    directory.mkdir(parents=True)
    model_text = deck(model)
    (directory / "model.mbd").write_text(model_text, encoding="utf-8")
    (directory / "project.json").write_text(json.dumps(model, indent=2), encoding="utf-8")
    argv = command(config, ["-f", "model.mbd", "-o", "result"], directory, bounded=True, cancellable=bool(control) and config["mode"] == "wsl")
    start = time.monotonic()
    result = {"ok": False, "source": "MBDyn", "runId": run_id, "model": model,
              "solver": info, "deckSha256": hashlib.sha256(model_text.encode()).hexdigest(),
              "files": {"deck": f"/api/runs/{run_id}/model.mbd", "log": f"/api/runs/{run_id}/solver.log", "csv": f"/api/runs/{run_id}/results.csv", "project": f"/api/runs/{run_id}/project.json"}}
    try:
        outcome = execute(argv, directory, control=control, wsl=bool(control) and config["mode"] == "wsl")
        result.update(outcome)
        if "error" in outcome:
            raise ValueError(outcome["error"])
        if model["kind"] in (planar_assembly.KIND, spatial_assembly.KIND):
            with (directory / "solver.log").open("rb") as log:
                log.seek(0, 2)
                log.seek(max(0, log.tell() - 4096))
                if b"MBDyn terminated normally" not in log.read():
                    raise ValueError("MBDyn did not report normal termination; partial trajectories are not a completed assembly result.")
        samples = parse_output(directory, model)
        if model["kind"] == spatial_assembly.KIND:
            spatial_assembly.write_csv(directory / "results.csv", samples)
        elif model["kind"] == planar_assembly.KIND:
            planar_assembly.write_csv(directory / "results.csv", samples)
        else:
            with (directory / "results.csv").open("w", encoding="utf-8", newline="") as out:
                writer = csv.DictWriter(out, fieldnames=list(samples[0]))
                writer.writeheader()
                writer.writerows(samples)
        calculated = metrics(model,samples)
        if any(isinstance(value,(int,float)) and not math.isfinite(value) for value in calculated.values()):
            raise ValueError("Non-finite derived metric in solver output.")
        result.update(ok=True, metrics=calculated)
        if model["kind"] in (planar_assembly.KIND, spatial_assembly.KIND):
            result["nodeLabels"] = check["summary"]["nodeLabels"]
            result["units"] = {"time": "s", "position": "m", "velocity": "m/s", "nativeEuler123": "deg", "angularVelocity": "rad/s"}
            if model["kind"] == planar_assembly.KIND:
                result["units"].update(angleDeg="deg", energy="J")
            else:
                result["units"].update(angularConstraintError="rad")
                result['reactionInfo']={'available':bool(model['joints']),'frame':'world','on':'body B','momentAbout':'body B joint anchor','source':'MBDyn constraint elements','excludes':'separate applied loads, springs, torques and contact elements'}
                if model['joints']:
                    result['units'].update(jointReactionForce='N',jointReactionMoment='N*m')
                    result['files']['jointOutput']=f'/api/runs/{run_id}/result.jnt'
                else:result['reactionInfo']['reason']='The model has no spatial joints.'
        stride = max(1, math.ceil((len(samples)-1)/2000))
        result["samples"] = samples[::stride]
        if result["samples"][-1] != samples[-1]:
            result["samples"].append(samples[-1])
        result["displaySampleCount"] = len(result["samples"])
    except (OSError, ValueError, ArithmeticError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
        redundant = check["summary"].get("mobility", {}).get("redundant", []) if model["kind"] == spatial_assembly.KIND else []
        if redundant:
            listed = "; ".join(f"{item['joint']} ({item['component']})" for item in redundant[:4])
            result["error"] += (f" The constraint analysis found {len(redundant)} redundant constraint(s): {listed}"
                                f"{' …' if len(redundant) > 4 else ''}. MBDyn cannot assemble redundant loops; "
                                "make the loop exact, for example with a spherical joint at one end of a link and a universal joint at the other.")
            result["redundantConstraints"] = redundant
    result["elapsedSeconds"] = time.monotonic()-start
    with (directory / "solver.log").open("rb") as log:
        log.seek(0, 2)
        log.seek(max(0, log.tell()-12000))
        result["log"] = log.read().decode("utf-8", errors="replace")
    (directory / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result, 200 if result["ok"] else 409 if result.get("cancelled") else 422
