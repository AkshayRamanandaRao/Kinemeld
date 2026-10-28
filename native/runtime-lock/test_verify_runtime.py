"""Offline fixture checks: no actual Python or third-party binaries are bundled."""
import copy
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
import tempfile
import unittest

import verify_runtime as check
import draft_manifest


def digest(data): return hashlib.sha256(data).hexdigest()


class RuntimeInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.runtime=self.root/'runtime';self.artifacts=self.root/'artifacts';self.runtime.mkdir();self.artifacts.mkdir()
        self.files={'python.exe':b'not a real executable','python312.dll':b'not a real dll','python312.zip':b'not a real standard library','python312._pth':b'python312.zip\n.\nLib/site-packages\n../../backend\n','notices/all.txt':b'Test notice only; no legal review.'}
        for name,data in self.files.items():
            target=self.runtime/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        self.wheel='fixture-1-py3-none-any.whl';self.archive='python-3.12.10-embed-amd64.zip';(self.artifacts/self.wheel).write_bytes(b'test wheel');(self.artifacts/self.archive).write_bytes(b'test archive')
        self.lock={'format':'mbdyn-python-wheel-lock/1','pythonArtifact':{'filename':self.archive,'sha256':digest(b'test archive'),'source':'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip','sbom':'fixture'},'packages':{'fixture':{'filename':self.wheel,'sha256':digest(b'test wheel')}}}
        notice=['notices/all.txt'];self.manifest={'format':check.FORMAT,'target':'windows-x86_64-cpython-312','pythonArtifact':{'filename':self.archive,'sha256':digest(b'test archive'),'source':'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'},'wheels':{'fixture':{'filename':self.wheel,'sha256':digest(b'test wheel')}},'files':{name:digest(data) for name,data in self.files.items()},'notices':{'python':notice,'fixture':notice},'nativeNotices':{'python.exe':notice,'python312.dll':notice}}
        self.save()
    def tearDown(self):self.tmp.cleanup()
    def save(self): (self.runtime/'runtime-manifest.json').write_text(json.dumps(self.manifest),encoding='utf8')
    def verify(self):return check.validate(self.runtime,self.artifacts,self.lock)
    def test_consistent_inventory_is_not_legal_or_execution_certification(self):
        result=self.verify();self.assertEqual(result['redistributionStatus'],'not-established');self.assertEqual(result['wheelCount'],1)
    def test_changed_unlisted_missing_or_misnamed_files_fail(self):
        for mode in ('changed','extra','missing','case'):
            with self.subTest(mode=mode):
                original=copy.deepcopy(self.manifest)
                if mode=='changed':(self.runtime/'python.exe').write_bytes(b'changed')
                if mode=='extra':(self.runtime/'unexpected').write_bytes(b'x')
                if mode=='missing':(self.runtime/'python312.dll').unlink()
                if mode=='case':self.manifest['files']['Python.exe']=self.manifest['files'].pop('python.exe');self.save()
                with self.assertRaises(ValueError):self.verify()
                self.manifest=original
                for name,data in self.files.items():
                    target=self.runtime/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                (self.runtime/'unexpected').unlink(missing_ok=True);self.save()
    def test_artifacts_pth_and_native_notices_are_required(self):
        (self.artifacts/self.wheel).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'artifact hash mismatch'):self.verify()
        (self.artifacts/self.wheel).write_bytes(b'test wheel')
        self.manifest['nativeNotices'].pop('python312.dll');self.save()
        with self.assertRaisesRegex(ValueError,'each packaged'):self.verify()
        self.manifest['nativeNotices']['python312.dll']=['notices/all.txt']
        new=b'python312.zip\n.\n';(self.runtime/'python312._pth').write_bytes(new);self.manifest['files']['python312._pth']=digest(new);self.save()
        with self.assertRaisesRegex(ValueError,'import site is forbidden'):self.verify()
    def test_rejects_import_site_to_prevent_roaming_user_site(self):
        content=b"python312.zip\n.\nLib/site-packages\n../../backend\nimport site\n"
        (self.runtime/"python312._pth").write_bytes(content);self.manifest["files"]["python312._pth"]=digest(content);self.save()
        with self.assertRaisesRegex(ValueError,"import site is forbidden"):self.verify()

    def test_rejects_installer_metadata_that_exposes_build_paths(self):
        name='Lib/site-packages/fixture-1.dist-info/direct_url.json';data=b'{"url":"file:///builder/private/fixture.whl"}'
        path=self.runtime/name;path.parent.mkdir(parents=True);path.write_bytes(data)
        self.manifest['files'][name]=digest(data);self.save()
        with self.assertRaisesRegex(ValueError,'machine-specific'):self.verify()

    def test_rejects_traversal_and_duplicate_json_keys(self):
        with self.assertRaises(ValueError):check.safe_name('../outside')
        with self.assertRaises(ValueError):check.safe_name('dir\\evil')
        duplicate=self.root/'duplicate.json';duplicate.write_text('{"format":1,"format":2}',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):check.read_json(duplicate)
    def test_packager_includes_only_verified_synthetic_runtime(self):
        pwsh=shutil.which('pwsh')
        if not pwsh:self.skipTest('PowerShell 7 is required for the package boundary')
        project=self.root/'fixture project';native=project/'native';tool=native/'runtime-lock'
        for folder in ('backend','frontend','examples','docs'):
            directory=project/folder;directory.mkdir(parents=True);(directory/'fixture.txt').write_text('test',encoding='utf8')
        tool.mkdir(parents=True);(native/'MBDynStudio.exe').write_bytes(b'synthetic desktop, never executed')
        for name in ('LICENSE','THIRD_PARTY_NOTICES.md','README.md','Start MBDyn Studio Desktop.cmd'):(project/name).write_text('fixture',encoding='utf8')
        (native/'README.md').write_text('fixture',encoding='utf8')
        source=Path(__file__).resolve().parent
        shutil.copyfile(source.parent/'package-windows.ps1',native/'package-windows.ps1')
        for name in ('README.md','requirements-windows-cp312.txt','resolve.py','verify_runtime.py','draft_manifest.py','prepare_runtime.py','smoke_runtime.py','audit_provenance.py'):shutil.copyfile(source/name,tool/name)
        with zipfile.ZipFile(self.artifacts/self.archive,'w') as archive:
            for name in ('python.exe','python312.dll','python312.zip','python312._pth'):archive.writestr(name,self.files[name])
        with zipfile.ZipFile(self.artifacts/self.wheel,'w') as archive:archive.writestr('fixture.py',b'synthetic wheel payload')
        payload='Lib/site-packages/fixture.py';target=self.runtime/payload;target.parent.mkdir(parents=True);target.write_bytes(b'synthetic wheel payload')
        self.manifest['files'][payload]=digest(target.read_bytes())
        self.lock['pythonArtifact']['sha256']=check.sha256(self.artifacts/self.archive)
        self.lock['packages']['fixture']['sha256']=check.sha256(self.artifacts/self.wheel)
        self.manifest['pythonArtifact']['sha256']=self.lock['pythonArtifact']['sha256']
        self.manifest['wheels']['fixture']['sha256']=self.lock['packages']['fixture']['sha256'];self.save()
        (tool/'windows-cp312.json').write_text(json.dumps(self.lock),encoding='utf8')
        plain=subprocess.run([pwsh,'-NoProfile','-File',str(native/'package-windows.ps1')],capture_output=True,text=True,timeout=90)
        self.assertEqual(plain.returncode,0,plain.stdout+plain.stderr)
        with zipfile.ZipFile(native/'dist'/'MBDynStudio-Windows-local.zip') as bundle:
            manifest=json.loads(bundle.read('package-manifest.json'))
            self.assertFalse(manifest['privateRuntimeIncluded']);self.assertIn('native/runtime-lock/README.md',bundle.namelist())
        run=subprocess.run([pwsh,'-NoProfile','-File',str(native/'package-windows.ps1'),'-PrivateRuntimeDirectory',str(self.runtime),'-PrivateRuntimeArtifacts',str(self.artifacts)],capture_output=True,text=True,timeout=90)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        archive=native/'dist'/'MBDynStudio-Windows-private-runtime-test.zip'
        with zipfile.ZipFile(archive) as bundle:
            manifest=json.loads(bundle.read('package-manifest.json'))
            self.assertTrue(manifest['privateRuntimeIncluded']);self.assertEqual(manifest['runtimeRedistributionStatus'],'not-established')
            self.assertEqual(manifest['runtimePayloadComparison']['matchedFiles'],4)
            self.assertEqual(bundle.read('runtime/python/python.exe'),b'not a real executable')
            self.assertIn('runtime/python/runtime-manifest.json',bundle.namelist())
            self.assertIn('native/runtime-lock/audit_provenance.py',bundle.namelist())
            self.assertNotIn(self.wheel,bundle.namelist())
        target.write_bytes(b'modified payload');self.manifest['files'][payload]=digest(target.read_bytes());self.save()
        fail=subprocess.run([pwsh,'-NoProfile','-File',str(native/'package-windows.ps1'),'-PrivateRuntimeDirectory',str(self.runtime),'-PrivateRuntimeArtifacts',str(self.artifacts)],capture_output=True,text=True,timeout=90)
        self.assertNotEqual(fail.returncode,0)
        self.assertIn('payload', (fail.stdout+fail.stderr).lower())

    def test_draft_requires_explicit_notice_mappings(self):
        result=draft_manifest.draft(self.runtime,self.artifacts/self.archive,self.lock)
        self.assertEqual(result["notices"]["fixture"],[])
        self.assertEqual(result["nativeNotices"]["python.exe"],[])
        self.manifest=result;self.save()
        with self.assertRaisesRegex(ValueError,"notice file"):self.verify()

    def test_manifest_rejects_unpinned_python_archive(self):
        self.manifest["pythonArtifact"]["sha256"]=digest(b"substitute archive");self.save()
        with self.assertRaisesRegex(ValueError,"pinned provenance"):self.verify()

    def test_manifest_rejects_case_collisions(self):
        self.manifest['files']['Python.exe']=self.manifest['files']['python.exe'];self.save()
        with self.assertRaisesRegex(ValueError,'duplicate'):self.verify()

if __name__=='__main__':unittest.main()
