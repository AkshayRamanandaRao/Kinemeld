"""Check constraint wrenches against independent Newton/Euler balances in MBDyn."""
import copy
import json
import math
from pathlib import Path

import spatial_assembly as spatial
from verify_spatial_assembly import run


def vector(x,y,z):return {'x':x,'y':y,'z':z}
def example(kind,moving=False):
    model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-revolute'))
    model['name']='Reaction balance '+kind;model['simulation']={'duration':.04,'step':.001};model['parameters']['gravity']=vector(0,0,0)
    body=model['bodies'][0];body['pose'].update(x=0,y=0,z=0,rx=0,ry=0,rz=0);body['velocity']=dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)
    joint={'id':'reaction','type':kind,'a':'ground','b':'arm','anchorA':vector(0,.5,0),'anchorB':vector(0,.5,0)}
    if kind in ('revolute','prismatic','cylindrical','universal'):joint['axisA']=vector(0,0,1)
    if kind in ('revolute','cylindrical'):joint['axisB']=vector(0,0,1)
    if kind=='universal':joint['axisB']=vector(0,1,0)
    if kind=='prescribed':joint.update(type='prismatic',axisA=vector(0,0,1),motion={'amplitude':.01,'frequencyHz':1.})
    if moving:
        joint['anchorA']=joint['anchorB']=vector(0,0,0)
        carrier=copy.deepcopy(body);carrier['id']='carrier';carrier['name']='Carrier';carrier['velocity']['wz']=1.;body['velocity']['wz']=1.
        model['bodies'].insert(0,carrier);joint['a']='carrier'
    model['joints']=[joint]
    force=vector(11,17,0 if kind in ('prismatic','cylindrical') else 23)
    # Spherical and universal/revolute free moments are balanced at the displaced anchor.
    torque={'spherical':vector(11.5,0,-5.5),'revolute':vector(3,5,-5.5),'universal':vector(3,0,-5.5),
            'prismatic':vector(3,5,7),'cylindrical':vector(3,5,-5.5),'weld':vector(3,5,7),'prescribed':vector(3,5,7)}[kind]
    if moving:force=vector(11,17,0);torque=vector(0,0,0)
    model['loads']=[{'id':'load','body':'arm','frame':'global','point':vector(0,0,0),'force':force,'torque':torque,'offset':1.,'amplitude':0.,'frequencyHz':1.}]
    return model


def main():
    cases=[]
    for kind in ('spherical','revolute','universal','prismatic','cylindrical','weld','prescribed'):
        model=example(kind);result,directory=run(model)
        if not result['ok']:raise SystemExit(json.dumps({'kind':kind,'result':result},indent=2))
        force=model['loads'][0]['force'];torque=model['loads'][0]['torque'];r=[0,-.5,0]
        moment=spatial.cross(r,spatial.xyz(force));target_m=[-(moment[i]+spatial.xyz(torque)[i]) for i in range(3)]
        force_errors=[];moment_errors=[]
        # Initial derivative solution and the first post-initial step need not have settled acceleration reactions.
        checked=result['samples'][2:] if kind=='prescribed' else result['samples']
        for sample in checked:
            reaction=sample['jointReactions'][0];a=.01*(2*math.pi)**2*math.cos(2*math.pi*sample['time']) if kind=='prescribed' else 0.
            expected=[-force['x'],-force['y'],-force['z']+a];expected_m=[target_m[0]-.5*a,target_m[1],target_m[2]]
            force_errors.extend(abs(reaction['force'][k]-expected[i]) for i,k in enumerate('xyz'));moment_errors.extend(abs(reaction['moment'][k]-expected_m[i]) for i,k in enumerate('xyz'))
        force_error,moment_error=max(force_errors),max(moment_errors);cases.append({'kind':kind,'runId':result['runId'],'maxForceBalanceErrorN':force_error,'maxMomentBalanceErrorNm':moment_error,'excludedStartupSamples':2 if kind=='prescribed' else 0,'ok':max(force_error,moment_error)<2e-3})
    for kind in ('spherical','revolute','universal','prismatic','cylindrical','weld'):
        model=example(kind,True);result,directory=run(model)
        if not result['ok']:raise SystemExit(json.dumps({'kind':kind,'moving':True,'result':result},indent=2))
        errors=[abs(s['jointReactions'][0]['force'][k]-target) for s in result['samples'] for k,target in zip('xyz',(-5.5,-8.5,0))]
        error=max(errors);cases.append({'kind':kind,'movingParent':True,'runId':result['runId'],'maxForceBalanceErrorN':error,'ok':error<2e-3})
    report={'solver':'MBDyn 1.7.3','ok':all(case['ok'] for case in cases),'cases':cases,'scope':'Representative ideal joint constraints; separate springs, drives, contacts and real bearing loads are excluded.'}
    print(json.dumps(report,indent=2))
    if not report['ok']:raise SystemExit(1)
    Path('verification/joint-reactions.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')


if __name__=='__main__':main()
