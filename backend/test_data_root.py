"""Resource/data separation, non-destructive legacy fallback and real local HTTP."""
import hashlib
import importlib.util
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import build_opener, ProxyHandler, Request
import solver

RESOURCE = Path(__file__).resolve().parents[1]

class DataRootTests(unittest.TestCase):
    def test_read_only_resources_independent_data_and_legacy_fallback(self):
        with tempfile.TemporaryDirectory(prefix='mbdyn-data-root-') as folder:
            base=Path(folder);resource=base/'read only resources';data=base/'user data';resource.mkdir();data.mkdir()
            for name in ('backend','frontend','examples'):
                shutil.copytree(RESOURCE/name,resource/name,ignore=shutil.ignore_patterns('vendor' if name=='backend' else '__no_such_dir__','__pycache__','evidence','*.pyc','solver.json','agent.json'))
            legacy_config=resource/'backend'/'solver.json';legacy_agent=resource/'backend'/'agent.json'
            config=solver.configuration() or {'mode':'native','executable':str(base/'missing-solver')}
            legacy_config.write_text(json.dumps(config),encoding='utf8');legacy_agent.write_text('{"endpoint":"http://127.0.0.1:11435"}',encoding='utf8')
            run_id='a'*32;legacy=resource/'runs'/run_id;legacy.mkdir(parents=True);(legacy/'solver.log').write_text('original log',encoding='utf8')
            (resource/'runs'/'tour-preference.json').write_text('{"enabled":false}',encoding='utf8')
            def snapshot():return {str(p.relative_to(resource)):('file:'+hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else 'directory') for p in resource.rglob('*')}
            before=snapshot()
            for p in resource.rglob('*'):
                if p.is_file():os.chmod(p,stat.S_IREAD)
            env={**os.environ,'MBDYN_STUDIO_DATA_DIR':str(data)}
            env.pop('PYTHONDONTWRITEBYTECODE',None)
            try:
                script='import json,solver,agent; print(json.dumps({"solver":solver.configuration(),"agent":agent.configuration()}))'
                initial=json.loads(subprocess.check_output([sys.executable,'-B','-c',script],cwd=resource/'backend',env=env,text=True))
                self.assertEqual(initial['solver'],config);self.assertEqual(initial['agent'],'http://127.0.0.1:11435')
                self.assertFalse((data/'solver.json').exists());self.assertFalse((data/'agent.json').exists())
                custom={'mode':'native','executable':'user-specific-solver'}
                (data/'solver.json').write_text(json.dumps(custom),encoding='utf8');(data/'agent.json').write_text('{"endpoint":"http://127.0.0.1:11436"}',encoding='utf8')
                selected=json.loads(subprocess.check_output([sys.executable,'-B','-c',script],cwd=resource/'backend',env=env,text=True))
                self.assertEqual(selected['solver'],custom);self.assertEqual(selected['agent'],'http://127.0.0.1:11436')
                (data/'solver.json').write_text('{bad json',encoding='utf8')
                bad=subprocess.run([sys.executable,'-B','-c','import solver;solver.configuration()'],cwd=resource/'backend',env=env,capture_output=True,text=True)
                self.assertNotEqual(bad.returncode,0,'Invalid user settings must not fall back to the legacy file')
                (data/'solver.json').unlink();(data/'agent.json').unlink()
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                process=subprocess.Popen([sys.executable,'-B',str(resource/'backend'/'server.py'),'--port',str(port)],cwd=resource,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                try:
                    opener=build_opener(ProxyHandler({}));url=f'http://127.0.0.1:{port}'
                    for _ in range(100):
                        if process.poll() is not None: self.fail(f'Backend exited: {process.stderr.read().decode(errors="replace")}')
                        try:
                            with opener.open(url+'/api/health',timeout=1) as response:
                                if json.load(response)['application']=='mbdyn-studio':break
                        except OSError:time.sleep(.05)
                    else:self.fail('Backend did not start')
                    with opener.open(url+'/api/tour-preference') as response:self.assertFalse(json.load(response)['enabled'])
                    request=Request(url+'/api/tour-preference',data=b'{"enabled":true}',headers={'Content-Type':'application/json'})
                    with opener.open(request) as response:self.assertTrue(json.load(response)['enabled'])
                    self.assertTrue(json.loads((data/'runs'/'tour-preference.json').read_text())['enabled'])
                    self.assertFalse(json.loads((resource/'runs'/'tour-preference.json').read_text())['enabled'])
                    with opener.open(url+f'/api/runs/{run_id}/solver.log') as response:self.assertEqual(response.read(),b'original log')
                    selected_run=data/'runs'/run_id;selected_run.mkdir();(selected_run/'project.json').write_text('{}')
                    c=http.client.HTTPConnection('127.0.0.1',port);c.request('GET',f'/api/runs/{run_id}/solver.log');response=c.getresponse();self.assertEqual(response.status,404);response.read();c.close()
                    if importlib.util.find_spec('OCP'):
                        step=(resource/'examples'/'step-pendulum'/'pendulum.step').read_bytes()
                        request=Request(url+'/api/step/convert',data=step,headers={'Content-Type':'application/step','X-Step-Filename':'pendulum.step'})
                        with opener.open(request,timeout=120) as response:self.assertTrue(json.load(response)['ok'])
                        request=Request(url+'/api/step/mass',data=step,headers={'Content-Type':'application/step','X-Step-Density':'1000','X-Step-Part':'part-1'})
                        with opener.open(request,timeout=120) as response:self.assertGreater(json.load(response)['mass'],0)
                        primitive={'shape':'brick','dimensions':{'x':.1,'y':.2,'z':.3},'pose':{'x':0,'z':0,'angleDeg':0}}
                        request=Request(url+'/api/step/primitive',data=json.dumps(primitive).encode(),headers={'Content-Type':'application/json'})
                        with opener.open(request,timeout=120) as response:self.assertIn(b'ISO-10303-21;',response.read()[:1024])
                    if solver.status()['available']:
                        with opener.open(url+'/api/examples') as response:model=json.load(response)['examples'][0]['model']
                        request=Request(url+'/api/run',data=json.dumps({'model':model}).encode(),headers={'Content-Type':'application/json'})
                        with opener.open(request,timeout=120) as response:result=json.load(response)
                        self.assertTrue(result['ok'],result);self.assertTrue((data/'runs'/result['runId']/'summary.json').is_file())
                        self.assertFalse((resource/'runs'/result['runId']).exists())
                finally:
                    process.terminate();process.wait(timeout=10);process.stderr.close()
                self.assertEqual(snapshot(),before,'The application modified its immutable resource tree')
            finally:
                for p in resource.rglob('*'):
                    if p.is_file():os.chmod(p,stat.S_IREAD|stat.S_IWRITE)

    def test_rejects_relative_data_root(self):
        env={**os.environ,'MBDYN_STUDIO_DATA_DIR':'relative','PYTHONDONTWRITEBYTECODE':'1'}
        result=subprocess.run([sys.executable,'-c','import app_paths'],cwd=RESOURCE/'backend',env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0);self.assertIn('absolute writable directory',result.stderr)

if __name__=='__main__':unittest.main()
