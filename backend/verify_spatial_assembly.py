import copy,json,math,uuid
from pathlib import Path
import spatial_assembly as spatial
import solver

def run(model):
 check=spatial.validate(model)
 if not check['valid']:return {'ok':False,'error':check['issues']},None
 info=solver.status()
 if not info['available']:return {'ok':False,'error':info},None
 run_id=uuid.uuid4().hex;directory=solver.RUNS/run_id;directory.mkdir(parents=True)
 (directory/'model.mbd').write_text(spatial.deck(model),encoding='utf8')
 (directory/'project.json').write_text(json.dumps(model,indent=2),encoding='utf8')
 outcome=solver.execute(solver.command(solver.configuration(),['-f','model.mbd','-o','result'],directory,bounded=True),directory)
 if outcome.get('exitCode')!=0:return {'ok':False,'runId':run_id,'error':outcome,'log':(directory/'solver.log').read_text(errors='replace')[-8000:]},directory
 try:
  if 'MBDyn terminated normally' not in (directory/'solver.log').read_text(errors='replace'):raise ValueError('Solver did not terminate normally')
  samples=spatial.parse_output(directory,model);spatial.write_csv(directory/'results.csv',samples)
  return {'ok':True,'runId':run_id,'samples':samples,'metrics':spatial.metrics(model,samples)},directory
 except (OSError,ValueError) as exc:return {'ok':False,'runId':run_id,'error':str(exc),'log':(directory/'solver.log').read_text(errors='replace')[-3000:]},directory

def main():
 cases=[]
 for item in (item for item in spatial.EXAMPLES if item['id'] in ('spatial-spherical','spatial-revolute')):
  result,_=run(item['model']); cases.append({'name':item['id'],'ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')})
  if result['ok']:
   cases[-1].update(metrics=result['metrics'],start=result['samples'][0],end=result['samples'][-1])
   if item['id']=='spatial-revolute':
    # Independent rigid pendulum equation: theta rotates the initial COM about +Y.
    theta=omega=t=0.; ref=[]; dt=.0001
    def deriv(q,w):return (w,9.81*math.sin(math.pi/6-q)/1.1)
    def evolve(q,w,h):
     a,b=deriv(q,w);c,d=deriv(q+a*h/2,w+b*h/2);e,f=deriv(q+c*h/2,w+d*h/2);g,k=deriv(q+e*h,w+f*h)
     return q+h*(a+2*c+2*e+g)/6,w+h*(b+2*d+2*f+k)/6
    for sample in result['samples']:
     while sample['time']-t>1e-12:
      h=min(dt,sample['time']-t);theta,omega=evolve(theta,omega,h);t+=h
     expected=[.5*math.cos(theta)-.8660254037844386*math.sin(theta),0,-.5*math.sin(theta)-.8660254037844386*math.cos(theta)]
     actual=sample['nodes'][0];ref.append(math.dist(expected,[actual['x'],actual['y'],actual['z']]))
    cases[-1]['maxReferencePositionError']=max(ref)
 weld=copy.deepcopy(spatial.EXAMPLES[0]['model']);weld['name']='Welded body';weld['joints'][0]={'id':'weld','type':'weld','a':'ground','b':'bob','anchorA':{'x':.5,'y':0.,'z':-.8660254037844386},'anchorB':{'x':0.,'y':0.,'z':0.}}
 result,_=run(weld);cases.append({'name':'ground-weld','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')})
 if result['ok']:cases[-1].update(metrics=result['metrics'],end=result['samples'][-1])
 # A genuinely spatial spherical pendulum, with consistent nonzero initial velocity.
 ball=copy.deepcopy(spatial.EXAMPLES[0]['model']);ball['bodies'][0]['velocity'].update(vy=.25,wz=.5)
 result,_=run(ball);case={'name':'spatial-spherical-out-of-plane','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  case.update(metrics=result['metrics'],maxOutOfPlane=max(abs(s['nodes'][0]['y']) for s in result['samples']))
  case['ok'] = case['maxOutOfPlane'] > .05 and result['metrics']['maxConstraintError'] < 1e-6
 # Two bodies, three joints: a loop whose second body spins about its spherical endpoints.
 loop=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-closed-loop'))
 result,_=run(loop);case={'name':'spatial-closed-loop','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  node=result['samples'][-1]['nodes'][1];case.update(metrics=result['metrics'],end=node)
  # Rodrigues formula for rotation of one radian/second about axle direction.
  u=[0,2/math.sqrt(5),1/math.sqrt(5)];angle=result['samples'][-1]['time'];c=math.cos(angle);sn=math.sin(angle)
  expected=[[c*(i==j)+(1-c)*u[i]*u[j]+sn*([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]][i][j]) for j in range(3)] for i in range(3)]
  case['maxRotationMatrixError']=max(abs(node['rotationMatrix'][3*i+j]-expected[i][j]) for i in range(3) for j in range(3))
  case['ok']=result['metrics']['maxConstraintError']<1e-6 and case['maxRotationMatrixError']<1e-3
 # Nontrivial initial orientation and local anchor/axis transformations.
 tilted=copy.deepcopy(spatial.EXAMPLES[1]['model']);b=tilted['bodies'][0];b['pose'].update(rx=20,ry=30,rz=-10)
 rt=spatial.transpose(spatial.body_rotation(b)); tilted['joints'][0]['anchorB']=dict(zip(('x','y','z'),spatial.mul(rt,[-.5,0,.8660254037844386])))
 tilted['joints'][0]['axisB']=dict(zip(('x','y','z'),spatial.mul(rt,[0,1,0])))
 result,_=run(tilted);case={'name':'spatial-tilted-body','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  case.update(metrics=result['metrics'],initial=result['samples'][0]['nodes'][0]);initial=case['initial']['rotationMatrix'];expected=[x for row in spatial.body_rotation(b) for x in row];case['initialMatrixError']=max(abs(a-b) for a,b in zip(initial,expected));case['ok']=case['initialMatrixError']<1e-9 and result['metrics']['maxConstraintError']<1e-6 and result['metrics']['maxJointAngularError']<1e-6
 # Oblique fixed guide: q = 0.3 + 0.2 t - 1.5 t² in metres.
 slider=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-prismatic'))
 result,_=run(slider);case={'name':'spatial-prismatic-oblique','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  case['maxReferencePositionError']=max(abs(sample['sliders'][0]['position']-(.3+.2*sample['time']-1.5*sample['time']**2)) for sample in result['samples'])
  case['maxReferenceVelocityError']=max(abs(sample['sliders'][0]['velocity']-(.2-3*sample['time'])) for sample in result['samples'])
  case['metrics']=result['metrics'];case['ok']=case['maxReferencePositionError']<1e-4 and case['maxReferenceVelocityError']<1e-4
 # Moving guide: a free spherical carrier and a slider conserve angular momentum.
 moving=copy.deepcopy(slider);moving['name']='Moving-axis slider';moving['parameters']['gravity']={'x':0,'y':0,'z':0};moving['simulation']['duration']=.4
 carrier=copy.deepcopy(moving['bodies'][0]);carrier['id']='carrier';carrier['name']='Carrier';carrier['pose'].update(x=0,y=0,z=0);carrier['velocity'].update(vx=0,vy=0,vz=0)
 r=spatial.body_rotation(carrier);axis=spatial.mul(r,[0,0,1]);omega=spatial.mul(r,[1,0,0]);carrier['velocity'].update(zip(('wx','wy','wz'),omega))
 block=moving['bodies'][0];offset=[.5*x for x in axis];vel=[a+.2*b for a,b in zip(spatial.cross(omega,offset),axis)];block['pose'].update(zip(('x','y','z'),offset));block['pose']['rx']+=25;block['velocity'].update(zip(('vx','vy','vz'),vel));block['velocity'].update(zip(('wx','wy','wz'),omega))
 moving['bodies'].insert(0,carrier);moving['joints']=[{'id':'ball','type':'spherical','a':'ground','b':'carrier','anchorA':{'x':0,'y':0,'z':0},'anchorB':{'x':0,'y':0,'z':0}}, {'id':'guide','type':'prismatic','a':'carrier','b':'block','anchorA':{'x':0,'y':0,'z':0},'anchorB':{'x':0,'y':0,'z':0},'axisA':{'x':0,'y':0,'z':1}}]
 result,_=run(moving);case={'name':'spatial-prismatic-moving-axis','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  # r'' = r H²/(I + m r²)²; H = 0.45, I = 0.2, m = 1.
  q=.5;velocity=.2;time=0.;errors=[]
  def derivatives(position,speed):return speed,position*(.45/(.2+position*position))**2
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a,b=derivatives(q,velocity);c,d=derivatives(q+h*a/2,velocity+h*b/2);e,f=derivatives(q+h*c/2,velocity+h*d/2);g,k=derivatives(q+h*e,velocity+h*f);q+=h*(a+2*c+2*e+g)/6;velocity+=h*(b+2*d+2*f+k)/6;time+=h
   errors.append(abs(sample['sliders'][0]['position']-q))
  case.update(maxReferencePositionError=max(errors),metrics=result['metrics']);case['ok']=case['maxReferencePositionError']<1e-4 and result['metrics']['maxConstraintError']<1e-6
 # Cylindrical guide permits simultaneous spin and translation on an oblique fixed axis.
 cylindrical=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-cylindrical'))
 result,_=run(cylindrical);case={'name':'spatial-cylindrical-oblique','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  position_errors=[];angle_errors=[]
  for sample in result['samples']:
   t=sample['time'];state=sample['cylinders'][0];position_errors.append(abs(state['position']-(.3+.2*t-1.5*t*t)));angle_errors.append(abs(state['angle']-1.2*t))
  case.update(maxReferencePositionError=max(position_errors),maxReferenceAngleError=max(angle_errors),metrics=result['metrics']);case['ok']=case['maxReferencePositionError']<1e-4 and case['maxReferenceAngleError']<1e-4
 # Cylindrical spin and sliding with a torsional spring and sinusoidal torque.
 cylinder_drive=copy.deepcopy(cylindrical);cylinder_drive['parameters']['gravity']={'x':0.,'y':0.,'z':0.};cylinder_drive['simulation']['duration']=.3
 cylinder_drive['rotationalElements']=[{'id':'torsion','joint':'guide','stiffness':1.,'damping':.1,'restAngleDeg':15.}]
 cylinder_drive['jointTorques']=[{'id':'drive','joint':'guide','amplitude':.2,'frequencyHz':2.,'offset':.1}]
 result,_=run(cylinder_drive);case={'name':'spatial-cylindrical-spring-torque','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  q=0.;omega=1.2;time=0.;angle_errors=[];position_errors=[];rest=math.radians(15.)
  def derivative(t,angle,speed):return speed,(-1.*(angle-rest)-.1*speed+.1+.2*math.sin(4*math.pi*t))/.1
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a,b=derivative(time,q,omega);c,d=derivative(time+h/2,q+h*a/2,omega+h*b/2);e,f=derivative(time+h/2,q+h*c/2,omega+h*d/2);g,k=derivative(time+h,q+h*e,omega+h*f);q+=h*(a+2*c+2*e+g)/6;omega+=h*(b+2*d+2*f+k)/6;time+=h
   state=sample['cylinders'][0];angle_errors.append(abs(state['angle']-q));position_errors.append(abs(state['position']-(.3+.2*sample['time'])))
  case.update(maxReferenceAngleError=max(angle_errors),maxReferencePositionError=max(position_errors),metrics=result['metrics']);case['ok']=case['maxReferenceAngleError']<1e-4 and case['maxReferencePositionError']<1e-4
 # Confirm cylindrical angle unwrap across the Euler branch by spinning five radians.
 multi_turn=copy.deepcopy(cylindrical);multi_turn['bodies'][0]['velocity'].update(wx=6,wy=8,wz=0)
 result,_=run(multi_turn);case={'name':'spatial-cylindrical-multiturn','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  case['maxReferenceAngleError']=max(abs(sample['cylinders'][0]['angle']-10*sample['time']) for sample in result['samples']);case['metrics']=result['metrics'];case['ok']=case['maxReferenceAngleError']<2e-4 and result['samples'][-1]['cylinders'][0]['angle']>math.pi
 # Cylindrical child with independent relative spin on a tilted rotating carrier.
 cylinder_move=copy.deepcopy(moving);cylinder_move['name']='Moving-axis cylindrical guide';cylinder_move['joints'][0]['type']='revolute';r=spatial.body_rotation(cylinder_move['bodies'][0]);first_axis=spatial.mul(r,[1,0,0]);cylinder_move['joints'][0].update(axisA=dict(zip(('x','y','z'),first_axis)),axisB={'x':1,'y':0,'z':0})
 joint=cylinder_move['joints'][1];joint['type']='cylindrical';b=cylinder_move['bodies'][1];joint['axisB']=dict(zip(('x','y','z'),spatial.mul(spatial.transpose(spatial.body_rotation(b)),spatial.mul(r,[0,0,1]))))
 spin_axis=spatial.mul(r,[0,0,1]);b['velocity'].update(zip(('wx','wy','wz'),[a+.7*c for a,c in zip(spatial.xyz({'x':cylinder_move['bodies'][0]['velocity']['wx'],'y':cylinder_move['bodies'][0]['velocity']['wy'],'z':cylinder_move['bodies'][0]['velocity']['wz']}),spin_axis)]))
 result,_=run(cylinder_move);case={'name':'spatial-cylindrical-moving-axis','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  # With isotropic carrier and child, spin about the guide decouples; r''=r H²/(I + m r²)².
  q=.5;velocity=.2;time=0.;position_errors=[];angle_errors=[]
  def derivatives(position,speed):return speed,position*(.45/(.2+position*position))**2
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a,b=derivatives(q,velocity);c,d=derivatives(q+h*a/2,velocity+h*b/2);e,f=derivatives(q+h*c/2,velocity+h*d/2);g,k=derivatives(q+h*e,velocity+h*f);q+=h*(a+2*c+2*e+g)/6;velocity+=h*(b+2*d+2*f+k)/6;time+=h
   state=sample['cylinders'][0];position_errors.append(abs(state['position']-q));angle_errors.append(abs(state['angle']-.7*sample['time']))
  case.update(maxReferencePositionError=max(position_errors),maxReferenceAngleError=max(angle_errors),metrics=result['metrics']);case['ok']=case['maxReferencePositionError']<1e-4 and case['maxReferenceAngleError']<1e-4 and case['metrics']['maxConstraintError']<1e-6
 # Arbitrarily oriented hinge with a physically independent damped oscillator reference.
 driven=copy.deepcopy(spatial.EXAMPLES[1]['model']);driven['parameters']['gravity']={'x':0,'y':0,'z':0};driven['simulation']={'duration':.4,'step':.001};body=driven['bodies'][0];body['pose'].update(x=0,y=0,z=0,rx=20,ry=30,rz=-10)
 joint=driven['joints'][0];joint['anchorB']={'x':0,'y':0,'z':0};axis=[.6,.8,0];joint['axisA']=dict(zip(('x','y','z'),axis));joint['axisB']=dict(zip(('x','y','z'),spatial.mul(spatial.transpose(spatial.body_rotation(body)),axis)))
 driven['rotationalElements']=[{'id':'spring','joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':20.}]
 result,_=run(driven);case={'name':'tilted-spring-damper','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  # q''+q'+10q=10*20deg, q(0)=q'(0)=0; independently derived underdamped solution.
  w=math.sqrt(10-.25);rest=math.radians(20)
  errors=[]
  for sample in result['samples']:
   t=sample['time'];expected=rest*(1-math.exp(-t/2)*(math.cos(w*t)+.5/w*math.sin(w*t)))
   q=sample['rotationalStates'][0]['angle']+rest;errors.append(abs(q-expected))
  case.update(maxReferenceAngleError=max(errors),end=result['samples'][-1]['rotationalStates'][0]);case['ok']=case['maxReferenceAngleError']<5e-4
 # Time-varying torque: exact angular displacement for I=.1, torque=sin(2*pi*t).
 driven.pop('rotationalElements');driven['simulation']['duration']=.1;driven['jointTorques']=[{'id':'drive','joint':'hinge','amplitude':1.,'frequencyHz':1.,'offset':0.}]
 result,_=run(driven);case={'name':'tilted-sinusoidal-torque','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  initial=spatial.body_rotation(body);errors=[];omega=2*math.pi
  for sample in result['samples']:
   n=sample['nodes'][0];r=[n['rotationMatrix'][i:i+3] for i in (0,3,6)];relative=spatial.matmul(r,spatial.transpose(initial));sin_angle=(axis[0]*(relative[2][1]-relative[1][2])+axis[1]*(relative[0][2]-relative[2][0])+axis[2]*(relative[1][0]-relative[0][1]))/2;cos_angle=(sum(relative[i][i] for i in range(3))-1)/2;q=math.atan2(sin_angle,cos_angle)
   expected=(omega*sample['time']-math.sin(omega*sample['time']))/(.1*omega*omega);errors.append(abs(q-expected))
  case.update(maxReferenceAngleError=max(errors),end=result['samples'][-1]['actuationStates'][0]);case['ok']=case['maxReferenceAngleError']<5e-4
 # The hinge axis moves with the two-body mechanism; internal torque cannot change its total angular momentum.
 pair=copy.deepcopy(driven);pair['simulation']['duration']=.2;pair['jointTorques'][0].update(amplitude=0.,offset=1.)
 a=copy.deepcopy(pair['bodies'][0]);a['id']='carrier';a['name']='Carrier';a['pose'].update(rx=0,ry=0,rz=0);a['velocity'].update(wx=1,wy=0,wz=0);b=pair['bodies'][0];b['pose'].update(rx=0,ry=0,rz=0);b['velocity'].update(wx=1,wy=0,wz=0);pair['bodies'].insert(0,a)
 joint=pair['joints'][0];joint.update(a='carrier',axisA={'x':0,'y':0,'z':1},axisB={'x':0,'y':0,'z':1});pair['joints'].insert(0,{'id':'groundball','type':'spherical','a':'ground','b':'carrier','anchorA':{'x':0,'y':0,'z':0},'anchorB':{'x':0,'y':0,'z':0}})
 result,_=run(pair);case={'name':'moving-axis-internal-torque','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  errors=[math.dist([.1*(n['nodes'][0][key]+n['nodes'][1][key]) for key in ('wx','wy','wz')],[.2,0,0]) for n in result['samples']]
  rates=[]
  for sample in result['samples']:
   a,b=sample['nodes'];r=spatial.rotation(a['rx'],a['ry'],a['rz']);axis=spatial.mul(r,[0,0,1]);delta=[b[k]-a[k] for k in ('wx','wy','wz')];rates.append(abs(sum(x*y for x,y in zip(axis,delta))-20*sample['time']))
  case.update(maxAngularMomentumError=max(errors),maxRelativeRateError=max(rates),metrics=result['metrics']);case['ok']=case['maxAngularMomentumError']<1e-5 and case['maxRelativeRateError']<1e-3 and case['metrics']['maxJointAngularError']<1e-6
 # A moving-axis spring also exerts paired internal moments without angular-momentum drift.
 pair.pop('jointTorques');pair['rotationalElements']=[{'id':'spring','joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':20.}]
 result,_=run(pair);case={'name':'moving-axis-internal-spring','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  errors=[math.dist([.1*(n['nodes'][0][key]+n['nodes'][1][key]) for key in ('wx','wy','wz')],[.2,0,0]) for n in result['samples']]
  final=result['samples'][-1]['rotationalStates'][0];rest=math.radians(20);w=math.sqrt(19);angles=[]
  for sample in result['samples']:
   t=sample['time'];expected=rest*(1-math.exp(-t)*(math.cos(w*t)+math.sin(w*t)/w));angles.append(abs(sample['rotationalStates'][0]['angle']+rest-expected))
  case.update(maxAngularMomentumError=max(errors),maxReferenceAngleError=max(angles),end=final,metrics=result['metrics']);case['ok']=case['maxAngularMomentumError']<1e-5 and case['maxReferenceAngleError']<5e-4 and case['metrics']['maxJointAngularError']<1e-6
 # A spatial oblique spring-slider has a closed-form damped oscillator solution.
 spring=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-spring'))
 result,_=run(spring);case={'name':'spatial-spring-oblique','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  # x(0)=.3, x'(0)=.2; x''+x'+10x=0, omega=sqrt(10-1/4).
  omega=math.sqrt(10-.25);errors=[]
  for sample in result['samples']:
   t=sample['time'];expected=math.exp(-t/2)*(.3*math.cos(omega*t)+(.2+.15)/omega*math.sin(omega*t));errors.append(abs(sample['sliders'][0]['position']-expected))
  case.update(maxReferencePositionError=max(errors),initialLength=result['samples'][0]['forces'][0]['length'],metrics=result['metrics']);case['ok']=case['maxReferencePositionError']<1e-4 and abs(case['initialLength']-1.3)<1e-9
 # Two sliders exchange equal-and-opposite spring force without moving their centroid.
 pair=copy.deepcopy(spring);pair['name']='Two-body spring action and reaction';pair['bodies'][0]['pose'].update(x=-.36,y=-.48);pair['bodies'][0]['velocity'].update(vx=0,vy=0)
 other=copy.deepcopy(pair['bodies'][0]);other['id']='other';other['name']='Other';other['pose'].update(x=.42,y=.56);pair['bodies'].append(other)
 joint=copy.deepcopy(pair['joints'][0]);joint.update(id='other-guide',b='other');pair['joints'].append(joint)
 pair['forces'][0].update(a='block',b='other',anchorA={'x':0,'y':0,'z':0})
 result,_=run(pair);case={'name':'spatial-spring-body-pair','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  omega=math.sqrt(19);errors=[];centroid=[]
  for sample in result['samples']:
   t=sample['time'];expected=.3*math.exp(-t)*(math.cos(omega*t)+math.sin(omega*t)/omega);errors.append(abs(sample['forces'][0]['extension']-expected));centroid.append(abs(sum(s['position'] for s in sample['sliders'])/2-.05))
  case.update(maxReferencePositionError=max(errors),maxCentroidError=max(centroid),metrics=result['metrics']);case['ok']=case['maxReferencePositionError']<1e-4 and case['maxCentroidError']<1e-6
 # Offset body anchor on a tilted revolute hinge: the spring must produce a moment.
 pendulum=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'));pendulum['parameters']['gravity']={'x':0,'y':0,'z':0};pendulum['simulation'].update(duration=.5,step=.001)
 body=pendulum['bodies'][0];body['pose'].update(rx=20,ry=30,rz=10);r=spatial.body_rotation(body);initial_position=spatial.mul(r,[0,0,-1]);body['pose'].update(zip(('x','y','z'),initial_position))
 hinge=pendulum['joints'][0];hinge['anchorB']={'x':0,'y':0,'z':1};hinge['axisB']={'x':0,'y':1,'z':0};hinge['axisA']=dict(zip(('x','y','z'),spatial.mul(r,[0,1,0])))
 fixed=spatial.mul(r,[-.5,0,0]);pendulum['forces']=[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'arm','anchorA':dict(zip(('x','y','z'),fixed)),'anchorB':{'x':0,'y':0,'z':-.25},'stiffness':2.,'damping':.2,'restLength':1.}]
 result,_=run(pendulum);case={'name':'spatial-spring-offset-moment','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  # Generalized spring moment about the hinge is -T*dL/dq, L²=1.8125-1.25*sin(q).
  q=velocity=time=0.;errors=[]
  def derivatives(q,velocity):
   length=math.sqrt(1.8125-1.25*math.sin(q));slope=-1.25*math.cos(q)/(2*length);tension=2*(length-1)+.2*slope*velocity
   return velocity,-tension*slope/1.1
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a,b=derivatives(q,velocity);c,d=derivatives(q+h*a/2,velocity+h*b/2);e,f=derivatives(q+h*c/2,velocity+h*d/2);g,k=derivatives(q+h*e,velocity+h*f);q+=h*(a+2*c+2*e+g)/6;velocity+=h*(b+2*d+2*f+k)/6;time+=h
   node=sample['nodes'][0];actual=[node['rotationMatrix'][i:i+3] for i in (0,3,6)];relative=spatial.matmul(spatial.transpose(r),actual);angle=math.atan2(relative[0][2],relative[0][0]);errors.append(abs(q-angle))
  case.update(maxReferenceAngleError=max(errors),metrics=result['metrics']);case['ok']=case['maxReferenceAngleError']<1e-4 and case['metrics']['maxConstraintError']<1e-6
 # Tilted hinge, off-center global force: q''=-1.25*cos(q)/1.1.
 loaded=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'));loaded['parameters']['gravity']={'x':0,'y':0,'z':0};loaded['simulation'].update(duration=.4,step=.001)
 body=loaded['bodies'][0];body['pose'].update(rx=20,ry=30,rz=10);r=spatial.body_rotation(body);initial_position=spatial.mul(r,[0,0,-1]);body['pose'].update(zip(('x','y','z'),initial_position))
 hinge=loaded['joints'][0];hinge['anchorB']={'x':0,'y':0,'z':1};hinge['axisB']={'x':0,'y':1,'z':0};hinge['axisA']=dict(zip(('x','y','z'),spatial.mul(r,[0,1,0])))
 initial_force=spatial.mul(r,[1,0,0]);loaded['loads']=[{'id':'load','body':'arm','frame':'global','point':{'x':0,'y':0,'z':-.25},'force':dict(zip(('x','y','z'),initial_force)),'torque':{'x':0,'y':0,'z':0},'offset':1.,'amplitude':0.,'frequencyHz':1.}]
 result,_=run(loaded);case={'name':'spatial-global-offset-force','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  q=velocity=time=0.;errors=[];work_errors=[]
  def derivatives(q,velocity):return velocity,-1.25*math.cos(q)/1.1
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a,b=derivatives(q,velocity);c,d=derivatives(q+h*a/2,velocity+h*b/2);e,f=derivatives(q+h*c/2,velocity+h*d/2);g,k=derivatives(q+h*e,velocity+h*f);q+=h*(a+2*c+2*e+g)/6;velocity+=h*(b+2*d+2*f+k)/6;time+=h
   node=sample['nodes'][0];actual=[node['rotationMatrix'][i:i+3] for i in (0,3,6)];relative=spatial.matmul(spatial.transpose(r),actual);angle=math.atan2(relative[0][2],relative[0][0]);errors.append(abs(q-angle));axis=spatial.mul(r,[0,1,0]);angular_speed=sum(axis[i]*node[k] for i,k in enumerate(('wx','wy','wz')));work_errors.append(abs(sample['appliedWork']-.55*angular_speed**2))
  case.update(maxReferenceAngleError=max(errors),maxWorkError=max(work_errors),initialLoad=result['samples'][0]['loadStates'][0],metrics=result['metrics']);case['ok']=case['maxReferenceAngleError']<1e-4 and case['maxWorkError']<1e-4
 # Follower force and torque rotate with the body: exact acceleration under a sinusoidal scale.
 follower=copy.deepcopy(loaded);follower['loads'][0].update(frame='body',force={'x':1,'y':0,'z':0},torque={'x':0,'y':.3,'z':0},amplitude=.5)
 result,_=run(follower);case={'name':'spatial-follower-sinusoidal-force-torque','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  omega=2*math.pi;accel=(-1.25+.3)/1.1;errors=[];vector_errors=[];work_errors=[]
  for sample in result['samples']:
   t=sample['time'];expected=accel*(t*t/2+.5*(omega*t-math.sin(omega*t))/omega**2);node=sample['nodes'][0];actual=[node['rotationMatrix'][i:i+3] for i in (0,3,6)];relative=spatial.matmul(spatial.transpose(r),actual);angle=math.atan2(relative[0][2],relative[0][0]);errors.append(abs(angle-expected));force=sample['loadStates'][0]['force'];expected_force=[(1+.5*math.sin(omega*t))*x for x in spatial.mul(actual,[1,0,0])];vector_errors.append(math.dist(spatial.xyz(force),expected_force));axis=spatial.mul(r,[0,1,0]);angular_speed=sum(axis[i]*node[k] for i,k in enumerate(('wx','wy','wz')));work_errors.append(abs(sample['appliedWork']-.55*angular_speed**2))
  case.update(maxReferenceAngleError=max(errors),maxForceFrameError=max(vector_errors),maxWorkError=max(work_errors),metrics=result['metrics']);case['ok']=case['maxReferenceAngleError']<1e-4 and case['maxForceFrameError']<1e-9 and case['maxWorkError']<1e-4
 # A prismatic child attached to a revolute carrier with both spring and torque.
 combined=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'))
 child=copy.deepcopy(combined['bodies'][0]);child['id']='slider';child['name']='Slider';combined['bodies'].append(child)
 combined['joints'].append({'id':'guide','type':'prismatic','a':'arm','b':'slider','anchorA':{'x':0,'y':0,'z':0},'anchorB':{'x':0,'y':0,'z':0},'axisA':{'x':0,'y':0,'z':1}})
 combined['rotationalElements']=[{'id':'spring','joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':0.}]
 combined['jointTorques']=[{'id':'drive','joint':'hinge','amplitude':.5,'frequencyHz':1.,'offset':0.}]
 combined['forces']=[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'slider','anchorA':{'x':1.,'y':0.,'z':0.},'anchorB':{'x':0.,'y':0.,'z':0.},'stiffness':1.,'damping':.1,'restLength':1.}]
 result,_=run(combined);case={'name':'spatial-prismatic-spring-drive','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  case['metrics']=result['metrics'];case['ok']=case['metrics']['maxConstraintError']<1e-6 and case['metrics']['maxJointVelocityError']<1e-4 and all(math.isfinite(sample['sliders'][0]['position']) and math.isfinite(sample['rotationalStates'][0]['torque']) and math.isfinite(sample['actuationStates'][0]['torque']) and math.isfinite(sample['forces'][0]['force']) and math.isfinite(sample['elasticEnergy']) for sample in result['samples'])
 # The isotropic yoke has independent fixed-axis rates alpha and beta; the exact orientation is Rz(alpha*t) Ry(beta*t) R0.
 universal=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-universal'))
 result,_=run(universal);case={'name':'spatial-universal-two-axis','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  initial=spatial.body_rotation(universal['bodies'][0]);errors=[]
  for sample in result['samples']:
   t=sample['time'];expected=spatial.matmul(spatial.matmul(spatial.rotation(0,0,math.degrees(1.2*t)),spatial.rotation(0,math.degrees(.8*t),0)),initial)
   actual=sample['nodes'][0]['rotationMatrix'];errors.append(max(abs(actual[3*i+j]-expected[i][j]) for i in range(3) for j in range(3)))
  case.update(maxRotationMatrixError=max(errors),metrics=result['metrics']);case['ok']=case['maxRotationMatrixError']<1e-4 and case['metrics']['maxJointAngularError']<1e-6
 # Two different initial frames follow the same free 3D spin. Their joint axes move with the carrier.
 moving=copy.deepcopy(universal);moving['name']='Moving universal carrier';moving['simulation']['duration']=.3
 carrier=copy.deepcopy(moving['bodies'][0]);carrier['id']='carrier';carrier['name']='Carrier';carrier['pose'].update(x=0,y=0,z=0,rx=-25,ry=17,rz=-13)
 yoke=moving['bodies'][0];yoke['pose'].update(x=0,y=0,z=0)
 for body in (carrier,yoke):body['velocity'].update(wx=.3,wy=.5,wz=.7)
 moving['bodies'].insert(0,carrier);vec=lambda x,y,z:{'x':x,'y':y,'z':z}
 joint=moving['joints'][0];joint.update(a='carrier',anchorA=vec(0,0,0),axisA=dict(zip(('x','y','z'),spatial.mul(spatial.transpose(spatial.body_rotation(carrier)),[0,0,1]))),axisB=dict(zip(('x','y','z'),spatial.mul(spatial.transpose(spatial.body_rotation(yoke)),[0,1,0]))))
 moving['joints'].insert(0,{'id':'base','type':'spherical','a':'ground','b':'carrier','anchorA':vec(0,0,0),'anchorB':vec(0,0,0)})
 result,_=run(moving);case={'name':'spatial-universal-moving-axis','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  omega=[.3,.5,.7];mag=spatial.norm(omega);u=[x/mag for x in omega];errors=[]
  for sample in result['samples']:
   angle=mag*sample['time'];c=math.cos(angle);sn=math.sin(angle);k=[[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]]
   spin=[[c*(i==j)+(1-c)*u[i]*u[j]+sn*k[i][j] for j in range(3)] for i in range(3)]
   for index,body in enumerate(moving['bodies']):
    expected=spatial.matmul(spin,spatial.body_rotation(body));actual=sample['nodes'][index]['rotationMatrix'];errors.append(max(abs(actual[3*i+j]-expected[i][j]) for i in range(3) for j in range(3)))
  case.update(maxRotationMatrixError=max(errors),metrics=result['metrics']);case['ok']=case['maxRotationMatrixError']<1e-4 and case['metrics']['maxJointAngularError']<1e-6
 # Torque-free off-diagonal inertia with a nonidentity body orientation.
 tensor_model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-spherical'))
 tensor_body=tensor_model['bodies'][0];tensor_body['pose'].update(rx=20.,ry=-10.,rz=15.);tensor_body['velocity'].update(wx=.8,wy=.5,wz=1.1)
 tensor_body['inertia']={'xx':.225,'yy':.275,'zz':.4,'xy':-.04330127018922193,'xz':0.,'yz':0.}
 tensor_model['joints'][0]['anchorA']={k:tensor_body['pose'][k] for k in ('x','y','z')};tensor_model['joints'][0]['anchorB']={'x':0.,'y':0.,'z':0.}
 tensor_model['parameters']['gravity']={'x':0.,'y':0.,'z':0.};tensor_model['simulation']={'duration':.25,'step':.001}
 result,_=run(tensor_model);case={'name':'spatial-full-inertia-free-rotation','ok':result['ok'],'runId':result.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if result['ok']:
  inertia=[[.225,-.04330127018922193,0.],[-.04330127018922193,.275,0.],[0.,0.,.4]];det=.225*.275-inertia[0][1]**2
  inverse=[[.275/det,-inertia[0][1]/det,0.],[-inertia[0][1]/det,.225/det,0.],[0.,0.,2.5]]
  x,y,z=map(math.radians,(20.,-10.,15.));cx,sx=math.cos(x),math.sin(x);cy,sy=math.cos(y),math.sin(y);cz,sz=math.cos(z),math.sin(z)
  r=[cy*cz,-cy*sz,sy,cx*sz+sx*sy*cz,cx*cz-sx*sy*sz,-sx*cy,sx*sz-cx*sy*cz,sx*cz+cx*sy*sz,cx*cy]
  mat=lambda A,v:[sum(A[3*i+j]*v[j] for j in range(3)) for i in range(3)]
  transpose_mul=lambda A,v:[sum(A[3*j+i]*v[j] for j in range(3)) for i in range(3)]
  mul3=lambda M,v:[sum(M[i][j]*v[j] for j in range(3)) for i in range(3)]
  momentum=mat(r,mul3(inertia,transpose_mul(r,[.8,.5,1.1])))
  def rhs(A):
   wx,wy,wz=mat(A,mul3(inverse,transpose_mul(A,momentum)));cross=[[0.,-wz,wy],[wz,0.,-wx],[-wy,wx,0.]]
   return [sum(cross[i][k]*A[3*k+j] for k in range(3)) for i in range(3) for j in range(3)]
  time=0.;rotation_errors=[];momentum_errors=[]
  for sample in result['samples']:
   while sample['time']-time>1e-12:
    h=min(.0001,sample['time']-time);a=rhs(r);b=rhs([v+h*d/2 for v,d in zip(r,a)]);c=rhs([v+h*d/2 for v,d in zip(r,b)]);d=rhs([v+h*e for v,e in zip(r,c)]);r=[v+h*(aa+2*bb+2*cc+dd)/6 for v,aa,bb,cc,dd in zip(r,a,b,c,d)];time+=h
   node=sample['nodes'][0];actual=node['rotationMatrix'];rotation_errors.append(max(abs(a-b) for a,b in zip(actual,r)))
   omega=[node[k] for k in ('wx','wy','wz')];observed=mat(actual,mul3(inertia,transpose_mul(actual,omega)));momentum_errors.append(math.dist(observed,momentum))
  case.update(maxRotationMatrixError=max(rotation_errors),maxAngularMomentumError=max(momentum_errors),metrics=result['metrics']);case['ok']=case['maxRotationMatrixError']<2e-4 and case['maxAngularMomentumError']<1e-5
 # Translate the structural node away from COM without changing the physical rigid body.
 # The two models have the same tilted inertia, load point and constraints in world coordinates.
 reference=copy.deepcopy(tilted);reference['simulation']={'duration':.3,'step':.001}
 reference['loads']=[{'id':'load','body':reference['bodies'][0]['id'],'frame':'global','point':{'x':.2,'y':-.3,'z':.1},'force':{'x':1.,'y':.2,'z':-.3},'torque':{'x':.1,'y':.2,'z':.3},'offset':1.,'amplitude':0.,'frequencyHz':1.}]
 shifted=copy.deepcopy(reference);body=shifted['bodies'][0];center=[.2,-.3,.15];r=spatial.body_rotation(body);world_offset=spatial.mul(r,center)
 body['pose'].update({k:body['pose'][k]-world_offset[i] for i,k in enumerate(('x','y','z'))});body['centerOfMass']=dict(zip(('x','y','z'),center))
 for point in (shifted['joints'][0]['anchorB'],shifted['loads'][0]['point']):
  point.update({k:point[k]+center[i] for i,k in enumerate(('x','y','z'))})
 baseline,_=run(reference);result,_=run(shifted);case={'name':'spatial-offset-center-equivalent-tilted-pendulum','ok':baseline['ok'] and result['ok'],'runId':result.get('runId'),'referenceRunId':baseline.get('runId'),'error':result.get('error'),'log':result.get('log')};cases.append(case)
 if case['ok']:
  position_errors=[];rotation_errors=[];moment_errors=[];power_errors=[]
  for a,b in zip(baseline['samples'],result['samples']):
   na,nb=a['nodes'][0],b['nodes'][0];rm=[nb['rotationMatrix'][i:i+3] for i in (0,3,6)];offset=spatial.mul(rm,center)
   position_errors.append(math.dist([na[k] for k in ('x','y','z')],[nb[k]+offset[i] for i,k in enumerate(('x','y','z'))]))
   rotation_errors.append(max(abs(x-y) for x,y in zip(na['rotationMatrix'],nb['rotationMatrix'])))
   moment_errors.append(math.dist(spatial.xyz(a['loadStates'][0]['moment']),spatial.xyz(b['loadStates'][0]['moment'])))
   power_errors.append(abs(a['loadPower']-b['loadPower']))
  case.update(maxCenterPositionError=max(position_errors),maxRotationMatrixError=max(rotation_errors),maxLoadMomentError=max(moment_errors),maxLoadPowerError=max(power_errors),metrics=result['metrics'])
  case['ok']=len(baseline['samples'])==len(result['samples']) and max(position_errors)<2e-4 and max(rotation_errors)<2e-4 and max(moment_errors)<2e-4 and max(power_errors)<2e-4
 for case in cases:
  if case.get('maxReferencePositionError',0)>1e-4:case['ok']=False
  if case.get('metrics',{}).get('maxConstraintError',0)>1e-6:case['ok']=False
  if case.get('metrics',{}).get('maxJointAngularError',0)>1e-6:case['ok']=False
 path=Path(__file__).resolve().parents[1]/'verification'/'spatial-assembly.json';path.write_text(json.dumps({'cases':cases},indent=2),encoding='utf8')
 print(json.dumps(cases,indent=2))
 if not all(c['ok'] for c in cases):raise SystemExit(1)
if __name__=='__main__':main()
