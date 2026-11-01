"""Native-control inventory regressions that do not require a running desktop."""
from pathlib import Path
import runpy
import unittest


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
