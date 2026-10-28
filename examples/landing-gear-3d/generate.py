"""Generate original STEP solids and an illustrative two-body landing-gear drop project."""
import base64, hashlib, json, math, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import primitive_step
import spatial_assembly as spatial
import step_mass
from step_example_identity import identify_authored_step

OUT=Path(__file__).resolve().parent

def vector(x,y,z):return {'x':x,'y':y,'z':z}
def body(identifier,name,pose,shape,dimensions,density,path):
    data=primitive_step.generate_step({'shape':shape,'dimensions':dimensions,'pose':pose});path.write_bytes(data)
    measured=step_mass.calculate(data,density,'part-1');rotation=spatial.rotation(*(pose[k] for k in ('rx','ry','rz')))
    matrix=spatial.matmul(spatial.matmul(spatial.transpose(rotation),measured['inertia']),rotation)
    center=spatial.mul(spatial.transpose(rotation),[measured['centerOfMass'][k]-pose[k] for k in ('x','y','z')])
    inertia={'xx':matrix[0][0],'yy':matrix[1][1],'zz':matrix[2][2],'xy':matrix[0][1],'xz':matrix[0][2],'yz':matrix[1][2]}
    return {'id':identifier,'name':name,'mass':measured['mass'],'inertia':inertia,'centerOfMass':dict(zip(('x','y','z'),center)),
            'pose':pose,'velocity':{'vx':0.,'vy':0.,'vz':-1.5,'wx':0.,'wy':0.,'wz':0.}}


def main():
    upper_pose={'x':0.,'y':0.,'z':1.,'rx':0.,'ry':0.,'rz':0.};wheel_pose={'x':0.,'y':0.,'z':.35,'rx':90.,'ry':0.,'rz':0.}
    upper_path=OUT/'strut.step';wheel_path=OUT/'wheel.step'
    upper=body('upper','Upper strut',upper_pose,'cylinder',{'radius':.09,'length':1.1},100/(math.pi*.09**2*1.1),upper_path)
    wheel=body('wheel','Wheel',wheel_pose,'cylinder',{'radius':.15,'length':.10},5/(math.pi*.15**2*.10),wheel_path)
    model={'kind':'spatial-assembly','name':'3D landing-gear drop teaching model','parameters':{'gravity':vector(0,0,-9.81)},'simulation':{'duration':.7,'step':.0005},'bodies':[upper,wheel],
      'joints':[{'id':'oleo','type':'prismatic','a':'upper','b':'wheel','anchorA':vector(0,0,0),'anchorB':vector(0,0,0),'axisA':vector(0,0,1)}],
      'forces':[{'id':'strut','type':'linear-spring-damper','a':'wheel','b':'upper','anchorA':vector(0,0,0),'anchorB':vector(0,0,0),'stiffness':12000.,'damping':900.,'restLength':.65}],
      'contacts':[{'id':'tire','body':'wheel','center':vector(0,0,0),'radius':.15,'planePoint':vector(0,0,0),'planeNormal':vector(0,0,1),'stiffness':250000.}]}
    check=spatial.validate(model)
    if not check['valid']:raise ValueError(check)
    files=[];bindings={}
    for i,(item,path) in enumerate(zip([upper,wheel],[upper_path,wheel_path])):
        data=path.read_bytes();files.append({'name':path.name,'sha256':hashlib.sha256(data).hexdigest(),'byteLength':len(data),'data':base64.b64encode(data).decode('ascii')});bindings[f'{i}:part-1']={'body':item['id'],'pose':item['pose']}
    project={'format':'mbdyn-studio/1','model':model,'assets':{'step':{'schemaVersion':1,'format':'step','files':files,'bindings':bindings}}}
    identify_authored_step(project['assets']['step'], {key:None for key in bindings})
    (OUT/'landing-gear-drop.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8');print(json.dumps({'bodies':[upper,wheel],'geometryBytes':sum(f['byteLength'] for f in files)},indent=2))
if __name__=='__main__':main()
