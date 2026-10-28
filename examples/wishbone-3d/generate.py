"""Generate original STEP parts and a matching illustrative spatial suspension project."""
import base64
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
import primitive_step
import step_mass
from step_example_identity import identify_authored_step
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.gp import gp_Pnt, gp_Vec

OUT=Path(__file__).resolve().parent

def prism(points,z,height):
    polygon=BRepBuilderAPI_MakePolygon()
    for x,y in points:polygon.Add(gp_Pnt(x,y,z))
    polygon.Close()
    return BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(polygon.Wire()).Face(),gp_Vec(0,0,height)).Shape()

def arm_step(z,path):
    # Original triangular plate wishbone, millimetres, in the model's world coordinates.
    outer=prism([(-180,0),(180,0),(0,400)],1000*z-15,30)
    inner=prism([(-100,40),(100,40),(0,280)],1000*z-16,32)
    shape=BRepAlgoAPI_Cut(outer,inner).Shape()
    if shape.IsNull():raise ValueError('Could not cut the control-arm opening.')
    Interface_Static.SetCVal_s('write.step.unit','MM');writer=STEPControl_Writer()
    if writer.Transfer(shape,STEPControl_AsIs)!=IFSelect_RetDone or writer.Write(str(path))!=IFSelect_RetDone:raise ValueError('STEP export failed.')

def v(x,y,z):return {'x':x,'y':y,'z':z}
def props(path,density,pose):
    result=step_mass.calculate(path.read_bytes(),density,'part-1');M=result['inertia'];com=result['centerOfMass']
    body={'mass':result['mass'],'inertia':{'xx':M[0][0],'yy':M[1][1],'zz':M[2][2],'xy':M[0][1],'xz':M[0][2],'yz':M[1][2]},'centerOfMass':{k:com[k]-pose[k] for k in ('x','y','z')}}
    return body

def main():
    lower=OUT/'lower-arm.step';upper=OUT/'upper-arm.step';upright=OUT/'upright.step';arm_step(0.,lower);arm_step(.35,upper)
    pose_u={'x':0.,'y':.4,'z':.175,'rx':0.,'ry':0.,'rz':0.}
    upright.write_bytes(primitive_step.generate_step({'shape':'brick','dimensions':{'x':.05,'y':.05,'z':.35},'pose':pose_u}))
    bodies=[]
    for identifier,filename,pos,density in [('lower',lower,v(0,.2,0),2700.),('upper',upper,v(0,.2,.35),2700.),('upright',upright,v(0,.4,.175),7800.)]:
        pose={**pos,'rx':0.,'ry':0.,'rz':0.};bodies.append({'id':identifier,'name':identifier.title(),**props(filename,density,pose),'pose':pose,'velocity':dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)})
    model={'kind':'spatial-assembly','name':'3D double-wishbone teaching model','parameters':{'gravity':v(0,0,-9.81)},'simulation':{'duration':.5,'step':.0005},'bodies':bodies,
      'joints':[{'id':'lower_pivot','type':'revolute','a':'ground','b':'lower','anchorA':v(0,0,0),'anchorB':v(0,-.2,0),'axisA':v(1,0,0),'axisB':v(1,0,0)},
       {'id':'upper_pivot','type':'revolute','a':'ground','b':'upper','anchorA':v(0,0,.35),'anchorB':v(0,-.2,0),'axisA':v(1,0,0),'axisB':v(1,0,0)},
       {'id':'lower_ball','type':'spherical','a':'lower','b':'upright','anchorA':v(0,.2,0),'anchorB':v(0,0,-.175)},
       {'id':'upper_ball','type':'spherical','a':'upper','b':'upright','anchorA':v(0,.2,0),'anchorB':v(0,0,.175)}],
      'forces':[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'lower','anchorA':v(0,0,.6),'anchorB':v(0,.1,0),'stiffness':3000.,'damping':30.,'restLength':.62}],
      'loads':[{'id':'hub_excitation','body':'upright','frame':'global','point':v(0,0,0),'force':v(0,0,20),'torque':v(0,0,0),'offset':0.,'amplitude':1.,'frequencyHz':2.}]}
    files=[];bindings={}
    for i,(body,path) in enumerate(zip(bodies,[lower,upper,upright])):
        data=path.read_bytes();files.append({'name':path.name,'sha256':hashlib.sha256(data).hexdigest(),'byteLength':len(data),'data':base64.b64encode(data).decode('ascii')});bindings[f'{i}:part-1']={'body':body['id'],'pose':body['pose']}
    project={'format':'mbdyn-studio/1','model':model,'assets':{'step':{'schemaVersion':1,'format':'step','files':files,'bindings':bindings}}}
    identify_authored_step(project['assets']['step'], {key:None for key in bindings})
    (OUT/'wishbone.mbdyn-studio').write_text(json.dumps(project,indent=2)+'\n',encoding='utf8');print(json.dumps({'bodies':bodies,'bytes':sum(x['byteLength'] for x in files)},indent=2))
if __name__=='__main__':main()
