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
import runpy
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
    for attempt in range(20):
        try:
            temp.replace(path)
            return
        except PermissionError:
            if sys.platform != "win32" or attempt == 19:
                raise
            time.sleep(0.01)  # The host may still hold the previous JSON open on Windows.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LinuxControls:
    """AT-SPI buttons/fields, constrained to this private desktop's owned processes."""
    def __init__(self, root, app_pid, portal_pids):
        import pyatspi
        from gi.repository import Atspi, GLib
        Atspi.set_timeout(1000, 1000)
        self.api, self.root, self.app_pid = pyatspi, root, app_pid
        self.groups = {app_pid, *portal_pids}
        self.current, self.index, self.stage, self.since = None, 0, 0, 0
        self.events = []
        self.native_error = GLib.Error

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
                # RFD blocks the app's GTK thread while its separate portal is modal.
                if pid != self.app_pid and self.owned(pid):
                    for window in app:
                        if window.getState().contains(self.api.STATE_SHOWING):
                            result.append((pid, window))
            except Exception:
                continue
        return result

    @staticmethod
    def label(item):
        return (item.name or "").replace("_", "").replace("&", "").strip().lower()

    def buttons(self, window, enabled=True):
        return [item for item in self.walk(window) if item.getRole() == self.api.ROLE_PUSH_BUTTON and (not enabled or item.getState().contains(self.api.STATE_ENABLED) or item.getState().contains(self.api.STATE_SENSITIVE))]

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
        if not name and len(candidates) == 1:
            return candidates[0]  # GTK's portal can expose an empty AT-SPI name.
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
        try:
            self._advance()
        except self.native_error:
            pass  # A closing portal/Zenity window invalidates its AT-SPI objects; retry within the deadline.

    def _advance(self):
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
        if action["kind"] == "close":
            xid = self.xid(self.app_pid, "Kinemeld")
            self.events.append({"action": action, "pid": self.app_pid, "window": "Kinemeld", "xid": xid})
            self.next()
            subprocess.run(["wmctrl", "-ic", hex(int(xid))], check=True)
            return
        for pid, window in self.windows():
            nodes = list(self.walk(window))
            buttons = self.buttons(window)
            names = {self.label(item) for item in self.buttons(window, enabled=False)}
            is_file = any(item.getRole() == self.api.ROLE_FILE_CHOOSER for item in nodes)
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
            opening = bool({"open", "select"} & names)
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
                subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+l"], check=True)
                self.stage, self.since = 1, time.monotonic()
                return
            if time.monotonic() - self.since < 0.4:
                return
            if self.stage == 2:
                button = next((item for item in buttons if self.label(item) in ("open", "select", "save")), None)
                if button:
                    self.next(); self.press(button)
                return
            entries = [item for item in self.walk(window) if item.getRole() in (self.api.ROLE_TEXT, self.api.ROLE_ENTRY) and item.getState().contains(self.api.STATE_EDITABLE) and item.getState().contains(self.api.STATE_FOCUSED)]
            if not entries:
                continue
            entries[0].queryEditableText().setTextContents(action["path"])
            self.stage, self.since = 2, time.monotonic()
            return

    def next(self):
        self.index += 1
        self.stage, self.since = 0, time.monotonic()
        self.result()


class WindowsControls:
    """Reuse the existing PID-scoped Win32 picker driver without requiring WebView2 CDP."""
    def __init__(self, root, app_pid):
        self.root, self.app_pid, self.current, self.index, self.events = root, app_pid, None, 0, []
        self.pending = None

    def call(self, command, *args):
        helper = Path(__file__).with_name("native-dialog-controls.py")
        result = subprocess.run([os.environ.get("MBDYN_STUDIO_PYTHON", sys.executable), str(helper), "--pid", str(self.app_pid), command, *args], capture_output=True, text=True, timeout=25)
        if result.returncode:
            raise RuntimeError(f"Win32 {command}: {result.stdout or result.stderr}")
        value = json.loads(result.stdout)
        assert value["ok"], value
        return value

    def advance(self):
        plan = load(self.root / "action.json")
        if not plan:
            return
        if plan["id"] != self.current:
            self.plan, self.current, self.index, self.events = plan, plan["id"], 0, []
            self.pending = None
        if self.index >= len(self.plan["actions"]):
            return
        if self.pending:
            pending = self.pending
            windows = self.call("list")["windows"]
            visible = any(window["hwnd"] == pending["evidence"]["window"]["hwnd"] for window in windows)
            overwrite = pending["action"]["kind"] == "save" and any("Confirm Save As" in window["text"] for window in windows)
            if not visible or overwrite:
                self.finish(pending["action"], pending["evidence"])
                self.pending = None
                return
            elapsed = time.monotonic() - pending["since"]
            if elapsed > 15:
                raise RuntimeError(f"Native action did not dismiss its dialog: {pending}; windows={windows}")
            if pending["action"]["kind"] in ("open", "save") and elapsed > pending["retries"] + 1 and pending["retries"] < 2:
                pending["evidence"] = self.call("file", "--title", pending["title"], "--path", str(Path(pending["action"]["path"])))
                pending["retries"] += 1
            return
        action = self.plan["actions"][self.index]
        kind = action["kind"]
        if kind == "close":
            evidence = self.call("close")
        else:
            title = "^Open$" if kind == "open" or action.get("dialog") == "open" else "^Save As$"
            if kind == "button":
                title = "Confirm Save As" if action["text"] == "refuse-overwrite" else "^Unsaved project$"
            evidence = self.call("wait", "--title", title)
            self.call("screenshot", "--title", title, "--out", str(self.root / f"native-{self.current}-{self.index}.png"))
            if kind in ("open", "save"):
                evidence = self.call("file", "--title", title, "--path", str(Path(action["path"])))
            elif kind == "cancel":
                evidence = self.call("cancel", "--title", title)
            else:
                button = "No" if action["text"] == "refuse-overwrite" else action["text"]
                evidence = self.call("button", "--title", title, "--text", f"^{button}$")
        if kind != "close":
            self.pending = {"action": action, "evidence": evidence, "title": title, "since": time.monotonic(), "retries": 0}
            return
        self.finish(action, evidence)

    def finish(self, action, evidence):
        self.events.append({"action": action, "pid": self.app_pid, "control": evidence})
        self.index += 1
        atomic(self.root / "action-result.json", {"id": self.current, "done": self.index >= len(self.plan["actions"]), "events": self.events})

    def terminate(self, process):
        children = self.call("children")["children"]
        process.kill(); process.wait(timeout=10)
        remaining = self.call("children")["children"]
        for child in remaining:
            if any(before["pid"] == child["pid"] for before in children):
                try:
                    self.call("terminate-child", "--child-pid", str(child["pid"]))
                except RuntimeError:
                    if any(item["pid"] == child["pid"] for item in self.call("children")["children"]):
                        raise


def health(url):
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def terminate(process):
    if process and sys.platform == "darwin":
        process.terminate_owned()
        return
    if process and process.poll() is None:
        if sys.platform == "win32":
            WindowsControls(Path.cwd(), process.pid).terminate(process)
            return
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path)
    parser.add_argument("--solver-config", required=True, type=Path)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assert sys.platform in ("linux", "darwin", "win32"), "Unsupported native platform."
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
            for name in ("viewer-report.json", "action.json", "action-result.json", "mac-driver.json"):
                (root / name).unlink(missing_ok=True)
            atomic(root / "config.json", {"root": str(root), "phase": phase})
            log = (root / f"native-{phase}.log").open("wb"); streams.append(log)
            if sys.platform == "darwin":
                MacApplication = runpy.run_path(str(Path(__file__).with_name("native-dialog-macos.py")))["MacApplication"]
                app = MacApplication(exe, root / "config.json", environment, log, report.get("nativePids", []))
                report.setdefault("launchServicesPids", []).append(app.launcher.pid)
            else:
                app = subprocess.Popen([str(exe), "--native-gui-test", str(root / "config.json")], cwd=exe.parent, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                report.setdefault("nativePids", []).append(app.pid)
            controls = LinuxControls(root, app.pid, [portal.pid for portal in portals]) if sys.platform == "linux" else WindowsControls(root, app.pid) if sys.platform == "win32" else None
            deadline, latest, observed = time.monotonic() + 900, None, {}
            action_id, action_since, progress, close_since = None, time.monotonic(), None, None
            while time.monotonic() < deadline:
                if sys.platform == "darwin":
                    app.poll()
                    if app.native_pid and app.native_pid not in report.setdefault("nativePids", []):
                        report["nativePids"].append(app.native_pid)
                if controls:
                    controls.advance()
                result = load(root / "action-result.json")
                if result:
                    observed[result["id"]] = result
                    assert not result.get("error"), result.get("error")
                plan = load(root / "action.json")
                if plan and plan["id"] != action_id:
                    action_id, action_since = plan["id"], time.monotonic()
                if plan and (not result or result["id"] != action_id or not result.get("done")):
                    assert time.monotonic() - action_since < 50, f"Native driver did not complete action {plan}; see {root}"
                latest = load(root / "viewer-report.json") or latest
                assert latest or time.monotonic() < deadline - 790, f"Viewer test initialization did not report within 110 seconds; see {root}"
                marker = (len(latest["checks"]), latest["status"]) if latest else None
                if marker != progress:
                    print(json.dumps({"phase": phase, "progress": marker, "output": str(root)}), flush=True)
                    progress = marker
                if latest and latest.get("status") == "failed":
                    raise AssertionError(latest.get("error"))
                if latest and latest.get("status") == goal:
                    if phase == "initial":
                        assert health(latest["url"]), "Owned backend not healthy before crash."
                        terminate(app)  # Real abrupt exit, with the actual autosave retained.
                        break
                    if app.poll() is not None:
                        assert app.returncode == 0, f"Normal native close exited {app.returncode}"
                        if sys.platform == "darwin":
                            report["nativeExitEvent"] = app.exit_event
                        break
                    close_since = close_since or time.monotonic()
                    assert time.monotonic() - close_since < 20, "Confirmed native close did not exit within 20 seconds."
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
        if app and sys.platform == "darwin":
            app.diagnostics()
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
