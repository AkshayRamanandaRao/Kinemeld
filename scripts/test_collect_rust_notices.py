"""Negative checks for checksum, attribution, source and toolchain drift."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("rust_notices",Path(__file__).with_name("collect_rust_notices.py"))
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)
ROOT = Path(__file__).resolve().parents[1]


class RustNoticeChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)/"notices"
        shutil.copytree(ROOT/"notices/rust",self.output)

    def manifest(self):
        return json.loads((self.output/"manifest.json").read_text(encoding="utf8"))

    def alter_manifest(self, value):
        (self.output/"manifest.json").write_text(json.dumps(value),encoding="utf8")

    def test_offline_bundle_covers_all_release_targets(self):
        for target in audit.TARGETS:
            manifest = audit.check_bundle(self.output,target,ROOT)
            self.assertTrue(manifest["targets"][target]["components"])

    def test_lf_and_crlf_source_checkouts_match(self):
        root = Path(self.temp.name)/"checkout"
        for name in audit.INPUTS:
            file = root/name
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_bytes(audit.canonical_text((ROOT/name).read_bytes()).replace(b"\n",b"\r\n"))
        audit.check_bundle(self.output,source_root=root)
        (root/"rust-toolchain.toml").write_text('[toolchain]\nchannel="other"\n',encoding="utf8")
        with self.assertRaisesRegex(ValueError,"stale"):
            audit.check_bundle(self.output,source_root=root)

    def test_altered_notice_bytes_are_rejected(self):
        (self.output/"THIRD_PARTY_RUST.txt").write_bytes(b"not the upstream notices")
        with self.assertRaisesRegex(ValueError,"checksum"):
            audit.check_bundle(self.output)

    def test_missing_mpl_source_is_rejected(self):
        manifest = self.manifest()
        mpl = next(p for p in manifest["components"] if p["licenseSelected"]=="MPL-2.0")
        (self.output/mpl["sourceArchive"]).unlink()
        with self.assertRaisesRegex(ValueError,"inventory"):
            audit.check_bundle(self.output)

    def test_unknown_license_and_missing_target_component_are_rejected(self):
        manifest = self.manifest()
        original = copy.deepcopy(manifest)
        manifest["components"][0]["licenseDeclared"] = "LicenseRef-Unreviewed"
        self.alter_manifest(manifest)
        with self.assertRaisesRegex(ValueError,"Unreviewed"):
            audit.check_bundle(self.output)
        original["components"].pop()
        self.alter_manifest(original)
        with self.assertRaisesRegex(ValueError,"Incomplete"):
            audit.check_bundle(self.output)

    def test_omitted_attribution_is_rejected_even_if_aggregate_hash_is_updated(self):
        manifest = self.manifest()
        file = self.output/"THIRD_PARTY_RUST.txt"
        data = bytearray(file.read_bytes())
        notice = manifest["components"][0]["notices"][0]
        data[notice["aggregateOffset"]] ^= 1
        file.write_bytes(data)
        manifest["files"]["THIRD_PARTY_RUST.txt"] = audit.digest(data)
        self.alter_manifest(manifest)
        with self.assertRaisesRegex(ValueError,"attribution"):
            audit.check_bundle(self.output)

    def test_unsafe_archive_paths_and_checksum_drift_are_rejected(self):
        file = Path(self.temp.name)/"test.crate"
        with tarfile.open(file,"w:gz") as archive:
            member = tarfile.TarInfo("example-1.0/../escape")
            member.size=1
            archive.addfile(member,io.BytesIO(b"x"))
        with self.assertRaisesRegex(ValueError,"checksum"):
            audit.crate_contents(file,"0"*64,"example","1.0")
        with self.assertRaisesRegex(ValueError,"Unsafe"):
            audit.crate_contents(file,audit.digest(file.read_bytes()),"example","1.0")

    def test_compiler_commit_is_checked_without_requiring_same_host(self):
        manifest = self.manifest()
        version = manifest["toolchain"]["rustcVerbose"]
        with patch.object(audit.subprocess,"check_output",return_value=version.replace("x86_64-pc-windows-msvc","x86_64-unknown-linux-gnu")):
            audit.check_compiler(manifest)
        with patch.object(audit.subprocess,"check_output",return_value=version.replace("commit-hash: ","commit-hash: altered-")):
            with self.assertRaisesRegex(ValueError,"compiler identity"):
                audit.check_compiler(manifest)


if __name__ == "__main__":
    unittest.main()
