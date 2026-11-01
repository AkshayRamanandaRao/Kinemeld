"""Cross-platform native robotics smoke using only an extracted package's backend.

No GUI coverage is claimed. The package is read-only; all runtime data goes to --out.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def tree_digest(root):
    manifest=[];size=0
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        if not path.resolve().is_relative_to(root):raise ValueError(f'Package file resolves outside its resources: {path}')
        length=path.stat().st_size;size+=length;manifest.append((path.relative_to(root).as_posix(),length,digest(path)))
    return {'sha256':hashlib.sha256(json.dumps(manifest,separators=(',',':')).encode()).hexdigest(),'files':len(manifest),'bytes':size}


def full_csv(path,model,expected_frames):
    ids={body['id'] for body in model.get('bodies',[])} if model['kind']=='spatial-assembly' else {f'flex{i}' for i in range(1,int(model['parameters']['nodes'])+1)}
    maximum={};held={};final={};frames=rows=0;previous=None;frame_ids=set()
    with path.open(encoding='utf-8',newline='') as stream:
        reader=csv.DictReader(stream);columns=reader.fieldnames
        assert columns and len(columns)==len(set(columns)) and {'time','id','label'}<=set(columns),'Missing or duplicate full-CSV columns.'
        for row in reader:
            assert set(row)==set(columns) and all(value not in ('',None) for value in row.values()),'Incomplete full-CSV row.'
            numeric={key:float(value) for key,value in row.items() if key not in ('id','label')}
            assert all(math.isfinite(value) for value in numeric.values()),'Nonfinite full-CSV value.'
            time=numeric['time']
            if previous is None or time!=previous:
                if previous is not None:assert frame_ids==ids and time>previous,'Incomplete or reordered full-CSV frame.'
                else:assert abs(time)<1e-10,'Full CSV must include time zero.'
                previous=time;frame_ids=set();frames+=1
            assert row['id'] in ids and row['id'] not in frame_ids,'Unexpected or repeated body in full CSV.'
            frame_ids.add(row['id']);rows+=1;final=numeric
            for key,value in numeric.items():
                maximum[key]=max(maximum.get(key,0.),abs(value))
                if time<.11:held[key]=max(held.get(key,0.),abs(value))
    assert frame_ids==ids and frames==expected_frames and rows==frames*len(ids),'Native/full-CSV sample count mismatch.'
    duration,step=(model['simulation'][key] for key in ('duration','step'))
    assert duration-step*.1<=previous<=duration+step*1.1,'Full CSV does not reach its requested final time.'
    return {'frames':frames,'rows':rows,'columns':columns,'maximum':maximum,'held':held,'final':final}


def artifact_files(result,directory):
    values={};run_id=result['runId']
    for key,url in result['files'].items():
        assert isinstance(url,str) and re.fullmatch(r'/api/runs/'+re.escape(run_id)+r'/[A-Za-z0-9_.-]+',url),f'Nonlocal result file link: {key}.'
        path=(directory/url.rsplit('/',1)[1]).resolve()
        assert path.parent==directory and path.is_file(),f'Advertised artifact is absent or escapes the run: {key}.'
        values[key]={'bytes':path.stat().st_size,'sha256':digest(path)}
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources',type=Path,required=True)
    parser.add_argument('--solver',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();resources=args.resources.resolve();binary=args.solver.resolve();out=args.out.resolve();backend=resources/'backend'
    if not backend.is_dir() or not (backend/'models.py').is_file():parser.error('--resources must be the extracted application resource root.')
    if not binary.is_file() or not binary.is_relative_to(resources):parser.error('--solver must be the actual native executable inside those packaged resources.')
    if out.is_relative_to(resources) or resources.is_relative_to(out):parser.error('--out must be an isolated directory outside the packaged resources and their ancestors.')
    if out.exists() and any(out.iterdir()):parser.error('--out must be new or empty so stale evidence is never reused.')
    out.mkdir(parents=True,exist_ok=True);data=out/'data';data.mkdir()
    report={'ok':False,'scope':'Packaged backend/native robotics smoke; no GUI, hardware or exhaustive platform qualification.','source_injection':None,'resources':str(resources),'executable':str(binary),'executableSha256':digest(binary),'cases':[]}
    before=tree_digest(resources);report['resourceTreeBefore']=before
    try:
        # The controller's child interpreter inherits only this packaged backend path.
        os.environ['MBDYN_STUDIO_DATA_DIR']=str(data)
        os.environ['PYTHONDONTWRITEBYTECODE']='1'
        os.environ['PYTHONPATH']=str(backend)
        os.environ.pop('MBDYN_STUDIO_WORKSPACE',None)
        (data/'solver.json').write_text(json.dumps({'mode':'native','executable':str(binary)}),encoding='utf-8')
        sys.path.insert(0,str(backend))
        import models,solver,spatial_assembly,flexible_link,rotary_control,app_paths
        from verify_rotary_control import assert_stopped
        package_names={path.stem for path in backend.glob('*.py')}
        origins={}
        for name,module in list(sys.modules.items()):
            if name not in package_names or not getattr(module,'__file__',None):continue
            path=Path(module.__file__).resolve();assert path.is_relative_to(backend),f'Source injection: {name} loaded from {path}.'
            origins[name]={'path':path.relative_to(resources).as_posix(),'sha256':digest(path)}
        assert {'models','solver','spatial_assembly','flexible_link','rotary_control','verify_rotary_control'}<=set(origins),'Packaged module provenance is incomplete.'
        assert app_paths.RESOURCE_ROOT==resources and solver.RUNS.resolve()==data/'runs','Packaged runtime escaped its scoped data root.'
        report.update(source_injection=False,modules=origins)
        info=solver.status();assert info.get('available'),f'Packaged native MBDyn unavailable: {info}'
        report['solverVersion']=info.get('version')
        for identifier in ('spatial-robot-servo','flexible-link','spatial-joint-brake','spatial-sphere-pair'):
            print(f'Packaged native robotics: {identifier}',file=sys.stderr,flush=True)
            record={'example':identifier,'ok':False};report['cases'].append(record);directory=None
            try:
                entry=next(item for item in models.EXAMPLES if item['id']==identifier);model=copy.deepcopy(entry['model'])
                check=models.validate(model);assert check['valid'],f'Packaged example is invalid: {check["issues"]}'
                record['inputSha256']=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                result,code=solver.run(model);record.update(runId=result.get('runId'),httpCode=code)
                if result.get('runId'):directory=(solver.RUNS/result['runId']).resolve();assert directory.parent==data/'runs','Run escaped isolated data.'
                assert code==200 and result.get('ok') and result.get('source')=='MBDyn',result.get('error',result)
                assert 'MBDyn terminated normally' in (directory/'solver.log').read_text(errors='replace'),'Native solver did not terminate normally.'
                assert result['deckSha256']==digest(directory/'model.mbd'),'Retained deck byte hash mismatch.'
                csv_data=full_csv(directory/'results.csv',model,result['metrics']['sampleCount'])
                checks={'normalTermination':True,'completeCsv':True,'csvFrames':csv_data['frames'],'csvRows':csv_data['rows'],'deckHashConvention':'file'}
                if identifier=='spatial-robot-servo':
                    controls=rotary_control.servos(model);assert len(controls)==2 and len(model['bodies'])==2,'Expected packaged two-link robot arm.'
                    maxima={}
                    for control in controls:
                        peak=csv_data['maximum'][f'servo:{control["id"]}:torque_Nm'];assert peak<=control['torqueLimit']+1e-10,'Native servo exceeded torque limit.';maxima[control['id']]=peak
                        assert abs(csv_data['final'][f'servo:{control["id"]}:error_rad'])<.01,'Packaged servo failed final tracking.'
                    meta=result['coSimulation'];assert meta['status']=='completed' and meta['actuatorCount']==2 and meta['exchangeCount']==csv_data['frames'],'Incomplete native controller exchange.'
                    assert result['metrics']['maxConstraintError']<1e-7,'Robot joint constraints failed.'
                    assert_stopped(directory);checks.update(peakTorquesNm=maxima,finalTrackingErrorRad=result['metrics']['finalServoTrackingError'],controllerExchangeCount=meta['exchangeCount'],childrenStopped=True)
                elif identifier=='flexible-link':
                    p=model['parameters'];expected=p['tipLoad']*(p['length']**3/(3*p['bendingStiffness'])+p['length']/p['shearStiffness']);actual=csv_data['final']['tipDeflection_m']
                    assert abs(actual-expected)<3e-6 and abs(actual/expected-1)<.001,'Packaged beam failed independent static deflection.'
                    assert csv_data['maximum']['z']>0.,'Packaged flexible nodes did not move.'
                    checks.update(tipDeflectionM=actual,independentDeflectionM=expected,nativeBeamForces=True)
                elif identifier=='spatial-joint-brake':
                    joint=next(j for j in model['joints'] if j.get('friction'));prefix=f'jointFriction:{joint["id"]}:'
                    assert csv_data['held'][prefix+'speed_rad_s']<1e-12,'Packaged brake crept while held.'
                    assert csv_data['final'][prefix+'dissipatedEnergy_J']>.1 and csv_data['maximum'][prefix+'speed_rad_s']>.1,'Packaged brake did not release and dissipate energy.'
                    checks.update(heldSpeedRadS=csv_data['held'][prefix+'speed_rad_s'],dissipatedEnergyJ=csv_data['final'][prefix+'dissipatedEnergy_J'])
                else:
                    contact=model['contacts'][0];peak=csv_data['maximum'][f'contact:{contact["id"]}:force_N'];loss=csv_data['final'][f'contact:{contact["id"]}:dissipatedEnergy_J']
                    assert peak>20. and loss>.2,'Packaged sphere pair lacked native contact/damping.'
                    momentum=max(abs(sum(body['mass']*node['vx'] for body,node in zip(model['bodies'],sample['nodes']))) for sample in result['samples'])
                    assert momentum<1e-7,'Packaged sphere contact violated linear momentum.'
                    checks.update(peakNativeNormalForceN=peak,dissipatedEnergyJ=loss,maxMomentumErrorKgMS=momentum)
                record.update(ok=True,checks=checks,artifacts=artifact_files(result,directory))
            except (AssertionError,KeyError,ValueError,OSError,StopIteration) as error:record['error']=str(error)
            finally:
                if identifier=='spatial-robot-servo' and directory and (directory/'controller-processes.json').is_file():
                    try:assert_stopped(directory);record['childrenStopped']=True
                    except (AssertionError,OSError,ValueError) as error:record.update(ok=False,childrenStopped=False,error=str(error))
        report['ok']=len(report['cases'])==4 and all(item['ok'] for item in report['cases'])
    except (AssertionError,ImportError,KeyError,ValueError,OSError) as error:report['error']=str(error)
    finally:
        after=tree_digest(resources);report['resourceTreeAfter']=after;report['resourcesUnchanged']=before==after
        if before!=after:report.update(ok=False,error='Packaged resources changed during smoke; runtime isolation failed.')
        (out/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(report,separators=(',',':'),allow_nan=False),flush=True)
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
