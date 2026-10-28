"""Verify constant planar loads against analytic and independent RK4 references."""
import copy
import json
import math
from pathlib import Path
import planar_assembly as planar
import solver


def rk4(state, f, dt):
    a=f(state);b=f([x+dt*y/2 for x,y in zip(state,a)])
    c=f([x+dt*y/2 for x,y in zip(state,b)]);d=f([x+dt*y for x,y in zip(state,c)])
    return [x+dt*(v+2*w+2*y+z)/6 for x,v,w,y,z in zip(state,a,b,c,d)]


def create(name):
    if name=='slider':
        model=copy.deepcopy(next(e['model'] for e in planar.EXAMPLES if e['id']=='assembly-slider'))
        model['loads']=[{'id':'load1','body':'block','fx':0.,'fz':4.,'torque':0.}]
    else:
        model=copy.deepcopy(planar.EXAMPLES[0]['model'])
        model['loads']=[{'id':'load1','body':'upper_link','fx':0. if name=='torque' else 2.,'fz':0. if name=='torque' else -3.,'torque':.7 if name=='torque' else 1.}]
        if name=='combined':
            model['forces']=[{'id':'spring1','type':'linear-spring-damper','a':'ground','b':'upper_link','anchorA':{'x':1.,'z':0.},'anchorB':{'x':0.,'z':-.5},'restLength':1.3,'stiffness':10.,'damping':.5}]
    model['simulation']={'duration':1.,'step':.001}
    return model


def pendulum_error(model,samples):
    body,load=model['bodies'][0],model['loads'][0]
    inertia=body['inertia']['yy']+body['mass']*.25
    state=[math.radians(body['pose']['angleDeg']),body['velocity']['omega']]
    spring=model.get('forces',[])
    def deriv(q):
        angle,omega=q
        torque=load['torque']-.5*load['fx']*math.cos(angle)+.5*load['fz']*math.sin(angle)-body['mass']*model['parameters']['gravity']*.5*math.sin(angle)
        if spring:
            # Tip is one metre below pivot, independent from the deck exporter.
            item=spring[0];x,z=-math.sin(angle),-math.cos(angle);vx,vz=-math.cos(angle)*omega,math.sin(angle)*omega
            dx,dz=x-1.,z;length=math.hypot(dx,dz);rate=(dx*vx+dz*vz)/length
            tension=item['stiffness']*(length-item['restLength'])+item['damping']*rate
            fx,fz=-tension*dx/length,-tension*dz/length
            torque+=-fx*math.cos(angle)+fz*math.sin(angle)
        return [omega,torque/inertia]
    error,time=0.,0.
    for sample in samples:
        while sample['time']-time>1e-12:
            dt=min(.00025,sample['time']-time);state=rk4(state,deriv,dt);time+=dt
        delta=math.radians(sample['nodes'][0]['angleDeg'])-state[0]
        error=max(error,abs(math.degrees(math.atan2(math.sin(delta),math.cos(delta)))))
    return error


def main():
    records=[]
    for name in ('slider','torque','force-and-torque','combined'):
        model=create(name);result,status=solver.run(model)
        record={'id':name,'ok':result['ok'],'httpStatus':status,'runId':result.get('runId'),'error':result.get('error')}
        if result['ok']:
            samples=planar.parse_output(solver.RUNS/result['runId'],model)
            first,last=samples[0],samples[-1];body=model['bodies'][0];load=model['loads'][0]
            if name=='slider':
                acceleration=load['fz']/body['mass']-model['parameters']['gravity']; t=last['time']
                error=abs(last['nodes'][0]['z']-(body['pose']['z']+.5*acceleration*t*t))
                record['positionErrorM']=error;pos_ok=error<.0001
            else:
                error=pendulum_error(model,samples);record['angleErrorDeg']=error;pos_ok=error<.05
            # Conservative constant loads admit exact work from COM displacement and unwrapped rotation.
            n0,n1=first['nodes'][0],last['nodes'][0]
            exact_work=load['fx']*(n1['x']-n0['x'])+load['fz']*(n1['z']-n0['z'])+load['torque']*math.radians(n1['angleDeg']-n0['angleDeg'])
            record['workErrorJ']=abs(last['appliedWork']-exact_work)
            record['energyBalanceErrorJ']=result['metrics']['maxEnergyBalanceError']
            record['constraintErrorM']=result['metrics']['maxConstraintError']
            record['pass']=pos_ok and record['workErrorJ']<.0001 and record['energyBalanceErrorJ']<.002 and record['constraintErrorM']<1e-6
        records.append(record);print(json.dumps(record),flush=True)
    report={'passed':all(item.get('pass',False) for item in records),'cases':records,'scope':'Constant global COM force and +Y torque against an analytic slider and independent RK4 pendulum, including spring/damping energy balance. MBDyn 1.7.3 only.'}
    (Path(__file__).resolve().parents[1]/'verification'/'planar-loads.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
