"""Check original-CAD wheel-end MBDyn dynamics against an independent rigid-axis solution."""
import copy,json,math
from pathlib import Path
from verify_spatial_assembly import run
project=json.loads(Path('examples/open-wheel-end/wheel-end.mbdyn-studio').read_text(encoding='utf8'))
def check(step):
 model=copy.deepcopy(project['model']);model['simulation']['step']=step;result,_=run(model)
 if not result['ok']:return {'ok':False,'step':step,'error':result}
 wheel=model['bodies'][1];c=wheel['centerOfMass'];J=wheel['inertia']['xx']+wheel['mass']*(c['y']**2+c['z']**2);w0=wheel['velocity']['wx'];offset=.5;amp=.2;omega=4*math.pi
 angle_errors=[];rate_errors=[];work_errors=[]
 for s in result['samples']:
  n=next(n for n in s['nodes'] if n['id']=='wheel');t=s['time'];angle=w0*t+offset*t*t/(2*J)+amp*(omega*t-math.sin(omega*t))/(J*omega*omega);rate=w0+offset*t/J+amp*(1-math.cos(omega*t))/(J*omega)
  angle_errors.append(abs(math.radians(n['rx'])-angle));rate_errors.append(abs(n['wx']-rate));work_errors.append(abs(s['actuationWork']-.5*J*(n['wx']**2-w0**2)))
 return {'ok':max(angle_errors)<2e-4 and max(rate_errors)<2e-4 and max(work_errors)<1e-4 and result['metrics']['maxConstraintError']<1e-7,'stepS':step,'runId':result['runId'],'samples':len(result['samples']),'effectiveAxisInertiaKgM2':J,'maxAngleErrorRad':max(angle_errors),'maxAngularVelocityErrorRadS':max(rate_errors),'maxWorkBalanceErrorJ':max(work_errors),'maxConstraintErrorM':result['metrics']['maxConstraintError']}
cases=[check(.001),check(.0005)];report={'ok':all(c['ok'] for c in cases) and cases[1]['maxAngleErrorRad']<cases[0]['maxAngleErrorRad'],'cases':cases,'scope':'Rigid wheel-end, prescribed axis torque, illustrative density and inferred alignment; no road contact or OEM validation.'}
Path('verification/open-wheel-end.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
