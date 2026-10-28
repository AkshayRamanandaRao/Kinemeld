"""Cancellation owns exactly one run and retains its partial process output."""
import copy
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import models
import server
import solver


def wait_for(predicate,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.05)
    raise AssertionError('Timed out waiting for owned process')

class CancelTests(unittest.TestCase):
    def test_before_launch_and_native_descendant_cleanup(self):
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path);control=solver.RunControl();control.cancel()
            result=solver.execute([sys.executable,'-c','print("unexpected")'],folder,control=control)
            self.assertTrue(result['cancelled']);self.assertEqual((folder/'solver.log').read_text(),'')
            control=solver.RunControl();desc=folder/'descendant';other=folder/'unrelated'
            delayed=lambda path:f'import pathlib,time;time.sleep(2);pathlib.Path({str(path)!r}).write_text("done")'
            unrelated=subprocess.Popen([sys.executable,'-c',delayed(other)])
            program=('import subprocess,sys,time; '+f'subprocess.Popen([sys.executable,"-c",{delayed(desc)!r}]); '+ 'print("started",flush=True);time.sleep(20)')
            answer={};thread=threading.Thread(target=lambda:answer.update(solver.execute([sys.executable,'-c',program],folder,timeout=15,control=control)));thread.start()
            try:
                wait_for(lambda:(folder/'solver.log').exists() and 'started' in (folder/'solver.log').read_text(errors='replace'))
                control.cancel();thread.join(10);self.assertFalse(thread.is_alive());self.assertTrue(answer['cancelled']);self.assertIn('started',(folder/'solver.log').read_text())
                self.assertEqual(unrelated.wait(timeout=6),0);time.sleep(.2);self.assertTrue(other.exists());self.assertFalse(desc.exists())
            finally:
                if unrelated.poll() is None:unrelated.kill();unrelated.wait()

    @unittest.skipUnless(os.environ.get('MBDYN_TEST_WSL_CANCEL')=='1','explicit WSL process-tree verification')
    def test_wsl_guest_process_tree_stops_and_unrelated_guest_survives(self):
        config=solver.configuration();self.assertEqual(config['mode'],'wsl')
        with tempfile.TemporaryDirectory() as path:
            folder=Path(path);ctrl=solver.RunControl();answer={}
            guest=('trap "" TERM; echo started; (trap "" TERM; sleep 2; echo survivor > descendant.txt) & '
                   'echo $! > descendant.pid; while :; do sleep 1; done')
            unrelated=subprocess.Popen(['wsl.exe','-d',config['distribution'],'--cd',solver.linux_path(folder),'--exec','/bin/sh','-c','sleep 3; echo okay > unrelated.txt'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            guest_config={**config,'executable':'/bin/sh'}
            argv=solver.command(guest_config,['-c',guest],folder,bounded=True,cancellable=True)
            thread=threading.Thread(target=lambda:answer.update(solver.execute(argv,folder,timeout=20,control=ctrl,wsl=True)));thread.start()
            try:
                wait_for(lambda:(folder/'descendant.pid').exists() and (folder/'solver.log').exists() and 'started' in (folder/'solver.log').read_text(errors='replace'),20)
                ctrl.cancel();thread.join(15);self.assertFalse(thread.is_alive());self.assertTrue(answer.get('cancelled'),str(answer));self.assertIn('started',(folder/'solver.log').read_text(errors='replace'))
                self.assertEqual(unrelated.wait(timeout=10),0);time.sleep(.5);self.assertTrue((folder/'unrelated.txt').exists());self.assertFalse((folder/'descendant.txt').exists())
                pid=int((folder/'descendant.pid').read_text())
                probe=subprocess.run(['wsl.exe','-d',config['distribution'],'--exec','/bin/sh','-c',f'if [ -r /proc/{pid}/stat ]; then cat /proc/{pid}/stat; fi'],capture_output=True,text=True,timeout=10)
                state=probe.stdout.rsplit(')',1)[-1].strip().split()
                self.assertTrue(not state or state[0]=='Z',f'Guest child {pid} still running: {probe.stdout}')
            finally:
                if unrelated.poll() is None:unrelated.kill();unrelated.wait()

    def test_http_token_ownership_cancellation_and_early_race(self):
        web=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);worker=threading.Thread(target=web.serve_forever,daemon=True);worker.start()
        token='1'*32;wrong='2'*32; early='3'*32
        def post(path,payload,headers=None):
            c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=20);c.request('POST',path,json.dumps(payload),{'Content-Type':'application/json',**(headers or {})});r=c.getresponse();result=(r.status,json.loads(r.read()));c.close();return result
        try:
            self.assertEqual(post('/api/run/cancel',{'runToken':'bad'})[0],400)
            self.assertEqual(post('/api/run/cancel',{'runToken':token},{'Origin':'https://example.com'})[0],403)
            with tempfile.TemporaryDirectory() as directory:
                folder=Path(directory)
                def fake_run(model,control=None):
                    outcome=solver.execute([sys.executable,'-c','import time;print("started",flush=True);time.sleep(20)'],folder,timeout=15,control=control)
                    return {'ok':False,**outcome,'runId':'a'*32,'log':(folder/'solver.log').read_text()},409 if outcome.get('cancelled') else 422
                result={}
                with patch.object(server.solver,'run',side_effect=fake_run):
                    task=threading.Thread(target=lambda:result.update(zip(('status','value'),post('/api/run',{'model':copy.deepcopy(models.EXAMPLES[0]['model']),'runToken':token}))));task.start()
                    wait_for(lambda:(folder/'solver.log').exists() and 'started' in (folder/'solver.log').read_text(errors='replace'))
                    self.assertEqual(post('/api/run/cancel',{'runToken':wrong})[0],404)
                    self.assertEqual(post('/api/run/cancel',{'runToken':token})[0],200)
                    task.join(15);self.assertFalse(task.is_alive());self.assertEqual(result['status'],409);self.assertTrue(result['value']['cancelled']);self.assertIn('started',result['value']['log'])
                    self.assertEqual(post('/api/run/cancel',{'runToken':token})[0],409)
                    self.assertEqual(post('/api/run',{'model':copy.deepcopy(models.EXAMPLES[0]['model']),'runToken':token})[0],409)
                    self.assertEqual(post('/api/run/cancel',{'runToken':early})[1]['state'],'pending')
                    status,result=post('/api/run',{'model':copy.deepcopy(models.EXAMPLES[0]['model']),'runToken':early})
                    self.assertEqual(status,409);self.assertTrue(result['cancelled'])
        finally:web.shutdown();web.server_close();worker.join()


    def test_real_run_paths_preserve_downloadable_artifacts_on_cancel(self):
        web=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);worker=threading.Thread(target=web.serve_forever,daemon=True);worker.start()
        def post(path,payload):
            c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=20);c.request('POST',path,json.dumps(payload),{'Content-Type':'application/json'});r=c.getresponse();result=(r.status,json.loads(r.read()));c.close();return result
        def get(path):
            c=http.client.HTTPConnection('127.0.0.1',web.server_port,timeout=20);c.request('GET',path);r=c.getresponse();result=(r.status,r.read());c.close();return result
        try:
            with tempfile.TemporaryDirectory() as directory:
                runs=Path(directory);info={'available':True,'version':'test','mode':'native'}
                slow=[sys.executable,'-c','import time;print("real partial output",flush=True);time.sleep(20)']
                with patch.object(solver,'RUNS',runs),patch.object(solver,'status',return_value=info),patch.object(solver,'configuration',return_value={'mode':'native','executable':sys.executable}),patch.object(solver,'command',return_value=slow):
                    for i,(path,body) in enumerate((('/api/run',{'model':copy.deepcopy(models.EXAMPLES[0]['model'])}),('/api/source-run',{'id':'triangle'}))):
                        token=('4' if i==0 else '5')*32;answer={};task=threading.Thread(target=lambda:answer.update(zip(('status','value'),post(path,{**body,'runToken':token}))));task.start()
                        def current_log():
                            return any('real partial output' in log.read_text(errors='replace') for log in runs.glob('*/solver.log'))
                        wait_for(current_log)
                        self.assertEqual(post('/api/run/cancel',{'runToken':token})[0],200)
                        task.join(15);self.assertFalse(task.is_alive());self.assertEqual(answer['status'],409);result=answer['value'];self.assertTrue(result['cancelled']);self.assertIn('real partial output',result['log']);self.assertFalse(result['ok'])
                        status,log=get(result['files']['log']);self.assertEqual(status,200);self.assertIn(b'real partial output',log)
                        status,summary=get(f"/api/runs/{result['runId']}/summary.json");self.assertEqual(status,200);self.assertTrue(json.loads(summary)['cancelled'])
                        self.assertEqual(get(result['files']['csv'])[0],404)
                        # Avoid satisfying the next iteration with this run's retained log.
                        (runs/result['runId']/'solver.log').rename(runs/result['runId']/'checked.log')
        finally:web.shutdown();web.server_close();worker.join()

if __name__=='__main__':unittest.main()
