"""Bounded clamped, uniform, flexible robot link using native MBDyn beam3 elements."""
import csv,math

KIND='flexible-link'
RANGES={KIND:{'length':(.05,10.),'linearDensity':(.001,10000.),'axialStiffness':(1.,1e10),'shearStiffness':(1.,1e10),'bendingStiffness':(.001,1e8),'torsionalStiffness':(.001,1e8),'rotaryInertia':(1e-10,100.),'dampingTime':(0.,1.),'tipLoad':(-1e6,1e6),'rampTime':(.001,10.),'nodes':(3,9)}}
DEFAULT={'kind':KIND,'name':'Flexible robot link','parameters':{'length':.5,'linearDensity':1.,'axialStiffness':2e5,'shearStiffness':5e4,'bendingStiffness':5.,'torsionalStiffness':5.,'rotaryInertia':2.5e-5,'dampingTime':.02,'tipLoad':-1.,'rampTime':.1,'nodes':5},'simulation':{'duration':2.,'step':.001}}
EXAMPLES=[{'id':KIND,'title':DEFAULT['name'],'description':'A clamped flexible robot link bends and vibrates under a smoothly applied tip force. Native three-node beam elements and moving solver nodes.','model':DEFAULT}]
FIELDS=('x','y','z','rx','ry','rz','vx','vy','vz','wx','wy','wz')
SCALARS={'tipDeflection':'tipDeflection_m','tipVelocity':'tipVelocity_m_s','tipSlope':'tipSlope_rad','appliedForce':'appliedForce_N','rootForce':'rootForce_N','rootMoment':'rootMoment_Nm'}


def references(model):
    p=model['parameters'];L=p['length'];EI=p['bendingStiffness'];mu=p['linearDensity']
    omega=1.875104068711961**2*math.sqrt(EI/mu/L**4)
    return {'staticDeflection':p['tipLoad']*(L**3/(3*EI)+L/p['shearStiffness']),'eulerBernoulliFrequencyHz':omega/(2*math.pi),'estimatedDampingRatio':p['dampingTime']*omega/2,'totalMass':mu*L}


def validate(model):
    issues=[];summary={}
    def issue(path,message,level='error'):issues.append({'level':level,'field':path,'message':message})
    if not isinstance(model,dict):return {'valid':False,'issues':[{'level':'error','field':'model','message':'Supply a model object.'}],'summary':summary}
    for key in model.keys()-{'kind','name','parameters','simulation'}:issue(key,'Unsupported flexible-link field.')
    if model.get('kind')!=KIND:issue('kind','Choose flexible-link.')
    name=model.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>120 or any(ord(c)<32 for c in name):issue('name','Use 1–120 printable characters.')
    for group,bounds in [('parameters',RANGES[KIND]),('simulation',{'duration':(.01,30.),'step':(.0001,.02)})]:
        values=model.get(group)
        if not isinstance(values,dict):issue(group,'Supply an object.');continue
        for key in values.keys()-bounds.keys():issue(f'{group}.{key}','Unsupported field.')
        for key,(low,high) in bounds.items():
            value=values.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:issue(f'{group}.{key}',f'Use a finite number from {low:g} to {high:g}.')
    if issues:return {'valid':False,'issues':issues,'summary':summary}
    p,s=model['parameters'],model['simulation'];nodes=p['nodes']
    if nodes not in (3,5,9):issue('parameters.nodes','Use 3, 5 or 9 structural nodes (one, two or four beam3 elements).')
    steps=math.ceil(s['duration']/s['step'])
    if steps>20000 or (steps+2)*nodes>160000:issue('simulation.step','Limit a run to 20,000 steps and 160,000 node-steps.')
    if (steps+2)*nodes*len(SCALARS)>1600000:issue('simulation.step','Limit repeated scalar CSV output to 1,600,000 values.')
    ref=references(model);omega=2*math.pi*ref['eulerBernoulliFrequencyHz']
    if 2*abs(ref['staticDeflection'])>.1*p['length']:issue('parameters.tipLoad','Limit twice the static tip deflection to 10% of link length; reduce the load or increase section stiffness.')
    if math.sqrt(p['rotaryInertia']/p['linearDensity'])>.1*p['length']:issue('parameters.rotaryInertia','The radius of gyration must be at most 10% of link length for this slender-link template.')
    if p['rampTime']<20*s['step']:issue('parameters.rampTime','Apply the load over at least 20 integration steps.')
    if p['rampTime']>=s['duration']:issue('simulation.duration','Run beyond the end of the load ramp.')
    if s['step']*omega>.1:issue('simulation.step',f'Resolve the first bending mode with a step no larger than {.1/omega:.6g} s; also compare mesh and timestep refinements.')
    if s['duration']<p['rampTime']+2/ref['eulerBernoulliFrequencyHz']:issue('simulation.duration','Extend the run to observe at least two first-mode periods after the load ramp.','warning')
    if p['bendingStiffness']/(p['shearStiffness']*p['length']**2)>.001:issue('parameters.shearStiffness','Shear flexibility may shift the frequency from the Euler–Bernoulli reference.','warning')
    summary.update(degreesOfFreedom=6*(nodes-1),structuralNodes=nodes,beams=(nodes-1)//2,nodeLabels={f'flex{i}':f'Node {i}'+(' · clamped' if i==1 else ' · tip' if i==nodes else '') for i in range(1,int(nodes)+1)},**ref)
    return {'valid':not any(i['level']=='error' for i in issues),'issues':issues,'summary':summary}


def nodal_weights(model):
    p=model['parameters'];count=int(p['nodes']);element_length=2*p['length']/(count-1);weights=[0.]*count
    for start in range(0,count-2,2):
        for index,multiplier in enumerate((1,4,1)):weights[start+index]+=element_length*multiplier/6
    return weights


def load(model,time):
    p=model['parameters'];return p['tipLoad']*(.5*(1-math.cos(math.pi*max(0.,time)/p['rampTime'])) if time<p['rampTime'] else 1.)


def deck(model):
    check=validate(model)
    if not check['valid']:raise ValueError('Flexible link validation failed: '+'; '.join(i['field']+': '+i['message'] for i in check['issues'] if i['level']=='error'))
    p,s=model['parameters'],model['simulation'];N=int(p['nodes']);E=(N-1)//2;f=lambda x:format(float(x),'.15g')
    text=f'''# Native MBDyn beam3 uniform flexible link; illustrative SI section inputs.
begin: data;
 problem: initial value;
end: data;
begin: initial value;
 initial time: 0;
 final time: {f(s['duration'])};
 time step: {f(s['step'])};
 method: ms, 0.6;
 max iterations: 50;
 tolerance: 1.e-8;
 derivatives tolerance: 1.e-8;
 derivatives max iterations: 100;
 derivatives coefficient: 1.e-3, auto;
end: initial value;
begin: control data;
 structural nodes: {N};
 rigid bodies: {N};
 joints: 1;
 beams: {E};
 forces: 1;
 output precision: 12;
end: control data;
begin: nodes;
'''
    for i in range(N):text+=f' structural: {i+1}, dynamic, {f(i*p["length"]/(N-1))},0,0, eye, null, null;\n'
    text+='end: nodes;\nbegin: elements;\n'
    for i,w in enumerate(nodal_weights(model),1):
        J=p['rotaryInertia']*w
        text+=f' body: {i}, {i}, {f(p["linearDensity"]*w)}, null, diag, {f(2*J)},{f(J)},{f(J)};\n'
    text+=' joint: 1, clamp, 1, node, node;\n'
    stiffness=','.join(f(p[k]) for k in ('axialStiffness','shearStiffness','shearStiffness','torsionalStiffness','bendingStiffness','bendingStiffness'))
    law=f'linear viscoelastic generic, diag, {stiffness}, proportional, {f(p["dampingTime"])}' if p['dampingTime'] else f'linear elastic generic, diag, {stiffness}'
    for element,start in enumerate(range(1,N-1,2),1):text+=f' beam3: {element}, {start}, reference, node, null, {start+1}, reference, node, null, {start+2}, reference, node, null, eye, {law}, same, same;\n'
    text+=f' force: 1, absolute, {N}, position, reference, node, null, 0,0,1, cosine, 0, {f(math.pi/p["rampTime"])}, {f(p["tipLoad"]/2)}, half, 0;\nend: elements;\n'
    return text


def parse_output(directory,model):
    from source_catalog import parse_output as parse_native
    N=int(model['parameters']['nodes']);samples=parse_native(directory,{'simulation':model['simulation'],'nodes':[{'id':i} for i in range(1,N+1)]})
    if abs(samples[0]['time'])>1e-10:raise ValueError('Flexible link output must start at time zero.')
    if len(samples)*N>160000 or len(samples)*N*len(SCALARS)>1600000:raise ValueError('Actual flexible link output exceeds its node-step/CSV budget.')
    if 'MBDyn terminated normally' not in (directory/'solver.log').read_text(errors='replace'):raise ValueError('Incomplete native beam run; no completed flexible result was generated.')
    elements=(N-1)//2;connectivity={}
    with (directory/'result.log').open() as stream:
        for line in stream:
            fields=line.split()
            if fields[:1]!=['beam3:']:continue
            if len(fields)!=14:raise ValueError('Unexpected native beam3 metadata.')
            try:label=int(fields[1]);nodes=[int(fields[i]) for i in (2,6,10)];offsets=[float(fields[i]) for i in (3,4,5,7,8,9,11,12,13)]
            except ValueError as exc:raise ValueError('Invalid native beam3 metadata.') from exc
            if label in connectivity or any(value!=0 for value in offsets):raise ValueError('Duplicate or offset native beam3 metadata.')
            connectivity[label]=nodes
    if connectivity!={i+1:[2*i+1,2*i+2,2*i+3] for i in range(elements)}:raise ValueError('Native beam3 connectivity does not match the requested flexible mesh.')
    if (directory/'result.act').stat().st_size>64*1024*1024:raise ValueError('Native beam output exceeds its parsing limit.')
    count=0
    with (directory/'result.act').open() as stream:
        for line in stream:
            fields=line.split()
            if not fields:continue
            if len(fields)!=13 or fields[0]!=str(count%elements+1):raise ValueError('Incomplete or reordered native beam force record.')
            try:values=[float(v) for v in fields[1:]]
            except ValueError as exc:raise ValueError('Invalid native beam force record.') from exc
            if not all(math.isfinite(v) for v in values):raise ValueError('Non-finite native beam force record.')
            count+=1
    if count!=len(samples)*elements:raise ValueError('Native beam force frames do not match structural-node frames.')
    if (directory/'result.jnt').stat().st_size>64*1024*1024:raise ValueError('Native beam clamp output exceeds its parsing limit.')
    with (directory/'result.jnt').open() as stream:reactions=[line.split() for line in stream if line.strip()]
    if len(reactions)!=len(samples):raise ValueError('Incomplete native beam clamp reaction frames.')
    for sample,fields in zip(samples,reactions):
        if len(fields)!=13 or fields[0]!='1':raise ValueError('Unexpected native beam clamp output record.')
        try:values=[float(v) for v in fields[1:]]
        except ValueError as exc:raise ValueError('Invalid native clamp reaction.') from exc
        if not all(math.isfinite(v) for v in values):raise ValueError('Non-finite native clamp reaction.')
        for i,node in enumerate(sample['nodes'],1):node.update(id=f'flex{i}',label=f'Node {i}')
        tip=sample['nodes'][-1];root=sample['nodes'][0]
        if max(abs(root[k]) for k in FIELDS)>1e-7:raise ValueError('Clamped flexible-link root moved beyond tolerance.')
        if max(abs(n['z']) for n in sample['nodes'])>.15*model['parameters']['length']:raise ValueError('Flexible link exceeded its supported small-deflection range.')
        sample.update(tipDeflection=tip['z'],tipVelocity=tip['vz'],tipSlope=math.radians(tip['ry']),appliedForce=load(model,sample['time']),rootForce=values[8],rootMoment=values[10],value=tip['z'],x=tip['x'],y=tip['y'],z=tip['z'],angle=tip['ry'],velocity=tip['vz'])
    return samples


def write_csv(path,samples):
    fields=['time','id','label',*FIELDS,*SCALARS.values()]
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for sample in samples:
            for node in sample['nodes']:writer.writerow({'time':sample['time'],**{k:node[k] for k in ('id','label',*FIELDS)},**{column:sample[key] for key,column in SCALARS.items()}})


def metrics(model,samples):
    return {'duration':samples[-1]['time'],'sampleCount':len(samples),'nodeCount':int(model['parameters']['nodes']),'beamCount':(int(model['parameters']['nodes'])-1)//2,'maxTipDeflection':max(abs(s['tipDeflection']) for s in samples),'finalTipDeflection':samples[-1]['tipDeflection'],'maxRootMoment':max(abs(s['rootMoment']) for s in samples),**references(model),'validationScope':'Uniform clamped beam3 robot link, lumped nodal mass/rotary inertia, equal principal section properties, global-Z ramped tip force. Native flexible nodes; no general FE importer, joint coupling, stress/fatigue or hardware qualification.'}
