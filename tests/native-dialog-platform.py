"""Real macOS/Linux desktop GUI matrix; never substitutes the native IPC or picker.

Linux: run under a private dbus-run-session + Xvfb desktop (see docs/native-gui-testing.md).
The test host is the normal release binary, explicitly launched with --native-gui-test.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def atomic(path, value):
    temp = path.with_name("." + path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LinuxControls:
    """AT-SPI buttons/fields, constrained to this private desktop's owned processes."""
    def __init__(self, root, app_pid, portal_pids):
        import pyatspi
        self.api, self.root, self.app_pid = pyatspi, root, app_pid
        self.groups = {app_pid, *portal_pids}
        self.current, self.index, self.stage, self.since = None, 0, 0, 0
        self.events = []

    def owned(self, pid):
        try:
            return os.getpgid(pid) in self.groups
        except ProcessLookupError:
            return False

    def walk(self, item):
        yield item
        try:
            for child in item:
                yield from self.walk(child)
        except Exception:
            pass  # AT-SPI objects can disappear as native modal windows close.

    def windows(self):
        result = []
        for app in self.api.Registry.getDesktop(0):
            try:
                pid = app.get_process_id()
                if self.owned(pid):
                    for window in app:
                        if window.getState().contains(self.api.STATE_SHOWING):
                            result.append((pid, window))
            except Exception:
                continue
        return result

    @staticmethod
    def label(item):
        return (item.name or "").replace("_", "").replace("&", "").strip().lower()

    def buttons(self, window):
        return [item for item in self.walk(window) if item.getRole() == self.api.ROLE_PUSH_BUTTON and item.getState().contains(self.api.STATE_ENABLED)]

    def press(self, button):
        action = button.queryAction()
        if not action.nActions or not action.doAction(0):
            raise RuntimeError("The native button did not accept its accessibility action")

    def xid(self, pid, name):
        candidates = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)], capture_output=True, text=True).stdout.split()
        for candidate in candidates:
            title = subprocess.run(["xdotool", "getwindowname", candidate], capture_output=True, text=True, check=True).stdout.strip()
            if title == name:
                return candidate
        raise RuntimeError(f"No owned X window matches {pid}: {name}")

    def record(self, action, pid, window):
        event = {"action": action, "pid": pid, "window": window.name, "role": window.getRoleName(), "buttons": [item.name for item in self.buttons(window)]}
        self.events.append(event)
        # This X display is private to this test, including the portal's native windows.
        subprocess.run(["scrot", "--overwrite", str(self.root / f"native-{self.current}-{self.index}.png")], check=True, capture_output=True)

    def result(self, error=None):
        value = {"id": self.current, "done": self.index >= len(self.plan["actions"]), "events": self.events}
        if error:
            value["error"] = error
        atomic(self.root / "action-result.json", value)

    def advance(self):
        plan = load(self.root / "action.json")
        if not plan:
            return
        if plan["id"] != self.current:
            self.plan, self.current, self.index, self.stage = plan, plan["id"], 0, 0
            self.events, self.since = [], time.monotonic()
        if self.index >= len(self.plan["actions"]):
            return
        if time.monotonic() - self.since > 35:
            windows = [{"pid": pid, "title": window.name, "controls": [{"role": item.getRoleName(), "name": item.name} for item in self.walk(window)]} for pid, window in self.windows()]
            self.result(f"Timed out locating native control; windows={windows}")
            return
        action = self.plan["actions"][self.index]
        for pid, window in self.windows():
            nodes = list(self.walk(window))
            buttons = self.buttons(window)
            names = {self.label(item) for item in buttons}
            is_file = any(item.getRole() == self.api.ROLE_FILE_CHOOSER for item in nodes)
            if action["kind"] == "close":
                if pid != self.app_pid or window.name != "Kinemeld":
                    continue
                xid = self.xid(pid, window.name)
                self.record(action, pid, window)
                self.next()
                subprocess.run(["wmctrl", "-ic", hex(int(xid))], check=True)
                return
            if action["kind"] == "button":
                # Do not confuse a chooser's Cancel with its overwrite confirmation.
                candidates = [node for node in nodes if node.getRole() in (self.api.ROLE_ALERT, self.api.ROLE_DIALOG)]
                candidates.sort(key=lambda item: len(list(self.walk(item))))
                for dialog in candidates:
                    controls = self.buttons(dialog)
                    labels = {self.label(item) for item in controls}
                    wanted = action["text"].lower()
                    if wanted == "refuse-overwrite":
                        if not any("replace" in label for label in labels):
                            continue
                        wanted = "cancel"
                    match = next((item for item in controls if self.label(item) == wanted), None)
                    if match:
                        self.record(action, pid, dialog); self.next(); self.press(match); return
                continue
            if not is_file:
                continue
            opening = "open" in names
            if action["kind"] == "cancel":
                if (action.get("dialog") == "open") != opening:
                    continue
                button = next((item for item in buttons if self.label(item) == "cancel"), None)
                if button:
                    self.record(action, pid, window); self.next(); self.press(button); return
            if action["kind"] not in ("open", "save") or (action["kind"] == "open") != opening:
                continue
            xid = self.xid(pid, window.name)
            if self.stage == 0:
                self.record(action, pid, window)
                subprocess.run(["xdotool", "windowactivate", "--sync", xid], check=True)
                subprocess.run(["xdotool", "key", "--clearmodifiers", "--window", xid, "ctrl+l"], check=True)
                self.stage, self.since = 1, time.monotonic()
                return
            if time.monotonic() - self.since < 0.4:
                return
            entries = [item for item in self.walk(window) if item.getRole() in (self.api.ROLE_TEXT, self.api.ROLE_ENTRY) and item.getState().contains(self.api.STATE_EDITABLE) and item.getState().contains(self.api.STATE_FOCUSED)]
            if not entries:
                continue
            entries[0].queryEditableText().setTextContents(action["path"])
            # Native Return validates the entered pathname and activates the picker.
            self.next()
            subprocess.run(["xdotool", "key", "--clearmodifiers", "--window", xid, "Return"], check=True)
            return

    def next(self):
        self.index += 1
        self.stage, self.since = 0, time.monotonic()
        self.result()


def health(url):
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def terminate(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--solver-config", required=True, type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assert sys.platform in ("linux", "darwin"), "Windows uses tests/native-dialog-ui.mjs."
    repo = Path(__file__).resolve().parents[1]
    output = (args.output or repo / "tests/evidence").resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="native-platform-", dir=output))
    (root / ".kinemeld-native-gui-test").touch()
    data = root / "user-data"
    (data / "runs").mkdir(parents=True)
    atomic(data / "runs/tour-preference.json", {"enabled": False})
    shutil.copy2(args.solver_config, data / "solver.json")
    exe = args.exe.resolve()
    resources = next((path for path in [*exe.parents, exe.parent.parent / "Resources/app"] if (path / "backend/server.py").is_file()), None)
    assert resources, "The actual executable needs its packaged resources."
    fixture = (args.project or resources / "examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio").resolve()
    shutil.copy2(fixture, root / "fixture.mbdyn-studio")
    assert load(fixture).get("assets", {}).get("step", {}).get("bindings"), "Fixture needs actual CAD assets."
    report = {"ok": False, "platform": sys.platform, "executable": str(exe), "executableSha256": digest(exe), "resourceRoot": str(resources), "frontendSha256": digest(resources / "frontend/app.js"), "workspaceOverride": False, "fixtureSha256": digest(fixture), "output": str(root), "checks": [], "nativeControls": [], "skipped": []}
    app, portals, streams = None, [], []
    environment = os.environ.copy()
    environment.pop("MBDYN_STUDIO_WORKSPACE", None)
    environment["MBDYN_STUDIO_DATA_DIR"] = str(data)
    try:
        if sys.platform == "linux":
            assert environment.get("DBUS_SESSION_BUS_ADDRESS") and environment.get("DISPLAY") and environment.get("KINEMELD_PRIVATE_GUI_SESSION") == "1", "Linux GUI qualification requires its own private D-Bus/Xvfb desktop."
            for name in ("xdg-desktop-portal-gtk", "xdg-desktop-portal"):
                binary = next((path for path in (Path("/usr/libexec") / name, Path("/usr/lib/xdg-desktop-portal") / name) if path.is_file()), None)
                assert binary, f"Install {name} to exercise the release-default native portal."
                log = (root / (name + ".log")).open("wb"); streams.append(log)
                portals.append(subprocess.Popen([str(binary), "--replace"], env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
            time.sleep(2)
        for phase, goal in (("initial", "crash-ready"), ("recovery", "close-ready")):
            for name in ("viewer-report.json", "action.json", "action-result.json"):
                (root / name).unlink(missing_ok=True)
            atomic(root / "config.json", {"root": str(root), "phase": phase})
            log = (root / f"native-{phase}.log").open("wb"); streams.append(log)
            app = subprocess.Popen([str(exe), "--native-gui-test", str(root / "config.json")], cwd=exe.parent, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            report.setdefault("nativePids", []).append(app.pid)
            controls = LinuxControls(root, app.pid, [portal.pid for portal in portals]) if sys.platform == "linux" else None
            deadline, latest, observed = time.monotonic() + 900, None, {}
            while time.monotonic() < deadline:
                if controls:
                    controls.advance()
                result = load(root / "action-result.json")
                if result:
                    observed[result["id"]] = result
                latest = load(root / "viewer-report.json") or latest
                if latest and latest.get("status") == "failed":
                    raise AssertionError(latest.get("error"))
                if latest and latest.get("status") == goal:
                    if phase == "initial":
                        assert health(latest["url"]), "Owned backend not healthy before crash."
                        terminate(app)  # Real abrupt exit, with the actual autosave retained.
                        break
                    if app.poll() is not None:
                        assert app.returncode == 0, f"Normal native close exited {app.returncode}"
                        break
                if app.poll() is not None:
                    raise AssertionError(f"Native app exited early ({app.returncode}); see {log.name}")
                time.sleep(0.1)
            else:
                raise TimeoutError(f"Native GUI {phase} exceeded 15 minutes; see {root}")
            report["checks"].extend(latest["checks"])
            report["nativeControls"].extend(observed.values())
            atomic(root / f"viewer-{phase}.json", latest)
            assert not latest["pageErrors"], latest["pageErrors"]
            assert all(item["ok"] for item in latest["checks"]), latest["checks"]
            deadline = time.monotonic() + 15
            while health(latest["url"]) and time.monotonic() < deadline:
                time.sleep(0.2)
            assert not health(latest["url"]), "Owned backend survived native process shutdown."
        assert len(report["checks"]) == 12, "Every case must run without skips."
        assert not (data / "recovery/autosave.json").exists(), "Confirmed normal close left recoverable unsaved work."
        assert digest(fixture) == report["fixtureSha256"], "The original fixture changed."
        assert any(event["action"]["kind"] == "open" for result in report["nativeControls"] for event in result["events"]), "No native Open control evidence."
        assert any(event["action"]["kind"] == "save" for result in report["nativeControls"] for event in result["events"]), "No native Save control evidence."
        report["checks"][-1]["evidence"].update({"normalExit": 0, "backendStopped": True, "recoveryCleared": True, "fixtureUnchanged": True})
        report["ok"] = True
    except Exception as error:
        report["error"] = repr(error)
        latest = load(root / "viewer-report.json")
        if latest:
            report["failureViewer"] = latest
        raise
    finally:
        terminate(app)
        for portal in portals:
            terminate(portal)
        for stream in streams:
            stream.close()
        atomic(root / "report.json", report)
        print(json.dumps({"ok": report["ok"], "checks": len(report["checks"]), "report": str(root / "report.json")}), flush=True)


if __name__ == "__main__":
    main()
