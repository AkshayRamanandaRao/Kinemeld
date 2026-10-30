"""Real MBDyn friction runs versus closed-form results and an independent RK4 integration."""
import json,math
from pathlib import Path
import spatial_assembly as sp
from verify_spatial_assembly import run

G=9.81

def euler123(matrix):
    b=math.asin(max(-1.,min(1.,matrix[0][2])))
    return math.degrees(math.atan2(-matrix[1][2],matrix[2][2])),math.degrees(b),math.degrees(math.atan2(-matrix[0][1],matrix[0][0]))

def unit(v):
    length=math.sqrt(sum(x*x for x in v));return [x/length for x in v]

def energy_error(model,samples):
    """Kinetic + potential + contact elastic + dissipated energy against its initial value."""
    gravity=sp.xyz(model['parameters']['gravity']);bodies={b['id']:b for b in model['bodies']};values=[]
    for sample in samples:
        total=0.
        for node in sample['nodes']:
            body=bodies[node['id']];r=sp.rotation(node['rx'],node['ry'],node['rz']);w=[node['wx'],node['wy'],node['wz']];local=sp.mul(sp.transpose(r),w)
            inertia=sp.inertia_matrix(body['inertia']);total+=.5*body['mass']*(node['vx']**2+node['vy']**2+node['vz']**2)+.5*sum(local[i]*sum(inertia[i][j]*local[j] for j in range(3)) for i in range(3))
            total-=body['mass']*sum(g*node[k] for g,k in zip(gravity,'xyz'))
        total+=sum(c['energy']+c['dissipatedEnergy']+c.get('frictionEnergy',0.) for c in sample['contactStates'])
        values.append(total)
    return max(abs(v-values[0]) for v in values)

def native_consistency(model,samples):
    """MBDyn's applied friction against mu*N*tanh(slip/v_s) rebuilt from the body motion."""
    contacts={c['id']:c for c in model['contacts']};worst=0.
    for sample in samples:
        for state in sample['contactStates']:
            contact=contacts[state['id']]
            expected=sp.friction(contact)*state['force']*math.tanh(state['slip']/sp.slip_velocity(contact))
            worst=max(worst,abs(state['frictionForce']-expected))
    return worst

def rolling_ball(v0=2.,mu=.3,vs=.02,step=.0005,duration=.45):
    """A sliding ball spins up: v = v0 - mu g t until it rolls at 5/7 v0 from t = 2 v0 / (7 mu g)."""
    m,R,k=1.,.1,1e5;I=.4*m*R*R;z0=R-m*G/k
    model={'kind':'spatial-assembly','name':'Rolling ball','parameters':{'gravity':{'x':0.,'y':0.,'z':-G}},'simulation':{'duration':duration,'step':step},
           'bodies':[{'id':'ball','name':'Ball','mass':m,'inertia':{'xx':I,'yy':I,'zz':I},'pose':{'x':0.,'y':0.,'z':z0,'rx':0.,'ry':0.,'rz':0.},'velocity':{'vx':v0,'vy':0.,'vz':0.,'wx':0.,'wy':0.,'wz':0.}}],
           'joints':[],'contacts':[{'id':'floor','body':'ball','center':{'x':0.,'y':0.,'z':0.},'radius':R,'planePoint':{'x':0.,'y':0.,'z':0.},'planeNormal':{'x':0.,'y':0.,'z':1.},'stiffness':k,'friction':mu,'slipVelocity':vs}]}
    result,directory=run(model)
    if not result['ok']:return {'name':'rolling ball','ok':False,'error':result}
    samples=result['samples']
    # Independent RK4 of the same regularised law with the static normal force m g.
    def rates(state):
        v,w=state;s=v-R*w;force=-mu*m*G*math.tanh(s/vs);return force/m,-R*force/I
    dt=1e-5;state=(v0,0.);tick=0;velocity_error=spin_error=0.
    for sample in samples:
        while tick<round(sample['time']/dt):
            a=rates(state);b=rates((state[0]+a[0]*dt/2,state[1]+a[1]*dt/2));c=rates((state[0]+b[0]*dt/2,state[1]+b[1]*dt/2));d=rates((state[0]+c[0]*dt,state[1]+c[1]*dt))
            state=(state[0]+dt*(a[0]+2*b[0]+2*c[0]+d[0])/6,state[1]+dt*(a[1]+2*b[1]+2*c[1]+d[1])/6);tick+=1
        node=sample['nodes'][0];velocity_error=max(velocity_error,abs(node['vx']-state[0]));spin_error=max(spin_error,abs(node['wy']-state[1]))
    transition=2*v0/(7*mu*G);sliding=[s for s in samples if s['time']<.9*transition]
    deceleration=(sliding[0]['nodes'][0]['vx']-sliding[-1]['nodes'][0]['vx'])/(sliding[-1]['time']-sliding[0]['time'])
    rolled=next(s['time'] for s in samples if s['contactStates'][0]['slip']<vs)
    final=samples[-1]['nodes'][0]
    case={'name':'rolling ball','runId':result['runId'],'samples':len(samples),'step':step,'slipVelocity':vs,
          'finalSpeed':final['vx'],'expectedFinalSpeed':5*v0/7,'rollingRadiusError':abs(final['vx']-R*final['wy']),
          'deceleration':deceleration,'expectedDeceleration':mu*G,'rollingFrom':rolled,'expectedRollingFrom':transition,
          'maxVelocityErrorVsRk4':velocity_error,'maxSpinErrorVsRk4':spin_error,'maxNativeFrictionError':native_consistency(model,samples),
          'maxEnergyError':energy_error(model,samples),'frictionEnergy':samples[-1]['contactStates'][0]['frictionEnergy'],'expectedFrictionEnergy':.5*m*v0*v0*2/7}
    case['ok']=(abs(case['finalSpeed']-case['expectedFinalSpeed'])<1e-3 and case['rollingRadiusError']<1e-3 and abs(deceleration/(mu*G)-1)<1e-3
                and abs(rolled-transition)<.01 and velocity_error<2e-3 and spin_error<2e-2 and case['maxNativeFrictionError']<1e-6
                and case['maxEnergyError']<1e-3 and abs(case['frictionEnergy']/case['expectedFrictionEnergy']-1)<5e-3)
    return case

def block(normal,slope_deg,mu,v0,duration,vs=.01,step=.0005):
    """A block on four corner spheres slides down-slope on a plane with a general world orientation."""
    # Light contact damping settles the block's pitching on its corner springs once it stops.
    m,a,h,r,k,damping=2.,.2,.05,.01,5e3,10.;n=unit(normal)
    seed=[1.,0.,0.] if abs(n[0])<.9 else [0.,1.,0.];x=unit(sp.cross(seed,n));y=sp.cross(n,x)
    theta=math.radians(slope_deg);down=x;gravity=[G*(-math.cos(theta)*ni+math.sin(theta)*di) for ni,di in zip(n,down)]
    rx,ry,rz=euler123([[x[i],y[i],n[i]] for i in range(3)]);rest=h/2-m*G*math.cos(theta)/(4*k)
    corners=[(sx*(a/2-r),sy*(a/2-r),-h/2+r) for sx in (-1,1) for sy in (-1,1)]
    inertia={'xx':m*(a*a+h*h)/12,'yy':m*(a*a+h*h)/12,'zz':m*a*a/6}
    model={'kind':'spatial-assembly','name':'Sliding block','parameters':{'gravity':dict(zip('xyz',gravity))},'simulation':{'duration':duration,'step':step},
           'bodies':[{'id':'block','name':'Block','mass':m,'inertia':inertia,'pose':{**dict(zip('xyz',[rest*c for c in n])),'rx':rx,'ry':ry,'rz':rz},'velocity':{**dict(zip(('vx','vy','vz'),[v0*c for c in down])),'wx':0.,'wy':0.,'wz':0.}}],
           'joints':[],'contacts':[{'id':f'corner{i}','body':'block','center':dict(zip('xyz',c)),'radius':r,'planePoint':{'x':0.,'y':0.,'z':0.},'planeNormal':dict(zip('xyz',n)),'stiffness':k,'damping':damping,'friction':mu,'slipVelocity':vs} for i,c in enumerate(corners)]}
    result,directory=run(model)
    label=f'block, normal ({n[0]:.2f}, {n[1]:.2f}, {n[2]:.2f}), {slope_deg:g}° slope, mu {mu}'
    if not result['ok']:return {'name':label,'ok':False,'error':result}
    samples=result['samples'];along=lambda node,keys:sum(node[k]*d for k,d in zip(keys,down))
    acceleration=G*(math.sin(theta)-mu*math.cos(theta));stop=-v0/acceleration if acceleration<0 else math.inf
    position_error=velocity_error=0.;moving=[s for s in samples if s['time']<.97*min(stop,duration)]
    for sample in moving:
        node=sample['nodes'][0];t=sample['time']
        position_error=max(position_error,abs(along(node,'xyz')-along(samples[0]['nodes'][0],'xyz')-(v0*t+.5*acceleration*t*t)));velocity_error=max(velocity_error,abs(along(node,('vx','vy','vz'))-(v0+acceleration*t)))
    case={'name':label,'runId':result['runId'],'normal':n,'samples':len(samples),'acceleration':acceleration,'maxPositionError':position_error,'maxVelocityError':velocity_error,
          'maxNativeFrictionError':native_consistency(model,samples),'maxEnergyError':energy_error(model,samples)}
    ok=position_error<2e-3 and velocity_error<5e-3 and case['maxNativeFrictionError']<1e-6 and case['maxEnergyError']<2e-3
    if math.isfinite(stop):
        travel=along(samples[-1]['nodes'][0],'xyz')-along(samples[0]['nodes'][0],'xyz');distance=v0*v0/(2*-acceleration)
        # Regularised friction cannot hold a block on a slope: it creeps at v_s * atanh(tan(theta)/mu).
        creep=vs*math.atanh(math.tan(theta)/mu);residual=abs(along(samples[-1]['nodes'][0],('vx','vy','vz')))
        case.update(stoppingDistance=travel,expectedStoppingDistance=distance,stoppingTime=stop,finalSpeed=residual,expectedCreepSpeed=creep)
        ok=ok and abs(travel-distance)<.01*distance+creep*(duration-stop) and abs(residual-creep)<.1*creep+5e-4
    case['ok']=ok
    return case

if __name__=='__main__':
    cases=[rolling_ball(),block([0.,0.,1.],0.,.4,2.,.7),block([.36,.48,.8],0.,.4,2.,.7),block([-.48,.6,.64],15.,.5,1.5,1.1),block([.6,0.,.8],25.,.3,.5,.6)]
    report={'solver':'MBDyn 1.7.3','cases':cases,'ok':all(case['ok'] for case in cases),'scope':'Regularised Coulomb friction for spheres on fixed planes: rolling transition, sliding to rest and sliding down slopes. No true stiction.'}
    Path('verification').mkdir(exist_ok=True);Path('verification/contact-friction.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
