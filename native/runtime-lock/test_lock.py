"""Verify the recorded Windows CPython wheel closure offline."""
import importlib.util
import json
from pathlib import Path
import re
import unittest
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent


@unittest.skipUnless(importlib.util.find_spec('packaging'),'packaging is needed to verify requirement markers')
class RuntimeLockTests(unittest.TestCase):
    def test_hash_lock_and_target_dependency_closure(self):
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        from packaging.version import Version
        lock=json.loads((ROOT/'windows-cp312.json').read_text(encoding='utf8'))
        self.assertEqual(lock['format'],'mbdyn-python-wheel-lock/1');self.assertEqual(lock['licenseReview'],'not completed')
        self.assertEqual(lock['pythonArtifact']['sha256'],'4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3')
        self.assertEqual(lock['pythonArtifact']['sbom'],'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json')
        packages=lock['packages'];self.assertEqual(len(packages),14)
        environment=default_environment();environment.update(python_version='3.12',python_full_version='3.12.10',sys_platform='win32',os_name='nt',platform_system='Windows',platform_machine='AMD64',implementation_name='cpython',platform_python_implementation='CPython',extra='')
        lines=(ROOT/'requirements-windows-cp312.txt').read_text(encoding='utf8').splitlines()
        for name,item in packages.items():
            self.assertEqual(item['source'],f"https://pypi.org/pypi/{name}/{item['version']}/json")
            self.assertEqual(urlparse(item['url']).hostname,'files.pythonhosted.org')
            self.assertTrue(item['url'].endswith('/'+item['filename']))
            self.assertTrue(re.fullmatch('[0-9a-f]{64}',item['sha256']))
            self.assertTrue(item['filename'].endswith(('-cp312-cp312-win_amd64.whl','-py3-none-any.whl','-py2.py3-none-any.whl')))
            self.assertIn(f"{name}=={item['version']} --hash=sha256:{item['sha256']}",lines)
            for text in item['requires']:
                requirement=Requirement(text)
                if requirement.marker and not requirement.marker.evaluate(environment):continue
                dep=canonicalize_name(requirement.name);self.assertIn(dep,packages,f'{name}: {text}')
                self.assertTrue(requirement.specifier.contains(Version(packages[dep]['version']),prereleases=True),f'{name}: {text}')

if __name__=='__main__':unittest.main()
