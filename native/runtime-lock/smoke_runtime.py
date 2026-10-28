"""Exercise an app-private Windows Python runtime against a disposable app data directory.

The solver is caller-configured. These checks establish local behavior, not clean-host
qualification, redistribution clearance or industrial simulation validation.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys


def worker():
    import primitive_step, solver, spatial_assembly, step_geometry, step_mass
    runtime=Path(sys.executable).resolve().parent
    backend=(runtime.parent.parent/'backend').resolve()
    paths=[Path(value).resolve() for value in sys.path]
    if sys.flags.no_site != 1 or sys.flags.isolated != 1 or any(not (path.is_relative_to(runtime) or path==backend) for path in paths):
        raise ValueError('The embedded interpreter includes a non-application Python path.')
    child=subprocess.run([sys.executable,'-B','-c','import json,sys; print(json.dumps({"noSite":sys.flags.no_site,"isolated":sys.flags.isolated,"paths":sys.path}))'],capture_output=True,text=True,timeout=30,check=True)
    details=json.loads(child.stdout)
    if details['noSite']!=1 or details['isolated']!=1 or any(not (Path(p).resolve().is_relative_to(runtime) or Path(p).resolve()==backend) for p in details['paths']):
        raise ValueError('An embedded interpreter child includes a non-application Python path.')
    spec={'shape':'brick','dimensions':{'x':.1,'y':.2,'z':.3},'pose':{'x':.1,'y':.2,'z':.3,'rx':20,'ry':30,'rz':-15}}
    data=primitive_step.generate_step(spec);converted=step_geometry.convert_step(data,'probe.step');mass=step_mass.calculate(data,500,'part-1')
    if abs(mass['mass']-3)>1e-7 or converted['triangleCount']<=0:raise ValueError('Private OpenCascade STEP calculation failed.')
    model=next(item['model'] for item in spatial_assembly.EXAMPLES if item['id']=='spatial-spherical');model['simulation']['duration']=.1
    result,code=solver.run(model)
    if code!=200 or not result['ok'] or result.get('source')!='MBDyn':raise ValueError('Configured MBDyn solve failed: '+str(result.get('error','unknown error')))
    return {'python':sys.executable,'noSite':sys.flags.no_site,'childNoSite':details['noSite'],'stepTriangles':converted['triangleCount'],'stepMassKg':mass['mass'],'solverSource':result['source'],'solverRunId':result['runId']}


def smoke(app_root, data_dir, desktop=False):
    root=Path(app_root).resolve(strict=True);data=Path(data_dir).resolve(strict=True)
    if not root.is_dir() or not data.is_dir():raise ValueError('Application root and data directory must exist.')
    if (data/'runs').exists():raise ValueError('Choose a fresh data directory with no runs folder; existing run history is never replaced.')
    interpreter=root/'runtime'/'python'/'python.exe'
    if not interpreter.is_file() or not (root/'backend'/'solver.py').is_file():raise ValueError('The staged runtime or application backend is missing.')
    systemroot=os.environ.get('SystemRoot')
    if sys.platform!='win32' or not systemroot:raise ValueError('This test requires Windows and its SystemRoot.')
    env=os.environ.copy();env['PATH']=str(Path(systemroot)/'System32')+os.pathsep+systemroot
    env.pop('MBDYN_STUDIO_PYTHON',None);env.pop('MBDYN_STUDIO_WORKSPACE',None);env.pop('PYTHONDONTWRITEBYTECODE',None)
    env['MBDYN_STUDIO_DATA_DIR']=str(data);env['PYTHONPATH']=str(data/'should-not-be-imported');env['TEMP']=str(data);env['TMP']=str(data)
    command=[str(interpreter),'-B',str(Path(__file__).resolve()),'--worker']
    result=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=180,check=False,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise ValueError('Private runtime check failed: '+(result.stderr or result.stdout)[-4000:])
    try:report=json.loads(result.stdout)
    except (ValueError,TypeError) as exc:raise ValueError('Private runtime returned unreadable test results.') from exc
    if not isinstance(report,dict) or not isinstance(report.get('python'),str) or Path(report['python']).resolve()!=interpreter.resolve() or type(report.get('noSite')) is not int or report['noSite']!=1 or type(report.get('childNoSite')) is not int or report['childNoSite']!=1 or type(report.get('stepTriangles')) is not int or report['stepTriangles']<=0 or type(report.get('stepMassKg')) not in (int,float) or not math.isfinite(report['stepMassKg']) or abs(report['stepMassKg']-3)>1e-7 or report.get('solverSource')!='MBDyn' or not isinstance(report.get('solverRunId'),str) or not re.fullmatch(r'[0-9a-f]{32}',report['solverRunId']):
        raise ValueError('Private runtime returned inconsistent test results.')
    report.update(ok=True,scope='Local isolated interpreter, OpenCascade and configured solver; redistribution and clean-machine qualification not established.')
    if desktop:
        exe=root/'native'/'MBDynStudio.exe'
        if not exe.is_file():raise ValueError('The native desktop executable is missing.')
        process=subprocess.Popen([str(exe),'--smoke'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try: code=process.wait(timeout=120)
        except subprocess.TimeoutExpired as exc:raise ValueError(f'Desktop smoke timed out; inspect owned process {process.pid}.') from exc
        path=data/'runs'/f'native-smoke-report-{process.pid}.json'
        if code or not path.is_file():raise ValueError('Native desktop smoke failed or returned no report.')
        document=json.loads(path.read_text(encoding='utf8'))
        if not document.get('ok') or document.get('source')!='MBDyn' or not document.get('hasCanvas') or Path(document.get('workspace','')).resolve()!=root:raise ValueError('Native desktop smoke did not verify its own workspace and configured solver.')
        report['desktop']={'ok':True,'runId':document['runId'],'hasCanvas':True}
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--worker',action='store_true');parser.add_argument('--app-root');parser.add_argument('--data-dir');parser.add_argument('--desktop',action='store_true');args=parser.parse_args()
    try:
        if args.worker:report=worker()
        elif args.app_root and args.data_dir:report=smoke(args.app_root,args.data_dir,args.desktop)
        else:parser.error('Provide --app-root and --data-dir.')
        print(json.dumps(report,indent=2))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:parser.exit(1,f'Private runtime test failed: {exc}\n')


if __name__=='__main__':main()
