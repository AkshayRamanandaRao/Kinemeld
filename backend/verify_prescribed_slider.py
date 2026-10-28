"""Compare actual MBDyn slider motion against the prescribed trajectory."""
import copy
import json
import math
from pathlib import Path

import spatial_assembly as spatial
from verify_spatial_assembly import run


def main():
    cases = []
    for amplitude in (.1, -.07):
        for step in (.001, .0005):
            model = copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id'] == 'spatial-prismatic'))
            model['bodies'][0]['velocity'].update(vx=0, vy=0)
            model['joints'][0]['motion'] = {'amplitude':amplitude, 'frequencyHz':1.}
            model['simulation']['step'] = step
            result, _ = run(model)
            case = {'amplitude':amplitude, 'step':step, 'runId':result.get('runId'), 'ok':result['ok']}
            if result['ok']:
                samples = result['samples']
                case['maxPositionErrorM'] = max(abs(s['sliders'][0]['position']-(.3+amplitude*(1-math.cos(2*math.pi*s['time'])))) for s in samples)
                case['maxVelocityErrorMS'] = max(abs(s['sliders'][0]['velocity']-amplitude*2*math.pi*math.sin(2*math.pi*s['time'])) for s in samples)
                case['maxTransverseErrorM'] = max(s['sliders'][0]['transverse'] for s in samples)
                case['samples'] = len(samples)
                case['ok'] = case['maxPositionErrorM'] < 1e-7 and case['maxVelocityErrorMS'] < 1e-5 and case['maxTransverseErrorM'] < 1e-7
            else:
                case['error'] = result.get('error')
            cases.append(case)
    model = copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id'] == 'spatial-prismatic'))
    model['parameters']['gravity'] = dict.fromkeys(('x','y','z'), 0.)
    model['simulation'] = {'duration':.4,'step':.001}
    carrier = copy.deepcopy(model['bodies'][0]); carrier.update(id='carrier',name='Carrier')
    carrier['pose'].update(x=0,y=0,z=0); carrier['velocity'].update(vx=0,vy=0,vz=0)
    rotation=spatial.body_rotation(carrier); axis=spatial.mul(rotation,[0,0,1]); omega=spatial.mul(rotation,[1,0,0])
    carrier['velocity'].update(zip(('wx','wy','wz'),omega)); block=model['bodies'][0]
    block['pose']['rx']+=25
    anchor_a={'x':.1,'y':.04,'z':-.02}; anchor_b={'x':.07,'y':-.03,'z':.02}
    parent_anchor=spatial.mul(rotation,spatial.xyz(anchor_a)); child_anchor=spatial.mul(spatial.body_rotation(block),spatial.xyz(anchor_b))
    offset=[a+.5*u-b for a,u,b in zip(parent_anchor,axis,child_anchor)]
    velocity=spatial.cross(omega,offset); block['pose'].update(zip(('x','y','z'),offset))
    block['velocity'].update(zip(('vx','vy','vz'),velocity)); block['velocity'].update(zip(('wx','wy','wz'),omega))
    model['bodies'].insert(0,carrier); zero=dict.fromkeys(('x','y','z'),0.)
    model['joints']=[{'id':'ball','type':'spherical','a':'ground','b':'carrier','anchorA':zero.copy(),'anchorB':zero.copy()},
      {'id':'guide','type':'prismatic','a':'carrier','b':'block','anchorA':anchor_a,'anchorB':anchor_b,'axisA':{'x':0,'y':0,'z':1},'motion':{'amplitude':.1,'frequencyHz':1}}]
    result,_=run(model); case={'name':'rotating parent','runId':result.get('runId'),'ok':result['ok']}
    if result['ok']:
        case['maxPositionErrorM']=max(abs(s['sliders'][0]['position']-(.5+.1*(1-math.cos(2*math.pi*s['time'])))) for s in result['samples'])
        case['maxVelocityErrorMS']=max(abs(s['sliders'][0]['velocity']-.2*math.pi*math.sin(2*math.pi*s['time'])) for s in result['samples'])
        case['ok']=case['maxPositionErrorM']<1e-7 and case['maxVelocityErrorMS']<1e-5
    else:case['error']=result.get('error')
    cases.append(case)
    fixture=json.loads(Path('examples/prescribed-wheel-bump/wheel-bump.mbdyn-studio').read_text(encoding='utf8'))['model']
    result,_=run(fixture); case={'name':'open CAD wheel-end travel fixture','runId':result.get('runId'),'ok':result['ok']}
    if result['ok']:
        case['maxPositionErrorM']=max(abs(s['sliders'][0]['position']-.025*(1-math.cos(2*math.pi*s['time']))) for s in result['samples'])
        case['ok']=case['maxPositionErrorM']<1e-7
    else:case['error']=result.get('error')
    cases.append(case)
    report={'ok':all(c['ok'] for c in cases),'solver':'MBDyn 1.7.3','cases':cases,'scope':'Representative prismatic joints with prescribed cosine displacement. Does not establish actuator forces or hardware validation.'}
    Path('verification/prescribed-slider.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
