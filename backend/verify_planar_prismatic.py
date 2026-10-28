"""Run actual MBDyn sliders against independent analytic and RK4 trajectories."""
import copy
import json
import math
from pathlib import Path
import planar_assembly as p
import solver


def ground(axis=60., angle=30., speed=.4, displacement=.2):
    radians=math.radians(axis); u=(math.cos(radians),-math.sin(radians))
    return {'kind':'planar-assembly','name':'Gravity slider','parameters':{'gravity':9.81},'simulation':{'duration':.5,'step':.001},
        'bodies':[{'id':'block','name':'Block','mass':1.,'inertia':{'xx':.1,'yy':.1,'zz':.01},
                   'pose':{'x':displacement*u[0],'z':displacement*u[1],'angleDeg':angle},
                   'velocity':{'vx':speed*u[0],'vz':speed*u[1],'omega':0.}}],
        'joints':[{'id':'slider','type':'prismatic','parent':'ground','child':'block','parentAnchor':{'x':0.,'z':0.},
                   'childAnchor':{'x':0.,'z':0.},'axisAngleDeg':axis,'referenceAngleDeg':angle}]}


def ground_offset():
    model=ground(axis=-40.,angle=45.)
    joint=model['joints'][0];body=model['bodies'][0]
    joint['parentAnchor']={'x':.3,'z':-.2};joint['childAnchor']={'x':.2,'z':-.1}
    ux,uz=math.cos(math.radians(-40.)),-math.sin(math.radians(-40.))
    ax,az=p.rotate(math.radians(45.),joint['childAnchor'])
    body['pose']['x']=joint['parentAnchor']['x']+.2*ux-ax
    body['pose']['z']=joint['parentAnchor']['z']+.2*uz-az
    return model


def rotating():
    theta=-20.; omega=.4; q=.8; qdot=.2; a=.5; angle=math.radians(theta)
    c,s=math.cos(angle),math.sin(angle)
    x,z=-a*s,-a*c
    vx,vz=omega*z,-omega*x
    dx,dz=q*c,-q*s
    model={'kind':'planar-assembly','name':'Rotating guide','parameters':{'gravity':9.81},'simulation':{'duration':.5,'step':.001},
      'bodies':[{'id':'parent','name':'Parent','mass':1.2,'inertia':{'xx':.10009,'yy':.10009,'zz':.00018},
                 'pose':{'x':x,'z':z,'angleDeg':theta},'velocity':{'vx':vx,'vz':vz,'omega':omega}},
                {'id':'child','name':'Slider','mass':.8,'inertia':{'xx':.1,'yy':.1,'zz':.01},
                 'pose':{'x':x+dx,'z':z+dz,'angleDeg':theta+30},
                 'velocity':{'vx':vx+omega*dz+qdot*c,'vz':vz-omega*dx-qdot*s,'omega':omega}}],
      'joints':[{'id':'pin','type':'revolute','parent':'ground','child':'parent','parentAnchor':{'x':0.,'z':0.},'childAnchor':{'x':0.,'z':.5}},
                {'id':'slider','type':'prismatic','parent':'parent','child':'child','parentAnchor':{'x':0.,'z':0.},
                 'childAnchor':{'x':0.,'z':0.},'axisAngleDeg':0.,'referenceAngleDeg':30.}]}
    return model


def rk4(state, derivative, dt):
    a=derivative(state);b=derivative([x+dt*y/2 for x,y in zip(state,a)])
    c=derivative([x+dt*y/2 for x,y in zip(state,b)]);d=derivative([x+dt*y for x,y in zip(state,c)])
    return [x+dt*(v+2*w+2*y+z)/6 for x,v,w,y,z in zip(state,a,b,c,d)]


def independent_rotating(model,samples):
    m1,m2=(body['mass'] for body in model['bodies']);i1,i2=(body['inertia']['yy'] for body in model['bodies']);g=model['parameters']['gravity'];a=.5
    state=[math.radians(-20.),.8,.4,.2]
    def derivative(s):
        theta,q,omega,rate=s
        m11=i1+m1*a*a+i2+m2*(q*q+a*a);m12=-m2*a;m22=m2
        r1=-2*m2*q*rate*omega-(m1+m2)*g*a*math.sin(theta)+m2*g*q*math.cos(theta)
        r2=m2*q*omega*omega+m2*g*math.sin(theta)
        det=m11*m22-m12*m12
        return [omega,rate,(r1*m22-m12*r2)/det,(m11*r2-m12*r1)/det]
    t=0.;max_angle=0.;max_distance=0.
    for sample in samples:
        while sample['time']-t>1e-12:
            dt=min(.00025,sample['time']-t);state=rk4(state,derivative,dt);t+=dt
        diff=math.radians(sample['nodes'][0]['angleDeg'])-state[0]
        max_angle=max(max_angle,abs(math.degrees(math.atan2(math.sin(diff),math.cos(diff)))))
        max_distance=max(max_distance,abs(sample['sliders'][0]['position']-state[1]))
    return max_angle,max_distance


def main():
    records=[]
    refined=rotating();refined['simulation']['step']=.0005
    sprung=ground(axis=0.,angle=30.);sprung['parameters']['gravity']=0.
    sprung['forces']=[{'id':'spring1','type':'linear-spring-damper','a':'ground','b':'block','anchorA':{'x':-1.,'z':0.},'anchorB':{'x':0.,'z':0.},'stiffness':10.,'damping':.5,'restLength':1.}]
    for name,model in [('ground-oblique',ground()),('ground-horizontal',ground(axis=0.,angle=-40.)),('ground-offset',ground_offset()),('rotating-parent',rotating()),('rotating-refined',refined),('slider-spring',sprung)]:
        result,status=solver.run(model)
        rec={'name':name,'ok':result.get('ok'),'status':status,'runId':result.get('runId'),'error':result.get('error')}
        if result.get('ok'):
            samples=p.parse_output(solver.RUNS/result['runId'],model)
            if name.startswith('ground'):
                axis=math.radians(model['joints'][0]['axisAngleDeg']);u=(math.cos(axis),-math.sin(axis));b=model['bodies'][0]
                pa=p.anchor_position(None,model['joints'][0]['parentAnchor']);pb=p.anchor_position(b,model['joints'][0]['childAnchor']);vb=p.anchor_velocity(b,model['joints'][0]['childAnchor']);q0=(pb[0]-pa[0])*u[0]+(pb[1]-pa[1])*u[1];v0=vb[0]*u[0]+vb[1]*u[1]
                rec['maxPositionErrorM']=max(abs(s['sliders'][0]['position']-(q0+v0*s['time']+.5*model['parameters']['gravity']*math.sin(axis)*s['time']**2)) for s in samples)
                rec['maxAngleErrorDeg']=max(abs(s['nodes'][0]['angleDeg']-b['pose']['angleDeg']) for s in samples)
            elif name == 'slider-spring':
                # Analytic underdamped oscillator m*q'' + c*q' + k*q = 0, for q > -1 m.
                mass=1.; k=10.; damping=.5; alpha=damping/(2*mass); wd=math.sqrt(k/mass-alpha*alpha);q0=.2;v0=.4
                expected=lambda t: math.exp(-alpha*t)*(q0*math.cos(wd*t)+(v0+alpha*q0)/wd*math.sin(wd*t))
                rec['maxPositionErrorM']=max(abs(sample['sliders'][0]['position']-expected(sample['time'])) for sample in samples)
                rec['maxAngleErrorDeg']=max(abs(sample['nodes'][0]['angleDeg']-30.) for sample in samples)
                rec['dissipatedEnergyJ']=result['metrics']['dissipatedEnergy']
                rec['maxEnergyBalanceErrorJ']=result['metrics']['maxEnergyBalanceError']
            else:rec['maxAngleErrorDeg'],rec['maxPositionErrorM']=independent_rotating(model,samples)
            rec['maxConstraintErrorM']=result['metrics']['maxConstraintError'];rec['maxAngularErrorRad']=result['metrics']['maxJointAngularError']
            rec['pass']=rec['maxPositionErrorM']<.002 and rec['maxAngleErrorDeg']<.05 and rec['maxConstraintErrorM']<1e-6 and rec['maxAngularErrorRad']<1e-6 and (name!='slider-spring' or (rec['dissipatedEnergyJ']>0 and rec['maxEnergyBalanceErrorJ']<.002))
        records.append(rec);print(json.dumps(rec),flush=True)
    ratio=records[3]['maxPositionErrorM']/max(records[4]['maxPositionErrorM'],1e-30)
    report={'passed':all(r.get('pass',False) for r in records) and ratio>2, 'rotatingRefinementRatio':ratio,'cases':records,'scope':'Planar prismatic trees: actual MBDyn 1.7.3 compared with independent ground-slider analytic and rotating-guide RK4 equations.'}
    (Path(__file__).resolve().parents[1]/'verification'/'planar-prismatic.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
