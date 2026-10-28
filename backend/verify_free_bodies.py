"""Real MBDyn free-body cases checked against independent translation and rotation."""
import copy,json,math
from pathlib import Path
import spatial_assembly as spatial
from verify_spatial_assembly import run


def mm(A,v):return [sum(A[i][j]*v[j] for j in range(3)) for i in range(3)]
def rm(A,v):return [sum(A[3*i+j]*v[j] for j in range(3)) for i in range(3)]
def rtm(A,v):return [sum(A[3*j+i]*v[j] for j in range(3)) for i in range(3)]

def verify_free():
 model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-free'))
 result,_=run(model)
 if not result['ok']:return {'ok':False,'name':'free-fall with asymmetric inertia','error':result}
 inertia=[[.1,.01,.005],[.01,.12,-.008],[.005,-.008,.15]]
 a,b,c=inertia[0];d,e=inertia[1][1:];f=inertia[2][2];det=a*d*f+2*b*c*e-a*e*e-d*c*c-f*b*b
 inverse=[[(d*f-e*e)/det,(c*e-b*f)/det,(b*e-c*d)/det],[(c*e-b*f)/det,(a*f-c*c)/det,(b*c-a*e)/det],[(b*e-c*d)/det,(b*c-a*e)/det,(a*d-b*b)/det]]
 orientation=[1.,0.,0.,0.,1.,0.,0.,0.,1.];momentum=mm(inertia,[.8,.5,1.1])
 def rhs(R):
  x,y,z=rm(R,mm(inverse,rtm(R,momentum)));W=[[0,-z,y],[z,0,-x],[-y,x,0]]
  return [sum(W[i][k]*R[3*k+j] for k in range(3)) for i in range(3) for j in range(3)]
 time=0.;position_error=velocity_error=rotation_error=momentum_error=0.
 for sample in result['samples']:
  t=sample['time']
  while t-time>1e-12:
   h=min(.0001,t-time);a1=rhs(orientation);b1=rhs([v+h*x/2 for v,x in zip(orientation,a1)]);c1=rhs([v+h*x/2 for v,x in zip(orientation,b1)]);d1=rhs([v+h*x for v,x in zip(orientation,c1)])
   orientation=[v+h*(a0+2*b0+2*c0+d0)/6 for v,a0,b0,c0,d0 in zip(orientation,a1,b1,c1,d1)];time+=h
  node=sample['nodes'][0];expected=[.2*t,-.1*t,1-9.81*t*t/2];vel=[.2,-.1,-9.81*t]
  position_error=max(position_error,math.dist([node[k] for k in ('x','y','z')],expected));velocity_error=max(velocity_error,math.dist([node[k] for k in ('vx','vy','vz')],vel))
  actual=node['rotationMatrix'];rotation_error=max(rotation_error,max(abs(x-y) for x,y in zip(actual,orientation)))
  observed=rm(actual,mm(inertia,rtm(actual,[node[k] for k in ('wx','wy','wz')])));momentum_error=max(momentum_error,math.dist(observed,momentum))
  assert sample['joints']==[]
 return {'name':'free-fall with asymmetric inertia','ok':position_error<1e-5 and velocity_error<1e-5 and rotation_error<2e-4 and momentum_error<1e-5,'runId':result['runId'],'samples':len(result['samples']),'maxPositionError':position_error,'maxVelocityError':velocity_error,'maxRotationError':rotation_error,'maxAngularMomentumError':momentum_error,'jointCount':result['metrics']['jointCount']}

def verify_disconnected():
 model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-free'));second=copy.deepcopy(model['bodies'][0]);second.update(id='other',name='Other');second['pose']['x']=1.;second['velocity'].update(vx=-.2,vy=.3,wx=0.,wy=0.,wz=0.);model['bodies'].append(second)
 result,_=run(model)
 if not result['ok']:return {'name':'two disconnected bodies','ok':False,'error':result}
 error=0.
 for sample in result['samples']:
  t=sample['time'];a,b=sample['nodes'];error=max(error,math.dist([a['x'],a['y'],a['z']],[.2*t,-.1*t,1-9.81*t*t/2]),math.dist([b['x'],b['y'],b['z']],[1-.2*t,.3*t,1-9.81*t*t/2]))
 return {'name':'two disconnected bodies','ok':error<1e-5,'runId':result['runId'],'maxPositionError':error,'samples':len(result['samples'])}

def verify_contact():
 model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-sphere-contact'));model['joints']=[]
 result,_=run(model)
 if not result['ok']:return {'name':'free sphere-plane impact','ok':False,'error':result}
 z=.3;v=0.;t=0.;error=0.;max_force=0.
 def deriv(q,w):return w,-9.81+1000*max(0,.1-q)
 for sample in result['samples']:
  while sample['time']-t>1e-12:
   h=min(.00001,sample['time']-t);a,b=deriv(z,v);c,d=deriv(z+a*h/2,v+b*h/2);e,f=deriv(z+c*h/2,v+d*h/2);g,k=deriv(z+e*h,v+f*h);z+=h*(a+2*c+2*e+g)/6;v+=h*(b+2*d+2*f+k)/6;t+=h
  error=max(error,abs(sample['nodes'][0]['z']-z));max_force=max(max_force,sample['contactStates'][0]['force'])
 return {'name':'free sphere-plane impact','ok':error<.001 and max_force>10,'runId':result['runId'],'maxPositionError':error,'maxForce':max_force,'samples':len(result['samples'])}

def verify_offset_contact():
 model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-sphere-contact'));model['joints']=[];b=model['bodies'][0];b['centerOfMass']={'x':.03,'y':0.,'z':0.};b['velocity']['wy']=.5
 result,_=run(model)
 if not result['ok']:return {'name':'free offset-COM impact','ok':False,'error':result}
 initial_energy=None;max_error=0.;max_force=0.;angular_change=0.
 for sample in result['samples']:
  node=sample['nodes'][0];R=node['rotationMatrix'];offset=rm(R,[.03,0.,0.]);omega=[node[k] for k in ('wx','wy','wz')];velocity=[node[k] for k in ('vx','vy','vz')];vcom=[x+y for x,y in zip(velocity,spatial.cross(omega,offset))]
  energy=.5*sum(x*x for x in vcom)+.002*sum(x*x for x in omega)+9.81*(node['z']+offset[2])+sample['contactStates'][0]['energy']
  if initial_energy is None:initial_energy=energy
  max_error=max(max_error,abs(energy-initial_energy));max_force=max(max_force,sample['contactStates'][0]['force']);angular_change=max(angular_change,abs(omega[1]-.5))
 return {'name':'free offset-COM impact','ok':max_error<.03 and max_force>10 and angular_change>.01,'runId':result['runId'],'maxEnergyError':max_error,'maxForce':max_force,'angularVelocityChange':angular_change,'samples':len(result['samples'])}

if __name__=='__main__':
 cases=[verify_free(),verify_disconnected(),verify_contact(),verify_offset_contact()];report={'solver':'MBDyn 1.7.3','cases':cases,'ok':all(case['ok'] for case in cases),'scope':'Free rigid-body motion and ideal sphere-plane contact; no hardware validation.'};Path('verification/free-bodies.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
