"""Real native beam3 static and first-mode checks against independent beam theory."""
import copy,hashlib,json,math,uuid
from pathlib import Path
import flexible_link as fl
import solver


def run(model):
    check=fl.validate(model)
    if not check['valid']:return {'ok':False,'error':check['issues']},None
    directory=solver.RUNS/uuid.uuid4().hex;directory.mkdir(parents=True)
    text=fl.deck(model);(directory/'model.mbd').write_text(text,encoding='utf-8');(directory/'project.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    outcome=solver.execute(solver.command(solver.configuration(),['-f','model.mbd','-o','result'],directory,bounded=True),directory)
    if outcome.get('exitCode')!=0:return {'ok':False,'error':outcome,'log':(directory/'solver.log').read_text(errors='replace')[-5000:],'runId':directory.name},directory
    try:
        samples=fl.parse_output(directory,model);fl.write_csv(directory/'results.csv',samples)
        return {'ok':True,'samples':samples,'metrics':fl.metrics(model,samples),'runId':directory.name},directory
    except (ValueError,OSError) as exc:return {'ok':False,'error':str(exc),'log':(directory/'solver.log').read_text(errors='replace')[-3000:],'runId':directory.name},directory


def frequency(samples):
    """Interpolate upward velocity zero-crossings after the smooth load ramp; no solver beam matrices."""
    peaks=[]
    for a,b in zip(samples,samples[1:]):
        if a['time']>.3 and a['tipVelocity']<0<=b['tipVelocity']:
            peaks.append(a['time']+(b['time']-a['time'])*-a['tipVelocity']/(b['tipVelocity']-a['tipVelocity']))
    if len(peaks)<3:raise ValueError('Too few native oscillation peaks to determine first-mode frequency.')
    return (len(peaks)-1)/(peaks[-1]-peaks[0])


def main():
    cases=[];mesh_static=[];mesh_frequency=[];refinements=[]
    for nodes in (3,5,9):
        for damping in (.02,0.):
            model=copy.deepcopy(fl.DEFAULT);model['parameters'].update(nodes=nodes,dampingTime=damping);model['simulation']['step']=.0005
            result,directory=run(model);case={'name':f'{nodes} nodes damping {damping:g}','ok':result['ok'],'runId':result.get('runId')};cases.append(case)
            if not result['ok']:case.update(error=result.get('error'),log=result.get('log'));continue
            ref=fl.references(model);samples=result['samples'];case.update(staticReference=ref['staticDeflection'],finalDeflection=samples[-1]['tipDeflection'],maxTipDeflection=result['metrics']['maxTipDeflection'])
            if damping:
                case.update(relativeStaticError=abs(samples[-1]['tipDeflection']/ref['staticDeflection']-1),rootForce=samples[-1]['rootForce'],rootMoment=samples[-1]['rootMoment'])
                L=model['parameters']['length'];EI=model['parameters']['bendingStiffness'];GA=model['parameters']['shearStiffness'];F=model['parameters']['tipLoad']
                case['maxStaticShapeError']=max(abs(node['z']-F*((i*L/(nodes-1))**2*(3*L-i*L/(nodes-1))/(6*EI)+(i*L/(nodes-1))/GA)) for i,node in enumerate(samples[-1]['nodes']))
                case['ok']=case['relativeStaticError']<.001 and case['maxStaticShapeError']<3e-6 and abs(abs(case['rootForce'])-1)<1e-5 and abs(abs(case['rootMoment'])-.5)<.002
                mesh_static.append(case['finalDeflection'])
            else:
                measured=frequency(samples);case.update(frequencyHz=measured,frequencyReferenceHz=ref['eulerBernoulliFrequencyHz'],relativeFrequencyError=abs(measured/ref['eulerBernoulliFrequencyHz']-1));case['ok']=case['relativeFrequencyError']<.01;mesh_frequency.append(measured)
    for step in (.001,.0005,.00025):
        model=copy.deepcopy(fl.DEFAULT);model['parameters']['nodes']=9;model['simulation'].update(duration=.6,step=step)
        result,directory=run(model);case={'name':f'time refinement {step:g}','ok':result['ok'],'runId':result.get('runId'),'step':step};cases.append(case)
        if not result['ok']:case.update(error=result.get('error'),log=result.get('log'));continue
        refinements.append({round(sample['time']/.00025):sample for sample in result['samples'] if sample['time']<=.6+1e-10});case['maxTipDeflection']=result['metrics']['maxTipDeflection']
    convergence={}
    if len(refinements)==3:
        errors=[]
        for a,b in zip(refinements,refinements[1:]):errors.append(max(abs(sample['tipDeflection']-b[tick]['tipDeflection']) for tick,sample in a.items()))
        convergence.update(timeDeflectionDifferences=errors,timeRefinementRatio=errors[0]/errors[1])
        cases.append({'name':'time refinement improves native deflection','ok':errors[1]<errors[0]/2 and errors[1]<1e-6})
    if len(mesh_static)==len(mesh_frequency)==3:
        static=[abs(a-b) for a,b in zip(mesh_static,mesh_static[1:])];freq=[abs(a-b) for a,b in zip(mesh_frequency,mesh_frequency[1:])]
        convergence.update(meshStaticDifferences=static,meshFrequencyDifferences=freq)
        cases.append({'name':'mesh refinement improves static shape and frequency','ok':static[1]<static[0]/2 and freq[1]<freq[0]/2})
    model=copy.deepcopy(fl.DEFAULT);model['parameters'].update(length=.7,linearDensity=2.,bendingStiffness=12.,rotaryInertia=5e-5,tipLoad=.75,dampingTime=.03,rampTime=.15,nodes=9);model['simulation'].update(duration=3.5,step=.001)
    result,directory=run(model);case={'name':'changed length/mass/stiffness and upward load','ok':result['ok'],'runId':result.get('runId')};cases.append(case)
    if not result['ok']:case.update(error=result.get('error'),log=result.get('log'))
    else:
        final=result['samples'][-1];ref=fl.references(model);case.update(staticReference=ref['staticDeflection'],finalDeflection=final['tipDeflection'],relativeStaticError=abs(final['tipDeflection']/ref['staticDeflection']-1),rootForce=final['rootForce'],rootMoment=final['rootMoment'])
        case['ok']=case['relativeStaticError']<.001 and abs(case['rootForce']-.75)<1e-5 and abs(case['rootMoment']+.525)<.002
    for case in cases:
        if not case.get('runId'):continue
        directory=solver.RUNS/case['runId'];case.update(modelSha256=hashlib.sha256((directory/'project.json').read_bytes()).hexdigest(),deckSha256=hashlib.sha256((directory/'model.mbd').read_bytes()).hexdigest())
    executable=Path(solver.configuration()['executable'])
    report={'ok':all(c['ok'] for c in cases),'scope':'Native flexible-node cantilever. Illustrative independent section properties, no hardware calibration. Static small-deflection Timoshenko and approximate Euler-Bernoulli first-frequency references; finite mesh/lumped inertia and numerical damping are explicit.','solverSha256':hashlib.sha256(executable.read_bytes()).hexdigest() if executable.is_file() else None,'verifierSha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),'generatorSha256':hashlib.sha256(Path(fl.__file__).read_text(encoding='utf-8').encode()).hexdigest(),'convergence':convergence,'cases':cases}
    (Path(__file__).resolve().parents[1]/'examples/flexible-link-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2));return report


if __name__=='__main__':raise SystemExit(0 if main()['ok'] else 1)
