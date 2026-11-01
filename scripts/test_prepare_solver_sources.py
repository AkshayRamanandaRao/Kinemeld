import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("solver_sources", Path(__file__).with_name("prepare_solver_sources.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class SolverSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.solver, self.sources = self.root / "solver", self.root / "sources"
        (self.solver / "bin").mkdir(parents=True)
        (self.solver / "bin/mbdyn").write_bytes(b"compiled solver fixture")
        self.archive = self.root / "mbdyn-1.7.3.tar.gz"
        self.archive.write_bytes(b"exact corresponding source fixture")
        self.notice = self.root / "copyright.txt"
        self.notice.write_text("Copyright original upstream authors. Permission and all original notices retained.\n")
        self.build = self.root / "build_solver.sh"
        self.build.write_text("#!/bin/sh\n# Exact build arguments retained from this build runner.\n")
        self.metadata = self.root / "package-metadata.json"
        self.metadata.write_text('{"sourceVersion":"1.7.3","provider":"upstream-pinned"}\n')
        record = lambda path: {"path": str(path), "sha256": audit.digest(path)}
        self.spec = {"format": "kinemeld-solver-input/1", "platform": "linux", "components": [{
            "name": "mbdyn", "family": "mbdyn", "version": "1.7.3", "sourceVersion": "1.7.3",
            "files": ["bin/mbdyn"], "packageNotice": record(self.notice),
            "sources": [{**record(self.archive), "url": "https://www.mbdyn.org/mbdyn-1.7.3.tar.gz", "sourceVersion": "1.7.3"}],
            "evidence": [record(self.metadata)]}], "buildInputs": [record(self.build)]}
        self.inventory = self.root / "inventory.json"
        self.pin = patch.object(audit, "MBDYN_SHA", audit.digest(self.archive))
        self.pin.start()
        self.addCleanup(self.pin.stop)

    def prepare(self):
        self.inventory.write_text(json.dumps(self.spec), encoding="utf8")
        return audit.prepare(self.solver, self.sources, self.inventory)

    def test_full_inventory_and_source_pair_round_trip(self):
        self.prepare()
        result = audit.verify(self.solver, self.sources)
        self.assertEqual(result["components"][0]["files"][0]["sha256"], audit.digest(self.solver / "bin/mbdyn"))
        self.assertTrue((self.solver / "notices/licenses/GPL-2.0.txt").is_file())
        self.assertEqual((self.sources / "archives/mbdyn-1.7.3.tar.gz").read_bytes(), self.archive.read_bytes())

    def test_extra_runtime_binary_is_not_silently_accepted(self):
        self.prepare()
        (self.solver / "bin/unknown.dll").write_bytes(b"unreviewed dependency")
        with self.assertRaisesRegex(ValueError, "every bundled binary"):
            audit.verify(self.solver, self.sources)

    def test_changed_binary_notice_source_and_build_inputs_are_rejected(self):
        result = self.prepare()
        paths = [self.solver / "bin/mbdyn", self.solver / result["components"][0]["notices"][0]["path"],
                 self.sources / "archives/mbdyn-1.7.3.tar.gz", self.sources / "build/build_solver.sh"]
        for path in paths:
            with self.subTest(path=path):
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaisesRegex(ValueError, "changed"):
                    audit.verify(self.solver, self.sources)
                path.write_bytes(original)

    def test_bad_input_digest_and_source_version_fail(self):
        self.spec["components"][0]["sources"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Input digest mismatch"):
            self.prepare()
        self.spec["components"][0]["sources"][0]["sha256"] = audit.digest(self.archive)
        self.spec["components"][0]["sources"][0]["sourceVersion"] = "different version"
        with self.assertRaisesRegex(ValueError, "Source version"):
            self.prepare()

    def test_missing_package_copyright_and_build_evidence_fail(self):
        for key in ("packageNotice", "evidence"):
            with self.subTest(key=key):
                saved = self.spec["components"][0][key]
                self.spec["components"][0][key] = [] if key == "evidence" else {"path": "missing", "sha256": "0" * 64}
                with self.assertRaises((ValueError, OSError)):
                    self.prepare()
                self.spec["components"][0][key] = saved
        self.spec["buildInputs"] = []
        with self.assertRaisesRegex(ValueError, "build/packaging"):
            self.prepare()

    def test_unreviewed_family_and_binary_mapping_fail(self):
        self.spec["components"][0]["family"] = "unknown"
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            self.prepare()
        self.spec["components"][0]["family"] = "mbdyn"
        self.spec["components"][0]["files"].append("bin/mbdyn")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.prepare()

    def test_unsafe_relative_paths_are_rejected(self):
        for name in ("../escape", "/absolute", "bin/../../escape", "bin\\escape"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.child(self.solver, name)

    def test_mismatched_source_manifest_fails(self):
        self.prepare()
        (self.sources / "source-manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "manifests differ"):
            audit.verify(self.solver, self.sources)

    def test_changed_reviewed_license_text_is_rejected(self):
        import shutil
        target = self.root / "license-texts"
        shutil.copytree(audit.ROOT / "notices/solver", target)
        audit.verify_license_texts(target)
        (target / "GPL-2.0.txt").write_text("changed license text")
        with self.assertRaisesRegex(ValueError, "reviewed provenance"):
            audit.verify_license_texts(target)


if __name__ == "__main__":
    unittest.main()
