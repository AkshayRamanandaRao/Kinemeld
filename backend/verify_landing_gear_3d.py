"""Verify a STEP-backed two-body landing-gear drop against independent RK4 dynamics."""
import copy,json,math
from pathlib import Path
from verify_spatial_assembly import run

project=Path('examples/landing-gear-3d/landing-gear-drop.mbdyn-studio')
original=json.loads(project.read_text(encoding='utf8'))['model']

def verify(model):
 result,_=run(model)
 if not result['ok']:return {'ok':False,'error':result}
 upper,wheel=model['bodies'];spring=model['forces'][0];contact=model['contacts'][0]
 mu,mw=upper['mass'],wheel['mass'];stiffness,damping,rest=(spring[key] for key in ('stiffness','damping','restLength'));kc,radius=contact['stiffness'],contact['radius']
 # State is [upper height, wheel height, upper speed, wheel speed].
 y=[upper['pose']['z'],wheel['pose']['z'],upper['velocity']['vz'],wheel['velocity']['vz']];time=0.
 def derivative(state):
  zu,zw,vu,vw=state;separation=zu-zw
  if separation<=0:raise ValueError('Reference crossed the spring direction singularity.')
  force=stiffness*(separation-rest)+damping*(vu-vw);tire=kc*max(0.,radius-zw)
  return [vu,vw,-9.81-force/mu,-9.81+(force+tire)/mw]
 position_error=velocity_error=spring_error=contact_error=0.;peak=0.;compression=0.;first=None
 for sample in result['samples']:
  target=sample['time']
  while target-time>1e-12:
   h=min(.00001,target-time);a=derivative(y);b=derivative([v+h*x/2 for v,x in zip(y,a)]);c=derivative([v+h*x/2 for v,x in zip(y,b)]);d=derivative([v+h*x for v,x in zip(y,c)]);y=[v+h*(aa+2*bb+2*cc+dd)/6 for v,aa,bb,cc,dd in zip(y,a,b,c,d)];time+=h
  nodes={n['id']:n for n in sample['nodes']};position_error=max(position_error,abs(nodes['upper']['z']-y[0]),abs(nodes['wheel']['z']-y[1]));velocity_error=max(velocity_error,abs(nodes['upper']['vz']-y[2]),abs(nodes['wheel']['vz']-y[3]))
  reference_spring=stiffness*(y[0]-y[1]-rest)+damping*(y[2]-y[3]);reference_tire=kc*max(0.,radius-y[1]);observed_tire=sample['contactStates'][0]['force'];spring_error=max(spring_error,abs(sample['forces'][0]['force']-reference_spring));contact_error=max(contact_error,abs(observed_tire-reference_tire));peak=max(peak,observed_tire);compression=max(compression,rest-(nodes['upper']['z']-nodes['wheel']['z']))
  if observed_tire>0 and first is None:first=sample['time']
 return {'ok':position_error<.003 and velocity_error<.05 and spring_error<50 and contact_error<150 and peak>100 and compression>.01 and first is not None and result['metrics']['maxConstraintError']<1e-7,'stepS':model['simulation']['step'],'runId':result['runId'],'samples':len(result['samples']),'maxPositionErrorM':position_error,'maxVelocityErrorM_s':velocity_error,'maxStrutForceErrorN':spring_error,'maxContactForceErrorN':contact_error,'firstContactS':first,'peakContactN':peak,'maxStrutCompressionM':compression,'maxJointResidualM':result['metrics']['maxConstraintError']}

baseline=verify(original);refined=copy.deepcopy(original);refined['simulation']['step']/=2;fine=verify(refined)
report={'ok':baseline['ok'] and fine['ok'] and fine['maxPositionErrorM']<baseline['maxPositionErrorM'] and fine['maxVelocityErrorM_s']<baseline['maxVelocityErrorM_s'],'cases':[baseline,fine],'scope':'Illustrative vertical two-mass drop with ideal elastic tire, not a validated aircraft.'}
Path('verification/landing-gear-3d.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
