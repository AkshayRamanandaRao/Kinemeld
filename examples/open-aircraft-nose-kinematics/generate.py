"""Create a constrained kinematic demonstration from the original STEP occurrences."""
import base64, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import spatial_assembly as spatial
import step_mass
from step_example_identity import identify_authored_step

HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'examples/open-aircraft-nose-gear/source-assembly.step'
SHA='b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575'
# STEP assembly coordinates are translated to put the original axle centre at z = 0.35 m.
SHIFT={'x':1.3624089479151387,'y':.1404889931316861,'z':.6763863684055106}
GROUPS={'strut':[3], 'slider':[1,2,5], 'upper_link':[4,7], 'lower_link':[6,8,9], 'left_wheel':[10], 'right_wheel':[11]}

def main():
 data=SOURCE.read_bytes()
 if hashlib.sha256(data).hexdigest()!=SHA:raise ValueError('Source STEP hash mismatch')
 model=json.loads((HERE/'inferred-model-template.json').read_text(encoding='utf8'))
 model['name']='Aircraft gear · KINEMATIC ONLY · loads invalid · source overlaps'
 model['simulation']={'duration':.5,'step':.001}
 witnesses={f'0:part-{i}':{'scheme':'step-nauo-id-path/1','path':[f'NAUO{i}']} for i in range(1,12)}
 asset={'name':SOURCE.name,'sha256':SHA,'byteLength':len(data),'data':base64.b64encode(data).decode('ascii')}
 step={'schemaVersion':1,'format':'step','files':[asset],'bindings':{}}
 identify_authored_step(step,witnesses)
 records={i:step_mass.calculate(data,1100. if i in (10,11) else 2700.,f'part-{i}',witnesses[f'0:part-{i}']) for i in range(1,12)}
 bindings={}
 for body in model['bodies']:
  parts=GROUPS[body['id']];mass=sum(records[i]['mass'] for i in parts)
  center=[sum(records[i]['mass']*records[i]['centerOfMass'][axis] for i in parts)/mass for axis in 'xyz']
  matrix=[[0.]*3 for _ in range(3)]
  for i in parts:
   record=records[i];delta=[record['centerOfMass'][axis]-center[n] for n,axis in enumerate('xyz')];r2=sum(x*x for x in delta)
   for a in range(3):
    for b in range(3):matrix[a][b]+=record['inertia'][a][b]+record['mass']*((r2 if a==b else 0)-delta[a]*delta[b])
  body['mass']=mass;body['centerOfMass']={axis:center[n]-SHIFT[axis]-body['pose'][axis] for n,axis in enumerate('xyz')}
  body['inertia']={'xx':matrix[0][0],'yy':matrix[1][1],'zz':matrix[2][2],'xy':matrix[0][1],'xz':matrix[0][2],'yz':matrix[1][2]}
  binding={**{k:body['pose'][k]+SHIFT[k] for k in 'xyz'},'rx':0.,'ry':0.,'rz':0.}
  for i in parts:bindings[f'0:part-{i}']={'body':body['id'],'pose':binding.copy()}
 check=spatial.validate(model)
 if not check['valid']:raise ValueError(check)
 step['bindings']=bindings
 project={'format':'mbdyn-studio/1','model':model,'assets':{'step':step}}
 (HERE/'nose-gear-kinematics.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'masses':{b['id']:b['mass'] for b in model['bodies']},'sourceSha256':SHA,'bindings':len(bindings)},indent=2))

if __name__=='__main__':main()
