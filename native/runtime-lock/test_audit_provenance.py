"""Offline byte-comparison checks using synthetic ZIP and wheel artifacts."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile

import audit_provenance as audit


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.artifacts=self.root/'artifacts';self.artifacts.mkdir();self.runtime=self.root/'python';self.runtime.mkdir()
        self.archive=self.artifacts/'python-3.12.10-embed-amd64.zip';self.wheel=self.artifacts/'fixture-1-py3-none-any.whl'
        self.python={'python.exe':b'python','python312.dll':b'dll','python312.zip':b'lib','python312._pth':b'original'}
        self.payload={'fixture.pyd':b'extension','fixture-1.dist-info/METADATA':b'fixture','fixture-1.dist-info/RECORD':b'original',
                      'fixture-1.data/data/share/man/help':b'help'}
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,data in self.python.items():z.writestr(name,data)
        with zipfile.ZipFile(self.wheel,'w') as z:
            for name,data in self.payload.items():z.writestr(name,data)
        for name,data in self.python.items():(self.runtime/name).write_bytes(data)
        (self.runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../../backend\n')
        self.site=self.runtime/'Lib/site-packages';self.site.mkdir(parents=True)
        for name,data in [('fixture.pyd',b'extension'),('fixture-1.dist-info/METADATA',b'fixture'),('share/man/help',b'help'),('fixture-1.dist-info/RECORD',b'generated')]:
            p=self.site/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.lock={'format':'mbdyn-python-wheel-lock/1','pythonArtifact':{'filename':self.archive.name,'sha256':digest(self.archive),'source':'fixture','sbom':'fixture'},'packages':{'fixture':{'filename':self.wheel.name,'sha256':digest(self.wheel)}}}
    def tearDown(self):self.tmp.cleanup()
    def run_audit(self):return audit.audit(self.runtime,self.artifacts,self.lock)
    def test_matches_payload_but_reports_generated_metadata(self):
        result=self.run_audit();self.assertTrue(result['ok']);self.assertEqual(result['matchedFiles'],6)
        self.assertIn('Lib/site-packages/fixture-1.dist-info/RECORD',result['unprovenFiles'])
    def test_refuses_changed_or_missing_payload_and_extra_native_binary(self):
        p=self.site/'fixture.pyd';p.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError,'differs'):self.run_audit()
        p.unlink()
        with self.assertRaisesRegex(ValueError,'missing'):self.run_audit()
        p.write_bytes(b'extension');(self.runtime/'surprise.dll').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'importable files'):self.run_audit()
        (self.runtime/'surprise.dll').unlink();(self.site/'injected.py').write_text('pass')
        with self.assertRaisesRegex(ValueError,'importable files'):self.run_audit()
    def test_rejects_staging_metadata_and_wrong_python_configuration(self):
        p=self.site/'fixture-1.dist-info/direct_url.json';p.write_text('{}')
        with self.assertRaisesRegex(ValueError,'machine-specific'):self.run_audit()
        p.unlink();(self.runtime/'python312._pth').write_text('import site\n')
        with self.assertRaisesRegex(ValueError,'unexpected entries'):self.run_audit()
    def test_rejects_tampered_artifact(self):
        self.wheel.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):self.run_audit()


if __name__=='__main__':unittest.main()
