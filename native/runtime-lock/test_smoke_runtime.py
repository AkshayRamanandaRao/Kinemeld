"""Smoke harness boundary tests; fake executables are never launched."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import smoke_runtime


class SmokeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name).resolve();self.app=root/'app';self.data=root/'data';self.app.mkdir();self.data.mkdir();(self.app/'backend').mkdir();(self.app/'backend'/'solver.py').write_text('fixture');(self.app/'runtime'/'python').mkdir(parents=True);self.interpreter=self.app/'runtime'/'python'/'python.exe';self.interpreter.write_bytes(b'fixture')
        self.report={'python':str(self.interpreter),'noSite':1,'childNoSite':1,'stepTriangles':12,'stepMassKg':3.,'solverSource':'MBDyn','solverRunId':'a'*32}
    def tearDown(self):self.tmp.cleanup()
    def run_fixture(self,report=None):
        response=SimpleNamespace(returncode=0,stdout=json.dumps(report if report is not None else self.report),stderr='')
        with patch.object(smoke_runtime.sys,'platform','win32'),patch.dict(smoke_runtime.os.environ,{'SystemRoot':'C:\\Windows','PATH':'C:\\untrusted','PYTHONPATH':'C:\\untrusted','MBDYN_STUDIO_PYTHON':'untrusted'}),patch.object(smoke_runtime.subprocess,'run',return_value=response) as run:
            result=smoke_runtime.smoke(self.app,self.data);args=run.call_args
            self.assertEqual(args.kwargs['env']['PYTHONPATH'],str(self.data/'should-not-be-imported'))
            self.assertNotIn('MBDYN_STUDIO_PYTHON',args.kwargs['env']);self.assertNotIn('untrusted',args.kwargs['env']['PATH'])
            self.assertEqual(args.args[0][0],str(self.interpreter));self.assertEqual(args.args[0][1],'-B')
            return result
    def test_smoke_uses_private_interpreter_and_excludes_ambient_python(self):
        report=self.run_fixture();self.assertTrue(report['ok']);self.assertIn('not established',report['scope'])
    def test_invalid_or_inconsistent_worker_result_never_claims_success(self):
        for field,value in [('noSite',0),('childNoSite',True),('stepTriangles',0),('stepMassKg',float('nan')),('solverSource','preview'),('solverRunId','bad'),('python',str(self.data/'wrong.exe'))]:
            with self.subTest(field=field):
                report=dict(self.report);report[field]=value
                with self.assertRaisesRegex(ValueError,'inconsistent'):self.run_fixture(report)
    def test_existing_runs_and_missing_runtime_are_rejected_before_launch(self):
        (self.data/'runs').mkdir()
        with self.assertRaisesRegex(ValueError,'fresh data'):smoke_runtime.smoke(self.app,self.data)
        (self.data/'runs').rmdir();self.interpreter.unlink()
        with self.assertRaisesRegex(ValueError,'missing'):smoke_runtime.smoke(self.app,self.data)


if __name__=='__main__':unittest.main()
