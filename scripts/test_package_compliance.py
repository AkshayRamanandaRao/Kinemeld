"""Archive boundaries and corresponding-source gates, without launching a GUI."""
from pathlib import Path
import plistlib
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import check_package
import package_release


class PackageComplianceTests(unittest.TestCase):
    def test_macos_bundle_versions_use_numeric_semantic_core(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(package_release, "copy_resources"):
            root = Path(temporary)
            binary = root / "host"
            binary.write_bytes(b"owned host fixture")
            for version in ("1.2.3", "1.2.3-rc.1", "1.2.3+audit.1"):
                stage = root / version
                package_release.layout("macos", binary, version, None, stage)
                with (stage / "Kinemeld.app/Contents/Info.plist").open("rb") as stream:
                    info = plistlib.load(stream)
                self.assertEqual(info["CFBundleVersion"], "1.2.3")
                self.assertEqual(info["CFBundleShortVersionString"], "1.2.3")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.app = self.stage / "Kinemeld.app/Contents/Resources/app"
        self.app.mkdir(parents=True)
        host = self.stage / "Kinemeld.app/Contents/MacOS/kinemeld"
        host.parent.mkdir(parents=True)
        host.write_bytes(b"desktop host fixture")
        (self.app / "LICENSE").write_text("test license fixture")
        for name in ("verify_assets", "verify_rust", "verify_license_texts"):
            mock = patch.object(check_package, name)
            mock.start()
            self.addCleanup(mock.stop)

    def archive(self, sources=None):
        package_release.manifest(self.app, self.stage, "1.2.1", "macos", bool(sources), sources)
        return package_release.archive(self.stage, self.root, "fixture", "macos")

    def verify(self, archive):
        return check_package.verify_files(archive, self.root / "unpacked", "1.2.1")

    def test_host_outside_resources_is_verified(self):
        root, manifest = self.verify(self.archive())
        self.assertEqual(root.name, "app")
        self.assertIn("Kinemeld.app/Contents/MacOS/kinemeld", manifest["archiveFiles"])

    def test_unlisted_file_is_rejected(self):
        archive = self.archive()
        with zipfile.ZipFile(archive, "a") as bundle:
            bundle.writestr("Kinemeld.app/Contents/MacOS/unreviewed.dylib", b"extra")
        with self.assertRaisesRegex(SystemExit, "unlisted"):
            self.verify(archive)

    def test_changed_host_is_rejected(self):
        self.archive()
        (self.stage / "Kinemeld.app/Contents/MacOS/kinemeld").write_bytes(b"changed host")
        archive = package_release.archive(self.stage, self.root, "fixture", "macos")
        with self.assertRaisesRegex(SystemExit, "archive file"):
            self.verify(archive)

    def test_missing_or_changed_source_companion_is_rejected(self):
        archive = self.archive({"file": "sources.tar.gz", "sha256": "0" * 64})
        with self.assertRaisesRegex(SystemExit, "corresponding-source companion"):
            self.verify(archive)
        (self.root / "sources.tar.gz").write_bytes(b"incorrect source")
        with self.assertRaisesRegex(SystemExit, "corresponding-source companion"):
            self.verify(archive)

    def test_matching_source_companion_reaches_solver_inventory_check(self):
        sources = self.root / "source-input"
        sources.mkdir()
        (sources / "source-manifest.json").write_text("{}")
        companion = package_release.source_archive(sources, self.root, "fixture")
        archive = self.archive(companion)
        with patch.object(check_package, "verify_solver", return_value={"platform": "macos"}) as verify:
            self.verify(archive)
            self.assertTrue((verify.call_args.args[1] / "source-manifest.json").is_file())

    def test_unsafe_and_linked_archive_entries_are_rejected(self):
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape", b"bad")
        with self.assertRaisesRegex(SystemExit, "unsafe archive path"):
            check_package.unpack(archive, self.root / "unpacked")
        archive = self.root / "linked.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            link = tarfile.TarInfo("link")
            link.type = tarfile.SYMTYPE
            link.linkname = "../escape"
            bundle.addfile(link)
        with self.assertRaisesRegex(SystemExit, "non-regular"):
            check_package.unpack(archive, self.root / "unpacked")

    def test_asset_notice_failure_blocks_archive(self):
        with patch.object(check_package, "verify_assets", side_effect=ValueError("missing asset notice")):
            with self.assertRaisesRegex(ValueError, "missing asset notice"):
                self.verify(self.archive())


if __name__ == "__main__":
    unittest.main()
