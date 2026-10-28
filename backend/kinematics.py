"""Independent spatial position and velocity solvers with explicit variables."""
import copy
import math
import time

import spatial_assembly as spatial

COMPONENTS = ('x', 'y', 'z', 'rx', 'ry', 'rz')
VELOCITY_COMPONENTS = ('vx', 'vy', 'vz', 'wx', 'wy', 'wz')
MAX_ITERATIONS = 60
MAX_SECONDS = 8.0
TOLERANCE = 1e-7


class KinematicsError(ValueError):
    """Invalid input to the independent kinematic position solver."""


def _dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def _rotation_vector(matrix):
    """SO(3) logarithm, including the 180-degree branch."""
    cosine = max(-1., min(1., (sum(matrix[i][i] for i in range(3))-1)/2))
    skew = [(matrix[2][1]-matrix[1][2])/2, (matrix[0][2]-matrix[2][0])/2, (matrix[1][0]-matrix[0][1])/2]
    sine = spatial.norm(skew)
    angle = math.atan2(sine, cosine)
    if sine > 1e-8:
        return [angle*x/sine for x in skew]
    if cosine > 0:
        return skew
    # At pi the skew part vanishes. Recover an axis from R+I, not a false zero.
    index = max(range(3), key=lambda i: matrix[i][i])
    axis = [0., 0., 0.]
    axis[index] = math.sqrt(max(0., (matrix[index][index]+1)/2))
    if axis[index] < 1e-10:
        raise KinematicsError('A rotation near 180 degrees is numerically singular; change the initial guess.')
    for i in range(3):
        if i != index:
            axis[i] = (matrix[i][index]+matrix[index][i])/(4*axis[index])
    length = spatial.norm(axis)
    return [math.pi*x/length for x in axis]


def _allowed_initial_issue(issue):
    message = issue.get('message', '')
    return message.startswith(('Initial anchor positions differ by ', 'Initial anchor velocities differ by ',
        'Joint frame directions differ by ', 'Universal axes must be perpendicular;',
        'Joint-constrained angular velocities differ by ', 'Joint axes must point in the same direction.',
        'Spring endpoints must initially be at least ', 'Prescribed cosine motion starts at zero relative axial speed;'))


def _coordinate(entry, names, path, initial=False, components=COMPONENTS):
    if not isinstance(entry, dict):
        raise KinematicsError(f'{path} must be an object.')
    allowed = {'body', 'component', 'initial'} if initial else {'body', 'component', 'value'}
    required = {'body', 'component'} if initial else allowed
    if set(entry)-allowed or not required <= set(entry):
        raise KinematicsError(f'{path} has unsupported or missing fields.')
    body, component = entry['body'], entry['component']
    if not isinstance(body, str) or body not in names or component not in components:
        raise KinematicsError(f'{path} must name an existing body and one of {", ".join(components)}.')
    key = 'initial' if initial else 'value'
    if key in entry:
        value = entry[key]
        limit = 360 if component.startswith('r') else 1000
        if type(value) not in (int, float) or abs(value)>limit or not math.isfinite(value):
            raise KinematicsError(f'{path}.{key} must be finite and within ±{limit}.')
    return body, component


def _input(request):
    if not isinstance(request, dict) or set(request) != {'model', 'variables', 'targets'}:
        raise KinematicsError('Supply exactly model, variables and targets.')
    model=request['model']
    if not isinstance(model, dict) or model.get('kind') != 'spatial-assembly':
        raise KinematicsError('Kinematics requires a spatial assembly.')
    validation=spatial.validate(model)
    issues=[item for item in validation['issues'] if item.get('level') == 'error' and not _allowed_initial_issue(item)]
    if issues:
        raise KinematicsError('Correct the model structure first: '+'; '.join(f"{item['field']}: {item['message']}" for item in issues[:8]))
    names={item['id'] for item in model['bodies']}
    variables, targets=request['variables'],request['targets']
    if not isinstance(variables, list) or not 1<=len(variables)<=96:
        raise KinematicsError('Choose between 1 and 96 unknown body coordinates.')
    if not isinstance(targets, list) or len(targets)>96:
        raise KinematicsError('Supply at most 96 target coordinates.')
    pairs=[_coordinate(item,names,f'variables.{i}',True) for i,item in enumerate(variables)]
    if len(set(pairs)) != len(pairs):
        raise KinematicsError('Each unknown body coordinate must be selected only once.')
    target_pairs=[_coordinate(item,names,f'targets.{i}') for i,item in enumerate(targets)]
    if len(set(target_pairs)) != len(target_pairs):
        raise KinematicsError('Each target body coordinate must be selected only once.')
    return copy.deepcopy(model), pairs, targets


def _constraints(model, references, targets):
    bodies={body['id']:body for body in model['bodies']}
    values=[]
    for joint in model['joints']:
        a,b=bodies.get(joint['a']),bodies[joint['b']]
        ra,rb=spatial.body_rotation(a),spatial.body_rotation(b)
        delta=spatial.sub(spatial.anchor(b,joint['anchorB']),spatial.anchor(a,joint['anchorA']))
        kind=joint['type']
        if kind in ('prismatic','cylindrical'):
            axis=spatial.mul(ra,spatial.xyz(joint['axisA']))
            first,second,_=spatial.basis(axis)
            values.extend((_dot(delta,first),_dot(delta,second)))
        else:
            values.extend(delta)
        if kind in ('revolute','cylindrical'):
            axis_a=spatial.mul(ra,spatial.xyz(joint['axisA']));axis_b=spatial.mul(rb,spatial.xyz(joint['axisB']))
            first,second,_=spatial.basis(axis_a)
            values.extend((_dot(axis_b,first),_dot(axis_b,second),max(0.,-_dot(axis_a,axis_b))))
        elif kind=='universal':
            values.append(_dot(spatial.mul(ra,spatial.xyz(joint['axisA'])),spatial.mul(rb,spatial.xyz(joint['axisB']))))
        elif kind in ('weld','prismatic'):
            relative=spatial.matmul(spatial.transpose(ra),rb)
            reference=references[joint['id']] if kind=='prismatic' else [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
            values.extend(_rotation_vector(spatial.matmul(spatial.transpose(reference),relative)))
    for target in targets:
        current=bodies[target['body']]['pose'][target['component']]
        difference=current-target['value']
        values.append(math.radians(difference) if target['component'].startswith('r') else difference)
    return values


def _linear_solve(matrix, rhs):
    """Partial-pivot Gaussian elimination for a damped positive system."""
    a=[list(row)+[value] for row,value in zip(matrix,rhs)];n=len(rhs)
    for col in range(n):
        pivot=max(range(col,n),key=lambda row:abs(a[row][col]))
        if abs(a[pivot][col])<1e-20:raise KinematicsError('The linearized constraint system is singular.')
        a[col],a[pivot]=a[pivot],a[col];d=a[col][col]
        for row in range(col+1,n):
            scale=a[row][col]/d
            if scale:
                for k in range(col,n+1):a[row][k]-=scale*a[col][k]
    x=[0.]*n
    for i in range(n-1,-1,-1):x[i]=(a[i][n]-sum(a[i][j]*x[j] for j in range(i+1,n)))/a[i][i]
    return x


def _rank(jacobian):
    """Rank of selected-coordinate Jacobian; tolerance is relative to largest entry."""
    if not jacobian:return 0
    a=[row[:] for row in jacobian];m=len(a);n=len(a[0]);scale=max((abs(v) for row in a for v in row),default=0.)
    if not scale:return 0
    rank=0
    for col in range(n):
        pivot=max(range(rank,m),key=lambda row:abs(a[row][col]),default=rank)
        if rank>=m or abs(a[pivot][col])<=max(1e-10,scale*1e-7):continue
        a[rank],a[pivot]=a[pivot],a[rank];d=a[rank][col]
        for row in range(rank+1,m):
            q=a[row][col]/d
            for k in range(col+1,n):a[row][k]-=q*a[rank][k]
        rank+=1
    return rank


def solve(request):
    """Solve positions only; return a candidate without changing the supplied model."""
    if isinstance(request, dict) and request.get('mode') == 'velocity':
        return _solve_velocity(request)
    model,pairs,targets=_input(request)
    bodies={body['id']:body for body in model['bodies']}
    references={j['id']:spatial.matmul(spatial.transpose(spatial.body_rotation(bodies.get(j['a']))),spatial.body_rotation(bodies[j['b']])) for j in model['joints'] if j['type']=='prismatic'}
    values=[]
    for entry,(body,key) in zip(request['variables'],pairs):
        value=entry.get('initial',bodies[body]['pose'][key])
        values.append(math.radians(value) if key.startswith('r') else value)
    def update(vector):
        for (body,key),value in zip(pairs,vector):bodies[body]['pose'][key]=math.degrees(value) if key.startswith('r') else value
    def residual(vector):
        update(vector);result=_constraints(model,references,targets)
        if not all(math.isfinite(value) for value in result):raise KinematicsError('Constraint evaluation returned non-finite values.')
        return result
    def jacobian(vector,base):
        rows=[[0.]*len(vector) for _ in base]
        for i,value in enumerate(vector):
            if time.monotonic()-start > MAX_SECONDS: raise TimeoutError('Kinematic calculation deadline reached.')
            step=1e-6*max(1.,abs(value));positive=vector[:];negative=vector[:]
            positive[i]+=step;negative[i]-=step
            upper=residual(positive);lower=residual(negative)
            for r in range(len(base)):rows[r][i]=(upper[r]-lower[r])/(2*step)
        update(vector)
        return rows
    start=time.monotonic();iterations=0;damping=1e-4;reason='iteration_limit';r=residual(values)
    deadline_reached=False
    for iterations in range(MAX_ITERATIONS):
        if time.monotonic()-start>MAX_SECONDS:reason='time_limit';break
        try: j=jacobian(values,r)
        except TimeoutError: reason='time_limit';deadline_reached=True;break
        if max(map(abs,r),default=0.)<=TOLERANCE:reason='converged';break
        n=len(values);normal=[[sum(row[i]*row[k] for row in j)+(damping if i==k else 0.) for k in range(n)] for i in range(n)]
        gradient=[-sum(row[i]*value for row,value in zip(j,r)) for i in range(n)]
        step=_linear_solve(normal,gradient)
        trial=[x+dx for x,dx in zip(values,step)]
        if any(abs(value)>(2*math.pi if key.startswith('r') else 1000) for (_,key),value in zip(pairs,trial)):
            damping=min(damping*10,1e12);continue
        next_r=residual(trial)
        if sum(v*v for v in next_r)<sum(v*v for v in r):values,r=trial,next_r;damping=max(damping/3,1e-12)
        else:update(values);damping=min(damping*10,1e12)
    update(values);r=residual(values);rank=None
    if not deadline_reached and reason!='time_limit':
        try: rank=_rank(jacobian(values,r))
        except TimeoutError: reason='time_limit'
    max_residual=max(map(abs,r),default=0.)
    if reason!='time_limit' and max_residual<=TOLERANCE:reason='converged'
    if reason=='converged' and rank<len(values):reason='underdetermined'
    ok=reason=='converged'
    messages={'converged':'A position solution was found for the selected unknowns.',
      'underdetermined':'Selected unknowns are not uniquely constrained. Add targets or fix coordinates, and avoid singular configurations.',
      'time_limit':'The kinematic calculation reached its time limit. Reduce unknowns or improve the initial guess.',
      'iteration_limit':'The constraints did not converge. Check targets and joint geometry, or try another initial guess.'}
    result={'ok':ok,'source':'Independent kinematic position solve','reason':reason,'message':messages[reason],
      'iterations':iterations+1,'maxResidual':max_residual,'tolerance':TOLERANCE,'unknownCount':len(values),'jacobianRank':rank,
      'limitations':['Position constraints only; no MBDyn dynamics, contact, reactions or automatic branch discovery.',
        'Unselected body coordinates and all velocities remain fixed; a solved pose may require velocity repair before simulation.',
        'Rotations use Euler123 degrees. At Euler singularities or mechanism toggles, the selected coordinates may be singular.']}
    if ok:
        result['model']=model;result['dynamicsValidation']=spatial.validate(model)
    return result


def _velocity_constraints(model, targets):
    """Linear joint-velocity constraints expressed in world coordinates."""
    bodies={body['id']:body for body in model['bodies']}
    values=[]
    for joint in model['joints']:
        a,b=bodies.get(joint['a']),bodies[joint['b']]
        ra,rb=spatial.body_rotation(a),spatial.body_rotation(b)
        wa,wb=spatial.angular(a),spatial.angular(b)
        relative_angular=spatial.sub(wb,wa)
        relative_velocity=spatial.sub(spatial.anchor_velocity(b,joint['anchorB']),spatial.anchor_velocity(a,joint['anchorA']))
        kind=joint['type']
        if kind in ('prismatic','cylindrical'):
            delta=spatial.sub(spatial.anchor(b,joint['anchorB']),spatial.anchor(a,joint['anchorA']))
            relative_velocity=spatial.sub(relative_velocity,spatial.cross(wa,delta))
            axis=spatial.mul(ra,spatial.xyz(joint['axisA']))
            first,second,_=spatial.basis(axis)
            values.extend((_dot(relative_velocity,first),_dot(relative_velocity,second)))
            if joint.get('motion'):values.append(_dot(relative_velocity,axis))
        else:
            values.extend(relative_velocity)
        if kind in ('revolute','cylindrical'):
            axis=spatial.mul(ra,spatial.xyz(joint['axisA']))
            first,second,_=spatial.basis(axis)
            values.extend((_dot(relative_angular,first),_dot(relative_angular,second)))
        elif kind=='universal':
            ua=spatial.mul(ra,spatial.xyz(joint['axisA']));ub=spatial.mul(rb,spatial.xyz(joint['axisB']))
            values.append(_dot(relative_angular,spatial.cross(ua,ub)))
        elif kind in ('weld','prismatic'):
            values.extend(relative_angular)
    for target in targets:
        values.append(bodies[target['body']]['velocity'][target['component']]-target['value'])
    return values


def _solve_velocity(request):
    if set(request) != {'mode','model','variables','targets'}:
        raise KinematicsError('Supply exactly mode, model, variables and targets for the velocity solve.')
    model=request['model']
    if not isinstance(model,dict) or model.get('kind')!='spatial-assembly':
        raise KinematicsError('Kinematics requires a spatial assembly.')
    validation=spatial.validate(model)
    def allowed_velocity_issue(issue):
        message=issue.get('message','')
        return message.startswith(('Initial anchor velocities differ by ', 'Joint-constrained angular velocities differ by ', 'Prescribed cosine motion starts at zero relative axial speed;')) or (issue.get('field')=='simulation.step' and message=='Resolve initial rotation with at most 0.1 rad per step.')
    issues=[item for item in validation['issues'] if item.get('level')=='error' and not allowed_velocity_issue(item)]
    if issues:
        raise KinematicsError('Correct the model and its position constraints first: '+'; '.join(f"{item['field']}: {item['message']}" for item in issues[:8]))
    variables,targets=request['variables'],request['targets']
    if not isinstance(variables,list) or not 1<=len(variables)<=96:
        raise KinematicsError('Choose between 1 and 96 unknown body velocity components.')
    if not isinstance(targets,list) or len(targets)>96:
        raise KinematicsError('Supply at most 96 target velocity components.')
    names={item['id'] for item in model['bodies']}
    pairs=[_coordinate(item,names,f'variables.{i}',True,VELOCITY_COMPONENTS) for i,item in enumerate(variables)]
    target_pairs=[_coordinate(item,names,f'targets.{i}',False,VELOCITY_COMPONENTS) for i,item in enumerate(targets)]
    if len(set(pairs))!=len(pairs) or len(set(target_pairs))!=len(target_pairs):
        raise KinematicsError('Each unknown or target velocity component must be selected only once.')
    model=copy.deepcopy(model);bodies={body['id']:body for body in model['bodies']}
    values=[entry.get('initial',bodies[body]['velocity'][key]) for entry,(body,key) in zip(variables,pairs)]
    def update(vector):
        for (body,key),value in zip(pairs,vector):bodies[body]['velocity'][key]=value
    def residual(vector):
        update(vector);result=_velocity_constraints(model,targets)
        if not all(math.isfinite(value) for value in result):raise KinematicsError('Velocity constraint evaluation returned non-finite values.')
        return result
    start=time.monotonic();base=residual(values);columns=[];reason='converged';rank=None
    for i in range(len(values)):
        if time.monotonic()-start>MAX_SECONDS:reason='time_limit';break
        trial=values[:];trial[i]+=1.
        shifted=residual(trial);columns.append([b-a for a,b in zip(base,shifted)])
    update(values)
    if reason!='time_limit':
        jacobian=[list(row) for row in zip(*columns)];rank=_rank(jacobian)
        if rank<len(values):reason='underdetermined'
        else:
            n=len(values);normal=[[sum(row[i]*row[k] for row in jacobian) for k in range(n)] for i in range(n)]
            gradient=[-sum(row[i]*value for row,value in zip(jacobian,base)) for i in range(n)]
            delta=_linear_solve(normal,gradient);values=[value+change for value,change in zip(values,delta)]
            if any(not math.isfinite(value) or abs(value)>1000 for value in values):reason='out_of_range'
            else:
                base=residual(values)
                if max(map(abs,base),default=0.)>TOLERANCE:reason='inconsistent'
    max_residual=max(map(abs,base),default=0.)
    messages={'converged':'A velocity solution was found for the selected unknowns.',
       'underdetermined':'Selected velocity unknowns are not uniquely constrained. Add targets or fix components.',
       'time_limit':'The velocity calculation reached its time limit. Reduce unknowns.',
       'inconsistent':'The velocity targets and joint constraints are inconsistent.',
       'out_of_range':'The required velocity exceeds the supported range.'}
    result={'ok':reason=='converged','source':'Independent kinematic velocity solve','reason':reason,'message':messages[reason],
       'iterations':1,'maxResidual':max_residual,'tolerance':TOLERANCE,'unknownCount':len(values),'jacobianRank':rank,
       'limitations':['Instantaneous velocity constraints only; no acceleration, forces, contact or dynamics.',
          'Unselected velocity components and all poses stay fixed; rank does not establish a unique global mechanism.',
          'Angular velocities are world-frame radians per second, not Euler-angle rates.']}
    if result['ok']:
        update(values);result['model']=model;result['dynamicsValidation']=spatial.validate(model)
    return result
