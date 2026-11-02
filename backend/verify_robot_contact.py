"""Native Coulomb brake and two-body contact against independent mechanics.

Illustrative SI benchmarks, not hardware calibration. Uses the configured real MBDyn.
"""
import copy,hashlib,json,math
from pathlib import Path
import spatial_assembly as sp
from verify_spatial_assembly import run


def vec(x=0.,y=0.,z=0.):return dict(x=x,y=y,z=z)


def body(name,x=0.,mass=1.,velocity=0.):
    return {'id':name,'name':name.title(),'mass':mass,'inertia':dict(xx=.1,yy=.1,zz=.1),'pose':dict(x=x,y=0.,z=0.,rx=0.,ry=0.,rz=0.),'velocity':dict(vx=velocity,vy=0.,vz=0.,wx=0.,wy=0.,wz=0.)}


def brake(torque=.5,step=.001,initial_speed=0.):
    rotor=body('rotor');rotor['velocity']['wz']=initial_speed
    return {'kind':sp.KIND,'name':'Robot joint brake','parameters':{'gravity':vec()},'simulation':{'duration':.2,'step':step},'bodies':[rotor],
            'joints':[{'id':'hinge','type':'revolute','a':'ground','b':'rotor','anchorA':vec(),'anchorB':vec(),'axisA':vec(z=1.),'axisB':vec(z=1.),'friction':{'coefficient':.5,'radius':.1,'preload':20.}}],
            'jointTorques':[{'id':'motor','joint':'hinge','amplitude':0.,'frequencyHz':1.,'offset':torque}]}


def spheres(damping=0.,step=.0005,offset=False):
    a=body('a',-.15,1.,1.);b=body('b',.15,2.,-.5)
    center=vec(y=.04) if offset else vec()
    return {'kind':sp.KIND,'name':'Robot bumper collision','parameters':{'gravity':vec()},'simulation':{'duration':.25,'step':step},'bodies':[a,b],'joints':[],
            'contacts':[{'id':'bumper','type':'sphere-sphere','body':'a','otherBody':'b','center':copy.deepcopy(center),'otherCenter':copy.deepcopy(center),'radius':.1,'otherRadius':.1,'stiffness':1000.,'damping':damping}]}


def main():
    cases=[]
    for torque,ramp,step in [(0.,False,.001),(.5,False,.001),(-.5,False,.001)]+[(t,True,h) for t in (1.5,-1.5) for h in (.001,.0005,.00025)]:
        model=brake(torque,step=step)
        if ramp:model['jointTorques'][0].update(offset=0.,amplitude=torque);model['simulation']['duration']=.4
        result,directory=run(model)
        case={'name':f'brake {torque:g} Nm, sine {ramp}, dt={step:g}','ok':result['ok'],'runId':result.get('runId'),'step':step};cases.append(case)
        if not result['ok']:case.update(error=result.get('error'),log=result.get('log'));continue
        samples=result['samples'];I=.1;alpha=0. if abs(torque)<1. else (torque-math.copysign(1.,torque))/I
        # Initial derivatives are solved before stepping; native static friction balances subthreshold torque.
        crossing=math.asin(1/abs(torque))/(2*math.pi) if ramp else 0.
        def expected_speed(t):
            if ramp:return 0. if t<=crossing else (torque*(math.cos(2*math.pi*crossing)-math.cos(2*math.pi*t))/(2*math.pi)-math.copysign(t-crossing,torque))/I
            return alpha*t
        def expected_torque(t):return -torque*math.sin(2*math.pi*t) if ramp and t<=crossing else -torque if alpha==0 else -math.copysign(1.,torque)
        away=[s for s in samples[1:] if not ramp or abs(s['time']-crossing)>2*step]
        case.update(maxSpeedError=max(abs(s['nodes'][0]['wz']-expected_speed(s['time'])) for s in samples),maxTorqueError=max(abs(s['jointFrictionStates'][0]['torque']-expected_torque(s['time'])) for s in away),minimumPower=min(s['jointFrictionStates'][0]['power'] for s in samples),finalEnergy=samples[-1]['jointFrictionStates'][0]['dissipatedEnergy'])
        case['maxEnergyBalanceError']=max(abs(.5*I*s['nodes'][0]['wz']**2+s['jointFrictionStates'][0]['dissipatedEnergy']-s['actuationWork']) for s in samples)
        if ramp:
            case.update(analyticalBreakaway=crossing,observedBreakaway=next(s['time'] for s in samples if abs(s['nodes'][0]['wz'])>1e-12),maxHeldSpeed=max(abs(s['nodes'][0]['wz']) for s in samples if s['time']<crossing-step))
        case['ok']=case['maxSpeedError']<1e-4 and case['maxTorqueError']<1e-7 and case['minimumPower']>-1e-8 and case['maxEnergyBalanceError']<2e-5 and (not ramp or abs(case['observedBreakaway']-crossing)<3*step and case['maxHeldSpeed']<1e-12)
    result,directory=run(brake(1.5))
    cases.append({'name':'abrupt superthreshold startup rejected','ok':not result['ok'] and 'produces energy' in str(result.get('error')) and directory is not None and (directory/'result.jnt').is_file(),'runId':result.get('runId'),'diagnostic':result.get('error')})
    for damping in (0.,8.):
        for step in (.001,.0005,.00025):
            model=spheres(damping,step);result,directory=run(model);case={'name':f'spheres c={damping:g} dt={step:g}','ok':result['ok'],'runId':result.get('runId')};cases.append(case)
            if not result['ok']:case.update(error=result.get('error'),log=result.get('log'));continue
            samples=result['samples'];mu=2/3;u=1.5;omega=math.sqrt(1000/mu);duration=math.pi/omega;impact=.1/u;E0=.75
            momentum=max(abs(s['nodes'][0]['vx']+2*s['nodes'][1]['vx']) for s in samples)
            energy=max(abs(.5*s['nodes'][0]['vx']**2+s['nodes'][1]['vx']**2+s['contactStates'][0]['energy']+s['contactStates'][0]['dissipatedEnergy']-E0) for s in samples)
            force_error=max(abs(s['contactStates'][0]['force']-(1000*s['contactStates'][0]['penetration']+damping*max(0.,-sum(n*v for n,v in zip([1.,0.,0.],[s['nodes'][1]['vx']-s['nodes'][0]['vx'],0.,0.]))) if s['contactStates'][0]['gap']<0 else 0.)) for s in samples)
            case.update(step=step,maxMomentumError=momentum,maxEnergyError=energy,maxNativeForceError=force_error,finalSpeeds=[n['vx'] for n in samples[-1]['nodes']],dissipated=samples[-1]['contactStates'][0]['dissipatedEnergy'])
            # Independent two-mass relative-coordinate RK4; native rod constitutive code is not reused.
            q=.3;v=-u;t=0.;max_position=max_speed=0.;h=1e-5
            def rates(q,v):return v,(1000*max(0.,.2-q)+(damping*max(0.,-v) if q<.2 else 0.))/mu
            for sample in samples:
                while sample['time']-t>1e-10:
                    dt=min(h,sample['time']-t);a,b=rates(q,v);c,d=rates(q+a*dt/2,v+b*dt/2);e,f=rates(q+c*dt/2,v+d*dt/2);g,k=rates(q+e*dt,v+f*dt)
                    q+=dt*(a+2*c+2*e+g)/6;v+=dt*(b+2*d+2*f+k)/6;t+=dt
                a,b=sample['nodes'];max_position=max(max_position,abs((b['x']-a['x'])-q));max_speed=max(max_speed,abs((b['vx']-a['vx'])-v))
            case.update(maxReferencePositionError=max_position,maxReferenceSpeedError=max_speed)
            if damping==0:
                case['maxAnalyticalForceError']=max(abs(s['contactStates'][0]['force']-(1000*u/omega*math.sin(omega*(s['time']-impact)) if impact<=s['time']<=impact+duration else 0.)) for s in samples)
            case['ok']=momentum<1e-8 and energy<.004 and force_error<1e-7 and max_position<.0005 and max_speed<.01 and (damping>0 or max(abs(a-b) for a,b in zip(case['finalSpeeds'],[-1.,.5]))<.002)
    model=spheres(8.,.000125,offset=True)
    model['bodies'][0]['pose'].update(rx=20.,rz=30.);model['bodies'][1]['pose'].update(ry=-17.)
    result,directory=run(model);case={'name':'offset centers on rotated moving bodies','ok':result['ok'],'runId':result.get('runId')};cases.append(case)
    if not result['ok']:case.update(error=result.get('error'),log=result.get('log'))
    else:
        momenta=[];angular_momenta=[];energies=[];vector_error=0.;spin=0.
        for sample in result['samples']:
            p=[0.,0.,0.];H=[0.,0.,0.];E=0.;nodes=sample['nodes'];contact=sample['contactStates'][0]
            for definition,node in zip(model['bodies'],nodes):
                velocity=[node[k] for k in ('vx','vy','vz')];omega=[node[k] for k in ('wx','wy','wz')];mass=definition['mass'];linear=[mass*v for v in velocity];p=[a+b for a,b in zip(p,linear)]
                # Isotropic inertia is invariant under the arbitrary body orientation in this case.
                H=[a+b+.1*w for a,b,w in zip(H,sp.cross(sp.xyz(node),linear),omega)];E+=.5*mass*sum(v*v for v in velocity)+.05*sum(w*w for w in omega);spin=max(spin,sp.norm(omega))
            a=sp.anchor({'pose':nodes[0]},model['contacts'][0]['center']);b=sp.anchor({'pose':nodes[1]},model['contacts'][0]['otherCenter']);delta=sp.sub(a,b);length=sp.norm(delta)
            vector_error=max(vector_error,max(abs(contact['forceOnBody'][axis]-contact['force']*delta[i]/length) for i,axis in enumerate('xyz')),max(abs(contact['forceOnBody'][axis]+contact['forceOnOther'][axis]) for axis in 'xyz'))
            momenta.append(p);angular_momenta.append(H);energies.append(E+contact['energy']+contact['dissipatedEnergy'])
        case.update(maxMomentumError=max(math.dist(p,momenta[0]) for p in momenta),maxAngularMomentumError=max(math.dist(H,angular_momenta[0]) for H in angular_momenta),maxEnergyError=max(abs(E-energies[0]) for E in energies),maxForceVectorError=vector_error,maxSpin=spin)
        case['ok']=case['maxMomentumError']<1e-7 and case['maxAngularMomentumError']<1e-7 and case['maxEnergyError']<.002 and vector_error<1e-7 and spin>.1
    # Refinement must improve the independently calculated errors, not merely complete three runs.
    for prefix,field in [('brake 1.5 Nm, sine True','maxSpeedError'),('brake -1.5 Nm, sine True','maxSpeedError'),('spheres c=0','maxReferencePositionError'),('spheres c=8','maxReferencePositionError')]:
        selected=[c for c in cases if c['name'].startswith(prefix)]
        if len(selected)!=3 or not all(c['ok'] for c in selected) or not selected[-1][field]<selected[0][field]/2:cases.append({'name':f'{prefix} refinement','ok':False})
    import solver
    executable=Path(solver.configuration()['executable'])
    for case in cases:
        if 'runId' not in case:continue
        directory=solver.RUNS/case['runId']
        case['modelSha256']=hashlib.sha256((directory/'project.json').read_bytes()).hexdigest();case['deckSha256']=hashlib.sha256((directory/'model.mbd').read_bytes()).hexdigest()
    output={'ok':all(c['ok'] for c in cases),'scope':'Illustrative numerical benchmarks; no hardware or material calibration. Brakes start held; sphere pairs have normal force only.','nativeExecutableSha256':hashlib.sha256(executable.read_bytes()).hexdigest() if executable.is_file() else None,'verifierSha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),'deckGeneratorSha256':hashlib.sha256(Path(sp.__file__).read_text(encoding='utf-8').encode()).hexdigest(),'cases':cases}
    target=Path(__file__).resolve().parents[1]/'examples/robot-contact-verification.json';target.write_text(json.dumps(output,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output,indent=2));return output


if __name__=='__main__':raise SystemExit(0 if main()['ok'] else 1)
