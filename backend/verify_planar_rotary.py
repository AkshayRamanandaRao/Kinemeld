"""Real MBDyn verification against independently integrated planar equations."""
import copy
import json
import math
from pathlib import Path
import planar_assembly as planar
import solver


def rk4(y, t, f, h):
    a=f(t,y); b=f(t+h/2,[v+h*q/2 for v,q in zip(y,a)])
    c=f(t+h/2,[v+h*q/2 for v,q in zip(y,b)]); d=f(t+h,[v+h*q for v,q in zip(y,c)])
    return [v+h*(w+2*x+2*z+q)/6 for v,w,x,z,q in zip(y,a,b,c,d)]


def pendulum(model, samples):
    body=model['bodies'][0]; mass=body['mass']; inertia=body['inertia']['yy']+mass*.25
    state=[math.radians(body['pose']['angleDeg']),body['velocity']['omega']]
    def f(t,y):
        angle,omega=y; torque=-mass*model['parameters']['gravity']*.5*math.sin(angle)
        for e in model.get('rotationalElements',[]): torque-=e['stiffness']*(angle-math.radians(e['restAngleDeg']))+e['damping']*omega
        for e in model.get('jointTorques',[]): torque+=e['offset']+e['amplitude']*math.sin(2*math.pi*e['frequencyHz']*t)
        for load in model.get('loads',[]): torque+=load['torque']-.5*load['fx']*math.cos(angle)+.5*load['fz']*math.sin(angle)
        for e in model.get('forces',[]):
            x,z=-math.sin(angle),-math.cos(angle);vx,vz=-math.cos(angle)*omega,math.sin(angle)*omega
            dx,dz=x-1.,z;length=math.hypot(dx,dz);rate=(dx*vx+dz*vz)/length
            tension=e['stiffness']*(length-e['restLength'])+e['damping']*rate
            fx,fz=-tension*dx/length,-tension*dz/length
            torque+=-fx*math.cos(angle)+fz*math.sin(angle)
        return [omega,torque/inertia]
    return compare(samples,state,f)


def compare(samples,state,f):
    t=0.;error=0.
    for s in samples:
        while s['time']-t>1e-12:
            h=min(.00025,s['time']-t);state=rk4(state,t,f,h);t+=h
        for i,n in enumerate(s['nodes']):
            diff=math.radians(n['angleDeg'])-state[2*i]
            error=max(error,abs(math.degrees(math.atan2(math.sin(diff),math.cos(diff)))))
    return error


def two_body(model,samples):
    a,b=model['bodies'];e=model['rotationalElements'][0];drive=model['jointTorques'][0]
    state=[math.radians(a['pose']['angleDeg']),0.,math.radians(b['pose']['angleDeg']),0.]
    def f(t,y):
        aa,wa,ab,wb=y
        torque=drive['offset']+drive['amplitude']*math.sin(2*math.pi*drive['frequencyHz']*t)-e['stiffness']*(ab-aa-math.radians(e['restAngleDeg']))-e['damping']*(wb-wa)
        return [wa,-torque/a['inertia']['yy'],wb,torque/b['inertia']['yy']]
    return compare(samples,state,f)


def create(name):
    m=copy.deepcopy(planar.EXAMPLES[0]['model']);m['simulation']={'duration':.5,'step':.001}
    if name=='two-body':
        first=m['bodies'][0];first['pose']={'x':0.,'z':0.,'angleDeg':-10.};first['inertia']={'xx':.2,'yy':.2,'zz':.1}
        second=copy.deepcopy(first);second.update(id='second',name='second');second['pose']['angleDeg']=5.;second['inertia']={'xx':.3,'yy':.3,'zz':.1}
        m['bodies'].append(second);m['parameters']['gravity']=0.
        m['joints'][0]['childAnchor']={'x':0.,'z':0.}
        m['joints'].append({'id':'elbow','type':'revolute','parent':first['id'],'child':'second','parentAnchor':{'x':0.,'z':0.},'childAnchor':{'x':0.,'z':0.}})
    joint='elbow' if name=='two-body' else 'ground_pin'
    if name!='drive':
        m['rotationalElements']=[{'id':'spring1','joint':joint,'stiffness':0. if name=='damper' else 10.,'damping':0. if name=='spring' else .5,'restAngleDeg':-20. if name!='two-body' else 5.}]
    if name in ('combined','two-body','drive'):
        m['jointTorques']=[{'id':'drive1','joint':joint,'amplitude':1.,'frequencyHz':1.1,'offset':.3}]
    if name=='combined':
        m['forces']=[{'id':'axial','type':'linear-spring-damper','a':'ground','b':'upper_link','anchorA':{'x':1.,'z':0.},'anchorB':{'x':0.,'z':-.5},'restLength':1.3,'stiffness':10.,'damping':.5}]
        m['loads']=[{'id':'load1','body':'upper_link','fx':2.,'fz':-3.,'torque':1.}]
    return m


def main():
    records=[]
    for name in ('spring','damper','drive','combined','two-body'):
        m=create(name);result,status=solver.run(m)
        record={'id':name,'ok':result['ok'],'httpStatus':status,'runId':result.get('runId'),'error':result.get('error')}
        if result['ok']:
            samples=planar.parse_output(solver.RUNS/result['runId'],m)
            record['angleErrorDeg']=two_body(m,samples) if name=='two-body' else pendulum(m,samples)
            record['energyBalanceErrorJ']=result['metrics']['maxEnergyBalanceError']
            record['constraintErrorM']=result['metrics']['maxConstraintError']
            record['pass']=record['angleErrorDeg']<.05 and record['energyBalanceErrorJ']<.002 and record['constraintErrorM']<1e-6
        records.append(record);print(json.dumps(record),flush=True)
    report={'passed':all(r.get('pass',False) for r in records),'cases':records,'scope':'MBDyn 1.7.3 planar revolute torques, springs and damping against independent RK4; not spatial or industry qualification.'}
    (Path(__file__).resolve().parents[1]/'verification'/'planar-rotary.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if not report['passed']: raise SystemExit(1)
if __name__=='__main__':main()
