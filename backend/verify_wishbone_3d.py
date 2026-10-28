"""Verify the illustrative 3D wishbone against independent reduced dynamics."""
import json, math
from pathlib import Path
import spatial_assembly as spatial
from verify_spatial_assembly import run

project=Path('examples/wishbone-3d/wishbone.mbdyn-studio')
model=json.loads(project.read_text(encoding='utf8'))['model']
result,_=run(model)
if not result['ok']:raise SystemExit(str(result))
lower,upper,upright=model['bodies'];spring=model['forces'][0]
r0=.2+lower['centerOfMass']['y'];radius=.4
inertia=sum(b['inertia']['xx']+b['mass']*(.2+b['centerOfMass']['y'])**2 for b in (lower,upper))+upright['mass']*radius**2
grav=9.81*(sum(b['mass']*(.2+b['centerOfMass']['y']) for b in (lower,upper))+upright['mass']*radius)
def derivative(angle,omega,t):
    length=math.sqrt(.45-.36*math.sin(angle));dl=-.18*math.cos(angle)/length
    tension=spring['stiffness']*(length-spring['restLength'])+spring['damping']*dl*omega
    excitation=20*math.sin(4*math.pi*t)
    return omega,(-grav*math.cos(angle)-tension*dl+excitation*radius*math.cos(angle))/inertia
angle=omega=0.;now=0.;errors=[];angles=[];forces=[]
for sample in result['samples']:
    while sample['time']-now>1e-12:
        h=min(.0001,sample['time']-now);a,b=derivative(angle,omega,now);c,d=derivative(angle+a*h/2,omega+b*h/2,now+h/2);e,f=derivative(angle+c*h/2,omega+d*h/2,now+h/2);g,j=derivative(angle+e*h,omega+f*h,now+h);angle+=h*(a+2*c+2*e+g)/6;omega+=h*(b+2*d+2*f+j)/6;now+=h
    n=next(n for n in sample['nodes'] if n['id']=='upright');expected=(0,radius*math.cos(angle),.175+radius*math.sin(angle));errors.append(math.dist([n['x'],n['y'],n['z']],expected));angles.append(abs(next(n for n in sample['nodes'] if n['id']=='lower')['rx']-math.degrees(angle)))
    length=math.sqrt(.45-.36*math.sin(angle));dl=-.18*math.cos(angle)/length;forces.append(abs(sample['forces'][0]['force']-(spring['stiffness']*(length-spring['restLength'])+spring['damping']*dl*omega)))
metrics={'ok':max(errors)<1e-4 and max(angles)<.03 and max(forces)<.05 and result['metrics']['maxConstraintError']<1e-7,'runId':result['runId'],'samples':len(result['samples']),'maxPositionErrorM':max(errors),'maxAngleErrorDeg':max(angles),'maxSpringForceErrorN':max(forces),'maxJointResidualM':result['metrics']['maxConstraintError'],'maxTravelM':max(abs(s['nodes'][2]['z']-.175) for s in result['samples']),'inertiaKgM2':inertia,'scope':'Symmetric illustrative 3D linkage, not a validated vehicle or tire.'}
Path('verification/wishbone-3d.json').write_text(json.dumps(metrics,indent=2),encoding='utf8');print(json.dumps(metrics,indent=2));raise SystemExit(0 if metrics['ok'] else 1)
