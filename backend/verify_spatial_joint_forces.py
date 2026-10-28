"""Solver-backed axial-force checks against independent slider dynamics and energy."""
import copy
import csv
import json
import math
from pathlib import Path
import kinematics
import spatial_assembly as spatial
from verify_spatial_assembly import run


def run_fixed(kind, offset_center=False):
    model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-'+kind))
    model['parameters']['gravity']=dict.fromkeys(('x','y','z'),0.)
    model['simulation']={'duration':.4,'step':.001}
    model['jointForces']=[{'id':'push','joint':'guide','offset':1.,'amplitude':2.,'frequencyHz':1.}]
    speed=.2
    if offset_center:
        body=model['bodies'][0];body['centerOfMass']={'x':.08,'y':-.03,'z':.1};body['inertia']['xy']=.02
        body['velocity'].update(vx=.18,vy=0.)
        solved=kinematics.solve({'mode':'velocity','model':model,'variables':[{'body':'block','component':key} for key in ('vx','vy')],
                                 'targets':[{'body':'block','component':'vx','value':.18}]})
        if not solved['ok'] or not solved['dynamicsValidation']['valid']:return {'ok':False,'error':solved,'name':'offset COM and solved velocity'}
        model=solved['model'];speed=.3
    result,directory=run(model)
    if not result['ok']:return {'ok':False,'error':result,'name':kind}
    samples=result['samples'];w=2*math.pi;mass=model['bodies'][0]['mass'];position_error=[];velocity_error=[];work_error=[]
    for sample in samples:
        t=sample['time'];state=sample['sliders' if kind=='prismatic' else 'cylinders'][0]
        expected=.3+speed*t+(t*t/2+2*(w*t-math.sin(w*t))/(w*w))/mass
        rate=speed+(t+2*(1-math.cos(w*t))/w)/mass
        position_error.append(abs(state['position']-expected));velocity_error.append(abs(state['velocity']-rate))
        work_error.append(abs(sample['jointForceWork']-.5*mass*(state['velocity']**2-speed**2)))
    with (directory/'results.csv').open(encoding='utf-8',newline='') as stream:
        rows=list(csv.DictReader(stream))
    csv_error=max(abs(float(row['jointForce:push:force_N'])-sample['jointForceStates'][0]['force']) for row,sample in zip(rows,samples))
    case={'name':kind+(' with offset COM and solved velocity' if offset_center else ''),'runId':result['runId'],'maxPositionError':max(position_error),'maxVelocityError':max(velocity_error),'maxWorkError':max(work_error),'maxCsvForceError':csv_error,'samples':len(samples)}
    case['ok']=case['maxPositionError']<1e-4 and case['maxVelocityError']<1e-4 and case['maxWorkError']<1e-4 and case['maxCsvForceError']<1e-12
    return case


def run_moving():
    model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-prismatic'))
    model['parameters']['gravity']=dict.fromkeys(('x','y','z'),0.);model['simulation']={'duration':.4,'step':.001}
    carrier=copy.deepcopy(model['bodies'][0]);carrier.update(id='carrier',name='Carrier');carrier['pose'].update(x=0,y=0,z=0);carrier['velocity'].update(vx=0,vy=0,vz=0)
    r=spatial.body_rotation(carrier);axis=spatial.mul(r,[0,0,1]);omega=spatial.mul(r,[1,0,0]);carrier['velocity'].update(zip(('wx','wy','wz'),omega))
    block=model['bodies'][0];offset=[.5*x for x in axis];vel=[a+.2*b for a,b in zip(spatial.cross(omega,offset),axis)];block['pose'].update(zip(('x','y','z'),offset));block['pose']['rx']+=25;block['velocity'].update(zip(('vx','vy','vz'),vel));block['velocity'].update(zip(('wx','wy','wz'),omega));model['bodies'].insert(0,carrier)
    zero=dict.fromkeys(('x','y','z'),0.)
    model['joints']=[{'id':'ball','type':'spherical','a':'ground','b':'carrier','anchorA':zero.copy(),'anchorB':zero.copy()}, {'id':'guide','type':'prismatic','a':'carrier','b':'block','anchorA':zero.copy(),'anchorB':zero.copy(),'axisA':{'x':0,'y':0,'z':1}}]
    model['jointForces']=[{'id':'push','joint':'guide','offset':1.,'amplitude':2.,'frequencyHz':1.}]
    result,_=run(model)
    if not result['ok']:return {'ok':False,'name':'moving parent','error':result}
    q=.5;v=.2;time=0.;position_error=[];momentum_error=[];work_error=[];energy0=None;h0=None
    def derivatives(t,x,speed):return speed,x*(.45/(.2+x*x))**2+1+2*math.sin(2*math.pi*t)
    for sample in result['samples']:
        while sample['time']-time>1e-12:
            h=min(.0001,sample['time']-time);a,b=derivatives(time,q,v);c,d=derivatives(time+h/2,q+h*a/2,v+h*b/2);e,f=derivatives(time+h/2,q+h*c/2,v+h*d/2);g,k=derivatives(time+h,q+h*e,v+h*f);q+=h*(a+2*c+2*e+g)/6;v+=h*(b+2*d+2*f+k)/6;time+=h
        position_error.append(abs(sample['sliders'][0]['position']-q));momentum=[0.,0.,0.];energy=0.
        for node in sample['nodes']:
            pos=[node[k] for k in ('x','y','z')];vel=[node[k] for k in ('vx','vy','vz')];spin=[node[k] for k in ('wx','wy','wz')];orbital=spatial.cross(pos,vel)
            momentum=[x+y+.1*z for x,y,z in zip(momentum,orbital,spin)];energy+=.5*sum(x*x for x in vel)+.05*sum(x*x for x in spin)
        if h0 is None:h0=momentum;energy0=energy
        momentum_error.append(math.dist(momentum,h0));work_error.append(abs(sample['jointForceWork']-(energy-energy0)))
    case={'name':'moving parent','runId':result['runId'],'maxPositionError':max(position_error),'maxAngularMomentumError':max(momentum_error),'maxWorkError':max(work_error),'samples':len(result['samples'])}
    case['ok']=case['maxPositionError']<1e-4 and case['maxAngularMomentumError']<1e-5 and case['maxWorkError']<1e-4
    return case


if __name__=='__main__':
    cases=[run_fixed('prismatic'),run_fixed('cylindrical'),run_moving(),run_fixed('prismatic',offset_center=True)]
    report={'solver':'MBDyn 1.7.3','cases':cases,'ok':all(case['ok'] for case in cases),'scope':'Representative axial forces; no contact or industrial qualification.'}
    Path('verification/spatial-joint-forces.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
