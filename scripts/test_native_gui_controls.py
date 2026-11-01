"""Native-control inventory regressions that do not require a running desktop."""
from pathlib import Path
import json
import runpy
import subprocess
import tempfile
import unittest
from unittest.mock import patch


class NativeControlTests(unittest.TestCase):
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
