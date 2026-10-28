"""Boundaries for offline private-runtime preparation; fixtures contain no real binaries."""
import copy
import base64
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import prepare_runtime as prepare
import verify_runtime


def digest(data): return hashlib.sha256(data).hexdigest()


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.artifacts=self.root/'artifacts';self.artifacts.mkdir();self.parent=self.root/'runtime';self.parent.mkdir()
        self.archive=self.artifacts/'python-3.12.10-embed-amd64.zip';self.wheel=self.artifacts/'fixture-1-py3-none-any.whl'
        with zipfile.ZipFile(self.archive,'w') as z:
            for name in ('python.exe','python312.dll','python312.zip','python312._pth'):z.writestr(name,b'fixture')
        self.wheel.write_bytes(b'locked fixture wheel')
        self.lock={'format':'mbdyn-python-wheel-lock/1','pythonArtifact':{'filename':self.archive.name,'sha256':verify_runtime.sha256(self.archive),'source':'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip','sbom':'fixture'},'packages':{'fixture':{'filename':self.wheel.name,'sha256':digest(b'locked fixture wheel')}}}
    def tearDown(self):self.tmp.cleanup()
    def install(self,wheels,target):
        self.assertEqual(wheels,[self.wheel]);(target/'fixture.py').write_text('value = 1\n')
    def test_builds_new_draft_with_no_legal_claim_and_refuses_overwrite(self):
        dest=self.parent/'python';report=prepare.prepare(self.artifacts,dest,self.lock,self.install)
        self.assertEqual(report['redistributionStatus'],'not-established');self.assertEqual(report['noticeReview'],'required')
        self.assertEqual((dest/'Lib/site-packages/fixture.py').read_text(),'value = 1\n')
        self.assertEqual((dest/'python312._pth').read_text().splitlines(),['python312.zip','.','Lib/site-packages','../../backend'])
        manifest=json.loads((dest/'runtime-manifest.json').read_text());self.assertEqual(manifest['notices']['fixture'],[])
        with self.assertRaisesRegex(ValueError,'notice file'):verify_runtime.validate(dest,self.artifacts,self.lock)
        with self.assertRaisesRegex(ValueError,'already exists'):prepare.prepare(self.artifacts,dest,self.lock,self.install)
    def test_refuses_changed_python_or_wheel_before_destination_creation(self):
        for artifact in (self.archive,self.wheel):
            with self.subTest(artifact=artifact.name):
                saved=artifact.read_bytes();artifact.write_bytes(saved+b'tampered')
                with self.assertRaisesRegex(ValueError,'hash mismatch'):prepare.prepare(self.artifacts,self.parent/'python',self.lock,self.install)
                self.assertFalse((self.parent/'python').exists());artifact.write_bytes(saved)
    def test_rejects_unsafe_archive_and_cleans_staging(self):
        for name in ('../outside','C:/outside','bad\\path'):
            with self.subTest(name=name):
                with zipfile.ZipFile(self.archive,'w') as z:
                    z.writestr(name,b'bad')
                changed=copy.deepcopy(self.lock);changed['pythonArtifact']['sha256']=verify_runtime.sha256(self.archive)
                with self.assertRaises(ValueError):prepare.prepare(self.artifacts,self.parent/'python',changed,self.install)
                self.assertFalse((self.parent/'python').exists());self.assertEqual(list(self.parent.iterdir()),[])
    def test_installer_failure_leaves_no_destination_or_staging(self):
        def fail(_wheels,_target):raise ValueError('fixture installation failed')
        with self.assertRaisesRegex(ValueError,'fixture installation failed'):prepare.prepare(self.artifacts,self.parent/'python',self.lock,fail)
        self.assertEqual(list(self.parent.iterdir()),[])
    def test_rechecks_artifact_after_install(self):
        def change(_wheels,target):self.wheel.write_bytes(b'changed');(target/'fixture.py').write_text('x')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):prepare.prepare(self.artifacts,self.parent/'python',self.lock,change)
        self.assertEqual(list(self.parent.iterdir()),[])

    def test_removes_host_url_and_removed_entrypoints_from_record(self):
        site=self.root/'site';info=site/'fixture-1.dist-info';info.mkdir(parents=True)
        (info/'direct_url.json').write_text('{"url":"file:///private/path.whl"}',encoding='utf8')
        rows=[['fixture.py','sha256=example','5'],['fixture-1.dist-info/direct_url.json','sha256=secret','44'],
              ['../../bin/fixture.exe','sha256=gone','2'],['fixture-1.dist-info/RECORD','','']]
        with (info/'RECORD').open('w',encoding='utf8',newline='') as stream:csv.writer(stream).writerows(rows)
        prepare.sanitize_installer_metadata(site)
        self.assertFalse((info/'direct_url.json').exists())
        with (info/'RECORD').open(encoding='utf8',newline='') as stream:self.assertEqual(list(csv.reader(stream)),[rows[0],rows[-1]])

    def test_metadata_sanitization_rejects_unexpected_traversal(self):
        site=self.root/'site';info=site/'fixture-1.dist-info';info.mkdir(parents=True)
        (info/'direct_url.json').write_text('{}',encoding='utf8')
        with (info/'RECORD').open('w',encoding='utf8',newline='') as stream:csv.writer(stream).writerows([['fixture-1.dist-info/direct_url.json','',''],['../elsewhere','','']])
        with self.assertRaises(ValueError):prepare.sanitize_installer_metadata(site)
        self.assertTrue((info/'direct_url.json').exists())

    def test_rewrites_relocated_share_data_only_when_hash_matches(self):
        site=self.root/'site';info=site/'fixture-1.dist-info';info.mkdir(parents=True)
        share=site/'share/man/file';share.parent.mkdir(parents=True);share.write_bytes(b'data')
        (info/'direct_url.json').write_text('{}',encoding='utf8')
        sha=base64.urlsafe_b64encode(hashlib.sha256(b'data').digest()).decode().rstrip('=')
        record=info/'RECORD'
        with record.open('w',encoding='utf8',newline='') as stream:csv.writer(stream).writerows([['fixture-1.dist-info/direct_url.json','',''],['../../share/man/file','sha256='+sha,'4']])
        prepare.sanitize_installer_metadata(site)
        with record.open(encoding='utf8',newline='') as stream:self.assertEqual(list(csv.reader(stream)),[['share/man/file','sha256='+sha,'4']])


if __name__=='__main__':unittest.main()
