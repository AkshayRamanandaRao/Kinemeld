"""Launch the real .app through LaunchServices and measure the native PID's exit status."""
import json
import ctypes
import os
from pathlib import Path
import plistlib
import select
import signal
import subprocess
import time


def process_table():
    output = subprocess.run(["/bin/ps", "-ww", "-axo", "pid=,ppid=,command="], capture_output=True, text=True, check=True, timeout=5).stdout
    return {int(parts[0]): {"parent": int(parts[1]), "command": parts[2]} for line in output.splitlines() if len(parts := line.strip().split(None, 2)) == 3}


def descendants(table, parent):
    found = []
    for pid, record in table.items():
        if record["parent"] == parent:
            found.extend(descendants(table, pid))
            found.append(pid)
    return found


class MacApplication:
    # Darwin event.h: valid for children OR processes the caller may signal.
    NOTE_EXITSTATUS = getattr(select, "KQ_NOTE_EXITSTATUS", 0x04000000)

    def __init__(self, executable, config, environment, log, previous_pids=()):
        self.executable, self.config = Path(executable).resolve(), Path(config).resolve()
        self.root = self.config.parent
        self.phase = json.loads(self.config.read_text())["phase"]
        self.previous_pids = set(previous_pids)
        self.native_pid, self.returncode, self.exit_event, self.queue = None, None, None, None
        self.libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.libproc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.libproc.proc_pidpath.restype = ctypes.c_int
        bundle = self.executable.parents[2]
        assert bundle.suffix == ".app" and (bundle / "Contents/Info.plist").is_file(), "LaunchServices needs the actual packaged .app."
        with (bundle / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        signing = subprocess.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(bundle)], capture_output=True, text=True, timeout=10)
        metadata = {"bundle": str(bundle), "identifier": info.get("CFBundleIdentifier"), "version": info.get("CFBundleVersion"), "signingExit": signing.returncode, "signingDiagnostics": signing.stderr}
        usage = subprocess.run(["/usr/bin/open", "-h"], capture_output=True, text=True, timeout=5)
        metadata["openUsage"] = usage.stdout + usage.stderr
        (self.root / f"mac-launch-{self.phase}.json").write_text(json.dumps(metadata, indent=2))
        assert signing.returncode == 0, "The actual packaged .app must pass codesign --verify --deep --strict before native GUI qualification."
        assert "--env" in metadata["openUsage"], "The native GUI launcher requires open --env on this supported runner."
        data = Path(environment["MBDYN_STUDIO_DATA_DIR"])
        python = Path(environment["MBDYN_STUDIO_PYTHON"])
        assert data.is_absolute() and data.resolve() == self.root / "user-data", "LaunchServices data must stay in this test root."
        assert python.is_absolute() and python.is_file(), "LaunchServices needs the explicit CAD-enabled Python executable."
        command = ["/usr/bin/open", "-n", "-W", "--env", f"MBDYN_STUDIO_DATA_DIR={data}", "--env", f"MBDYN_STUDIO_PYTHON={python}", str(bundle), "--args", "--native-gui-test", str(self.config)]
        self.launcher = subprocess.Popen(command, env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    @property
    def pid(self):
        return self.native_pid or self.launcher.pid

    def owned(self, pid, table):
        record = table.get(pid)
        if not record or "--native-gui-test" not in record["command"] or str(self.config) not in record["command"] or pid in self.previous_pids or pid == os.getpid():
            return False
        path = ctypes.create_string_buffer(4096)
        return bool(self.libproc.proc_pidpath(pid, path, len(path)) > 0 and Path(os.fsdecode(path.value)).resolve() == self.executable)

    def bind(self, pid):
        assert self.owned(pid, process_table()), "Refusing to monitor an unowned native process."
        queue = select.kqueue()
        event = select.kevent(pid, filter=select.KQ_FILTER_PROC, flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT, fflags=select.KQ_NOTE_EXIT | self.NOTE_EXITSTATUS)
        queue.control([event], 0, 0)
        self.queue, self.native_pid = queue, pid

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        if self.native_pid is None:
            try:
                marker = json.loads((self.root / "mac-driver.json").read_text())
            except (OSError, ValueError):
                marker = None
            if marker:
                assert Path(marker["root"]).resolve() == self.root and marker["phase"] == self.phase, "Stale native GUI marker."
                self.bind(int(marker["pid"]))
            elif self.launcher.poll() is not None:
                raise RuntimeError(f"LaunchServices exited {self.launcher.returncode} before the native application initialized.")
        if self.queue:
            events = self.queue.control(None, 1, 0)
            if events:
                event = events[0]
                assert event.ident == self.native_pid and event.fflags & self.NOTE_EXITSTATUS, "The kernel did not provide the native exit status."
                self.exit_event = {"pid": self.native_pid, "flags": event.fflags, "status": event.data}
                self.returncode = os.waitstatus_to_exitcode(event.data & 0xFFFF)
        return self.returncode

    def wait(self, timeout):
        deadline = time.monotonic() + timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("The owned native application did not exit.")
            time.sleep(0.05)
        try:
            self.launcher.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.launcher.kill(); self.launcher.wait(timeout=2)
        return self.returncode

    def terminate_owned(self):
        if self.returncode is None:
            table = process_table()
            if self.native_pid is None:
                matches = [pid for pid in table if self.owned(pid, table)]
                assert len(matches) <= 1, "Ambiguous native GUI ownership."
                if matches:
                    self.bind(matches[0])
            if self.native_pid and self.native_pid in table:
                assert self.owned(self.native_pid, table), "Native process ownership changed."
                # Stop deepest descendants first, checking each current parent and command.
                for pid in descendants(table, self.native_pid):
                    current = process_table().get(pid)
                    if current == table[pid]:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                if self.owned(self.native_pid, process_table()):
                    os.kill(self.native_pid, signal.SIGKILL)
                self.wait(10)
        if self.launcher.poll() is None:
            self.launcher.kill(); self.launcher.wait(timeout=2)
        if self.queue:
            self.queue.close(); self.queue = None

    def diagnostics(self):
        predicate = f'processID == {self.native_pid or 0} OR process == "openAndSavePanelService" OR process == "OpenAndSavePanelService"'
        with (self.root / f"mac-system-{self.phase}.log").open("w") as output:
            try:
                subprocess.run(["/usr/bin/log", "show", "--last", "3m", "--style", "compact", "--predicate", predicate], stdout=output, stderr=subprocess.STDOUT, timeout=10)
            except subprocess.TimeoutExpired:
                output.write("\nScoped unified-log collection timed out.\n")
