"""Real MBDyn compression-only damped contact versus independent RK4."""
import copy,json,math
from pathlib import Path
import spatial_assembly as sp
from verify_spatial_assembly import run


def verify(normal,count,initial,damping):
    model=copy.deepcopy(next(item['model'] for item in sp.EXAMPLES if item['id']=='spatial-sphere-contact'))
    model['simulation']['step']=.00025
    body=model['bodies'][0];body['pose'].update(x=initial*normal[0],y=initial*normal[1],z=initial*normal[2],rx=20.,ry=-10.,rz=15.)
    model['parameters']['gravity']=dict(zip(('x','y','z'),[-9.81*n for n in normal]));model['joints'][0]['axisA']=dict(zip(('x','y','z'),normal))
    center=[.05,-.03,.02];shift=sum(n*x for n,x in zip(normal,sp.mul(sp.body_rotation(body),center)));plane=dict(zip(('x','y','z'),[shift*n for n in normal]))
    model['contacts']=[{'id':f'floor{i}','body':'ball','center':dict(zip(('x','y','z'),center)),'radius':.1,'planePoint':plane,'planeNormal':dict(zip(('x','y','z'),normal)),'stiffness':1000.,'damping':damping} for i in range(count)]
    result,directory=run(model)
    if not result['ok']:return {'ok':False,'case':str((normal,count,initial,damping)),'error':result}
    samples=result['samples'];dt=1e-5;position=initial;velocity=0.;dissipation=0.;tick=0;error=[];vel_error=[];energy_error=[];native_error=[]
    def derivative(q,v):
        pen=max(0.,.1-q);damp=damping*max(0.,-v) if q<.1 else 0.
        return v,-9.81+count*(1000*pen+damp),count*damp*max(0.,-v)
    label=2+len(model['joints'])+sum(j['type']=='prismatic' for j in model['joints'])
    native_rows=[];all_rows=[line.split() for line in (directory/'result.jnt').read_text().splitlines()]
    for contact in model['contacts']:
        if contact.get('damping',0)>0:label+=1
        rows=[row for row in all_rows if int(row[0])==label];label+=1
        if len(rows)!=len(samples):return {'ok':False,'error':'Native contact output sample mismatch.'}
        native_rows.append(rows)
    initial_energy=9.81*initial+.5*count*1000*max(0,.1-initial)**2
    for index,sample in enumerate(samples):
        target=round(sample['time']/dt)
        while tick<target:
            a,b,c=derivative(position,velocity);d,e,f=derivative(position+a*dt/2,velocity+b*dt/2);g,h,i=derivative(position+d*dt/2,velocity+e*dt/2);j,k,l=derivative(position+g*dt,velocity+h*dt)
            position+=(a+2*d+2*g+j)*dt/6;velocity+=(b+2*e+2*h+k)*dt/6;dissipation+=(c+2*f+2*i+l)*dt/6;tick+=1
        node=sample['nodes'][0];q=sum(node[k]*n for k,n in zip(('x','y','z'),normal));v=sum(node[k]*n for k,n in zip(('vx','vy','vz'),normal));state=sample['contactStates'][0]
        error.append(abs(q-position));vel_error.append(abs(v-velocity))
        for contact_rows,contact_state in zip(native_rows,sample['contactStates']):native_error.append(abs(-float(contact_rows[index][3])-contact_state['force']))
        energy=.5*v*v+9.81*q+sum(item['energy']+item['dissipatedEnergy'] for item in sample['contactStates']);energy_error.append(abs(energy-initial_energy))
    powers=[s['contactStates'][0]['dampingPower'] for s in samples];force=[s['contactStates'][0]['force'] for s in samples]
    separated=all(state['force']==0 and state['dampingPower']==0 for sample in samples for state in sample['contactStates'] if state['gap']>=0)
    releasing=all(state['dampingPower']==0 for sample in samples for state in sample['contactStates'] if state['power']>0)
    monotonic=all(b['dissipatedEnergy']>=a['dissipatedEnergy'] for first,second in zip(samples,samples[1:]) for a,b in zip(first['contactStates'],second['contactStates']))
    case={'normal':normal,'contacts':count,'initialPosition':initial,'damping':damping,'runId':result['runId'],'samples':len(samples),'maxPositionError':max(error),'maxVelocityError':max(vel_error),'maxEnergyError':max(energy_error),'maxNativeForceError':max(native_error),'finalDissipatedEnergy':sum(item['dissipatedEnergy'] for item in samples[-1]['contactStates']),'referenceDissipation':dissipation,'minForce':min(force),'maxDampingPower':max(powers)}
    case.update(separatedZero=separated,releasingUndamped=releasing,dissipationMonotonic=monotonic)
    case['ok']=max(error)<.001 and max(vel_error)<.02 and max(energy_error)<.05 and max(native_error)<1e-6 and min(force)>=0 and separated and releasing and monotonic and (damping==0 or max(powers)>.1)
    return case

def verify_initial_velocity(speed):
    model=copy.deepcopy(next(item['model'] for item in sp.EXAMPLES if item['id']=='spatial-sphere-contact'))
    model['joints']=[];model['simulation']={'duration':.04,'step':.00025}
    model['bodies'][0]['pose']['z']=.08;model['bodies'][0]['velocity']['vz']=speed;model['contacts'][0]['damping']=10.
    result,directory=run(model)
    if not result['ok']:return {'ok':False,'case':f'initial penetration speed {speed}','error':result}
    samples=result['samples'];rows=[line.split() for line in (directory/'result.jnt').read_text().splitlines() if int(line.split()[0])==3]
    if len(rows)!=len(samples):return {'ok':False,'error':'Native contact output sample mismatch.'}
    mismatch=max(abs(-float(row[3])-sample['contactStates'][0]['force']) for row,sample in zip(rows,samples))
    initial=samples[0]['contactStates'][0];expected=20+10*max(0.,-speed);power=10*max(0.,-speed)**2
    return {'name':f'initial penetration speed {speed}','runId':result['runId'],'initialForce':initial['force'],'initialDampingPower':initial['dampingPower'],'maxNativeForceError':mismatch,'ok':abs(initial['force']-expected)<1e-8 and abs(initial['dampingPower']-power)<1e-8 and mismatch<1e-6}

if __name__=='__main__':
    cases=[verify([0.,0.,1.],1,.3,10.),verify([.6,.8,0.],1,.3,10.),verify([.6,.8,0.],2,.3,10.),verify([0.,0.,1.],1,.08,10.),verify([0.,0.,1.],1,.3,0.),verify_initial_velocity(-10.),verify_initial_velocity(10.)]
    report={'solver':'MBDyn 1.7.3','cases':cases,'ok':all(case['ok'] for case in cases),'scope':'Compression-only, frictionless sphere-plane damping; representative guided impacts, not hardware qualification.'}
    Path('verification/contact-damping.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
