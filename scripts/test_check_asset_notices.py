"""Notice-integrity failures must stop packaging, including new unreviewed assets."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from check_asset_notices import verify


class AssetNoticeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for folder in ("notices", "frontend/vendor", "frontend/fonts", "examples/open-source"):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        self.asset = self.root / "frontend/vendor/example.js"
        self.notice = self.root / "frontend/vendor/LICENSE.txt"
        self.asset.write_bytes(b"// example\n")
        self.notice.write_bytes(b"MIT license notice\n")
        hashes = lambda data: {"lf": hashlib.sha256(data).hexdigest(), "crlf": hashlib.sha256(data.replace(b"\n", b"\r\n")).hexdigest()}
        entry = lambda path: {"path": str(path.relative_to(self.root)).replace("\\", "/"), "sha256": hashes(path.read_bytes()), "source": 0, "sourcePath": path.name, "upstreamSha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.manifest = {"format": "kinemeld-asset-notices/1", "components": [{"id": "example", "license": "MIT", "version": "1", "sources": [{"url": "https://example.com/source-1.tar.gz", "sha256": "1" * 64}], "files": [entry(self.asset)], "notices": [entry(self.notice)]}]}
        self.write_manifest()

    def write_manifest(self):
        (self.root / "notices/assets.json").write_text(json.dumps(self.manifest), encoding="utf8")

    def test_valid_package_and_only_declared_line_ending_conversion(self):
        self.assertTrue(verify(self.root)["ok"])
        self.asset.write_bytes(self.asset.read_bytes().replace(b"\n", b"\r\n"))
        self.assertTrue(verify(self.root)["ok"])
        self.asset.write_bytes(b"// changed\r\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify(self.root)

    def test_missing_notice_and_notice_tamper_fail(self):
        self.notice.unlink()
        with self.assertRaises(FileNotFoundError):
            verify(self.root)
        self.notice.write_bytes(b"replacement notice\n")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            verify(self.root)

    def test_unreviewed_asset_is_not_silently_bundled(self):
        (self.root / "frontend/vendor/new-library.js").write_bytes(b"new dependency")
        with self.assertRaisesRegex(ValueError, "lack pinned"):
            verify(self.root)

    def test_source_differences_need_an_explicit_modification_record(self):
        self.manifest["components"][0]["files"][0]["upstreamSha256"] = "2" * 64
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Unexplained upstream"):
            verify(self.root)
        self.manifest["components"][0]["files"][0]["modifications"] = "Reviewed comment change."
        self.write_manifest()
        self.assertTrue(verify(self.root)["ok"])

    def test_unbounded_paths_and_unproven_sources_fail(self):
        original = copy.deepcopy(self.manifest)
        self.manifest["components"][0]["notices"][0]["path"] = "../outside.txt"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Unsafe asset path"):
            verify(self.root)
        self.manifest = original
        self.manifest["components"][0]["sources"][0]["sha256"] = "unknown"
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Invalid source"):
            verify(self.root)


if __name__ == "__main__":
    unittest.main()
