"""Actual local MBDyn sampled feedback against independent constant-torque mechanics."""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch

import rotary_control
import solver
import spatial_assembly as spatial


def vector(x=0., y=0., z=0.):
    return dict(x=x, y=y, z=z)


def rotor(step=.001, target=30., limit=2.):
    return dict(kind='spatial-assembly', name='Sampled robot joint controller', parameters={'gravity':vector()},
                simulation=dict(duration=1.5, step=step),
                bodies=[dict(id='rotor',name='Robot rotor',mass=1.,inertia=dict(xx=.1,yy=.1,zz=.1),pose=dict(x=0.,y=0.,z=0.,rx=0.,ry=0.,rz=0.),velocity=dict(vx=0.,vy=0.,vz=0.,wx=0.,wy=0.,wz=0.))],
                joints=[dict(id='hinge',type='revolute',a='ground',b='rotor',anchorA=vector(),anchorB=vector(),axisA=vector(z=1.),axisB=vector(z=1.))],
                jointTorques=[dict(id='servo',joint='hinge',type='servo',kp=8.,kd=1.,targetAngleDeg=target,rampTime=.4,torqueLimit=limit)])


def robot_arm():
    model=rotor();model['name']='Two-link robot arm with local closed-loop actuators'
    model['simulation']=dict(duration=3.,step=.0005)
    model['bodies'][0].update(id='upper',name='Upper arm',mass=1.,inertia=dict(xx=.01,yy=.03,zz=.03))
    model['bodies'][0]['pose']['x']=.3
    forearm=deepcopy(model['bodies'][0]);forearm.update(id='forearm',name='Forearm',mass=.5,inertia=dict(xx=.005,yy=.01,zz=.01));forearm['pose']['x']=.8
    model['bodies'].append(forearm)
    model['joints'][0].update(id='shoulder',b='upper',anchorB=vector(x=-.3))
    model['joints'].append(dict(id='elbow',type='revolute',a='upper',b='forearm',anchorA=vector(x=.3),anchorB=vector(x=-.2),axisA=vector(z=1.),axisB=vector(z=1.)))
    model['jointTorques']=[dict(id='shoulderMotor',joint='shoulder',type='servo',kp=5.,kd=1.2,targetAngleDeg=30.,rampTime=.8,torqueLimit=2.),dict(id='elbowMotor',joint='elbow',type='servo',kp=2.,kd=.4,targetAngleDeg=-45.,rampTime=.8,torqueLimit=1.)]
    return model


def independent(model, count=None):
    """Exact integration of each held command for a one-inertia benchmark, independent of MBDyn."""
    control=model['jointTorques'][0];step=model['simulation']['step'];inertia=model['bodies'][0]['inertia']['zz']
    q=speed=0.;values=[(q,speed)]
    for index in range(count-1 if count else math.ceil(model['simulation']['duration']/step)):
        t=index*step;target=math.radians(control['targetAngleDeg']);phase=min(t/control['rampTime'],1.)
        desired=.5*target*(1-math.cos(math.pi*phase));rate=0. if phase==1 else .5*target*math.pi/control['rampTime']*math.sin(math.pi*phase)
        effort=max(-control['torqueLimit'],min(control['torqueLimit'],control['kp']*(desired-q)+control['kd']*(rate-speed)))
        acceleration=effort/inertia
        q+=speed*step+.5*acceleration*step*step;speed+=acceleration*step
        values.append((q,speed))
    return values


def assert_stopped(directory):
    pids=json.loads((directory/'controller-processes.json').read_text(encoding='utf-8'))
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.restype=ctypes.c_void_p
        kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        for pid in pids.values():
            handle=kernel.OpenProcess(0x100000,False,pid)
            if handle:
                try:assert kernel.WaitForSingleObject(handle,0)==0, f'Owned process {pid} survived.'
                finally:kernel.CloseHandle(handle)
    else:
        for pid in pids.values():
            try:os.kill(pid,0)
            except ProcessLookupError:continue
            raise AssertionError(f'Owned process {pid} survived.')


def main(binary):
    root=Path('verification/rotary-control').resolve();root.mkdir(parents=True,exist_ok=True)
    config={'mode':'native','executable':str(Path(binary).resolve())};records=[]
    tilted=rotor();tilted['bodies'][0]['pose'].update(rx=20.,ry=-10.,rz=30.);axis=[.6,.8,0.]
    tilted['joints'][0]['axisA']=dict(zip(('x','y','z'),axis));tilted['joints'][0]['axisB']=dict(zip(('x','y','z'),spatial.mul(spatial.transpose(spatial.body_rotation(tilted['bodies'][0])),axis)))
    braked=rotor();braked['joints'][0]['friction']=dict(coefficient=.5,radius=.1,preload=1.)
    negative_brake=deepcopy(braked);negative_brake['jointTorques'][0]['targetAngleDeg']=-30.
    with patch.object(solver,'RUNS',root),patch.object(solver,'configuration',return_value=config):
        for name,model in [('positive',rotor()),('positive-half-step',rotor(.0005)),('negative',rotor(target=-30.)),('saturated',rotor(limit=.1)),('zero',rotor(target=0.)),('robot-arm',robot_arm()),('tilted-axis',tilted),('braked-positive',braked),('braked-negative',negative_brake)]:
            result,code=solver.run(model)
            if not result['ok']:raise AssertionError(f'{name}: {result.get("error")}')
            record=dict(name=name,runId=result['runId'],deckSha256=result['deckSha256'],metrics=result['metrics'],coSimulation=result['coSimulation'])
            states=[sample['servoStates'] for sample in spatial.parse_output(root/result['runId'],model)]
            assert all(abs(state['torque'])<=control['torqueLimit']+1e-12 for row in states for state,control in zip(row,rotary_control.servos(model)))
            if name not in ('robot-arm','saturated') and not name.startswith('braked'):
                reference=independent(model,len(states))
                record['maxIndependentAngleError']=max(abs(row[0]['angle']-expected[0]) for row,expected in zip(states,reference))
                assert record['maxIndependentAngleError']<.002
                assert result['metrics']['finalServoTrackingError']<.002
            if name=='saturated':assert result['metrics']['servoSaturatedStepCount']>0
            if name=='zero':assert all(row[0]['angle']==row[0]['torque']==0. for row in states)
            if name=='robot-arm':
                assert result['metrics']['maxConstraintError']<1e-7
                assert result['metrics']['finalServoTrackingError']<.01
            if name.startswith('braked'):
                assert result['metrics']['jointFrictionDissipatedEnergy']>0
                assert states[0][0]['torque']==states[0][0]['angle']==0.
                assert result['metrics']['finalServoTrackingError']<.02
            assert_stopped(root/result['runId'])
            records.append(record)
            print(json.dumps(record),flush=True)
        cancellation=solver.RunControl();outcome={};model=rotor(.0001);model['simulation']['duration']=2.
        thread=threading.Thread(target=lambda:outcome.update(result=solver.run(model,control=cancellation)))
        known=set(root.iterdir());thread.start();deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            candidates=[directory for directory in root.iterdir() if directory not in known and (directory/'controller-trace.jsonl').exists()]
            if candidates and (candidates[0]/'controller-trace.jsonl').stat().st_size>1000:break
            time.sleep(.01)
        else:raise AssertionError('No actual controller exchange before cancellation deadline.')
        cancellation.cancel();thread.join(10);assert not thread.is_alive()
        result,code=outcome['result'];assert code==409 and result.get('cancelled')
        assert_stopped(root/result['runId']);records.append(dict(name='cancelled',runId=result['runId'],code=code,childrenStopped=True))
        original=Path(rotary_control.__file__);source=original.read_text(encoding='utf-8');anchor='                commands.sendall('
        assert anchor in source
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            fault=Path(temporary)/'rotary_control.py'
            fault.write_text(source.replace(anchor,"                if index == 3:raise ValueError('Owned test controller disconnect')\n"+anchor),encoding='utf-8')
            with patch.object(rotary_control,'__file__',str(fault)),patch.dict(os.environ,{'PYTHONPATH':str(original.resolve().parent)}):
                started=time.monotonic();result,code=solver.run(rotor());elapsed=time.monotonic()-started
            assert code==422 and not result['ok'] and elapsed<5
            assert 'local controller failed' in result['log']
            assert_stopped(root/result['runId']);records.append(dict(name='controller-failure',runId=result['runId'],code=code,elapsed=elapsed,childrenStopped=True))
    assert records[1]['maxIndependentAngleError']<records[0]['maxIndependentAngleError']*.6
    report=dict(scope='Actual native MBDyn, separate trusted Python peer, every-step socket feedback and native applied-couple verification; independent held-torque dynamics; illustrative robot inputs, no hardware calibration.',solverSha256=hashlib.sha256(Path(binary).read_bytes()).hexdigest(),controllerSha256=hashlib.sha256(Path(rotary_control.__file__).read_bytes()).hexdigest(),cases=records)
    (root/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')


if __name__=='__main__':
    import sys
    if len(sys.argv)!=2:raise SystemExit('Supply an existing native MBDyn executable.')
    main(sys.argv[1])
