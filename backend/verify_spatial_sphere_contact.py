"""Real MBDyn contact trajectories versus independent one-dimensional RK4."""
import copy,csv,json,math
from pathlib import Path
import spatial_assembly as sp
from verify_spatial_assembly import run

def verify(normal, center, count, stiffness=1000., step=.001):
    model=copy.deepcopy(next(e['model'] for e in sp.EXAMPLES if e['id']=='spatial-sphere-contact'))
    model['simulation']['step']=step
    b=model['bodies'][0];b['pose'].update(x=.3*normal[0],y=.3*normal[1],z=.3*normal[2],rx=20.,ry=-10.,rz=15.);b['centerOfMass']={'x':-.02,'y':.01,'z':.03}
    model['parameters']['gravity']=dict(zip(('x','y','z'),[-9.81*x for x in normal]));model['joints'][0]['axisA']=dict(zip(('x','y','z'),normal))
    offset=sp.mul(sp.body_rotation(b),center);shift=sum(x*y for x,y in zip(offset,normal));plane=dict(zip(('x','y','z'),[shift*x for x in normal]))
    model['contacts']=[{'id':f'floor{i}','body':'ball','center':dict(zip(('x','y','z'),center)),'radius':.1,'planePoint':plane,'planeNormal':dict(zip(('x','y','z'),normal)),'stiffness':stiffness} for i in range(count)]
    result,directory=run(model)
    if not result['ok']:return {'ok':False,'error':result,'case':f'{normal}, {center}, {count}'}
    samples=result['samples'];dt=1e-5;position=.3;velocity=0.;tick=0;position_error=[];velocity_error=[];energy_error=[];observed=[]
    def derivative(q,v):return v,-9.81+stiffness*count*max(0.,.1-q)
    for sample in samples:
        target=round(sample['time']/dt)
        while tick<target:
            a,b0=derivative(position,velocity);c,d=derivative(position+a*dt/2,velocity+b0*dt/2);e,f=derivative(position+c*dt/2,velocity+d*dt/2);g,h=derivative(position+e*dt,velocity+f*dt)
            position+=(a+2*c+2*e+g)*dt/6;velocity+=(b0+2*d+2*f+h)*dt/6;tick+=1
        n=sample['nodes'][0];q=sum(n[k]*v for k,v in zip(('x','y','z'),normal));speed=sum(n[k]*v for k,v in zip(('vx','vy','vz'),normal));state=sample['contactStates'][0]
        position_error.append(abs(q-position));velocity_error.append(abs(speed-velocity));energy_error.append(abs(.5*speed**2+9.81*q+sum(x['energy'] for x in sample['contactStates'])-9.81*.3));observed.append(state['force'])
    label=2+len(model['joints'])+sum(j['type']=='prismatic' for j in model['joints'])
    rows=[line.split() for line in (directory/'result.jnt').read_text().splitlines() if int(line.split()[0])==label]
    native_error=max(abs(-float(row[3])-force) for row,force in zip(rows,observed))
    with (directory/'results.csv').open(encoding='utf8',newline='') as stream:csv_rows=list(csv.DictReader(stream))
    csv_error=max(abs(float(row['contact:floor0:force_N'])-force) for row,force in zip(csv_rows,observed))
    case={'normal':normal,'center':center,'contacts':count,'stiffness':stiffness,'step':step,'runId':result['runId'],'maxPositionError':max(position_error),'maxVelocityError':max(velocity_error),'maxEnergyError':max(energy_error),'maxNativeForceError':native_error,'maxCsvForceError':csv_error,'maximumForce':max(observed),'samples':len(samples)}
    case['ok']=len(rows)==len(samples)==len(csv_rows) and max(position_error)<.001 and max(velocity_error)<.01 and max(energy_error)<.02 and native_error<1e-6 and csv_error<1e-9 and max(observed)>10 and observed[0]==observed[-1]==0
    return case

def verify_rotating():
    model=copy.deepcopy(next(e['model'] for e in sp.EXAMPLES if e['id']=='spatial-revolute'))
    model['simulation']['step']=.001
    model['contacts']=[{'id':'floor','body':'arm','center':{'x':0.,'y':0.,'z':0.},'radius':.1,'planePoint':{'x':0.,'y':0.,'z':-1.05},'planeNormal':{'x':0.,'y':0.,'z':1.},'stiffness':100.}]
    result,directory=run(model)
    if not result['ok']:return {'ok':False,'error':result,'case':'rotating pendulum contact'}
    samples=result['samples'];rows=[line.split() for line in (directory/'result.jnt').read_text().splitlines() if int(line.split()[0])==3]
    if len(rows)!=len(samples):return {'ok':False,'case':'rotating pendulum contact','error':'Native joint output sample count differs.'}
    forces=[sample['contactStates'][0]['force'] for sample in samples]
    error=max(abs(-float(row[3])-force) for row,force in zip(rows,forces))
    return {'name':'rotating pendulum contact','runId':result['runId'],'samples':len(samples),'maximumForce':max(forces),'maxNativeForceError':error,'ok':max(forces)>4.9 and error<1e-6}

if __name__=='__main__':
    cases=[verify([0.,0.,1.],[0.,0.,0.],1),verify([.6,.8,0.],[.05,-.03,.02],1),verify([.6,.8,0.],[.05,-.03,.02],2),verify([0.,0.,1.],[0.,0.,0.],4,20000.,.00025),verify_rotating()]
    report={'solver':'MBDyn 1.7.3','cases':cases,'ok':all(case['ok'] for case in cases),'scope':'Frictionless elastic spheres against fixed planes; representative guided and rotating bodies only.'}
    Path('verification/spatial-sphere-contact.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)

