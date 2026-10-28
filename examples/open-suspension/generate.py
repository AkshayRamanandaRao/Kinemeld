"""Build a source-STEP linkage with explicitly inferred connections."""
import base64, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import step_mass
from step_example_identity import identify_authored_step
OUT=Path(__file__).resolve().parent
SOURCE=ROOT/'examples/step-suspension'

def vec(x,y,z): return {'x':x,'y':y,'z':z}
def inertia(m): return {'xx':m[0][0],'yy':m[1][1],'zz':m[2][2],'xy':m[0][1],'xz':m[0][2],'yz':m[1][2]}
def pose(v,rx=90.,ry=0.): return {**v,'rx':rx,'ry':ry,'rz':0.}
def sub(a,b): return {k:a[k]-b[k] for k in 'xyz'}
def source_body(name,identifier,origin,world,ry=0.):
 data=(SOURCE/name).read_bytes(); p=step_mass.calculate(data,7850.,'part-1')
 body={'id':identifier,'name':identifier.title(),'mass':p['mass'],'inertia':inertia(p['inertia']),'centerOfMass':sub(p['centerOfMass'],origin),'pose':pose(world,ry=ry),'velocity':dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)}
 asset={'name':name,'sha256':hashlib.sha256(data).hexdigest(),'byteLength':len(data),'data':base64.b64encode(data).decode('ascii')}
 return body,asset

def main():
 upper_cad=vec(.18,0,-.095); lower_cad=vec(0,0,-.225225); knuckle_cad=vec(.035,0,.0125)
 knuckle_world=vec(.035,-.0125,0);upper_world=vec(.035,-.0125,.04);lower_world=vec(.035,.0125,-.209);wheel_world=vec(-.04,0,-.0875)
 upper,au=source_body('Assembly 1 - Upper Control Arm_Default-As Machined-.step','upper',upper_cad,upper_world)
 lower,al=source_body('Assembly 1 - Lower Control Arm_Default-As Machined-.step','lower',lower_cad,lower_world,-90.)
 knuckle,ak=source_body('Assembly 1 - Knuckle_Left Knuckle.step','knuckle',knuckle_cad,knuckle_world)
 original=json.loads((ROOT/'examples/open-wheel-end/wheel-end.mbdyn-studio').read_text(encoding='utf8'))
 wheel=original['model']['bodies'][1];wheel['pose']=pose(wheel_world);wheel['velocity']=dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)
 aw=original['assets']['step']['files'][1:]
 # One measured bore on each arm defines a hypothetical axis; the second chassis mount is not established.
 upper_pivot=sub(vec(-.011,0,.0175),upper_cad);lower_pivot=sub(vec(-.110,0,.011),lower_cad)
 up_axis=vec(0,0,1);low_axis=vec(1,0,0)
 def world_pos(body,local):
  import spatial_assembly as s
  return dict(zip('xyz',s.anchor(body,local)))
 up_world=world_pos(upper,upper_pivot);low_world=world_pos(lower,lower_pivot)
 lower_knuckle=sub(vec(.035,-.169,-.0125),knuckle_cad);wheel_knuckle=sub(vec(-.04,-.0875,0),knuckle_cad)
 model={'kind':'spatial-assembly','name':'Open-CAD inferred double wishbone','parameters':{'gravity':vec(0,0,-9.81)},'simulation':{'duration':.15,'step':.0005},'bodies':[upper,lower,knuckle,wheel],
  'joints':[{'id':'upper_pivot','type':'revolute','a':'ground','b':'upper','anchorA':up_world,'anchorB':upper_pivot,'axisA':vec(0,-1,0),'axisB':up_axis},
   {'id':'lower_pivot','type':'revolute','a':'ground','b':'lower','anchorA':low_world,'anchorB':lower_pivot,'axisA':vec(0,-1,0),'axisB':low_axis},
   {'id':'upper_ball','type':'spherical','a':'upper','b':'knuckle','anchorA':vec(0,-.04,0),'anchorB':vec(0,0,0)},
   {'id':'lower_ball','type':'spherical','a':'lower','b':'knuckle','anchorA':vec(0,.04,0),'anchorB':lower_knuckle},
   {'id':'hub_axis','type':'revolute','a':'knuckle','b':'wheel','anchorA':wheel_knuckle,'anchorB':vec(0,0,0),'axisA':vec(1,0,0),'axisB':vec(1,0,0)}],
  'forces':[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'lower','anchorA':vec(-.15,.0125,.35),'anchorB':vec(0,0,.08),'stiffness':2500.,'damping':30.,'restLength':.53}],
  'frames':[{'id':'vehicle','name':'Vehicle axes','body':'ground','translation':vec(0,0,0),'rotation':{'rx':0,'ry':0,'rz':-90}}]}
 assets=[au,al,ak,*aw];zero=pose(vec(0,0,0),rx=0)
 bindings={f'{i}:part-1':{'body':body,'pose':pose(origin,rx=0)} for i,(body,origin) in enumerate([('upper',upper_cad),('lower',lower_cad),('knuckle',knuckle_cad),('wheel',vec(0,0,0)),('wheel',vec(0,0,0))])}
 project={'format':'mbdyn-studio/1','model':model,'assets':{'step':{'schemaVersion':1,'format':'step','files':assets,'bindings':bindings}}}
 identify_authored_step(project['assets']['step'], {key:None for key in bindings})
 (OUT/'suspension.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'bodyMasses':{b['id']:b['mass'] for b in model['bodies']},'pivots':[up_world,low_world]},indent=2))
if __name__=='__main__':main()
