"""Compare the idealized source-CAD linkage against two-circle planar geometry."""
import copy,json,math
from pathlib import Path
from verify_spatial_assembly import run

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio'

def independent_scissor(model,q):
 joints={j['id']:j for j in model['joints']};bodies={b['id']:b for b in model['bodies']}
 upper=bodies['upper_link']['pose'];lower=bodies['lower_link']['pose'];pivot=(upper['y'],upper['z']);target=(lower['y'],lower['z']+q)
 joint=joints['scissor_pin'];a=joint['anchorA'];b=joint['anchorB'];r1=math.hypot(a['y'],a['z']);r2=math.hypot(b['y'],b['z'])
 dy,dz=target[0]-pivot[0],target[1]-pivot[1];distance=math.hypot(dy,dz)
 if distance<=0 or distance>r1+r2 or distance<abs(r1-r2):raise ValueError('No two-circle linkage solution')
 ux,uy=dy/distance,dz/distance;along=(r1*r1-r2*r2+distance*distance)/(2*distance);height=math.sqrt(max(0.,r1*r1-along*along))
 center=(pivot[0]+along*ux,pivot[1]+along*uy);candidates=[(center[0]-s*height*uy,center[1]+s*height*ux) for s in (-1,1)]
 initial=(pivot[0]+a['y'],pivot[1]+a['z'])
 return min(candidates,key=lambda p:math.dist(p,initial))

def actual_scissor(sample,model):
 upper=next(n for n in sample['nodes'] if n['id']=='upper_link');joint=next(j for j in model['joints'] if j['id']=='scissor_pin');a=joint['anchorA'];angle=math.radians(upper['rx']);c,s=math.cos(angle),math.sin(angle)
 return (upper['y']+c*a['y']-s*a['z'],upper['z']+s*a['y']+c*a['z'])

def main():
 model=json.loads(PROJECT.read_text(encoding='utf8'))['model'];coarse,_=run(model)
 finer=copy.deepcopy(model);finer['simulation']['step']/=2;fine,_=run(finer)
 if not coarse['ok'] or not fine['ok']:raise SystemExit(json.dumps({'coarse':coarse,'fine':fine},indent=2))
 if len(fine['samples'])!=2*len(coarse['samples'])-1:raise ValueError('Unexpected time alignment')
 errors=[];refinement=[];offplane=[]
 for c,f in zip(coarse['samples'],fine['samples'][::2]):
  if abs(c['time']-f['time'])>1e-10:raise ValueError('Samples are not time aligned')
  q=.005*(1-math.cos(2*math.pi*c['time']));errors.append(math.dist(actual_scissor(c,model),independent_scissor(model,q)))
  for ident in ('slider','upper_link','lower_link','left_wheel','right_wheel'):
   left=next(n for n in c['nodes'] if n['id']==ident);right=next(n for n in f['nodes'] if n['id']==ident)
   refinement.append(math.dist([left[k] for k in 'xyz'],[right[k] for k in 'xyz']))
  for ident in ('upper_link','lower_link'):
   node=next(n for n in c['nodes'] if n['id']==ident);offplane.append(abs(node['x']))
 report={'ok':max(errors)<1e-8 and max(refinement)<1e-7 and max(offplane)<1e-8,'sourceSha256':'b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575','durationS':.5,'coarseStepS':.001,'fineStepS':.0005,'maxScissorGeometryErrorM':max(errors),'maxBodyPositionRefinementDifferenceM':max(refinement),'maxLinkOutOfPlaneTranslationM':max(offplane),'maxConstraintResidualM':max(coarse['metrics']['maxConstraintError'],fine['metrics']['maxConstraintError']),'runIds':[coarse['runId'],fine['runId']],'scope':'Prescribed zero-gravity kinematic fixture with inferred nonphysical joint substitutions and overlapping STEP solids; not aircraft load or physical validation.'}
 out=ROOT/'verification/aircraft-nose-kinematics.json';out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2))
 if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
