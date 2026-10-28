"""Real MBDyn spring/damper checks against independently integrated pendulum equations."""
import copy
import json
import math
from pathlib import Path
import planar_assembly as planar
import solver


def rk4(state, derivative, dt):
    a=derivative(state);b=derivative([x+dt*y/2 for x,y in zip(state,a)])
    c=derivative([x+dt*y/2 for x,y in zip(state,b)]);d=derivative([x+dt*y for x,y in zip(state,c)])
    return [x+dt*(v+2*w+2*y+z)/6 for x,v,w,y,z in zip(state,a,b,c,d)]


def case(two=False,k=10,c=.5):
    first=copy.deepcopy(planar.EXAMPLES[0]['model']);first['simulation']={'duration':1,'step':.001}
    if two:
        body=planar._rod('second_link',.8,1.,12.,(2.,0.))
        first['bodies'].append(body)
        first['joints'].append({'id':'second_pin','type':'revolute','parent':'ground','child':'second_link','parentAnchor':{'x':2.,'z':0.},'childAnchor':{'x':0.,'z':.5}})
        a,b='upper_link','second_link';aa,ab={'x':0.,'z':-.5},{'x':0.,'z':-.5};rest=1.4
    else:
        a,b='ground','upper_link';aa,ab={'x':1.,'z':0.},{'x':0.,'z':-.5};rest=1.3
    first['forces']=[{'id':'spring1','type':'linear-spring-damper','a':a,'b':b,'anchorA':aa,'anchorB':ab,'restLength':rest,'stiffness':k,'damping':c}]
    return first


def independent(model,samples):
    # Generalized coordinates are each rod's absolute +Y angle, independent of the exporter.
    bodies=model['bodies'];force=model['forces'][0];count=len(bodies)
    state=[math.radians(b['pose']['angleDeg']) for b in bodies]+[b['velocity']['omega'] for b in bodies]
    def derivative(q):
        theta,omega=q[:count],q[count:]; positions=[];velocities=[]
        for i in range(count):
            pivot=2*i
            positions.append((pivot-math.sin(theta[i]),-math.cos(theta[i])))
            velocities.append((-math.cos(theta[i])*omega[i],math.sin(theta[i])*omega[i]))
        if count==1: pa,va=(1.,0.),(0.,0.);pb,vb=positions[0],velocities[0]
        else: pa,pb=positions;va,vb=velocities
        dx,dz=pb[0]-pa[0],pb[1]-pa[1];length=math.hypot(dx,dz)
        rate=(dx*(vb[0]-va[0])+dz*(vb[1]-va[1]))/length
        tension=force['stiffness']*(length-force['restLength'])+force['damping']*rate
        unit=(dx/length,dz/length)
        reactions=[(-tension*unit[0],-tension*unit[1])] if count==1 else [(tension*unit[0],tension*unit[1]),(-tension*unit[0],-tension*unit[1])]
        acceleration=[]
        for i,body in enumerate(bodies):
            torque=reactions[i][0]*(-math.cos(theta[i]))+reactions[i][1]*math.sin(theta[i])
            torque-=body['mass']*model['parameters']['gravity']*.5*math.sin(theta[i])
            acceleration.append(torque/(body['inertia']['yy']+body['mass']*.25))
        return omega+acceleration
    time=0.; max_error=0.
    for sample in samples:
        while sample['time']-time>1e-12:
            dt=min(.00025,sample['time']-time);state=rk4(state,derivative,dt);time+=dt
        for i,node in enumerate(sample['nodes']):
            d=math.radians(node['angleDeg'])-state[i]
            max_error=max(max_error,abs(math.degrees(math.atan2(math.sin(d),math.cos(d)))))
    return max_error


def main():
    cases=[]
    for name,two,k,c in [('ground-spring-damper',False,10,.5),('ground-spring',False,10,0),('ground-damper',False,0,.5),('two-body-reaction',True,10,.5)]:
        model=case(two,k,c);result,status=solver.run(model)
        record={'id':name,'ok':result['ok'],'httpStatus':status,'runId':result.get('runId'),'error':result.get('error')}
        if result['ok']:
            full=planar.parse_output(solver.RUNS/result['runId'],model)
            record['maxAngleDifferenceDeg']=independent(model,full)
            record['maxEnergyBalanceErrorJ']=result['metrics']['maxEnergyBalanceError']
            record['maxConstraintErrorM']=result['metrics']['maxConstraintError']
            record['dissipatedEnergyJ']=result['metrics']['dissipatedEnergy']
            record['pass']=(record['maxAngleDifferenceDeg']<.05 and record['maxEnergyBalanceErrorJ']<.002 and record['maxConstraintErrorM']<1e-6 and (c==0 or record['dissipatedEnergyJ']>0))
        cases.append(record);print(json.dumps(record),flush=True)
    result={'passed':all(item.get('pass',False) for item in cases),'cases':cases,'scope':'MBDyn 1.7.3 against independent RK4 rigid pendulum equations; reconstructed spring force and damping energy. No contact or flexible-body validation.'}
    (Path(__file__).resolve().parents[1]/'verification'/'planar-springs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if not result['passed']: raise SystemExit(1)
if __name__=='__main__':main()
