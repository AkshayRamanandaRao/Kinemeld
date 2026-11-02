"""Deck provenance hashes the retained file, including platform newline bytes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import models
import solver


class DeckProvenanceTests(unittest.TestCase):
    def test_retained_deck_hash_includes_windows_newlines(self):
        original_write = Path.write_text

        def write(path, text, *args, **kwargs):
            if path.name == "model.mbd":
                return path.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
            return original_write(path, text, *args, **kwargs)

        def execute(argv, directory, **kwargs):
            (directory / "solver.log").write_text("Owned unit fixture\n")
            return {"exitCode": 0}

        samples = [models.sample("mass-spring", time, (.1, 0, 0), 0) for time in (0, .1)]
        with tempfile.TemporaryDirectory() as temporary, patch.object(solver, "RUNS", Path(temporary)), patch.object(solver, "status", return_value={"available": True}), patch.object(solver, "configuration", return_value={"mode": "native", "executable": "owned-fixture"}), patch.object(solver, "execute", side_effect=execute), patch.object(solver, "parse_output", return_value=samples), patch.object(Path, "write_text", new=write):
            result, code = solver.run(models.EXAMPLES[1]["model"])
            self.assertEqual(code, 200)
            contents = (Path(temporary) / result["runId"] / "model.mbd").read_bytes()
            self.assertIn(b"\r\n", contents)
            self.assertEqual(result["deckSha256"], hashlib.sha256(contents).hexdigest())


if __name__ == "__main__":
    unittest.main()
