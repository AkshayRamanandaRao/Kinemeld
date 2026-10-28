"""Build an engineering study from unmodified, MIT-licensed source STEP files."""
import base64,copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'backend'))
import step_mass
from step_example_identity import identify_authored_step
OUT=Path(__file__).resolve().parent;SOURCE=ROOT/'examples/step-suspension'
FILES=[('Assembly 1 - Knuckle_Left Knuckle.step',7850.,'knuckle'),('Assembly 1 - Hub.step',7850.,'wheel'),('Assembly 1 - Front Tyre.step',1100.,'wheel')]
SHA=['670681b02f1923520f49d46eb6fe0166040eb43869283566f04fba7f2a4313b9','5a035846fcd27121ac5337484b4f5e791b5deb3349030faff4768eed0c0ffbdb','a0b7e75748354b03547decf398d0257d79442c051c330956d208136fac7255d0']
def v(x,y,z):return {'x':x,'y':y,'z':z}
def props(data,density):return step_mass.calculate(data,density,'part-1')
def inertia(m):return {'xx':m[0][0],'yy':m[1][1],'zz':m[2][2],'xy':m[0][1],'xz':m[0][2],'yz':m[1][2]}
def main():
    records=[]
    for (name,density,body),sha in zip(FILES,SHA):
        data=(SOURCE/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=sha:raise ValueError(f'Source SHA mismatch: {name}')
        records.append((name,body,data,props(data,density)))
    knuckle=records[0][3];parts=[record[3] for record in records[1:]];mass=sum(p['mass'] for p in parts);center=[sum(p['mass']*p['centerOfMass'][k] for p in parts)/mass for k in ('x','y','z')]
    matrix=[[0.]*3 for _ in range(3)]
    for p in parts:
        delta=[p['centerOfMass'][k]-center[i] for i,k in enumerate(('x','y','z'))];r2=sum(x*x for x in delta)
        for i in range(3):
            for j in range(3):matrix[i][j]+=p['inertia'][i][j]+p['mass']*((r2 if i==j else 0)-delta[i]*delta[j])
    hinge=v(-.04,-.0875,0.);pose={**hinge,'rx':0.,'ry':0.,'rz':0.};zero=dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)
    bodies=[{'id':'knuckle','name':'Knuckle','mass':knuckle['mass'],'inertia':inertia(knuckle['inertia']),'centerOfMass':{k:knuckle['centerOfMass'][k]-hinge[k] for k in hinge},'pose':pose.copy(),'velocity':zero.copy()},
            {'id':'wheel','name':'Hub and tyre','mass':mass,'inertia':inertia(matrix),'centerOfMass':dict(zip(('x','y','z'),center)),'pose':pose.copy(),'velocity':{**zero,'wx':.2}}]
    model={'kind':'spatial-assembly','name':'Open-CAD wheel-end torque study','parameters':{'gravity':v(0,0,0)},'simulation':{'duration':.5,'step':.001},'bodies':bodies,
      'joints':[{'id':'fixture','type':'weld','a':'ground','b':'knuckle','anchorA':hinge.copy(),'anchorB':v(0,0,0)},
                {'id':'hub_axis','type':'revolute','a':'knuckle','b':'wheel','anchorA':v(0,0,0),'anchorB':v(0,0,0),'axisA':v(1,0,0),'axisB':v(1,0,0)}],
      'jointTorques':[{'id':'drive','joint':'hub_axis','offset':.5,'amplitude':.2,'frequencyHz':2.}]}
    files=[];bindings={};zero_pose={'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.}
    for i,(name,body,data,_) in enumerate(records):
        files.append({'name':name,'sha256':hashlib.sha256(data).hexdigest(),'byteLength':len(data),'data':base64.b64encode(data).decode('ascii')})
        bindings[f'{i}:part-1']={'body':body,'pose':pose.copy() if body=='knuckle' else zero_pose.copy()}
    project={'format':'mbdyn-studio/1','model':model,'assets':{'step':{'schemaVersion':1,'format':'step','files':files,'bindings':bindings}}}
    identify_authored_step(project['assets']['step'], {key:None for key in bindings})
    (OUT/'wheel-end.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8')
    drop=copy.deepcopy(project);drop['model']['name']='Open-CAD wheel-end drop study';drop['model']['parameters']['gravity']=v(0,0,-9.81);drop['model']['simulation']={'duration':.5,'step':.0005}
    drop['model']['joints']=[drop['model']['joints'][1]];drop['model'].pop('jointTorques')
    for b in drop['model']['bodies']:b['pose']['z']=.6;b['velocity']['vz']=-1.
    drop['model']['contacts']=[{'id':'tire_plane','body':'wheel','center':v(0,0,0),'radius':.208,'planePoint':v(0,0,0),'planeNormal':v(0,0,1),'stiffness':20000.,'damping':100.}]
    (OUT/'wheel-end-drop.mbdyn-studio').write_text(json.dumps(drop,indent=2)+'\n',encoding='utf8');print(json.dumps({'masses_kg':{b['id']:b['mass'] for b in bodies},'wheelCenterLocal':center,'wheelIxx':matrix[0][0],'originalStepBytes':sum(len(r[2]) for r in records)},indent=2))
if __name__=='__main__':main()
