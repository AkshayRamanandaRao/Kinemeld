"""Verify two timesteps of a sourced-CAD drop by independent energy accounting."""
import copy,json
from pathlib import Path
import spatial_assembly as sp
from verify_spatial_assembly import run
original=json.loads(Path('examples/open-wheel-end/wheel-end-drop.mbdyn-studio').read_text(encoding='utf8'))['model']
cases=[]
for step in (.0005,.00025):
 model=copy.deepcopy(original);model['simulation']['step']=step
 result,_=run(model)
 if not result['ok']:raise SystemExit(json.dumps(result,indent=2))
 initial=None;errors=[];forces=[];diss=[]
 for sample in result['samples']:
  energy=0.
  for body in model['bodies']:
   n=next(node for node in sample['nodes'] if node['id']==body['id']);pose={k:n[k] for k in ('x','y','z','rx','ry','rz')};velocity={k:n[k] for k in ('vx','vy','vz','wx','wy','wz')};state={'pose':pose,'velocity':velocity};r=sp.body_rotation(state);offset=sp.mul(r,sp.xyz(body['centerOfMass']));w=sp.angular(state);v=sp.anchor_velocity(state,body['centerOfMass']);wb=sp.mul(sp.transpose(r),w);iw=sp.mul(sp.inertia_matrix(body['inertia']),wb)
   energy+=.5*body['mass']*sum(x*x for x in v)+.5*sum(x*y for x,y in zip(wb,iw))+body['mass']*9.81*(n['z']+offset[2])
  c=sample['contactStates'][0];energy+=c['energy']+c['dissipatedEnergy'];forces.append(c['force']);diss.append(c['dissipatedEnergy'])
  if initial is None:initial=energy
  errors.append(abs(energy-initial))
 cases.append({'step':step,'runId':result['runId'],'samples':len(result['samples']),'maxContactForceN':max(forces),'dissipatedEnergyJ':diss[-1],'maxEnergyBalanceErrorJ':max(errors),'maxConstraintErrorM':result['metrics']['maxConstraintError']})
ok=all(c['maxContactForceN']>10 and c['dissipatedEnergyJ']>0 and c['maxEnergyBalanceErrorJ']<.1 and c['maxConstraintErrorM']<1e-6 for c in cases)
report={'ok':ok,'cases':cases,'scope':'Open-CAD free rigid wheel end with ideal frictionless compression-damped sphere-plane contact; no tire calibration, rim, suspension or OEM validation.'}
Path('verification/open-wheel-end-drop.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if ok else 1)
