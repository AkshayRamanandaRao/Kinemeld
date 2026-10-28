"""Curated-file integrity, native output completeness and local API input boundaries."""

import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server
import source_catalog as catalog


class SourceCatalogTests(unittest.TestCase):
    def test_catalog_integrity_and_id_only_selection(self):
        for entry in catalog.catalog():
            for item in entry["files"]:
                self.assertTrue(catalog.checked_file(item["path"], item["sha256"]).is_file())
        for value in ("../triangle", "/tmp/model.mbd", "does-not-exist", None, {"id": "triangle"}):
            with self.assertRaises(ValueError):
                catalog.resolve_entry(value)
        with self.assertRaises(ValueError):
            catalog.checked_file("../../LICENSE", "0" * 64)
        first = catalog.catalog()[0]["files"][0]
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            catalog.checked_file(first["path"], "0" * 64)
        model = {"kind": "source-example", "sourceExampleId": "srscm"}
        self.assertTrue(catalog.validate_model(model)["valid"])
        self.assertFalse(catalog.validate_model({**model, "simulation": {"duration": 500, "step": 1}})["valid"])
        self.assertFalse(catalog.validate_model({**model, "sourceRevision": "changed"})["valid"])
        self.assertFalse(catalog.validate_model({**model, "sourceHashes": ["0" * 64]})["valid"])
        self.assertIn("Spatial Rigid Slider-crank", catalog.deck_for_model(model)["deck"])

    def test_native_frames_require_matching_time_node_order_and_orientation(self):
        entry = {"simulation": {"duration": .01, "step": .01}, "nodes": [{"id": 10}, {"id": 20}]}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "result.out").write_text("Step 0 0 0 0 0 0 0 1\nStep 1 0.01 0.01 2 0 0 0 1\n")
            (root / "result.log").write_text("structural node: 10 0 0 0 euler123 0 0 0\nstructural node: 20 0 0 0 euler123 0 0 0\n")
            records = "10 0 0 0 0 0 0 0 0 0 0 0 0\n20 1 0 0 0 0 0 0 0 0 0 0 0\n10 0 0 0 0 0 0 0 0 0 0 0 0\n20 1 0.1 0 0 0 0 0 1 0 0 0 0\n"
            (root / "result.mov").write_text(records)
            samples = catalog.parse_output(root, entry)
            self.assertEqual(samples[1]["nodes"][1]["y"], .1)
            for damaged in (records.rsplit("\n", 2)[0], records.replace("20 1", "10 1"), records.replace("0.1", "NaN")):
                (root / "result.mov").write_text(damaged)
                with self.assertRaises(ValueError):
                    catalog.parse_output(root, entry)
            (root / "result.mov").write_text(records)
            missing_end = copy.deepcopy(entry)
            missing_end["simulation"]["duration"] = 1
            with self.assertRaisesRegex(ValueError, "final time"):
                catalog.parse_output(root, missing_end)
            (root / "result.log").write_text("structural node: 10 0 0 0 phi 0 0 0\n")
            with self.assertRaisesRegex(ValueError, "Euler123"):
                catalog.parse_output(root, entry)

    def test_api_lists_catalog_and_rejects_paths_or_extra_fields(self):
        http = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http.server_port}"
        try:
            with urlopen(base + "/api/source-examples") as response:
                self.assertGreaterEqual(len(json.load(response)["examples"]), 3)
            for payload, expected in (({"id": "../../bad"}, 422), ({"id": "triangle", "path": "bad"}, 400), ({"model": {}}, 400)):
                request = Request(base + "/api/source-run", json.dumps(payload).encode(), {"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(request)
                self.assertEqual(caught.exception.code, expected)
        finally:
            http.shutdown()
            http.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
