"""Focused Linux source collector boundary tests (portable; no live apt/network required)."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_solver_linux as collector


class LinuxCollectorTests(unittest.TestCase):
    def test_quadmath_license_family_and_unknown_library(self):
        self.assertEqual(collector.family_for("libquadmath.so.0"), "quadmath")
        self.assertEqual(collector.family_for("libgfortran.so.5"), "gcc-runtime")
        self.assertEqual(collector.family_for("liblapack.so.3"), "lapack-blas")
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            collector.family_for("libunknown.so.1")

    def test_exact_source_package_and_all_artifacts_required(self):
        artifacts = {"libfoo_1.dsc": b"source metadata", "libfoo_1.orig.tar.gz": b"source archive"}
        hashes = {name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()}
        stanza = "Package: libfoo\nVersion: 1\nChecksums-Sha256:\n" + "".join(f" {hashes[name]} {len(data)} {name}\n" for name, data in artifacts.items())
        uris = "\n".join(f"'http://archive.ubuntu.com/ubuntu/{name}' {name} {len(data)} SHA256:{hashes[name]}" for name, data in artifacts.items())
        def response(url, **_):
            self.assertTrue(url.startswith("https://"))
            return io.BytesIO(artifacts[url.rsplit("/", 1)[-1]])
        with tempfile.TemporaryDirectory() as directory, patch.object(collector, "run", side_effect=[stanza, uris]), patch.object(collector.urllib.request, "urlopen", side_effect=response):
            records, evidence = collector.source_artifacts("libfoo", "1", Path(directory))
            self.assertEqual(len(records), 2)
            self.assertEqual(len(evidence), 2)
        with tempfile.TemporaryDirectory() as directory, patch.object(collector, "run", side_effect=[stanza, uris.splitlines()[0]]), patch.object(collector.urllib.request, "urlopen", side_effect=response):
            with self.assertRaisesRegex(ValueError, "Incomplete exact source"):
                collector.source_artifacts("libfoo", "1", Path(directory))

    def test_wrong_source_version_and_tampered_download_fail(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collector, "run", return_value="Package: libfoo\nVersion: 2\n"):
            with self.assertRaisesRegex(ValueError, "Exact source index unavailable"):
                collector.source_artifacts("libfoo", "1", Path(directory))
        sha = hashlib.sha256(b"good").hexdigest()
        stanza = f"Package: libfoo\nVersion: 1\nChecksums-Sha256:\n {sha} 4 libfoo_1.dsc\n"
        uri = f"'https://archive.ubuntu.com/libfoo_1.dsc' libfoo_1.dsc 4 SHA256:{sha}"
        with tempfile.TemporaryDirectory() as directory, patch.object(collector, "run", side_effect=[stanza, uri]), patch.object(collector.urllib.request, "urlopen", return_value=io.BytesIO(b"evil")):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                collector.source_artifacts("libfoo", "1", Path(directory))

    def test_missing_build_origin_and_changed_library_fail_before_package_query(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "solver/lib").mkdir(parents=True)
            (root / "solver/lib/libblas.so.3").write_bytes(b"test")
            with self.assertRaisesRegex(ValueError, "build origin"):
                collector.collect(root / "solver", root / "work", {})
            with patch.object(collector, "elf_identity", side_effect=[{"code": "changed"}, {"code": "original"}]):
                with self.assertRaisesRegex(ValueError, "differ from its installed origin"):
                    collector.collect(root / "solver", root / "work", {"lib/libblas.so.3": "/installed/library"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
