"""Compare two installed MBDyn timesteps for the illustrative CAD linkage."""
import copy,json,math
from pathlib import Path
from verify_spatial_assembly import run
project=Path('examples/open-suspension/suspension.mbdyn-studio')
model=json.loads(project.read_text(encoding='utf8'))['model']
coarse,_=run(model)
fine_model=copy.deepcopy(model);fine_model['simulation']['step']/=2
fine,_=run(fine_model)
if not coarse['ok'] or not fine['ok']:raise SystemExit(json.dumps({'coarse':coarse,'fine':fine},indent=2))
assert len(fine['samples'])==2*len(coarse['samples'])-1
errors=[]
for c,f in zip(coarse['samples'],fine['samples'][::2]):
 assert abs(c['time']-f['time'])<1e-10
 a=next(n for n in c['nodes'] if n['id']=='wheel');b=next(n for n in f['nodes'] if n['id']=='wheel')
 errors.append(math.dist([a[k] for k in ('x','y','z')],[b[k] for k in ('x','y','z')]))
travel=max(abs(next(n for n in s['nodes'] if n['id']=='wheel')['z']+.0875) for s in coarse['samples'])
residual=max(coarse['metrics']['maxConstraintError'],fine['metrics']['maxConstraintError'])
metrics={'ok':max(errors)<1e-5 and residual<1e-7 and travel>.01,'coarseStepS':model['simulation']['step'],'fineStepS':fine_model['simulation']['step'],'samples':[len(coarse['samples']),len(fine['samples'])],'maxWheelPositionDifferenceM':max(errors),'maxJointResidualM':residual,'maxWheelVerticalTravelM':travel,'runIds':[coarse['runId'],fine['runId']],'scope':'Inferred, uncalibrated open CAD linkage; time refinement is not physical or CAD-fit validation.'}
Path('verification/open-suspension.json').write_text(json.dumps(metrics,indent=2)+'\n',encoding='utf8');print(json.dumps(metrics,indent=2));raise SystemExit(0 if metrics['ok'] else 1)
