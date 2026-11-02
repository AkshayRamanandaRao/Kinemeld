"""Native-control inventory regressions that do not require a running desktop."""
from pathlib import Path
import json
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch


class NativeControlTests(unittest.TestCase):
    def test_armed_action_waits_for_dialog_and_acknowledges_actual_dismissal(self):
        controls_type = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-platform.py"))["WindowsControls"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "action.json").write_text(json.dumps({"id": 1, "actions": [{"kind": "cancel", "dialog": "save"}]}))
            controls = controls_type(root, 1234)
            with patch.object(controls, "call", return_value={"windows": []}) as call:
                controls.advance()
            call.assert_called_once_with("list")
            self.assertFalse((root / "action-result.json").exists())
            window = {"hwnd": 456, "class": "#32770", "text": "Save As"}
            with patch.object(controls, "call", side_effect=[{"windows": [window]}, {}, {"window": window}]):
                controls.advance()
            self.assertFalse((root / "action-result.json").exists())
            with patch.object(controls, "call", return_value={"windows": []}):
                controls.advance()
            result = json.loads((root / "action-result.json").read_text())
            self.assertTrue(result["done"])
            self.assertEqual(result["events"][0]["control"]["window"]["hwnd"], 456)

    def test_windows_cleanup_stops_owned_tree_without_control_helper(self):
        module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-platform.py"))
        process = Mock(pid=1234)
        process.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory, patch.object(module["sys"], "platform", "win32"), \
                patch.object(module["WindowsControls"], "call", side_effect=AssertionError("Control helper must not be needed for cleanup")), \
                patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0, "owned tree stopped", "")) as run:
            module["terminate"](process, Path(directory))
            evidence = json.loads((Path(directory) / "win32-forced-stop.json").read_text())
            self.assertEqual(evidence, {"pid": 1234, "stdout": "owned tree stopped", "stderr": ""})
        run.assert_called_once_with(["taskkill", "/PID", "1234", "/T", "/F"], capture_output=True, text=True, check=True, timeout=15)
        process.wait.assert_called_once_with(timeout=10)

    def test_exited_process_is_never_targeted_by_pid(self):
        module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-platform.py"))
        process = Mock(pid=1234)
        process.poll.return_value = 0
        with patch.object(module["sys"], "platform", "win32"), patch("subprocess.run") as run:
            module["terminate"](process, Path("owned-evidence"))
        run.assert_not_called()

    def test_xctest_write_scope_requires_marked_matching_data_root(self):
        suite = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-xctest.py"))["MacXCTest"]
        with tempfile.TemporaryDirectory(prefix="native-platform-") as directory:
            root = Path(directory)
            with self.assertRaisesRegex(AssertionError, "marked temporary root"):
                suite(root, root, root / "app", {"MBDYN_STUDIO_DATA_DIR": str(root / "user-data")})
            (root / ".kinemeld-native-gui-test").touch()
            with self.assertRaisesRegex(AssertionError, "same isolated data root"):
                suite(root, root, root / "app", {"MBDYN_STUDIO_DATA_DIR": str(root / "other-data")})

    def test_closed_accessible_child_preserves_remaining_controls(self):
        controls_type = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-platform.py"))["LinuxControls"]
        controls = controls_type.__new__(controls_type)
        button = []
        window = [None, button]
        observed = list(controls.walk(window))
        self.assertEqual(len(observed), 2)
        self.assertIs(observed[0], window)
        self.assertIs(observed[1], button)
        self.assertEqual(list(controls.walk(None)), [])

    def test_native_helper_timeout_retains_byte_stderr(self):
        controls_type = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tests" / "native-dialog-platform.py"))["WindowsControls"]
        with tempfile.TemporaryDirectory() as directory:
            controls = controls_type(Path(directory), 1234)
            error = subprocess.TimeoutExpired("owned helper", 25, output=b"partial output", stderr=b"native stack")
            with patch("subprocess.run", side_effect=error), self.assertRaisesRegex(RuntimeError, "retained helper diagnostics"):
                controls.call("file", "--path", "chosen.mbdyn-studio")
            evidence = json.loads((Path(directory) / "win32-helper-failure.json").read_text())
            self.assertEqual(evidence["stderr"], "native stack")
            self.assertEqual(evidence["stdout"], "partial output")
            self.assertEqual(evidence["args"], ["--path", "chosen.mbdyn-studio"])
