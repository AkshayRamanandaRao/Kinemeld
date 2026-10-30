"""Original 3D rigid bodies and constrained joints, solved by external MBDyn."""
import copy
import csv
import math
import re
import reference_frames

KIND = "spatial-assembly"
MAX_BODIES = 16
MAX_JOINTS = 32
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")


def matmul(a, b):
    return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def rotation(rx, ry, rz):
    """MBDyn Euler123 orientation Rx(rx) Ry(ry) Rz(rz), degrees."""
    x,y,z=(math.radians(v) for v in (rx,ry,rz));cx,sx=math.cos(x),math.sin(x);cy,sy=math.cos(y),math.sin(y);cz,sz=math.cos(z),math.sin(z)
    return matmul(matmul([[1,0,0],[0,cx,-sx],[0,sx,cx]],[[cy,0,sy],[0,1,0],[-sy,0,cy]]),[[cz,-sz,0],[sz,cz,0],[0,0,1]])


def transpose(m):
    return [list(v) for v in zip(*m)]


def mul(m,v):
    return [sum(m[i][k]*v[k] for k in range(3)) for i in range(3)]


def cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]


def sub(a,b):
    return [x-y for x,y in zip(a,b)]


def norm(v):
    return math.sqrt(sum(x*x for x in v))


def xyz(v):
    return [v[k] for k in ("x","y","z")]


def inertia_matrix(inertia):
    """Return the symmetric body-frame inertia tensor; omitted cross terms are zero."""
    xx,yy,zz=(inertia[k] for k in ('xx','yy','zz'))
    xy,xz,yz=(inertia.get(k,0.) for k in ('xy','xz','yz'))
    return [[xx,xy,xz],[xy,yy,yz],[xz,yz,zz]]


def determinant(matrix):
    a,b,c=matrix[0];_,d,e=matrix[1];_,_,f=matrix[2]
    return a*d*f+2*b*c*e-a*e*e-d*c*c-f*b*b


def inertia_valid(inertia):
    """Check positive definiteness and nonnegative physical second moments."""
    matrix=inertia_matrix(inertia);scale=max(inertia[k] for k in ('xx','yy','zz'))
    m=[[value/scale for value in row] for row in matrix]
    if m[0][0]<=0 or m[0][0]*m[1][1]-m[0][1]**2<=0 or determinant(m)<=0:return False
    half=sum(m[i][i] for i in range(3))/2
    covariance=[[(half if i==j else 0.)-m[i][j] for j in range(3)] for i in range(3)]
    tol=1e-12
    if any(covariance[i][i] < -tol for i in range(3)):return False
    if any(covariance[i][i]*covariance[j][j]-covariance[i][j]**2 < -tol for i,j in ((0,1),(0,2),(1,2))):return False
    return determinant(covariance)>=-tol


def minimum_inertia_bound(inertia):
    """Bound the smallest principal moment from below for step-size estimates."""
    if not any(inertia.get(k,0.) for k in ('xy','xz','yz')):return min(inertia[k] for k in ('xx','yy','zz'))
    scale=max(inertia[k] for k in ('xx','yy','zz'));m=[[v/scale for v in row] for row in inertia_matrix(inertia)]
    return scale*4*determinant(m)/(sum(m[i][i] for i in range(3))**2)


def body_rotation(body):
    return rotation(*(body["pose"][k] for k in ("rx","ry","rz"))) if body else [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]


def anchor(body, local):
    if body is None: return xyz(local)
    return [a+b for a,b in zip(xyz(body["pose"]),mul(body_rotation(body),xyz(local)))]


def anchor_velocity(body, local):
    if body is None: return [0.,0.,0.]
    v=body["velocity"];offset=mul(body_rotation(body),xyz(local));turn=cross([v["wx"],v["wy"],v["wz"]],offset)
    return [v[key]+t for key,t in zip(("vx","vy","vz"),turn)]


def angular(body):
    return [body["velocity"][k] for k in ("wx","wy","wz")] if body else [0.,0.,0.]


def spring_state(force,bodies):
    """Reconstruct axial tension, including velocity of body-local attachment points."""
    a,b=bodies.get(force['a']),bodies.get(force['b'])
    delta=sub(anchor(b,force['anchorB']),anchor(a,force['anchorA']));length=norm(delta)
    if length<1e-9:raise ValueError(f"Spring {force['id']} collapsed to zero length; force direction is undefined.")
    velocity=sub(anchor_velocity(b,force['anchorB']),anchor_velocity(a,force['anchorA']))
    rate=sum(x*y for x,y in zip(delta,velocity))/length;extension=length-force['restLength']
    if force.get('type')=='oleo-strut':
        volume_ratio=1+force['gasArea']*extension/force['gasVolume']
        if volume_ratio<=0:raise ValueError(f"Oleo {force['id']} reached a non-positive gas volume.")
        pressure=force['pressure']*volume_ratio**(-force['gamma']);gas=-force['gasArea']*pressure
        area=force['compressionMeteringArea'] if rate<0 else force['reboundMeteringArea']
        coefficient=.5*force['fluidDensity']*force['fluidArea']**3/(area**2*force['dischargeCoefficient']**2)
        hydraulic=coefficient*rate*abs(rate);stop=0.
        if length<force['minLength']:stop=force['stopStiffness']*(length-force['minLength'])+force['stopDamping']*min(rate,0.)
        elif length>force['maxLength']:stop=force['stopStiffness']*(length-force['maxLength'])+force['stopDamping']*max(rate,0.)
        values={'gasPressure':pressure,'gasForce':gas,'hydraulicForce':hydraulic,'stopForce':stop}
        if not all(math.isfinite(x) for x in values.values()):raise ValueError(f"Oleo {force['id']} produced non-finite reconstructed force.")
        return {'id':force['id'],'length':length,'extension':extension,'rate':rate,'force':gas+hydraulic+stop,**values}
    return {'id':force['id'],'length':length,'extension':extension,'rate':rate,'force':force['stiffness']*extension+force['damping']*rate}


def spring_energy(force,state):
    """Return elastic energy relative to reference length and nonnegative damping power."""
    x,v=state['extension'],state['rate']
    if force.get('type')!='oleo-strut':return .5*force['stiffness']*x*x,force['damping']*v*v
    ratio=1+force['gasArea']*x/force['gasVolume'];gamma=force['gamma'];scale=force['pressure']*force['gasVolume']
    gas_energy=-scale*math.log(ratio) if gamma==1 else scale*math.expm1((1-gamma)*math.log(ratio))/(gamma-1)
    bound=force['minLength'] if state['length']<force['minLength'] else force['maxLength'] if state['length']>force['maxLength'] else None
    displacement=state.get('_stopDeflection',state['length']-bound if bound is not None else 0.)
    stop_energy=.5*force['stopStiffness']*displacement**2
    stop_power=max(0.,(state['stopForce']-force['stopStiffness']*displacement)*v)
    return gas_energy+stop_energy,state['hydraulicForce']*v+stop_power


def validated_oleo_state(force,state,native_oleo):
    """Check native rod output against motion and law before using its measurements."""
    L=native_oleo['length'];v=native_oleo['rate'];x=L-force['restLength'];ratio=1+force['gasArea']*x/force['gasVolume']
    if L<1e-9 or ratio<=0:raise ValueError(f"Invalid native oleo length or gas volume for {force['id']}.")
    def same(a,b,absolute=1e-7):return math.isclose(a,b,rel_tol=1e-6,abs_tol=absolute)
    if not same(state['length'],L,1e-8) or not same(state['rate'],v,1e-8):raise ValueError(f"Native oleo length or rate disagrees with body motion for {force['id']}.")
    pressure=force['pressure']*ratio**(-force['gamma']);area=force['compressionMeteringArea'] if v<0 else force['reboundMeteringArea'];coefficient=.5*force['fluidDensity']*force['fluidArea']**3/(area**2*force['dischargeCoefficient']**2);hydraulic=coefficient*v*abs(v);gas=-force['gasArea']*pressure
    allowed_areas=(force['compressionMeteringArea'],force['reboundMeteringArea']) if abs(v)<=1e-9 else (area,)
    if not same(native_oleo['pressure'],pressure,1e-4) or not same(native_oleo['hydraulic'],hydraulic) or not any(same(native_oleo['meteringArea'],candidate,1e-12) for candidate in allowed_areas):raise ValueError(f"Native oleo pressure or hydraulic force disagrees with the configured law for {force['id']}.")
    stop=0.;displacement=0.
    if L<force['minLength']:displacement=L-force['minLength'];stop=force['stopStiffness']*displacement+force['stopDamping']*min(v,0.)
    elif L>force['maxLength']:displacement=L-force['maxLength'];stop=force['stopStiffness']*displacement+force['stopDamping']*max(v,0.)
    # Native rod output uses 12 decimal digits in scientific notation; bound stop-force changes from rounded length/rate.
    length_uncertainty=1e-12*max(1.,abs(L));velocity_uncertainty=1e-12*max(1.,abs(v))
    stop_tolerance=1e-7+force['stopStiffness']*length_uncertainty+force['stopDamping']*velocity_uncertainty
    nearest=min(('minLength','maxLength'),key=lambda key:abs(L-force[key]));near_stop=abs(L-force[nearest])<=length_uncertainty
    candidates=[(gas+stop,displacement)]
    if near_stop:
        outward=min(v,0.) if nearest=='minLength' else max(v,0.)
        candidates.extend(((gas,0.),(gas+force['stopStiffness']*(L-force[nearest])+force['stopDamping']*outward,L-force[nearest])))
    matches=[item for item in candidates if math.isclose(native_oleo['elastic'],item[0],rel_tol=1e-9,abs_tol=stop_tolerance)]
    # Native fields are printed independently with at least twelve significant digits; cancellation amplifies their rounding error.
    component_sum=native_oleo['elastic']+native_oleo['hydraulic']
    sum_tolerance=1e-11*(abs(native_oleo['elastic'])+abs(native_oleo['hydraulic'])+abs(native_oleo['force'])+1.)
    if not matches or not math.isfinite(component_sum) or abs(native_oleo['force']-component_sum)>sum_tolerance:raise ValueError(f"Native oleo force disagrees with the configured law for {force['id']}.")
    branch=min(matches,key=lambda item:abs(native_oleo['elastic']-item[0]))
    return {**state,'length':L,'extension':x,'rate':v,'force':native_oleo['force'],'gasPressure':native_oleo['pressure'],'gasForce':-force['gasArea']*native_oleo['pressure'],'hydraulicForce':native_oleo['hydraulic'],'stopForce':native_oleo['elastic']+force['gasArea']*native_oleo['pressure'],'_stopDeflection':branch[1]}


def joint_state(joint,a,b,reference=None):
    if joint['type'] in ('prismatic','cylindrical'):
        ra,rb=body_rotation(a),body_rotation(b);wa,wb=angular(a),angular(b)
        axis=mul(ra,xyz(joint['axisA']));delta=sub(anchor(b,joint['anchorB']),anchor(a,joint['anchorA']))
        relative_velocity=sub(sub(anchor_velocity(b,joint['anchorB']),anchor_velocity(a,joint['anchorA'])),cross(wa,delta))
        coordinate=sum(x*y for x,y in zip(axis,delta));rate=sum(x*y for x,y in zip(axis,relative_velocity))
        position=norm(sub(delta,[coordinate*x for x in axis]));velocity=norm(sub(relative_velocity,[rate*x for x in axis]))
        relative=matmul(transpose(ra),rb)
        if reference is not None:relative=matmul(transpose(reference),relative)
        else:relative=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
        cosine=max(-1.,min(1.,(sum(relative[i][i] for i in range(3))-1)/2))
        sine=norm([relative[2][1]-relative[1][2],relative[0][2]-relative[2][0],relative[1][0]-relative[0][1]])/2
        angle=math.atan2(sine,cosine);ang_velocity=norm(sub(wb,wa))
        if joint['type']=='cylindrical':
            axis_b=mul(rb,xyz(joint['axisB']));angle=math.atan2(norm(cross(axis,axis_b)),sum(x*y for x,y in zip(axis,axis_b)))
            relative_angular=sub(wb,wa);ang_velocity=norm(cross(axis,relative_angular))
        return {'id':joint['id'],'positionError':position,'velocityError':velocity,'angularError':angle,'angularVelocityError':ang_velocity,'position':coordinate,'velocity':rate,'transverse':position,'transverseVelocity':velocity,'angle':angle,'angularVelocity':ang_velocity}
    position=norm(sub(anchor(a,joint["anchorA"]),anchor(b,joint["anchorB"])))
    velocity=norm(sub(anchor_velocity(a,joint["anchorA"]),anchor_velocity(b,joint["anchorB"])))
    ra,rb=body_rotation(a),body_rotation(b);wa,wb=angular(a),angular(b)
    angular_error=angular_velocity_error=0.
    if joint["type"] == "revolute":
        ua=mul(ra,xyz(joint["axisA"]));ub=mul(rb,xyz(joint["axisB"]));angular_error=math.atan2(norm(cross(ua,ub)),sum(x*y for x,y in zip(ua,ub)))
        angular_velocity_error=norm(cross(ua,sub(wa,wb)))
    elif joint["type"] == "universal":
        ua=mul(ra,xyz(joint["axisA"]));ub=mul(rb,xyz(joint["axisB"]))
        dot=max(-1.,min(1.,sum(x*y for x,y in zip(ua,ub))));crossed=cross(ua,ub)
        angular_error=abs(math.asin(dot))
        angular_velocity_error=abs(sum(x*y for x,y in zip(sub(wa,wb),crossed)))/max(norm(crossed),1e-12)
    elif joint["type"] == "weld":
        rel=matmul(transpose(ra),rb);cosine=max(-1.,min(1.,(sum(rel[i][i] for i in range(3))-1)/2))
        angular_error=math.acos(cosine);angular_velocity_error=norm(sub(wa,wb))
    return {"id":joint["id"],"positionError":position,"velocityError":velocity,"angularError":angular_error,"angularVelocityError":angular_velocity_error}


def rotary_law(motion):
    """Name the drive law of a revolute motion: a speed ramp or a cosine oscillation."""
    keys=set(motion) if isinstance(motion,dict) else set()
    return 'speed' if keys=={'speedDegPerS','rampTime'} else 'oscillation' if keys=={'amplitudeDeg','frequencyHz'} else None


def rotary_angle(motion,t):
    """Prescribed relative rotation (rad) of a driven revolute at time t; starts at rest."""
    if rotary_law(motion)=='speed':
        w,tau=math.radians(motion['speedDegPerS']),motion['rampTime'];r=lambda x:max(x,0.)
        return w/(2*tau)*(r(t)**2-r(t-tau)**2)
    return math.radians(motion['amplitudeDeg'])*(1-math.cos(2*math.pi*motion['frequencyHz']*t))


def rotary_drive_caller(motion,f):
    """MBDyn drive for the rotation about the hinge axis; both laws have zero speed at t = 0."""
    if rotary_law(motion)=='speed':
        coefficient=math.radians(motion['speedDegPerS'])/(2*motion['rampTime'])
        return f'string, "{f(coefficient)}*(ramp(Time)^2-ramp(Time-{f(motion["rampTime"])})^2)"'
    return f"cosine, 0, {f(2*math.pi*motion['frequencyHz'])}, {f(math.radians(motion['amplitudeDeg']))}, forever, 0"


def driven(joint):
    return joint['type']=='revolute' and 'motion' in joint


FRICTION_SLIP_VELOCITY=.05
FRICTION_COLUMNS=(('frictionForce','frictionForce_N'),('slip','slip_m_s'),('frictionPower','frictionPower_W'),('frictionEnergy','frictionEnergy_J'))


def friction(contact):
    """Coulomb coefficient of a sphere-plane contact; 0 is frictionless."""
    return contact.get('friction',0.)


def slip_velocity(contact):
    """Slip speed (m/s) over which the regularised friction force rises to 76% of mu*N."""
    return contact.get('slipVelocity',FRICTION_SLIP_VELOCITY)


def friction_force_labels(model):
    """MBDyn force and couple labels of each frictional contact, after the drive and load forces."""
    joints={j['id']:j for j in model['joints']}
    label=1+sum(1+int(joints[d['joint']]['a']!='ground') for d in model.get('jointTorques',[]))+len(model.get('jointForces',[]))
    label+=sum(int(any(load['force'].values()))+int(any(load['torque'].values())) for load in model.get('loads',[]))
    labels={}
    for contact in model.get('contacts',[]):
        if friction(contact):labels[contact['id']]=(label,label+1);label+=2
    return labels


def element_csv_values_per_row(model):
    """Count the scalar element and reaction columns repeated on each body row."""
    joints=model['joints'];rotary=model.get('rotationalElements',[]);drives=model.get('jointTorques',[])
    linear=model.get('jointForces',[]);forces=model.get('forces',[]);loads=model.get('loads',[]);contacts=model.get('contacts',[])
    return (6*len(joints)+7*len(contacts)+4*sum(bool(friction(c)) for c in contacts)+4*sum(j['type']=='cylindrical' for j in joints)+4*sum(driven(j) for j in joints)+2*any(driven(j) for j in joints)
            +10*len(loads)+4*len(forces)+6*sum(j['type']=='prismatic' for j in joints)
            +4*sum(force.get('type')=='oleo-strut' for force in forces)
            +3*len(rotary)+2*len(drives)+2*len(linear)+2*bool(loads)+3*bool(rotary or forces)
            +2*bool(drives)+2*bool(linear))


def validate(model):
    issues=[]
    def issue(field,message,level="error"):issues.append({"level":level,"field":field,"message":message})
    def obj(value,keys,path):
        if not isinstance(value,dict):issue(path,"Supply an object.");return False
        for key in value.keys()-keys:issue(f"{path}.{key}".strip('.'),"Unsupported field.")
        for key in keys-value.keys():issue(f"{path}.{key}".strip('.'),"Required field is missing.")
        return True
    def nums(value,bounds,path):
        if not obj(value,set(bounds),path):return
        for key,(lo,hi) in bounds.items():
            n=value.get(key)
            if type(n) not in (int,float) or not lo<=n<=hi or not math.isfinite(n):issue(f"{path}.{key}",f"Enter a finite value from {lo:g} to {hi:g}.")
    def ident(value,path):
        if not isinstance(value,str) or not IDENTIFIER.fullmatch(value) or value=='ground':issue(path,'Use a unique letter-leading identifier (up to 32 characters); ground is reserved.')
    summary={"kind":KIND,"scope":"3D rigid bodies, spherical/revolute/prismatic/cylindrical/universal/weld constraints; loops require nonredundancy","units":"m, kg, s, kg*m^2, degrees, rad/s"}
    optional={k for k in ("rotationalElements","jointTorques","jointForces","forces","loads","contacts","frames","frameLinks") if isinstance(model,dict) and k in model}
    if not obj(model,{"kind","name","parameters","simulation","bodies","joints"}|optional,""):return {"valid":False,"issues":issues,"summary":summary}
    if model.get('kind')!=KIND:issue('kind','Choose spatial-assembly.')
    if not isinstance(model.get('name'),str) or not model['name'].strip() or len(model['name'])>120 or any(ord(c)<32 for c in model['name']):issue('name','Use 1–120 printable characters.')
    if obj(model.get('parameters'),{'gravity'},'parameters'):nums(model['parameters'].get('gravity'),{k:(-100,100) for k in ('x','y','z')},'parameters.gravity')
    nums(model.get('simulation'),{'duration':(.01,30),'step':(.0001,.02)},'simulation')
    bodies,joints=model.get('bodies'),model.get('joints')
    rotary,drives,forces,loads=model.get('rotationalElements',[]),model.get('jointTorques',[]),model.get('forces',[]),model.get('loads',[])
    linear_drives=model.get('jointForces',[]);contacts=model.get('contacts',[])
    for key,values in (('rotationalElements',rotary),('jointTorques',drives),('jointForces',linear_drives),('forces',forces),('loads',loads),('contacts',contacts)):
        if not isinstance(values,list) or len(values)>32:issue(key,'Supply at most 32 elements.')
    if any(not isinstance(values,list) or len(values)>32 for values in (rotary,drives,linear_drives,forces,loads,contacts)):return {'valid':False,'issues':issues,'summary':summary}
    if not isinstance(bodies,list) or not 1<=len(bodies)<=MAX_BODIES:issue('bodies','Supply 1–16 rigid bodies.')
    if not isinstance(joints,list) or len(joints)>MAX_JOINTS:issue('joints','Supply at most 32 constraints.')
    if not isinstance(bodies,list) or not isinstance(joints,list) or len(bodies)>MAX_BODIES or len(joints)>MAX_JOINTS:return {"valid":False,"issues":issues,"summary":summary}
    for i,body in enumerate(bodies):
        p=f'bodies.{i}'
        optional_body={'centerOfMass'} if isinstance(body,dict) and 'centerOfMass' in body else set()
        if not obj(body,{'id','name','mass','inertia','pose','velocity'}|optional_body,p):continue
        ident(body.get('id'),p+'.id')
        if not isinstance(body.get('name'),str) or not body['name'].strip() or len(body['name'])>120 or any(ord(c)<32 for c in body['name']):issue(p+'.name','Use 1–120 printable characters.')
        nums({'mass':body.get('mass')},{'mass':(.0001,1e6)},p)
        inertia=body.get('inertia'); extras={k for k in ('xy','xz','yz') if isinstance(inertia,dict) and k in inertia}
        nums(inertia,{**{k:(1e-9,1e9) for k in ('xx','yy','zz')},**{k:(-1e9,1e9) for k in extras}},p+'.inertia')
        if 'centerOfMass' in body:nums(body['centerOfMass'],{k:(-1000,1000) for k in ('x','y','z')},p+'.centerOfMass')
        nums(body.get('pose'),{**{k:(-1000,1000) for k in ('x','y','z')},**{k:(-360,360) for k in ('rx','ry','rz')}},p+'.pose')
        nums(body.get('velocity'),{k:(-1000,1000) for k in ('vx','vy','vz','wx','wy','wz')},p+'.velocity')
    for i,joint in enumerate(joints):
        p=f'joints.{i}';keys={'id','type','a','b','anchorA','anchorB'}
        if isinstance(joint,dict) and 'motion' in joint:keys.add('motion')
        if isinstance(joint,dict) and joint.get('type') in ('revolute','cylindrical','universal'):keys|={'axisA','axisB'}
        if isinstance(joint,dict) and joint.get('type')=='prismatic':keys|={'axisA'}
        if not obj(joint,keys,p):continue
        ident(joint.get('id'),p+'.id')
        if joint.get('type') not in ('revolute','prismatic','cylindrical','spherical','universal','weld'):issue(p+'.type','Only revolute, prismatic, cylindrical, spherical, universal and weld joints are supported.')
        for key in ('a','b'):
            if not (key=='a' and joint.get(key)=='ground'):ident(joint.get(key),p+'.'+key)
        for key in ('anchorA','anchorB'):nums(joint.get(key),{k:(-1000,1000) for k in ('x','y','z')},p+'.'+key)
        if joint.get('type') in ('revolute','prismatic','cylindrical','universal'):
            for key in (('axisA','axisB') if joint['type'] in ('revolute','cylindrical','universal') else ('axisA',)):
                before=len(issues);nums(joint.get(key),{k:(-1,1) for k in ('x','y','z')},p+'.'+key)
                if len(issues)==before and abs(norm(xyz(joint[key]))-1)>1e-7:issue(p+'.'+key,'Axis must be a unit vector.')
        if 'motion' in joint:
            if joint.get('type')=='revolute':
                motion=joint['motion'];law=rotary_law(motion)
                if law=='speed':nums(motion,{'speedDegPerS':(-36000,36000),'rampTime':(.001,1000)},p+'.motion')
                elif law=='oscillation':nums(motion,{'amplitudeDeg':(-360,360),'frequencyHz':(.001,1000)},p+'.motion')
                else:issue(p+'.motion','Drive a revolute joint with speedDegPerS and rampTime, or amplitudeDeg and frequencyHz.')
            elif joint.get('type')=='prismatic':nums(joint['motion'],{'amplitude':(-1000,1000),'frequencyHz':(.001,1000)},p+'.motion')
            else:issue(p+'.motion','Prescribed motion requires a prismatic or revolute joint.')
    for i,force in enumerate(forces):
        path=f'forces.{i}'
        kind=force.get('type') if isinstance(force,dict) else None
        common={'id','type','a','b','anchorA','anchorB','restLength'}
        params={'pressure':(1e3,1e8),'gasArea':(1e-8,1.),'gasVolume':(1e-8,100.),'gamma':(1.,2.),'minLength':(1e-6,2000.),'maxLength':(1e-6,2000.),'stopStiffness':(0.,1e9),'stopDamping':(0.,1e9),'compressionMeteringArea':(1e-8,1.),'reboundMeteringArea':(1e-8,1.),'fluidArea':(1e-8,1.),'fluidDensity':(1.,10000.),'dischargeCoefficient':(.05,1.)} if kind=='oleo-strut' else {'stiffness':(0,1e9),'damping':(0,1e9)}
        if not obj(force,common|set(params),path):continue
        ident(force.get('id'),path+'.id')
        if kind not in ('linear-spring-damper','oleo-strut'):issue(path+'.type','Choose a linear spring-damper or an oleo strut.')
        for side in ('a','b'):
            if force.get(side)!='ground':ident(force.get(side),path+'.'+side)
        for key in ('anchorA','anchorB'):nums(force.get(key),{k:(-1000,1000) for k in ('x','y','z')},path+'.'+key)
        nums({k:force.get(k) for k in (*params,'restLength')},{**params,'restLength':(1e-6,2000)},path)
    for i,load in enumerate(loads):
        path=f'loads.{i}'
        if not obj(load,{'id','body','frame','point','force','torque','offset','amplitude','frequencyHz'},path):continue
        ident(load.get('id'),path+'.id');ident(load.get('body'),path+'.body')
        if load.get('frame') not in ('global','body'):issue(path+'.frame','Choose global or body-local vector directions.')
        for key in ('point','force','torque'):nums(load.get(key),{k:(-1000,1000) if key=='point' else (-1e9,1e9) for k in ('x','y','z')},path+'.'+key)
        nums({k:load.get(k) for k in ('offset','amplitude','frequencyHz')},{'offset':(-1e6,1e6),'amplitude':(-1e6,1e6),'frequencyHz':(.001,1000)},path)
    for i,contact in enumerate(contacts):
        path=f'contacts.{i}'
        optional_contact={key for key in ('damping','friction','slipVelocity') if isinstance(contact,dict) and key in contact}
        if not obj(contact,{'id','body','center','radius','planePoint','planeNormal','stiffness'}|optional_contact,path):continue
        ident(contact.get('id'),path+'.id');ident(contact.get('body'),path+'.body')
        for key in ('center','planePoint'):nums(contact.get(key),{k:(-1000,1000) for k in ('x','y','z')},path+'.'+key)
        before=len(issues);nums(contact.get('planeNormal'),{k:(-1,1) for k in ('x','y','z')},path+'.planeNormal')
        if len(issues)==before and abs(norm(xyz(contact['planeNormal']))-1)>1e-7:issue(path+'.planeNormal','Plane normal must be a unit vector.')
        nums({k:contact.get(k) for k in ('radius','stiffness')},{'radius':(1e-6,1000),'stiffness':(1e-6,1e9)},path)
        if 'damping' in contact:nums({'damping':contact['damping']},{'damping':(0,1e9)},path)
        if 'friction' in contact:nums({'friction':contact['friction']},{'friction':(0,2)},path)
        if 'slipVelocity' in contact:nums({'slipVelocity':contact['slipVelocity']},{'slipVelocity':(1e-4,10)},path)
    for group,values,fields in (('rotationalElements',rotary,{'stiffness':(0,1e9),'damping':(0,1e9),'restAngleDeg':(-179.999,179.999)}),('jointTorques',drives,{'amplitude':(-1e9,1e9),'frequencyHz':(.001,1000),'offset':(-1e9,1e9)}),('jointForces',linear_drives,{'amplitude':(-1e9,1e9),'frequencyHz':(.001,1000),'offset':(-1e9,1e9)})):
        for i,value in enumerate(values):
            path=f'{group}.{i}'
            if not obj(value,{'id','joint'}|set(fields),path):continue
            ident(value.get('id'),path+'.id');ident(value.get('joint'),path+'.joint')
            nums({key:value.get(key) for key in fields},fields,path)
    issues.extend(reference_frames.validate_frames(model))
    issues.extend(reference_frames.validate_links(model))
    if issues:return {"valid":False,"issues":issues,"summary":summary}
    lookup={body['id']:body for body in bodies}
    for group,values in (('bodies',bodies),('joints',joints),('rotationalElements',rotary),('jointTorques',drives),('jointForces',linear_drives),('forces',forces),('loads',loads),('contacts',contacts)):
        seen=set()
        for i,value in enumerate(values):
            if value['id'] in seen:issue(f'{group}.{i}.id','Identifier is repeated in this collection.')
            seen.add(value['id'])
    for i,body in enumerate(bodies):
        if not inertia_valid(body['inertia']):issue(f'bodies.{i}.inertia','The body-frame inertia tensor must be positive definite and have physically realizable principal moments.')
    for i,joint in enumerate(joints):
        for side in ('a','b'):
            if joint[side] not in lookup and not (side=='a' and joint[side]=='ground'):issue(f'joints.{i}.{side}','Reference does not name a declared body.')
        if joint['a']==joint['b']:issue(f'joints.{i}.b','Joint endpoints must be different.')
    for i,force in enumerate(forces):
        for side in ('a','b'):
            if force[side]!='ground' and force[side] not in lookup:issue(f'forces.{i}.{side}','Reference does not name ground or a declared body.')
        if force['a']==force['b']:issue(f'forces.{i}.b','Connect two different bodies, or ground and a body.')
        if force['type']=='linear-spring-damper' and force['stiffness']==force['damping']==0:issue(f'forces.{i}.stiffness','Set nonzero stiffness or damping.')
        if force['type']=='oleo-strut':
            if not force['minLength']<force['restLength']<=force['maxLength']:issue(f'forces.{i}.restLength','Require minimum length < reference length ≤ maximum length.')
            if force['restLength']*force['gasArea']/force['gasVolume']>.9:issue(f'forces.{i}.gasVolume','Gas volume must be at least reference length × gas area / 0.9 to avoid gas-volume singularity for nonnegative lengths.')
            if force['stopStiffness']==0:issue(f'forces.{i}.stopStiffness','Set positive stop stiffness.')
    for i,load in enumerate(loads):
        if load['body'] not in lookup:issue(f'loads.{i}.body','Reference must name a declared dynamic body.')
        if all(load[key][axis]==0 for key in ('force','torque') for axis in ('x','y','z')):issue(f'loads.{i}.force','Set a nonzero force or torque component.')
        if load['offset']==load['amplitude']==0:issue(f'loads.{i}.offset','Set a nonzero offset or amplitude.')
        if load['amplitude'] and model['simulation']['step']*load['frequencyHz']>.05:issue(f'loads.{i}.frequencyHz','Use at least 20 integration steps per actuation cycle.')
    for i,contact in enumerate(contacts):
        if contact['body'] not in lookup:issue(f'contacts.{i}.body','Reference a declared dynamic body.')
    if issues:return {"valid":False,"issues":issues,"summary":summary}
    contact_rates={};contact_damping_rates={}
    for contact in contacts:
        body=lookup[contact['body']];lever=norm(sub(xyz(contact['center']),xyz(body.get('centerOfMass',dict.fromkeys(('x','y','z'),0.)))))
        bound=minimum_inertia_bound(body['inertia']) if lever else 1.
        contribution=math.inf if bound<=0 else contact['stiffness']*(1/body['mass']+lever**2/bound)
        contact_rates[body['id']]=contact_rates.get(body['id'],0.)+contribution
        damping_contribution=math.inf if bound<=0 else contact.get('damping',0.)*(1/body['mass']+lever**2/bound)
        contact_damping_rates[body['id']]=contact_damping_rates.get(body['id'],0.)+damping_contribution
    for body_id,squared_rate in contact_rates.items():
        rate=math.sqrt(squared_rate)+contact_damping_rates[body_id]
        if model['simulation']['step']*rate>.2:issue('simulation.step',f"Resolve combined contacts on body {body_id} with a smaller time step (at most {0.2/rate:.6g} s by a conservative estimate).")
    # Friction enters MBDyn's Newton iteration without its Jacobian, so near sticking each iteration
    # contracts only by about step*mu*N/v_s*(1/m + lever^2/I); N is estimated as the system weight shared by the contacts.
    rough=[(i,contact) for i,contact in enumerate(contacts) if friction(contact)]
    weight=sum(body['mass'] for body in bodies)*(norm(xyz(model['parameters']['gravity'])) or 9.81)/max(len(rough),1)
    for i,contact in rough:
        body=lookup[contact['body']];lever=norm(sub(xyz(contact['center']),xyz(body.get('centerOfMass',dict.fromkeys(('x','y','z'),0.)))))+contact['radius']
        bound=minimum_inertia_bound(body['inertia'])
        rate=math.inf if bound<=0 else friction(contact)*weight/slip_velocity(contact)*(1/body['mass']+lever**2/bound)
        if model['simulation']['step']*rate>.5:issue(f'contacts.{i}.slipVelocity',f"Resolve friction on contact {contact['id']} with a smaller time step (at most {0.5/rate:.6g} s) or a larger slip velocity (at least {slip_velocity(contact)*model['simulation']['step']*rate/.5:.6g} m/s) by a conservative estimate.")
    for i,force in enumerate(forces):
        initial_length=norm(sub(anchor(lookup.get(force['b']),force['anchorB']),anchor(lookup.get(force['a']),force['anchorA'])))
        if initial_length<1e-6:issue(f'forces.{i}.anchorB','Spring endpoints must initially be at least 1e-6 m apart.')
        if force['type']=='oleo-strut' and not force['minLength']<=initial_length<=force['maxLength']:issue(f'forces.{i}.anchorB','Initial oleo length must be within its stated stroke.')
        compliance=sum(1/lookup[force[side]]['mass']+norm(sub(xyz(force['anchor'+side.upper()]),xyz(lookup[force[side]].get('centerOfMass',dict.fromkeys(('x','y','z'),0.)))))**2/minimum_inertia_bound(lookup[force[side]]['inertia']) for side in ('a','b') if force[side]!='ground')
        if compliance:
            if force['type']=='oleo-strut':
                r=1+force['gasArea']*(force['minLength']-force['restLength'])/force['gasVolume']
                if r<=0:continue
                stiffness=force['gamma']*force['pressure']*force['gasArea']**2/force['gasVolume']*r**(-force['gamma']-1)+force['stopStiffness'];damping=force['stopDamping']
            else:stiffness,damping=force['stiffness'],force['damping']
            rate=math.sqrt(stiffness*compliance)+damping*compliance if force['type']=='oleo-strut' else max(math.sqrt(stiffness*compliance),damping*compliance)
            if model['simulation']['step']*rate>.2:
                detail='a heuristic; hydraulic and coupling effects need convergence checks' if force['type']=='oleo-strut' else 'a conservative estimate'
                issue('simulation.step',f"Resolve spring {force['id']} with a smaller time step (at most {0.2/rate:.6g} s by {detail}).")
    for i,joint in enumerate(joints):
        a,b=lookup.get(joint['a']),lookup[joint['b']];state=joint_state(joint,a,b)
        if state['positionError']>1e-7:issue(f'joints.{i}.anchorB',f"Initial anchor positions differ by {state['positionError']:.6g} m.")
        if state['velocityError']>1e-7:issue(f'joints.{i}.anchorB',f"Initial anchor velocities differ by {state['velocityError']:.6g} m/s.")
        if state['angularError']>1e-7:
            message=(f"Universal axes must be perpendicular; angular error is {state['angularError']:.6g} rad." if joint['type']=='universal' else f"Joint frame directions differ by {state['angularError']:.6g} rad (weld requires equal initial orientations).")
            issue(f'joints.{i}.axisB' if joint['type'] in ('revolute','cylindrical','universal') else f'joints.{i}.b',message)
        if state['angularVelocityError']>1e-7:issue(f'joints.{i}.b',f"Joint-constrained angular velocities differ by {state['angularVelocityError']:.6g} rad/s.")
        if joint.get('motion') and joint['type']=='prismatic':
            if abs(state['velocity'])>1e-7:issue(f'joints.{i}.motion','Prescribed cosine motion starts at zero relative axial speed; adjust initial velocities.')
            if model['simulation']['step']*joint['motion']['frequencyHz']>.05:issue('simulation.step','Use at least 20 steps per prescribed motion cycle.')
        if joint.get('motion') and joint['type']=='revolute':
            motion=joint['motion'];axis=mul(body_rotation(a),xyz(joint['axisA']))
            relative=sum(x*y for x,y in zip(axis,sub(angular(b),angular(a))))
            if abs(relative)>1e-7:issue(f'joints.{i}.motion','A driven revolute starts at rest about its axis; set equal initial angular velocities about the hinge.')
            dt=model['simulation']['step']
            if rotary_law(motion)=='speed':
                if abs(math.radians(motion['speedDegPerS']))*dt>.1:issue('simulation.step','Resolve the drive speed with at most 0.1 rad per step.')
                if motion['rampTime']<20*dt:issue(f'joints.{i}.motion.rampTime','Use a ramp of at least 20 time steps.')
            else:
                if dt*motion['frequencyHz']>.05:issue('simulation.step','Use at least 20 steps per prescribed motion cycle.')
                if abs(math.radians(motion['amplitudeDeg']))*2*math.pi*motion['frequencyHz']*dt>.1:issue('simulation.step','Resolve the oscillation speed with at most 0.1 rad per step.')
        if joint['type'] in ('revolute','cylindrical'):
            ua=mul(body_rotation(a),xyz(joint['axisA']));ub=mul(body_rotation(b),xyz(joint['axisB']))
            if sum(x*y for x,y in zip(ua,ub))<0:issue(f'joints.{i}.axisB','Joint axes must point in the same direction.')
    joint_lookup={j['id']:j for j in joints}
    for group,values in (('rotationalElements',rotary),('jointTorques',drives)):
        for i,value in enumerate(values):
            joint=joint_lookup.get(value['joint'])
            if not joint or joint['type'] not in ('revolute','cylindrical'):issue(f'{group}.{i}.joint','Reference an existing revolute or cylindrical joint.')
            if group=='rotationalElements':
                if value['stiffness']==value['damping']==0:issue(f'{group}.{i}.stiffness','Set nonzero stiffness or damping.')
                if joint and joint['type'] in ('revolute','cylindrical'):
                    involved=[lookup[joint['b']]]+([lookup[joint['a']]] if joint['a']!='ground' else [])
                    effective=1/sum(1/minimum_inertia_bound(body['inertia']) for body in involved)
                    rate=max(math.sqrt(value['stiffness']/effective),value['damping']/effective)
                    if model['simulation']['step']*rate>.2:issue('simulation.step',f"Resolve rotational element {value['id']} with a smaller step (at most {0.2/rate:.6g} s by the conservative inertia estimate).")
            if group=='jointTorques' and model['simulation']['step']*value['frequencyHz']>.05:issue(f'{group}.{i}.frequencyHz','Use at least 20 integration steps per actuation cycle.')
    for i,value in enumerate(linear_drives):
        joint=joint_lookup.get(value['joint'])
        if not joint or joint['type'] not in ('prismatic','cylindrical'):issue(f'jointForces.{i}.joint','Reference an existing prismatic or cylindrical joint.')
        if value['amplitude'] and model['simulation']['step']*value['frequencyHz']>.05:issue(f'jointForces.{i}.frequencyHz','Use at least 20 integration steps per actuation cycle.')
    steps=math.ceil(model['simulation']['duration']/model['simulation']['step'])
    if steps>20000 or steps*len(bodies)>160000:issue('simulation.step','Limit a job to 20,000 time steps and 160,000 body-steps.')
    if (steps+2)*len(bodies)*element_csv_values_per_row(model)>1600000:issue('simulation.step','Limit element and joint-reaction CSV output to 1,600,000 scalar values; shorten the duration, increase the step, or reduce bodies, joints or elements.')
    if any(norm(angular(b))*model['simulation']['step']>.1 for b in bodies):issue('simulation.step','Resolve initial rotation with at most 0.1 rad per step.')
    parents={key:key for key in ('ground',*lookup)}
    def root(key):
        while parents[key]!=key:key=parents[key]
        return key
    has_loops=False
    for joint in joints:
        a,b=root(joint['a']),root(joint['b'])
        if a==b:has_loops=True
        else:parents[b]=a
    summary.update(bodies=len(bodies),joints=len(joints),forces=len(forces),loads=len(loads),timeSteps=steps,nodeLabels={b['id']:i+1 for i,b in enumerate(bodies)},hasLoops=has_loops)
    import constraint_analysis
    summary['mobility']=constraint_analysis.analyse(model)
    return {"valid":not issues,"issues":issues,"summary":summary}


def orientation_spec(r):
    return '1,'+','.join(format(r[i][0],'.15g') for i in range(3))+',2,'+','.join(format(r[i][1],'.15g') for i in range(3))


def basis(axis):
    seed=[1.,0.,0.] if abs(axis[0])<.8 else [0.,1.,0.]
    t=cross(seed,axis); length=norm(t); t=[x/length for x in t]
    return t,cross(axis,t),axis


def deck(model):
    check=validate(model)
    if not check['valid']:raise ValueError('Spatial assembly validation failed: '+'; '.join(x['field']+': '+x['message'] for x in check['issues']))
    f=lambda x:format(float(x),'.15g')
    vec=lambda obj:','.join(f(obj[k]) for k in ('x','y','z'))
    bodies,joints=model['bodies'],model['joints'];rotary,drives,forces,loads=model.get('rotationalElements',[]),model.get('jointTorques',[]),model.get('forces',[]),model.get('loads',[]);linear_drives=model.get('jointForces',[]);contacts=model.get('contacts',[]);joint_lookup={j['id']:j for j in joints};labels={body['id']:i+1 for i,body in enumerate(bodies)};lookup={b['id']:b for b in bodies};sim=model['simulation'];g=xyz(model['parameters']['gravity']);gn=norm(g)
    contact_functions=''.join(f'scalar function: "contact_{i}", multilinear, -1,{f(-c["stiffness"])},0,0,1,0;\n' for i,c in enumerate(contacts))
    damped_contacts=sum(c.get('damping',0)>0 for c in contacts);friction_labels=friction_force_labels(model);friction_chains={}
    if damped_contacts:
        contact_functions+='scalar function: "contact_zero", multilinear, -1,0,1,0;\n'
        contact_functions+=''.join(f'scalar function: "contact_damping_{i}", multilinear, -1,{f(-c["damping"])},0,0,1,0;\n' for i,c in enumerate(contacts) if c.get('damping',0)>0)
    text=f'''# Kinemeld spatial rigid bodies; SI units.\nbegin: data;\n problem: initial value;\nend: data;\nbegin: initial value;\n initial time: 0;\n final time: {f(sim['duration'])};\n time step: {f(sim['step'])};\n max iterations: 40;\n tolerance: 1.e-9;\n derivatives tolerance: 1.e-8;\n derivatives max iterations: 100;\n derivatives coefficient: 1.e-3, auto;\nend: initial value;\n{contact_functions}begin: control data;\n max iterations: 40;\n {'skip initial joint assembly;' if rotary or forces or contacts else ''}\n structural nodes: {len(bodies)+1};\n rigid bodies: {len(bodies)};\n joints: {len(joints)+1+len(rotary)+len(forces)+len(contacts)+damped_contacts+sum(j['type']=='prismatic' and 'motion' not in j for j in joints)};\n {f"forces: {sum(1+int(joint_lookup[d['joint']]['a']!='ground') for d in drives)+len(linear_drives)+sum(int(any(load['force'].values()))+int(any(load['torque'].values())) for load in loads)+2*len(friction_labels)};" if drives or linear_drives or loads or friction_labels else ''}\n {'gravity;' if gn else ''}\n output precision: 12;\nend: control data;\nbegin: nodes;\n structural: 0, static, null, eye, null, null, output, no;\n'''
    for b in bodies:
        p,v=b['pose'],b['velocity'];r=body_rotation(b);orient=orientation_spec(r)
        text+=f" structural: {labels[b['id']]}, dynamic, {vec(p)}, {orient}, {f(v['vx'])},{f(v['vy'])},{f(v['vz'])}, {f(v['wx'])},{f(v['wy'])},{f(v['wz'])};\n"
    text+='end: nodes;\nbegin: elements;\n'
    for b in bodies:
        i=b['inertia'];label=labels[b['id']]
        if any(i.get(key,0.) for key in ('xy','xz','yz')):
            tensor=','.join(f(i.get(key,0.)) for key in ('xx','xy','xz','yy','yz','zz'));form=f'sym, {tensor}'
        else:form=f"diag, {f(i['xx'])},{f(i['yy'])},{f(i['zz'])}"
        center=vec(b['centerOfMass']) if 'centerOfMass' in b else 'null'
        text+=f" body: {label}, {label}, {f(b['mass'])}, {center}, {form};\n"
    text+=' joint: 1, clamp, 0, node, node;\n'
    extra_label=len(joints)+2+len(rotary)+len(forces)
    for index,j in enumerate(joints,2):
        a=0 if j['a']=='ground' else labels[j['a']];b=labels[j['b']]
        if j['type']=='spherical':
            text+=f" joint: {index}, spherical hinge, {a}, position, reference, node, {vec(j['anchorA'])}, {b}, position, reference, node, {vec(j['anchorB'])};\n"
        elif driven(j):
            ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);axis=mul(ra,xyz(j['axisA']));t,second,_=basis(axis)
            h=[[t[i],second[i],axis[i]] for i in range(3)];oa=orientation_spec(matmul(transpose(ra),h));ob=orientation_spec(matmul(transpose(rb),h))
            text+=f" joint: {index}, total joint, {a}, position, reference, node, {vec(j['anchorA'])}, position orientation, reference, node, {oa}, rotation orientation, reference, node, {oa}, {b}, position, reference, node, {vec(j['anchorB'])}, position orientation, reference, node, {ob}, rotation orientation, reference, node, {ob}, position constraint, active, active, active, null, orientation constraint, active, active, active, single, 0,0,1, {rotary_drive_caller(j['motion'],f)};\n"
        elif j['type']=='revolute':
            world_axis=mul(body_rotation(lookup.get(j['a'])),xyz(j['axisA']));tangent,_,_=basis(world_axis)
            ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);ta=mul(transpose(ra),tangent);tb=mul(transpose(rb),tangent)
            orientA='1,'+','.join(map(f,ta))+',3,'+vec(j['axisA']);orientB='1,'+','.join(map(f,tb))+',3,'+vec(j['axisB'])
            text+=f" joint: {index}, revolute hinge, {a}, position, reference, node, {vec(j['anchorA'])}, orientation, reference, node, {orientA}, {b}, position, reference, node, {vec(j['anchorB'])}, orientation, reference, node, {orientB};\n"
        elif j['type']=='universal':
            ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);ua=mul(ra,xyz(j['axisA']));ub=mul(rb,xyz(j['axisB']))
            transverse=cross(ub,ua);magnitude=norm(transverse);transverse=[v/magnitude for v in transverse]
            ya=cross(ua,transverse);zb=cross(transverse,ub)
            ha=[[transverse[i],ya[i],ua[i]] for i in range(3)];hb=[[transverse[i],ub[i],zb[i]] for i in range(3)]
            oa=orientation_spec(matmul(transpose(ra),ha));ob=orientation_spec(matmul(transpose(rb),hb))
            text+=f" joint: {index}, cardano hinge, {a}, position, reference, node, {vec(j['anchorA'])}, orientation, reference, node, {oa}, {b}, position, reference, node, {vec(j['anchorB'])}, orientation, reference, node, {ob};\n"
        elif j['type']=='cylindrical':
            ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);axis=mul(ra,xyz(j['axisA']));t,second,_=basis(axis)
            h=[[t[i],second[i],axis[i]] for i in range(3)];oa=orientation_spec(matmul(transpose(ra),h));ob=orientation_spec(matmul(transpose(rb),h))
            text+=f" joint: {index}, total joint, {a}, position, reference, node, {vec(j['anchorA'])}, position orientation, reference, node, {oa}, rotation orientation, reference, node, {oa}, {b}, position, reference, node, {vec(j['anchorB'])}, position orientation, reference, node, {ob}, rotation orientation, reference, node, {ob}, position constraint, active, active, inactive, null, orientation constraint, active, active, inactive, null;\n"
        elif j['type']=='prismatic' and 'motion' in j:
            ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);axis=mul(ra,xyz(j['axisA']));t,second,_=basis(axis)
            h=[[t[i],second[i],axis[i]] for i in range(3)];oa=orientation_spec(matmul(transpose(ra),h));ob=orientation_spec(matmul(transpose(rb),h))
            position=joint_state(j,lookup.get(j['a']),lookup[j['b']])['position'];motion=j['motion']
            text+=f" joint: {index}, total joint, {a}, position, reference, node, {vec(j['anchorA'])}, position orientation, reference, node, {oa}, rotation orientation, reference, node, {oa}, {b}, position, reference, node, {vec(j['anchorB'])}, position orientation, reference, node, {ob}, rotation orientation, reference, node, {ob}, position constraint, active, active, active, single, 0,0,1, cosine, 0, {f(2*math.pi*motion['frequencyHz'])}, {f(motion['amplitude'])}, forever, {f(position)}, orientation constraint, active, active, active, null;\n"
        elif j['type']=='prismatic':
            axis=xyz(j['axisA']);t,_,_=basis(axis)
            orient='1,'+','.join(map(f,t))+',3,'+vec(j['axisA'])
            text+=f" joint: {index}, in line, {a}, position, reference, node, {vec(j['anchorA'])}, orientation, reference, node, {orient}, {b}, offset, reference, node, {vec(j['anchorB'])};\n"
            text+=f" joint: {extra_label}, prismatic, {a}, orientation, reference, global, eye, {b}, orientation, reference, global, eye;\n"
            extra_label+=1
        else:
            text+=f" joint: {index}, total joint, {a}, position, reference, node, {vec(j['anchorA'])}, position orientation, reference, global, eye, rotation orientation, reference, global, eye, {b}, position, reference, node, {vec(j['anchorB'])}, position orientation, reference, global, eye, rotation orientation, reference, global, eye, position constraint, active, active, active, null, orientation constraint, active, active, active, null;\n"
    for index,element in enumerate(rotary,len(joints)+2):
        j=joint_lookup[element['joint']];a=0 if j['a']=='ground' else labels[j['a']];b=labels[j['b']]
        ra,rb=body_rotation(lookup.get(j['a'])),body_rotation(lookup[j['b']]);axis=mul(ra,xyz(j['axisA']));t,second,_=basis(axis)
        h=[[t[i],second[i],axis[i]] for i in range(3)];fa=matmul(transpose(ra),h);fb=matmul(matmul(transpose(rb),h),rotation(0,0,-element['restAngleDeg']))
        text+=f" joint: {index}, deformable hinge, {a}, orientation, reference, node, {orientation_spec(fa)}, {b}, orientation, reference, node, {orientation_spec(fb)}, linear viscoelastic generic, diag,0,0,{f(element['stiffness'])}, diag,0,0,{f(element['damping'])};\n"
    for index,force in enumerate(forces,len(joints)+2+len(rotary)):
        a=0 if force['a']=='ground' else labels[force['a']];b=0 if force['b']=='ground' else labels[force['b']];length=force['restLength']
        if force['type']=='oleo-strut':
            law=f"shock absorber, {f(force['pressure'])}, {f(force['gasArea'])}, {f(length*force['gasArea']/force['gasVolume'])}, {f(force['gamma'])}, epsilon max, {f((force['maxLength']-length)/length)}, epsilon min, {f((force['minLength']-length)/length)}, penalty, {f(force['stopStiffness']*length)}, {f(force['stopDamping']*length)}, metering, const, {f(force['reboundMeteringArea'])}, negative, const, {f(force['compressionMeteringArea'])}, {f(force['fluidArea'])}, {f(force['fluidDensity'])}, {f(force['dischargeCoefficient']/length)}"
        else:law=f"linear viscoelastic, {f(force['stiffness']*length)}, {f(force['damping']*length)}"
        text+=f" joint: {index}, rod, {a}, position, reference, node, {vec(force['anchorA'])}, {b}, position, reference, node, {vec(force['anchorB'])}, {f(length)}, {law};\n"
    for i,contact in enumerate(contacts):
        axis=xyz(contact['planeNormal']);t,second,_=basis(axis);orient=orientation_spec([[t[i],second[i],axis[i]] for i in range(3)])
        plane=[p+contact['radius']*n for p,n in zip(xyz(contact['planePoint']),axis)]
        args=f"deformable displacement joint, 0, position, reference, node, {','.join(f(x) for x in plane)}, orientation, reference, node, {orient}, {labels[contact['body']]}, position, reference, node, {vec(contact['center'])}, "
        law=f'scalar function elastic orthotropic, null, null, "contact_{i}"'
        if contact.get('damping',0)>0:
            sensor=extra_label;extra_label+=1
            text+=f' joint: {sensor}, {args}linear elastic generic, null, output, no;\n'
            # MBDyn 1.7.3 ignores nonlinear damping in a purely viscous NLSF law; a zero elastic function enables the viscoelastic path.
            law=f'array, 2, {law}, bistop, initial status, inactive, element, {sensor}, joint, string, "dz", string, "Var<0", element, {sensor}, joint, string, "dz", string, "Var>=0", nlsf viscoelastic, null, "contact_zero", null, null, null, null, null, "contact_damping_{i}"'
        text+=f' joint: {extra_label}, {args}{law};\n'
        if friction(contact):
            # Regularised Coulomb friction from the contact's own normal force and the slip of the contact
            # point, v_c + R n x w, in the plane; applied as a force at the sphere centre and its couple.
            # Element data are read through an array drive, which calls them without an argument; each
            # stores its value in a deck variable that the last member combines.
            node=labels[contact['body']];n=axis;R=contact['radius'];w=lambda k:f'model::{k}angvel({node})'
            terms=lambda pairs:'+'.join(f'{f(c)}*{e}' for c,e in pairs if c) or '0'
            v=[f'friction_v{k}_{i}' for k in 'xyz'];p=[f'friction_p{k}_{i}' for k in 'xyz'];s,c,q,normal=f'friction_s_{i}',f'friction_c_{i}',f'friction_q_{i}',f'friction_n_{i}'
            slip=[f'{p[0]}={v[0]}+{f(R)}*({terms([(n[1],w("z")),(-n[2],w("y"))])})',f'{p[1]}={v[1]}+{f(R)}*({terms([(n[2],w("x")),(-n[0],w("z"))])})',f'{p[2]}={v[2]}+{f(R)}*({terms([(n[0],w("y")),(-n[1],w("x"))])})']
            slip+=[f'{q}={terms(zip(n,p))}']+[f'{p[k]}={p[k]}-{q}*{f(n[k])}' for k in range(3) if n[k]]
            slip+=[f'{s}=sqrt({p[0]}^2+{p[1]}^2+{p[2]}^2)',f'{c}=-{f(friction(contact))}*{normal}*tanh({s}/{f(slip_velocity(contact))})/({s}+{f(1e-9*slip_velocity(contact))})']
            text+=''.join(f' set: real {name}=0.;\n' for name in (*v,*p,q,s,c,normal))
            reads=[f'element, {extra_label}, joint, string, "{datum}", string, "{name}=Var; 0"' for datum,name in zip(('vx','vy','vz'),v)]
            reads.append(f'element, {extra_label}, joint, string, "Fz", string, "{normal}=max(0.,-Var); 0"')
            friction_chains[contact['id']]=lambda result,reads=reads,slip=slip:f'array, 5, {", ".join(reads)}, string, "{"; ".join(slip)}; {result}"'
        extra_label+=1
    friction_text=''
    for i,contact in enumerate(contacts):
        if not friction(contact):continue
        chain=friction_chains[contact['id']];p=[f'friction_p{k}_{i}' for k in 'xyz'];c=f'friction_c_{i}';n=xyz(contact['planeNormal']);R=contact['radius']
        moment=[f'{f(-R)}*{c}*({f(a)}*{x}-{f(b)}*{y})' for a,x,b,y in ((n[1],p[2],n[2],p[1]),(n[2],p[0],n[0],p[2]),(n[0],p[1],n[1],p[0]))]
        force_label,couple_label=friction_labels[contact['id']]
        # The x component recomputes the slip; y and z, evaluated after it, reuse the stored values.
        friction_text+=f" force: {force_label}, absolute, {labels[contact['body']]}, position, reference, node, {vec(contact['center'])}, component, {chain(f'{c}*{p[0]}')}, "+', '.join(f'string, "{c}*{x}"' for x in p[1:])+';\n'
        friction_text+=f" couple: {couple_label}, absolute, {labels[contact['body']]}, component, {chain(moment[0])}, "+', '.join(f'string, "{x}"' for x in moment[1:])+';\n'
    label=1
    for drive in drives:
        j=joint_lookup[drive['joint']]
        for side,sign in (('b',1),('a',-1)):
            if j[side]=='ground':continue
            axis=xyz(j['axisB'] if side=='b' else j['axisA'])
            text+=f" couple: {label}, follower, {labels[j[side]]}, {','.join(f(v) for v in axis)}, sine, 0, {f(2*math.pi*drive['frequencyHz'])}, {f(sign*drive['amplitude'])}, forever, {f(sign*drive['offset'])};\n"
            label+=1
    for drive in linear_drives:
        j=joint_lookup[drive['joint']];a=0 if j['a']=='ground' else labels[j['a']];b=labels[j['b']]
        axis=xyz(j['axisB']) if j['type']=='cylindrical' else mul(transpose(body_rotation(lookup[j['b']])),mul(body_rotation(lookup.get(j['a'])),xyz(j['axisA'])))
        text+=f" force: {label}, follower internal, {b}, position, reference, node, {vec(j['anchorB'])}, {a}, position, reference, node, {vec(j['anchorA'])}, {','.join(f(v) for v in axis)}, sine, 0, {f(2*math.pi*drive['frequencyHz'])}, {f(drive['amplitude'])}, forever, {f(drive['offset'])};\n";label+=1
    for load in loads:
        kind='absolute' if load['frame']=='global' else 'follower';body=labels[load['body']]
        drive=f"sine, 0, {f(2*math.pi*load['frequencyHz'])}, {f(load['amplitude'])}, forever, {f(load['offset'])}"
        if any(load['force'].values()):
            text+=f" force: {label}, {kind}, {body}, position, reference, node, {vec(load['point'])}, {vec(load['force'])}, {drive};\n";label+=1
        if any(load['torque'].values()):
            text+=f" couple: {label}, {kind}, {body}, {vec(load['torque'])}, {drive};\n";label+=1
    text+=friction_text
    if gn:text+=f" gravity: uniform, {','.join(f(v/gn) for v in g)}, const, {f(gn)};\n"
    return text+'end: elements;\n'


def parse_joint_reactions(directory,model,samples):
    """Read complete native joint frames and normalize constraint wrenches on body B."""
    joints=model['joints']
    rotary,forces,contacts=model.get('rotationalElements',[]),model.get('forces',[]),model.get('contacts',[])
    if not joints and not any(force.get('type')=='oleo-strut' for force in forces):return
    extra=len(joints)+2+len(rotary)+len(forces)
    order=[1];records={};native_types={};oleo_labels={len(joints)+2+len(rotary)+i:force['id'] for i,force in enumerate(forces) if force.get('type')=='oleo-strut'}
    native_types.update({label:'rod' for label in oleo_labels})
    for label,joint in enumerate(joints,2):
        kind=joint['type'];free_slider=kind=='prismatic' and 'motion' not in joint
        total=driven(joint)
        order.append(label);records[label]=(joint['id'],'force' if free_slider else 'both',-1 if kind in ('prismatic','cylindrical','weld') or total else 1,13 if free_slider else 16 if kind in ('spherical','universal') else 19 if kind=='revolute' and not total else 25)
        native_types[label]='totaljoint' if total else {'spherical':'sphericalhinge','revolute':'revolutehinge','universal':'cardanohinge','prismatic':'inline' if free_slider else 'totaljoint','cylindrical':'totaljoint','weld':'totaljoint'}[kind]
        if free_slider:
            order.append(extra);records[extra]=(joint['id'],'moment',1,13);native_types[extra]='prismatic';extra+=1
    order.extend(range(len(joints)+2,len(joints)+2+len(rotary)+len(forces)))
    for contact in contacts:
        if contact.get('damping',0)>0:extra+=1  # zero-output gap sensor
        order.append(extra);extra+=1
    path=directory/'result.jnt'
    if not path.is_file():raise ValueError('Missing native joint output result.jnt; joint reactions cannot be verified.')
    if path.stat().st_size>256*1024*1024:raise ValueError('Native joint output exceeds the 256-MiB parsing limit.')
    found={}
    with (directory/'result.log').open(encoding='utf-8') as stream:
        for line in stream:
            fields=line.split()
            if len(fields)<2 or not fields[0].endswith(':'):continue
            try:label=int(fields[1])
            except ValueError:continue
            if label in native_types:
                observed=fields[0][:-1]
                if observed not in ('sphericalhinge','revolutehinge','cardanohinge','inline','prismatic','totaljoint','rod'):continue
                if label in found:raise ValueError('Duplicate native joint metadata.')
                found[label]=observed
    if found!=native_types:raise ValueError('Native joint types do not match the generated model; reaction interpretation is unavailable.')
    index=0;frame={};oleo_frame={}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            fields=line.split()
            if not fields:continue
            if index>=len(samples)*len(order):raise ValueError('Unexpected extra native joint output frame.')
            try:label=int(fields[0])
            except ValueError as exc:raise ValueError('Invalid native joint output label.') from exc
            if label!=order[index%len(order)]:raise ValueError('Missing, repeated or reordered native joint output record.')
            if label in records:
                joint_id,part,sign,width=records[label]
                if len(fields)!=width:raise ValueError(f'Unexpected native joint record width for {joint_id}.')
                try:values=[float(x) for x in fields[1:]]
                except ValueError as exc:raise ValueError(f'Invalid native reaction for {joint_id}.') from exc
                if not all(math.isfinite(x) for x in values):raise ValueError(f'Non-finite native reaction for {joint_id}.')
                reaction=frame.setdefault(joint_id,{'id':joint_id})
                if part in ('both','force'):reaction['force']=dict(zip(('x','y','z'),(sign*x for x in values[6:9])))
                if part in ('both','moment'):reaction['moment']=dict(zip(('x','y','z'),(sign*x for x in values[9:12])))
            if label in oleo_labels:
                if len(fields)!=22:raise ValueError(f"Unexpected native oleo record width for {oleo_labels[label]}.")
                try:values=[float(x) for x in fields[1:]]
                except ValueError as exc:raise ValueError(f"Invalid native oleo record for {oleo_labels[label]}.") from exc
                if not all(math.isfinite(x) for x in values):raise ValueError(f"Non-finite native oleo record for {oleo_labels[label]}.")
                oleo_frame[oleo_labels[label]]={'force':values[0],'length':values[12],'rate':values[16],'pressure':values[17],'meteringArea':values[18],'elastic':values[19],'hydraulic':values[20]}
            index+=1
            if index%len(order)==0:
                if len(frame)!=len(joints) or any('force' not in frame[j['id']] or 'moment' not in frame[j['id']] for j in joints):raise ValueError('Incomplete native joint reaction frame.')
                if len(oleo_frame)!=len(oleo_labels):raise ValueError('Incomplete native oleo output frame.')
                sample=samples[index//len(order)-1]
                if joints:sample['jointReactions']=[frame[j['id']] for j in joints]
                if oleo_labels:sample['_nativeOleo']=oleo_frame
                frame={};oleo_frame={}
    if index!=len(samples)*len(order):raise ValueError('Incomplete native joint output; reaction frames do not match node frames.')


def parse_friction(directory,model,samples):
    """Read the friction force and couple MBDyn applied to each frictional contact at every output frame."""
    labels=friction_force_labels(model)
    if not labels:return
    owners={label:(contact,kind) for contact,pair in labels.items() for label,kind in zip(pair,('force','couple'))}
    path=directory/'result.frc'
    if not path.is_file():raise ValueError('Missing native force output result.frc; contact friction cannot be read.')
    if path.stat().st_size>256*1024*1024:raise ValueError('Native force output exceeds the 256-MiB parsing limit.')
    rows={label:[] for label in owners}
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            fields=line.split()
            try:label=int(fields[0]) if fields else None
            except ValueError as exc:raise ValueError('Invalid native force output label.') from exc
            if label not in owners:continue
            if len(fields)!=(8 if owners[label][1]=='force' else 5):raise ValueError(f'Unexpected native friction record width for {owners[label][0]}.')
            try:values=[float(x) for x in fields[2:5]]
            except ValueError as exc:raise ValueError(f'Invalid native friction record for {owners[label][0]}.') from exc
            if not all(math.isfinite(x) for x in values):raise ValueError(f'Non-finite native friction for {owners[label][0]}.')
            rows[label].append(values)
    if any(len(values)!=len(samples) for values in rows.values()):raise ValueError('Native friction output frames do not match node frames.')
    for index,sample in enumerate(samples):
        sample['_friction']={contact:{kind:rows[label][index] for label,kind in zip(pair,('force','couple'))} for contact,pair in labels.items()}


def parse_output(directory,model):
    from source_catalog import parse_output as native_output
    native=native_output(directory,{'simulation':model['simulation'],'nodes':[{'id':i+1} for i in range(len(model['bodies']))]})
    if abs(native[0]['time'])>1e-10:raise ValueError('Spatial output must include its initial frame at time zero.')
    if len(native)*len(model['bodies'])>160000+2*len(model['bodies']) or len(native)*len(model['bodies'])*element_csv_values_per_row(model)>1600000:
        raise ValueError('Actual native output exceeds the body-step or 1,600,000 scalar-value limit; shorten the duration, increase the step, or reduce bodies, joints or elements.')
    parse_joint_reactions(directory,model,native)
    parse_friction(directory,model,native)
    initial={body['id']:body for body in model['bodies']};joints={j['id']:j for j in model['joints']}
    rotary,drives,forces,loads=model.get('rotationalElements',[]),model.get('jointTorques',[]),model.get('forces',[]),model.get('loads',[])
    linear_drives=model.get('jointForces',[]);contacts=model.get('contacts',[])
    linear_axes={}
    for drive in linear_drives:
        joint=joints[drive['joint']]
        linear_axes[drive['id']]=xyz(joint['axisB']) if joint['type']=='cylindrical' else mul(transpose(body_rotation(initial[joint['b']])),mul(body_rotation(initial.get(joint['a'])),xyz(joint['axisA'])))
    frames={}
    for element in rotary:
        joint=joints[element['joint']];ra=body_rotation(initial.get(joint['a']));rb=body_rotation(initial[joint['b']]);axis=mul(ra,xyz(joint['axisA']));t,second,_=basis(axis)
        h=[[t[i],second[i],axis[i]] for i in range(3)]
        frames[element['id']]=(matmul(transpose(ra),h),matmul(transpose(rb),h))
    references={j['id']:matmul(transpose(body_rotation(initial.get(j['a']))),body_rotation(initial[j['b']])) for j in model['joints'] if j['type']=='prismatic'}
    cylinder_frames={}
    for joint in model['joints']:
        if joint['type']=='cylindrical' or driven(joint):
            ra,rb=body_rotation(initial.get(joint['a'])),body_rotation(initial[joint['b']]);axis=mul(ra,xyz(joint['axisA']));t,second,_=basis(axis);h=[[t[i],second[i],axis[i]] for i in range(3)]
            cylinder_frames[joint['id']]=(matmul(transpose(ra),h),matmul(transpose(rb),h))
    previous_angles={};cylinder_angles={};previous_time=None;previous_damping=previous_power=previous_load_power=previous_linear_power=0.;dissipated=work=load_work=linear_work=0.
    contact_previous_time=None;contact_previous_power={};contact_dissipated={};friction_previous_power={};friction_dissipated={}
    drive_previous_time=None;drive_previous_power=0.;drive_work=0.
    for sample in native:
        observed={}
        for body,node in zip(model['bodies'],sample['nodes']):
            node.update(label=node['id'],id=body['id'])
            node['rotationMatrix']=[x for row in rotation(node['rx'],node['ry'],node['rz']) for x in row]
            observed[body['id']]={'pose':{k:node[k] for k in ('x','y','z','rx','ry','rz')},'velocity':{k:node[k] for k in ('vx','vy','vz','wx','wy','wz')},'centerOfMass':body.get('centerOfMass',dict.fromkeys(('x','y','z'),0.))}
        states=[joint_state(j,observed.get(j['a']),observed[j['b']],references.get(j['id'])) for j in model['joints']]
        sample['joints']=states
        sample['sliders']=[{key:state[key] for key in ('id','position','velocity','transverse','transverseVelocity','angle','angularVelocity')} for state,joint in zip(states,model['joints']) if joint['type']=='prismatic']
        cylinders=[]
        for joint,state in zip(model['joints'],states):
            if joint['type']!='cylindrical':continue
            a,b=observed.get(joint['a']),observed[joint['b']];fa,fb=cylinder_frames[joint['id']];ra,rb=body_rotation(a),body_rotation(b)
            relative=matmul(transpose(matmul(ra,fa)),matmul(rb,fb));wrapped=math.atan2(relative[1][0],relative[0][0]);axis=mul(ra,xyz(joint['axisA']));speed=sum(x*y for x,y in zip(axis,sub(angular(b),angular(a))))
            if abs(speed)*model['simulation']['step']>.1:raise ValueError(f"Cylindrical joint {joint['id']} rotation exceeds 0.1 rad per step; reduce the step.")
            previous=cylinder_angles.get(joint['id']);unwrapped=wrapped if previous is None else previous+math.atan2(math.sin(wrapped-previous),math.cos(wrapped-previous));cylinder_angles[joint['id']]=unwrapped
            cylinders.append({**{key:state[key] for key in ('id','position','velocity','transverse','transverseVelocity','angularError','angularVelocityError')},'angle':unwrapped,'angularVelocity':speed})
        if cylinders:sample['cylinders']=cylinders
        rotary_drives=[]
        for joint in model['joints']:
            if not driven(joint):continue
            a,b=observed.get(joint['a']),observed[joint['b']];fa,fb=cylinder_frames[joint['id']];ra,rb=body_rotation(a),body_rotation(b)
            relative=matmul(transpose(matmul(ra,fa)),matmul(rb,fb));wrapped=math.atan2(relative[1][0],relative[0][0]);axis=mul(ra,xyz(joint['axisA']))
            speed=sum(x*y for x,y in zip(axis,sub(angular(b),angular(a))))
            previous=cylinder_angles.get(joint['id']);unwrapped=wrapped if previous is None else previous+math.atan2(math.sin(wrapped-previous),math.cos(wrapped-previous));cylinder_angles[joint['id']]=unwrapped
            reaction=next(item for item in sample['jointReactions'] if item['id']==joint['id'])
            torque=sum(x*y for x,y in zip(axis,xyz(reaction['moment'])))
            rotary_drives.append({'id':joint['id'],'angle':unwrapped,'commandedAngle':rotary_angle(joint['motion'],sample['time']),'speed':speed,'torque':torque,'power':torque*speed})
        if rotary_drives:
            power=sum(item['power'] for item in rotary_drives)
            if drive_previous_time is not None:drive_work+=(sample['time']-drive_previous_time)*(power+drive_previous_power)/2
            drive_previous_time,drive_previous_power=sample['time'],power
            sample.update(rotaryDrives=rotary_drives,rotaryDrivePower=power,rotaryDriveWork=drive_work)
        sample['jointAngularError']=max((state['angularError'] for state in states),default=0.);sample['jointAngularVelocityError']=max((state['angularVelocityError'] for state in states),default=0.)
        for key in ('positionError','velocityError','angularError','angularVelocityError'):sample[key]=max((state[key] for state in states),default=0.)
        force_states=[]
        for force in forces:
            state=spring_state(force,observed)
            if force['type']=='oleo-strut':state=validated_oleo_state(force,state,sample['_nativeOleo'][force['id']])
            force_states.append(state)
        sample.pop('_nativeOleo',None)
        rotary_states=[];energy_terms=[spring_energy(force,state) for force,state in zip(forces,force_states)];elastic=sum(term[0] for term in energy_terms);damping_power=sum(term[1] for term in energy_terms)
        for state in force_states:state.pop('_stopDeflection',None)
        for element in rotary:
            joint=joints[element['joint']];a,b=observed.get(joint['a']),observed[joint['b']];fa,fb=frames[element['id']]
            ra,rb=body_rotation(a),body_rotation(b);relative=matmul(transpose(matmul(ra,fa)),matmul(rb,fb))
            q=math.atan2(relative[1][0],relative[0][0])-math.radians(element['restAngleDeg']);q=math.atan2(math.sin(q),math.cos(q))
            axis=mul(ra,xyz(joint['axisA']));omega=sum(x*y for x,y in zip(axis,sub(angular(b),angular(a))))
            if abs(q)>=math.pi-1e-6 or (element['id'] in previous_angles and abs(q-previous_angles[element['id']])>math.pi) or abs(omega)*model['simulation']['step']>.1:raise ValueError(f"Rotational element {element['id']} crossed or cannot resolve the +/-pi rotation branch.")
            previous_angles[element['id']]=q;torque=-element['stiffness']*q-element['damping']*omega
            rotary_states.append({'id':element['id'],'angle':q,'velocity':omega,'torque':torque})
            elastic+=.5*element['stiffness']*q*q;damping_power+=element['damping']*omega*omega
        drive_states=[];drive_power=0.
        for drive in drives:
            joint=joints[drive['joint']];a,b=observed.get(joint['a']),observed[joint['b']];axis=mul(body_rotation(a),xyz(joint['axisA']))
            omega=sum(x*y for x,y in zip(axis,sub(angular(b),angular(a))));torque=drive['offset']+drive['amplitude']*math.sin(2*math.pi*drive['frequencyHz']*sample['time']);power=torque*omega
            drive_states.append({'id':drive['id'],'torque':torque,'power':power});drive_power+=power
        linear_states=[];linear_power=0.
        for drive in linear_drives:
            joint=joints[drive['joint']];a,b=observed.get(joint['a']),observed[joint['b']]
            axis=mul(body_rotation(b),linear_axes[drive['id']])
            relative=sub(anchor_velocity(b,joint['anchorB']),anchor_velocity(a,joint['anchorA']))
            effort=drive['offset']+drive['amplitude']*math.sin(2*math.pi*drive['frequencyHz']*sample['time'])
            power=effort*sum(x*y for x,y in zip(axis,relative))
            linear_states.append({'id':drive['id'],'force':effort,'power':power});linear_power+=power
        load_states=[];load_power=0.
        for load in loads:
            body=observed[load['body']];rotation_matrix=body_rotation(body);scale=load['offset']+load['amplitude']*math.sin(2*math.pi*load['frequencyHz']*sample['time'])
            force=xyz(load['force']);torque=xyz(load['torque'])
            if load['frame']=='body':force=mul(rotation_matrix,force);torque=mul(rotation_matrix,torque)
            force=[v*scale for v in force];torque=[v*scale for v in torque];offset=mul(rotation_matrix,sub(xyz(load['point']),xyz(body['centerOfMass'])));moment=[a+b for a,b in zip(cross(offset,force),torque)]
            velocity=anchor_velocity(body,load['point']);power=sum(a*b for a,b in zip(force,velocity))+sum(a*b for a,b in zip(torque,angular(body)))
            vector=lambda values:dict(zip(('x','y','z'),values));load_states.append({'id':load['id'],'force':vector(force),'torque':vector(torque),'moment':vector(moment),'power':power});load_power+=power
        if previous_time is not None:
            dt=sample['time']-previous_time;dissipated+=dt*(damping_power+previous_damping)/2;work+=dt*(drive_power+previous_power)/2;load_work+=dt*(load_power+previous_load_power)/2;linear_work+=dt*(linear_power+previous_linear_power)/2
        previous_time=sample['time'];previous_damping=damping_power;previous_power=drive_power;previous_load_power=load_power;previous_linear_power=linear_power
        if contacts:
            sample['contactStates']=[]
            for contact in contacts:
                body=observed[contact['body']];normal=xyz(contact['planeNormal']);center=anchor(body,contact['center']);gap=sum(n*(x-p) for n,x,p in zip(normal,center,xyz(contact['planePoint'])))-contact['radius'];penetration=max(0.,-gap);speed=sum(n*v for n,v in zip(normal,anchor_velocity(body,contact['center'])))
                damping=contact.get('damping',0.)*max(0.,-speed) if gap<0 else 0.;effort=contact['stiffness']*penetration+damping;contact_power=damping*max(0.,-speed)
                if contact_previous_time is not None:contact_dissipated[contact['id']]=contact_dissipated.get(contact['id'],0.)+(sample['time']-contact_previous_time)*(contact_power+contact_previous_power[contact['id']])/2
                contact_previous_power[contact['id']]=contact_power
                state={'id':contact['id'],'gap':gap,'penetration':penetration,'force':effort,'power':effort*speed,'energy':.5*contact['stiffness']*penetration**2,'dampingPower':contact_power,'dissipatedEnergy':contact_dissipated.get(contact['id'],0.)}
                if friction(contact):
                    # Slip of the contact point in the plane; the friction force is MBDyn's own (result.frc).
                    point=[v+contact['radius']*t for v,t in zip(anchor_velocity(body,contact['center']),cross(normal,angular(body)))]
                    along=sum(n*v for n,v in zip(normal,point));slip=[v-along*n for v,n in zip(point,normal)];applied=sample['_friction'][contact['id']]['force']
                    friction_power=-sum(a*b for a,b in zip(applied,slip))
                    if contact_previous_time is not None:friction_dissipated[contact['id']]=friction_dissipated.get(contact['id'],0.)+(sample['time']-contact_previous_time)*(friction_power+friction_previous_power[contact['id']])/2
                    friction_previous_power[contact['id']]=friction_power
                    state.update(frictionForce=norm(applied),frictionVector=dict(zip(('x','y','z'),applied)),slip=norm(slip),frictionPower=friction_power,frictionEnergy=friction_dissipated.get(contact['id'],0.))
                sample['contactStates'].append(state)
            contact_previous_time=sample['time']
            sample.pop('_friction',None)
        if forces:sample['forces']=force_states
        if rotary:sample['rotationalStates']=rotary_states
        if rotary or forces:sample.update(elasticEnergy=elastic,dampingPower=damping_power,dissipatedEnergy=dissipated)
        if drives:sample.update(actuationStates=drive_states,actuationPower=drive_power,actuationWork=work)
        if linear_drives:sample.update(jointForceStates=linear_states,jointForcePower=linear_power,jointForceWork=linear_work)
        if loads:sample.update(loadStates=load_states,loadPower=load_power,appliedWork=load_work)
    return native


def metrics(model,samples):
    result={'duration':samples[-1]['time'],'sampleCount':len(samples),'bodyCount':len(model['bodies']),'jointCount':len(model['joints']),
            'maxConstraintError':max(s['positionError'] for s in samples),'maxJointVelocityError':max(s['velocityError'] for s in samples),
            'maxJointAngularError':max(s['angularError'] for s in samples),'maxJointAngularVelocityError':max(s['angularVelocityError'] for s in samples),
            'constraintErrorUnit':'m','angularConstraintErrorUnit':'rad',
            'validationScope':'3D rigid body motion, joint residuals and optional fixed-plane spherical penalty contact with regularised Coulomb friction; no general surface contact, true stiction, flexible bodies or certification.'}
    if model.get('rotationalElements') or model.get('forces'):result.update(finalElasticEnergy=samples[-1]['elasticEnergy'],dissipatedEnergy=samples[-1]['dissipatedEnergy'],energyUnit='J')
    if model.get('jointTorques'):result.update(actuationWork=samples[-1]['actuationWork'],energyUnit='J')
    if 'rotaryDriveWork' in samples[-1]:result.update(rotaryDriveWork=samples[-1]['rotaryDriveWork'],peakRotaryDriveTorque=max(abs(d['torque']) for s in samples for d in s['rotaryDrives']),energyUnit='J')
    if model.get('jointForces'):result.update(jointForceWork=samples[-1]['jointForceWork'],energyUnit='J')
    if model.get('loads'):result.update(appliedWork=samples[-1]['appliedWork'],energyUnit='J')
    if model.get('contacts'):result.update(maxContactForce=max(c['force'] for sample in samples for c in sample['contactStates']),maxPenetration=max(c['penetration'] for sample in samples for c in sample['contactStates']),contactDissipatedEnergy=sum(c.get('dissipatedEnergy',0.) for c in samples[-1]['contactStates']))
    if any(friction(c) for c in model.get('contacts',[])):result.update(maxFrictionForce=max(c.get('frictionForce',0.) for sample in samples for c in sample['contactStates']),frictionDissipatedEnergy=sum(c.get('frictionEnergy',0.) for c in samples[-1]['contactStates']))
    return result


def write_csv(path,samples):
    fields=['time','id','label','x','y','z','rx','ry','rz','vx','vy','vz','wx','wy','wz','positionError','velocityError','angularError','angularVelocityError']
    rotary=[v['id'] for v in samples[0].get('rotationalStates',[])];drives=[v['id'] for v in samples[0].get('actuationStates',[])];sliders=[v['id'] for v in samples[0].get('sliders',[])];forces=[v['id'] for v in samples[0].get('forces',[])];loads=[v['id'] for v in samples[0].get('loadStates',[])];cylinders=[v['id'] for v in samples[0].get('cylinders',[])]
    linear_drives=[v['id'] for v in samples[0].get('jointForceStates',[])];contacts=[v['id'] for v in samples[0].get('contactStates',[])]
    reactions=[v['id'] for v in samples[0].get('jointReactions',[])];rotary_drives=[v['id'] for v in samples[0].get('rotaryDrives',[])]
    for name in rotary_drives:fields += [f'rotaryDrive:{name}:angle_rad',f'rotaryDrive:{name}:speed_rad_s',f'rotaryDrive:{name}:torque_Nm',f'rotaryDrive:{name}:power_W']
    if rotary_drives:fields += ['rotaryDrivePower_W','rotaryDriveWork_J']
    for name in reactions:fields += [f'jointReaction:{name}:{kind}_{axis}_{unit}' for kind,unit in (('force','N'),('moment','Nm')) for axis in ('x','y','z')]
    for name in contacts:fields += [f'contact:{name}:gap_m',f'contact:{name}:penetration_m',f'contact:{name}:force_N',f'contact:{name}:power_W',f'contact:{name}:energy_J',f'contact:{name}:dampingPower_W',f'contact:{name}:dissipatedEnergy_J']
    for state in samples[0].get('contactStates',[]):
        if 'frictionForce' in state:fields += [f"contact:{state['id']}:{unit}" for _,unit in FRICTION_COLUMNS]
    for name in cylinders:fields += [f'cylindrical:{name}:position_m',f'cylindrical:{name}:velocity_m_s',f'cylindrical:{name}:angle_rad',f'cylindrical:{name}:angularVelocity_rad_s']
    for name in loads:fields += [f'load:{name}:{kind}_{axis}_{unit}' for kind,unit in (('force','N'),('torque','Nm'),('moment','Nm')) for axis in ('x','y','z')]+[f'load:{name}:power_W']
    if loads:fields += ['loadPower_W','appliedWork_J']
    for name in forces:fields += [f'force:{name}:length_m',f'force:{name}:extension_m',f'force:{name}:rate_m_s',f'force:{name}:tension_N']
    for state in samples[0].get('forces',[]):
        if 'gasPressure' in state:fields += [f"force:{state['id']}:gasPressure_Pa",f"force:{state['id']}:gasForce_N",f"force:{state['id']}:hydraulicForce_N",f"force:{state['id']}:stopForce_N"]
    for name in sliders:fields += [f'slider:{name}:position_m',f'slider:{name}:velocity_m_s',f'slider:{name}:transverse_m',f'slider:{name}:transverseVelocity_m_s',f'slider:{name}:angle_rad',f'slider:{name}:angularVelocity_rad_s']
    for name in rotary:fields += [f'rotational:{name}:angle_rad',f'rotational:{name}:velocity_rad_s',f'rotational:{name}:torque_Nm']
    for name in drives:fields += [f'actuation:{name}:torque_Nm',f'actuation:{name}:power_W']
    for name in linear_drives:fields += [f'jointForce:{name}:force_N',f'jointForce:{name}:power_W']
    if rotary or forces:fields += ['elasticEnergy_J','dampingPower_W','dissipatedEnergy_J']
    if drives:fields += ['actuationPower_W','actuationWork_J']
    if linear_drives:fields += ['jointForcePower_W','jointForceWork_J']
    with path.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for sample in samples:
            values={}
            for reaction in sample.get('jointReactions',[]):
                for kind,unit in (('force','N'),('moment','Nm')):
                    for axis in ('x','y','z'):values[f"jointReaction:{reaction['id']}:{kind}_{axis}_{unit}"]=reaction[kind][axis]
            for state in sample.get('rotaryDrives',[]):
                for key,unit in (('angle','angle_rad'),('speed','speed_rad_s'),('torque','torque_Nm'),('power','power_W')):values[f"rotaryDrive:{state['id']}:{unit}"]=state[key]
            if 'rotaryDrivePower' in sample:values.update(rotaryDrivePower_W=sample['rotaryDrivePower'],rotaryDriveWork_J=sample['rotaryDriveWork'])
            for state in sample.get('cylinders',[]):
                for key,unit in (('position','position_m'),('velocity','velocity_m_s'),('angle','angle_rad'),('angularVelocity','angularVelocity_rad_s')):values[f"cylindrical:{state['id']}:{unit}"]=state[key]
            for state in sample.get('loadStates',[]):
                for kind,unit in (('force','N'),('torque','Nm'),('moment','Nm')):
                    for axis in ('x','y','z'):values[f"load:{state['id']}:{kind}_{axis}_{unit}"]=state[kind][axis]
                values[f"load:{state['id']}:power_W"]=state['power']
            if loads:values.update(loadPower_W=sample['loadPower'],appliedWork_J=sample['appliedWork'])
            for state in sample.get('forces',[]):
                for key,unit in (('length','length_m'),('extension','extension_m'),('rate','rate_m_s'),('force','tension_N')):values[f"force:{state['id']}:{unit}"]=state[key]
                if 'gasPressure' in state:
                    for key,unit in (('gasPressure','gasPressure_Pa'),('gasForce','gasForce_N'),('hydraulicForce','hydraulicForce_N'),('stopForce','stopForce_N')):values[f"force:{state['id']}:{unit}"]=state[key]
            for state in sample.get('sliders',[]):
                for key,unit in (('position','position_m'),('velocity','velocity_m_s'),('transverse','transverse_m'),('transverseVelocity','transverseVelocity_m_s'),('angle','angle_rad'),('angularVelocity','angularVelocity_rad_s')):values[f"slider:{state['id']}:{unit}"]=state[key]
            for state in sample.get('rotationalStates',[]):
                for key,unit in (('angle','angle_rad'),('velocity','velocity_rad_s'),('torque','torque_Nm')):values[f"rotational:{state['id']}:{unit}"]=state[key]
            for state in sample.get('actuationStates',[]):
                for key,unit in (('torque','torque_Nm'),('power','power_W')):values[f"actuation:{state['id']}:{unit}"]=state[key]
            for state in sample.get('contactStates',[]):
                for key,unit in (('gap','gap_m'),('penetration','penetration_m'),('force','force_N'),('power','power_W'),('energy','energy_J'),('dampingPower','dampingPower_W'),('dissipatedEnergy','dissipatedEnergy_J')):values[f"contact:{state['id']}:{unit}"]=state.get(key,0.)
                if 'frictionForce' in state:
                    for key,unit in FRICTION_COLUMNS:values[f"contact:{state['id']}:{unit}"]=state[key]
            for state in sample.get('jointForceStates',[]):
                for key,unit in (('force','force_N'),('power','power_W')):values[f"jointForce:{state['id']}:{unit}"]=state[key]
            if rotary or forces:values.update(elasticEnergy_J=sample['elasticEnergy'],dampingPower_W=sample['dampingPower'],dissipatedEnergy_J=sample['dissipatedEnergy'])
            if drives:values.update(actuationPower_W=sample['actuationPower'],actuationWork_J=sample['actuationWork'])
            if linear_drives:values.update(jointForcePower_W=sample['jointForcePower'],jointForceWork_J=sample['jointForceWork'])
            for node in sample['nodes']:
                writer.writerow({**{k:node[k] for k in fields if k in node},**{k:sample[k] for k in ('time','positionError','velocityError','angularError','angularVelocityError')},**values})


def examples():
    def body(identifier,x,y,z):return {'id':identifier,'name':identifier.title(),'mass':1.,'inertia':{'xx':.1,'yy':.1,'zz':.1},'pose':{'x':x,'y':y,'z':z,'rx':0.,'ry':0.,'rz':0.},'velocity':{'vx':0.,'vy':0.,'vz':0.,'wx':0.,'wy':0.,'wz':0.}}
    def vec(x,y,z):return {'x':x,'y':y,'z':z}
    sphere={'kind':KIND,'name':'3D spherical pendulum','parameters':{'gravity':vec(0,0,-9.81)},'simulation':{'duration':1.,'step':.002},'bodies':[body('bob',.5,0,-.8660254037844386)],'joints':[{'id':'ball','type':'spherical','a':'ground','b':'bob','anchorA':vec(0,0,0),'anchorB':vec(-.5,0,.8660254037844386)}]}
    hinge={'kind':KIND,'name':'3D revolute pendulum','parameters':{'gravity':vec(0,0,-9.81)},'simulation':{'duration':1.,'step':.002},'bodies':[body('arm',.5,0,-.8660254037844386)],'joints':[{'id':'hinge','type':'revolute','a':'ground','b':'arm','anchorA':vec(0,0,0),'anchorB':vec(-.5,0,.8660254037844386),'axisA':vec(0,1,0),'axisB':vec(0,1,0)}]}
    slider_body=body('block',.18,.24,0.)
    slider_body['pose'].update(rx=20.,ry=-10.,rz=15.)
    slider_body['velocity'].update(vx=.12,vy=.16)
    slider={'kind':KIND,'name':'3D oblique slider','parameters':{'gravity':vec(-1.8,-2.4,0)},'simulation':{'duration':.5,'step':.001},'bodies':[slider_body],
            'joints':[{'id':'guide','type':'prismatic','a':'ground','b':'block','anchorA':vec(0,0,0),'anchorB':vec(0,0,0),'axisA':vec(.6,.8,0)}]}
    sprung=copy.deepcopy(slider);sprung.update(name='3D oblique spring-slider',parameters={'gravity':vec(0,0,0)},forces=[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'block','anchorA':vec(-.6,-.8,0),'anchorB':vec(0,0,0),'stiffness':10.,'damping':1.,'restLength':1.}])
    cylinder=copy.deepcopy(slider);cylinder['name']='3D cylindrical slider';cylinder['bodies'][0]['velocity'].update(wx=.72,wy=.96,wz=0.)
    axis_b=mul(transpose(body_rotation(cylinder['bodies'][0])),[.6,.8,0.]);cylinder['joints'][0].update(type='cylindrical',axisB=dict(zip(('x','y','z'),axis_b)))
    universal_body=body('yoke',.4,.1,-.3);universal_body['pose'].update(rx=20.,ry=-10.,rz=15.);universal_body['velocity'].update(wy=.8,wz=1.2)
    world_y_local=mul(transpose(body_rotation(universal_body)),[0,1,0])
    universal={'kind':KIND,'name':'3D universal joint','parameters':{'gravity':vec(0,0,0)},'simulation':{'duration':.5,'step':.001},'bodies':[universal_body],
               'joints':[{'id':'hooke','type':'universal','a':'ground','b':'yoke','anchorA':vec(.4,.1,-.3),'anchorB':vec(0,0,0),'axisA':vec(0,0,1),'axisB':dict(zip(('x','y','z'),world_y_local))}]}
    axle=body('axle',1.,.5,.25)
    axle['velocity'].update(wy=2/math.sqrt(5),wz=1/math.sqrt(5))
    loop={'kind':KIND,'name':'3D closed-loop axle','parameters':{'gravity':vec(0,0,0)},'simulation':{'duration':.5,'step':.002},'bodies':[body('arm',.5,0,0),axle],
          'joints':[{'id':'base','type':'revolute','a':'ground','b':'arm','anchorA':vec(0,0,0),'anchorB':vec(-.5,0,0),'axisA':vec(0,1,0),'axisB':vec(0,1,0)},
                    {'id':'coupler','type':'spherical','a':'arm','b':'axle','anchorA':vec(.5,0,0),'anchorB':vec(0,-.5,-.25)},
                    {'id':'end','type':'spherical','a':'ground','b':'axle','anchorA':vec(1,1,.5),'anchorB':vec(0,.5,.25)}]}
    full_inertia=copy.deepcopy(sphere);full_inertia['name']='3D full-inertia pendulum';full_inertia['bodies'][0]['inertia']['xy']=.02
    contact_ball=body('ball',0,0,.3);contact_ball['inertia']={'xx':.004,'yy':.004,'zz':.004}
    drop={'kind':KIND,'name':'3D sphere-plane contact','parameters':{'gravity':vec(0,0,-9.81)},'simulation':{'duration':.5,'step':.001},'bodies':[contact_ball],
          'joints':[{'id':'guide','type':'prismatic','a':'ground','b':'ball','anchorA':vec(0,0,0),'anchorB':vec(0,0,0),'axisA':vec(0,0,1)}],
          'contacts':[{'id':'floor','body':'ball','center':vec(0,0,0),'radius':.1,'planePoint':vec(0,0,0),'planeNormal':vec(0,0,1),'stiffness':1000.}]}
    free_body=body('payload',0,0,1);free_body['inertia']={'xx':.1,'yy':.12,'zz':.15,'xy':.01,'xz':.005,'yz':-.008};free_body['velocity'].update(vx=.2,vy=-.1,wx=.8,wy=.5,wz=1.1)
    free={'kind':KIND,'name':'3D free-falling body','parameters':{'gravity':vec(0,0,-9.81)},'simulation':{'duration':.5,'step':.001},'bodies':[free_body],'joints':[]}
    return [{'id':'spatial-spherical','title':sphere['name'],'description':'A rigid body on a 3D spherical joint under gravity.','model':sphere},
            {'id':'spatial-revolute','title':hinge['name'],'description':'A rigid body on a spatial revolute axis under gravity.','model':hinge},
            {'id':'spatial-prismatic','title':slider['name'],'description':'A rigid body slides along an oblique guide under gravity.','model':slider},
            {'id':'spatial-cylindrical','title':cylinder['name'],'description':'A rigid body slides and rotates independently along an oblique guide.','model':cylinder},
            {'id':'spatial-universal','title':universal['name'],'description':'A rigid body rotates about two perpendicular universal-joint axes.','model':universal},
            {'id':'spatial-spring','title':sprung['name'],'description':'An oblique slider oscillates on a 3D spring and damper.','model':sprung},
            {'id':'spatial-closed-loop','title':loop['name'],'description':'Two rigid bodies form a closed loop; the oblique axle spins between spherical joints.','model':loop},
            {'id':'spatial-full-inertia','title':full_inertia['name'],'description':'A spherical pendulum with a non-diagonal body-frame inertia tensor.','model':full_inertia},
            {'id':'spatial-sphere-contact','title':drop['name'],'description':'A guided sphere rebounds from a fixed plane with frictionless elastic contact.','model':drop},
            {'id':'spatial-free','title':free['name'],'description':'A free rigid body translates under gravity and rotates without joint constraints.','model':free}]


EXAMPLES=examples()
