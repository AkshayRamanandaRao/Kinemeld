"""Check native MBDyn oleo output and energy on a free guided compression/rebound."""
import copy,json,math,shutil,tempfile
from pathlib import Path
import spatial_assembly as spatial
from verify_spatial_assembly import run

def model_at(step):
 model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-spring'))
 model['name']='Nonlinear oleo independent balance';model['simulation']={'duration':.6,'step':step};model['bodies'][0]['velocity'].update(vx=-1.8,vy=-2.4)
 force=model['forces'][0];force.clear();force.update(id='oleo',type='oleo-strut',a='ground',b='block',anchorA={'x':-.6,'y':-.8,'z':0},anchorB={'x':0,'y':0,'z':0},restLength=1.3,pressure=10000.,gasArea=.001,gasVolume=.002,gamma=1.4,minLength=1.2,maxLength=1.35,stopStiffness=1000.,stopDamping=5.,fluidArea=.001,fluidDensity=850.,dischargeCoefficient=.8,compressionMeteringArea=.001,reboundMeteringArea=.0005)
 return model

def verify(step):
 model=model_at(step);result,directory=run(model)
 if not result['ok']:return {'ok':False,'error':result}
 native=[]
 for line in (directory/'result.jnt').read_text(encoding='utf8').splitlines():
  cols=line.split()
  if cols and cols[0]=='3':native.append([float(x) for x in cols])
 samples=result['samples'];assert len(native)==len(samples)
 force=model['forces'][0];previous=None;diss=0.;initial=None;max_energy=max_force=max_pressure=max_hydraulic=0.;seen={'compression':False,'rebound':False,'lowerStop':False,'upperStop':False}
 for sample,row in zip(samples,native):
  state=sample['forces'][0];L,v=state['length'],state['rate'];x=L-force['restLength'];ratio=1+force['gasArea']*x/force['gasVolume'];p=force['pressure']*ratio**(-force['gamma']);area=force['compressionMeteringArea'] if v<0 else force['reboundMeteringArea'];gas=-force['gasArea']*p;visc=.5*force['fluidDensity']*force['fluidArea']**3/(area**2*force['dischargeCoefficient']**2)*v*abs(v)
  stop=0.;stop_power=0.;stop_energy=0.
  if L<force['minLength']:
   displacement=L-force['minLength'];stop=force['stopStiffness']*displacement+force['stopDamping']*min(v,0.);stop_power=force['stopDamping']*min(v,0.)**2;stop_energy=.5*force['stopStiffness']*displacement**2;seen['lowerStop']=True
  elif L>force['maxLength']:
   displacement=L-force['maxLength'];stop=force['stopStiffness']*displacement+force['stopDamping']*max(v,0.);stop_power=force['stopDamping']*max(v,0.)**2;stop_energy=.5*force['stopStiffness']*displacement**2;seen['upperStop']=True
  seen['compression']|=v<-.001;seen['rebound']|=v>.001
  # Compare raw native element force, pressure and individual native hydraulic term.
  max_force=max(max_force,abs(row[1]-(gas+visc+stop)),abs(state['force']-row[1]));max_pressure=max(max_pressure,abs(row[18]-p));max_hydraulic=max(max_hydraulic,abs(row[21]-visc));assert abs(row[19]-area)<1e-12
  U=force['pressure']*force['gasVolume']*math.expm1((1-force['gamma'])*math.log(ratio))/(force['gamma']-1)+stop_energy;energy=.5*model['bodies'][0]['mass']*v*v+U;power=visc*v+stop_power
  if initial is None:initial=energy
  if previous is not None:diss+=(sample['time']-previous[0])*(power+previous[1])/2
  previous=(sample['time'],power);max_energy=max(max_energy,abs(energy+diss-initial))
 return {'ok':all(seen.values()) and max_force<1e-5 and max_pressure<1e-4 and max_hydraulic<1e-5 and max_energy<.1,'stepS':step,'runId':result['runId'],'samples':len(samples),'events':seen,'maxNativeForceErrorN':max_force,'maxNativePressureErrorPa':max_pressure,'maxNativeHydraulicErrorN':max_hydraulic,'maxEnergyBalanceErrorJ':max_energy,'maxJointResidualM':result['metrics']['maxConstraintError']}

def verify_free_and_corruption():
 model=model_at(.0005);model['simulation']['duration']=.05;model['joints']=[];result,directory=run(model)
 if not result['ok']:return {'ok':False,'error':result}
 # Mutate copies of native artifacts so the original run remains available for audit.
 with tempfile.TemporaryDirectory() as temp:
  target=Path(temp)
  for name in ('result.out','result.mov','result.log','result.jnt'):shutil.copyfile(directory/name,target/name)
  original=(target/'result.jnt').read_text(encoding='utf8');rows=original.splitlines();index=next(i for i,line in enumerate(rows) if line.split() and line.split()[0]=='2');fields=rows[index].split();fields[1]='nan';rows[index]=' '.join(fields);(target/'result.jnt').write_text('\n'.join(rows)+'\n')
  try:spatial.parse_output(target,model)
  except ValueError as exc:corruption_rejected='Non-finite native oleo' in str(exc)
  else:corruption_rejected=False
 return {'ok':corruption_rejected and not any('jointReactions' in s or '_nativeOleo' in s for s in result['samples']),'runId':result['runId'],'samples':len(result['samples']),'corruptRodRejected':corruption_rejected,'jointCount':0}

coarse=verify(.0005);fine=verify(.00025);free=verify_free_and_corruption();report={'ok':coarse['ok'] and fine['ok'] and free['ok'] and fine['maxEnergyBalanceErrorJ']<coarse['maxEnergyBalanceErrorJ'],'cases':[coarse,fine,free],'scope':'Guided and free-body illustrative gas and hydraulic law; not a calibrated aircraft oleo.'};Path('verification/oleo-strut.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');print(json.dumps(report,indent=2));raise SystemExit(0 if report['ok'] else 1)
