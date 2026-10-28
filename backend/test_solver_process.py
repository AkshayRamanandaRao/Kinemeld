"""Real child-process failures retain useful output and distinguish time limits."""
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest

import solver


class SolverProcessTests(unittest.TestCase):
    def test_exit_classification_preserves_partial_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for code in (124,137,2):
                result = solver.execute([sys.executable,"-c",f"import sys; print('partial solver observation', flush=True); sys.exit({code})"],directory)
                self.assertEqual(result["exitCode"],code)
                self.assertIn("partial solver observation",(directory/"solver.log").read_text())
                if code == 124:
                    self.assertIn("180-second solver time limit",result["error"])
                    self.assertIn("does not establish a convergence failure",result["error"])
                elif code == 137:
                    self.assertIn("external SIGKILL",result["error"])
                else:
                    self.assertIn("exit 2",result["error"])
                    self.assertNotIn("time limit",result["error"])

    @unittest.skipUnless(sys.platform == "win32", "Windows gated launcher diagnostics")
    def test_missing_executable_is_reported_in_retained_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = solver.execute([str(directory / "missing-solver.exe")], directory)
            self.assertEqual(result["exitCode"], 126)
            self.assertIn("could not be launched", result["error"])
            self.assertIn("Could not start the configured solver", (directory / "solver.log").read_text())

    def test_timeout_stops_descendants_but_not_an_unrelated_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            descendant_marker = directory / "descendant.txt"
            unrelated_marker = directory / "unrelated.txt"
            def delayed_write(path):
                return f"import pathlib,time;time.sleep(3);pathlib.Path({str(path)!r}).write_text('finished')"
            unrelated = subprocess.Popen([sys.executable, "-c", delayed_write(unrelated_marker)],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                child = delayed_write(descendant_marker)
                parent = ("import subprocess,sys,time; "
                          f"subprocess.Popen([sys.executable,'-c',{child!r}], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                          "print('descendant started',flush=True); time.sleep(10)")
                result = solver.execute([sys.executable, "-c", parent], directory, timeout=1.5)
                self.assertIn("process deadline", result["error"])
                self.assertIn("descendant started", (directory / "solver.log").read_text())
                self.assertEqual(unrelated.wait(timeout=5), 0)
                time.sleep(.3)
                self.assertTrue(unrelated_marker.exists(), "The unrelated process should continue")
                self.assertFalse(descendant_marker.exists(), "A solver descendant survived its deadline")
            finally:
                if unrelated.poll() is None:
                    unrelated.kill()
                    unrelated.wait()

    def test_outer_deadline_stops_child_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = solver.execute([sys.executable,"-c","import time; print('started',flush=True); time.sleep(10)"],directory,timeout=.2)
            self.assertIn("process deadline",result["error"])
            self.assertNotEqual(result.get("exitCode"),0)
            self.assertTrue((directory/"solver.log").is_file())


if __name__ == "__main__":
    unittest.main()
