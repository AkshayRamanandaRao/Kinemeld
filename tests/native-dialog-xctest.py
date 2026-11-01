"""Build and supervise a standard XCTest UI runner for the existing packaged app."""
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess


class MacXCTest:
    def __init__(self, repo, root, executable, environment):
        self.repo, self.root, self.executable = Path(repo), Path(root), Path(executable)
        self.environment = environment.copy()
        self.derived = self.repo / "build/native-macos-ui-tests"
        self.project = self.repo / "tests/native-macos/NativeDialogs.xcodeproj"
        self.command = ["/usr/bin/xcodebuild", "-project", str(self.project), "-scheme", "NativeDialogs",
                        "-destination", "platform=macOS", "-derivedDataPath", str(self.derived),
                        "-parallel-testing-enabled", "NO", "CODE_SIGN_IDENTITY=-", "CODE_SIGN_STYLE=Manual", "DEVELOPMENT_TEAM="]
        self.process, self.log, self.app, self.phase = None, None, None, None
        self.exits = []
        with (self.executable.parents[2] / "Contents/Info.plist").open("rb") as stream:
            self.bundle_id = plistlib.load(stream)["CFBundleIdentifier"]
        with (self.root / "xctest-build.log").open("wb") as output:
            subprocess.run(["/usr/bin/xcodebuild", "-version"], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=10)
            subprocess.run([*self.command, "build-for-testing"], cwd=self.repo, env=self.environment,
                           stdout=output, stderr=subprocess.STDOUT, check=True, timeout=180)

    def for_phase(self, app, phase):
        assert self.process is None, "The previous XCTest phase has not finished."
        self.app, self.phase = app, phase
        return self

    def advance(self):
        if self.process is None and self.app.native_pid:
            environment = self.environment.copy()
            for name, value in {"ROOT": self.root, "PHASE": self.phase, "PID": self.app.native_pid,
                                "EXECUTABLE": self.executable, "BUNDLE_ID": self.bundle_id}.items():
                environment["TEST_RUNNER_KINEMELD_GUI_" + name] = str(value)
            self.log = (self.root / f"xctest-{self.phase}.log").open("wb")
            self.process = subprocess.Popen([*self.command, "-resultBundlePath", str(self.root / f"xctest-{self.phase}.xcresult"),
                                             "-only-testing:NativeDialogs/NativeDialogTests/testNativeDialogs", "test-without-building"],
                                            cwd=self.repo, env=environment, stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)
        if self.process is not None:
            code = self.process.poll()
            assert code is None or code == 0, f"XCTest UI runner exited {code}; see xctest-{self.phase}.log and its xcresult."
            if code == 0:
                assert self._report().get("status") == "complete", "XCTest exited before completing its native phase."

    def _report(self):
        path = self.root / f"xcui-{self.phase}.json"
        return json.loads(path.read_text()) if path.is_file() else {}

    def finish(self):
        assert self.process is not None, "The XCTest UI runner never started."
        code = self.process.wait(timeout=40)
        assert code == 0, f"XCTest UI runner exited {code}; see its log and xcresult."
        result = self._report()
        assert result == {"status": "complete", "phase": self.phase, "pid": self.app.native_pid}, result
        self.exits.append({"phase": self.phase, "exit": code, "pid": self.app.native_pid})
        self.log.close(); self.log = None; self.process = None

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
        if self.log:
            self.log.close(); self.log = None
