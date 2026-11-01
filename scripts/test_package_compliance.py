"""Archive boundaries and corresponding-source gates, without launching a GUI."""
from pathlib import Path
import json
import plistlib
import subprocess
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
        seal = self.stage / "Kinemeld.app/Contents/_CodeSignature/CodeResources"
        seal.parent.mkdir(parents=True)
        seal.write_bytes(b"resource signature fixture (not a real code signature)")
        (self.app / "LICENSE").write_text("test license fixture")
        for name in ("verify_assets", "verify_rust", "verify_license_texts"):
            mock = patch.object(check_package, name)
            mock.start()
            self.addCleanup(mock.stop)
        # Fixture signatures are synthetic; actual Apple verification belongs to Mac CI.
        signature = patch.object(check_package.subprocess, "run")
        signature.start()
        self.addCleanup(signature.stop)

    def archive(self, sources=None, legacy=False):
        package_release.manifest(self.app, self.stage, "1.2.1", "macos", bool(sources), sources)
        if legacy:
            envelope = self.stage / "package-manifest.json"
            record = json.loads(envelope.read_text(encoding="utf-8"))
            del record["appRoot"]
            envelope.unlink()
            (self.app / "package-manifest.json").write_text(json.dumps(record), encoding="utf-8")
        return package_release.archive(self.stage, self.root, "fixture", "macos")

    def verify(self, archive):
        return check_package.verify_files(archive, self.root / "unpacked", "1.2.1")

    def test_host_outside_resources_is_verified(self):
        root, manifest = self.verify(self.archive())
        self.assertEqual(root.name, "app")
        self.assertIn("Kinemeld.app/Contents/MacOS/kinemeld", manifest["archiveFiles"])
        self.assertIn("Kinemeld.app/Contents/_CodeSignature/CodeResources", manifest["archiveFiles"])
        self.assertEqual(manifest["appRoot"], package_release.MACOS_APP_ROOT)
        self.assertTrue((root.parents[3] / "package-manifest.json").is_file())
        self.assertFalse((root / "package-manifest.json").exists())

    def test_legacy_internal_mac_manifest_remains_auditable_without_signature_claim(self):
        with patch.object(check_package, "sys") as system, patch.object(check_package.subprocess, "run") as run:
            system.platform = "darwin"
            root, record = self.verify(self.archive(legacy=True))
        self.assertTrue((root / "package-manifest.json").is_file())
        self.assertNotIn("appRoot", record)
        run.assert_not_called()

    def test_outer_mac_manifest_requires_fixed_resource_root(self):
        for value in (None, "../escape", "Kinemeld.app", "Kinemeld.app/Contents/Resources/alternate"):
            with self.subTest(appRoot=value):
                self.archive()
                envelope = self.stage / "package-manifest.json"
                record = json.loads(envelope.read_text(encoding="utf-8"))
                if value is None:
                    del record["appRoot"]
                else:
                    record["appRoot"] = value
                envelope.write_text(json.dumps(record), encoding="utf-8")
                archive = package_release.archive(self.stage, self.root, "fixture", "macos")
                with self.assertRaisesRegex(SystemExit, "fixed"):
                    self.verify(archive)

    def test_outer_manifest_cannot_be_relocated_inside_bundle(self):
        self.archive()
        (self.stage / "package-manifest.json").rename(self.app / "package-manifest.json")
        archive = package_release.archive(self.stage, self.root, "fixture", "macos")
        with self.assertRaisesRegex(SystemExit, "archive-root"):
            self.verify(archive)

    def test_new_mac_package_requires_host_and_resource_seal(self):
        for name in ("MacOS/kinemeld", "_CodeSignature/CodeResources"):
            with self.subTest(missing=name):
                path = self.stage / "Kinemeld.app/Contents" / name
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(SystemExit, "signed host or bundle resource signature"):
                        self.verify(self.archive())
                finally:
                    path.write_bytes(original)

    def test_macos_checker_verifies_new_signature_and_propagates_failure(self):
        with patch.object(check_package, "sys") as system, patch.object(check_package.subprocess, "run") as run:
            system.platform = "darwin"
            self.verify(self.archive())
            run.assert_called_once_with(["/usr/bin/codesign", "--verify", "--deep", "--strict",
                str(self.root / "unpacked/Kinemeld.app")], check=True)
            run.side_effect = subprocess.CalledProcessError(1, "codesign")
            with self.assertRaises(subprocess.CalledProcessError):
                self.verify(self.archive())

    def test_macos_signer_preserves_nested_solver_and_verifies_outer_bundle(self):
        solver = self.app / "solver/bin/mbdyn"
        solver.parent.mkdir(parents=True)
        solver.write_bytes(b"already audited signed solver fixture")
        with patch.object(package_release.subprocess, "run") as run:
            package_release.sign_macos_bundle(self.stage)
        self.assertEqual(run.call_args_list[0].args[0],
            ["/usr/bin/codesign", "--force", "--sign", "-", str(self.stage / "Kinemeld.app")])
        self.assertEqual(run.call_args_list[1].args[0],
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(self.stage / "Kinemeld.app")])
        self.assertTrue(all(call.kwargs == {"check": True} for call in run.call_args_list))
        self.assertEqual(solver.read_bytes(), b"already audited signed solver fixture")

    def test_packager_signs_and_verifies_before_hashing_final_host(self):
        binary = self.root / "unsigned-host"
        binary.write_bytes(b"unsigned fixture")
        arguments = ["package_release.py", "--platform", "macos", "--arch", "arm64", "--binary", str(binary),
            "--version", "1.2.1", "--out", str(self.root / "output")]
        events = []

        def sign(stage):
            events.append("sign")
            self.assertFalse(list(stage.rglob("package-manifest.json")))
            (stage / "Kinemeld.app/Contents/MacOS/kinemeld").write_bytes(b"final signed host fixture")
            signature = stage / "Kinemeld.app/Contents/_CodeSignature/CodeResources"
            signature.parent.mkdir()
            signature.write_bytes(b"final resource seal fixture")

        real_manifest = package_release.manifest
        def inventory(*args):
            events.append("inventory")
            return real_manifest(*args)

        with patch.object(package_release, "copy_resources"), patch.object(package_release, "verify_assets"), \
                patch.object(package_release, "verify_license_texts"), patch.object(package_release, "verify_rust"), \
                patch.object(package_release, "sign_macos_bundle", side_effect=sign), \
                patch.object(package_release, "manifest", side_effect=inventory), patch("sys.argv", arguments):
            package_release.main()
        self.assertEqual(events, ["sign", "inventory"])
        archive = self.root / "output/Kinemeld-1.2.1-macos-arm64.zip"
        root, record = check_package.verify_files(archive, self.root / "final-unpacked", "1.2.1")
        self.assertEqual(check_package.native_executable(root, "macos").read_bytes(), b"final signed host fixture")
        self.assertEqual(record["archiveFiles"]["Kinemeld.app/Contents/MacOS/kinemeld"],
            check_package.sha256(check_package.native_executable(root, "macos")))

    def test_signing_failure_blocks_manifest_and_archive(self):
        binary = self.root / "host"
        binary.write_bytes(b"host fixture")
        arguments = ["package_release.py", "--platform", "macos", "--arch", "arm64", "--binary", str(binary),
            "--version", "1.2.1", "--out", str(self.root / "output")]
        with patch.object(package_release, "copy_resources"), patch.object(package_release, "verify_assets"), \
                patch.object(package_release, "verify_license_texts"), patch.object(package_release, "verify_rust"), \
                patch.object(package_release, "sign_macos_bundle", side_effect=subprocess.CalledProcessError(1, "codesign")), \
                patch.object(package_release, "manifest") as inventory, patch.object(package_release, "archive") as archive, \
                patch("sys.argv", arguments):
            with self.assertRaises(subprocess.CalledProcessError):
                package_release.main()
        inventory.assert_not_called()
        archive.assert_not_called()

    def test_post_signing_solver_audit_failure_blocks_manifest_and_archive(self):
        binary = self.root / "host"
        binary.write_bytes(b"host fixture")
        arguments = ["package_release.py", "--platform", "macos", "--arch", "arm64", "--binary", str(binary),
            "--version", "1.2.1", "--out", str(self.root / "output"), "--solver", str(self.root / "solver"),
            "--solver-sources", str(self.root / "sources")]
        with patch.object(package_release, "copy_resources"), patch.object(package_release, "verify_assets"), \
                patch.object(package_release, "verify_license_texts"), patch.object(package_release, "verify_rust"), \
                patch.object(package_release, "bundle_solver", return_value=True), patch.object(package_release, "source_archive"), \
                patch.object(package_release, "verify_solver", side_effect=[{"platform": "macos"}, {}, ValueError("changed solver")]) as audit, \
                patch.object(package_release, "sign_macos_bundle") as sign, patch.object(package_release, "manifest") as inventory, \
                patch.object(package_release, "archive") as archive, patch("sys.argv", arguments):
            with self.assertRaisesRegex(ValueError, "changed solver"):
                package_release.main()
        self.assertEqual(audit.call_count, 3)
        sign.assert_called_once()
        inventory.assert_not_called()
        archive.assert_not_called()

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

    def test_changed_resource_seal_is_rejected(self):
        self.archive()
        (self.stage / "Kinemeld.app/Contents/_CodeSignature/CodeResources").write_bytes(b"changed seal")
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
