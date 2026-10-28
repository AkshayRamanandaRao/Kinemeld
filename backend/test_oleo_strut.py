"""Oleo validation, mechanics and energy, independent of solver execution."""
import copy,csv,json,math,tempfile,unittest
from pathlib import Path
import spatial_assembly as spatial

ROOT=Path(__file__).resolve().parents[1]
def example():return json.loads((ROOT/'examples/oleo-strut/wheel-oleo.mbdyn-studio').read_text(encoding='utf8'))['model']

class OleoTests(unittest.TestCase):
 def test_validate_deck_and_native_coefficients(self):
  model=example();self.assertTrue(spatial.validate(model)['valid']);deck=spatial.deck(model)
  self.assertIn('shock absorber, 1000000, 0.001, 0.5, 1.4',deck)
  self.assertIn('metering, const, 0.0001, negative, const, 0.00015',deck)
  self.assertIn('0.001, 850, 1.6;',deck)
 def test_invalid_domain_coefficients_and_unknown_fields(self):
  changes=[lambda f:f.update(gasVolume=.0001),lambda f:f.update(dischargeCoefficient=0),lambda f:f.update(compressionMeteringArea=0),lambda f:f.update(gamma=True),lambda f:f.update(minLength=.6),lambda f:f.update(stopStiffness=0),lambda f:f.update(unknown=1)]
  for change in changes:
   with self.subTest(change=change):
    model=example();change(model['forces'][0]);self.assertFalse(spatial.validate(model)['valid'])
 def test_gas_damping_and_both_penalty_stops(self):
  force=example()['forces'][0]
  def state(length,rate):
   body={'pose':{'x':0,'y':0,'z':length,'rx':0,'ry':0,'rz':0},'velocity':{'vx':0,'vy':0,'vz':rate,'wx':0,'wy':0,'wz':0}}
   return spatial.spring_state({**force,'a':'ground','b':'b','anchorA':{'x':0,'y':0,'z':0}}, {'b':body})
  for length,rate in ((.45,-.1),(.45,.1),(.51,.1),(.51,-.1),(.48,-.2),(.48,.2)):
   s=state(length,rate);ratio=1+force['gasArea']*(length-force['restLength'])/force['gasVolume'];pressure=force['pressure']*ratio**(-force['gamma']);area=force['compressionMeteringArea'] if rate<0 else force['reboundMeteringArea'];hydraulic=.5*force['fluidDensity']*force['fluidArea']**3/(area**2*force['dischargeCoefficient']**2)*rate*abs(rate)
   self.assertAlmostEqual(s['gasPressure'],pressure);self.assertAlmostEqual(s['hydraulicForce'],hydraulic);self.assertAlmostEqual(s['force'],s['gasForce']+s['hydraulicForce']+s['stopForce']);self.assertGreaterEqual(spatial.spring_energy(force,s)[1],0)
   if length==.45:self.assertAlmostEqual(s['stopForce'],force['stopStiffness']*(length-.46)+force['stopDamping']*min(rate,0))
   if length==.51:self.assertAlmostEqual(s['stopForce'],force['stopStiffness']*(length-.5)+force['stopDamping']*max(rate,0))
 def test_energy_gradient_and_gamma_one_limit(self):
  force=example()['forces'][0]
  for gamma in (1.,1.00000001,1.4):
   force['gamma']=gamma
   for length in (.44,.48,.52):
    def energy(L):
     ratio=1+force['gasArea']*(L-force['restLength'])/force['gasVolume'];pressure=force['pressure']*ratio**(-gamma);stop=force['stopStiffness']*(L-force['minLength']) if L<force['minLength'] else force['stopStiffness']*(L-force['maxLength']) if L>force['maxLength'] else 0
     state={'length':L,'extension':L-force['restLength'],'rate':0,'hydraulicForce':0,'stopForce':stop};return spatial.spring_energy(force,state)[0],-force['gasArea']*pressure+stop
    h=1e-7;left,_=energy(length-h);right,_=energy(length+h);_,expected=energy(length);self.assertAlmostEqual((right-left)/(2*h),expected,delta=2e-4)
 def test_csv_budget_matches_header(self):
  model=example();node=dict(id='knuckle',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0);state=dict(id='oleo',length=.5,extension=0,rate=0,force=-1000,gasPressure=1e6,gasForce=-1000,hydraulicForce=0,stopForce=0)
  sample=dict(time=0,nodes=[node],forces=[state],sliders=[dict(id='fixture',position=0,velocity=0,transverse=0,transverseVelocity=0,angle=0,angularVelocity=0)],jointReactions=[dict(id='fixture',force=dict.fromkeys('xyz',0),moment=dict.fromkeys('xyz',0)),dict(id='hub_axis',force=dict.fromkeys('xyz',0),moment=dict.fromkeys('xyz',0))],positionError=0,velocityError=0,angularError=0,angularVelocityError=0,elasticEnergy=0,dampingPower=0,dissipatedEnergy=0)
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'results.csv';spatial.write_csv(p,[sample])
   with p.open(newline='',encoding='utf8') as stream:headers=next(csv.reader(stream))
  self.assertEqual(len(headers)-19,spatial.element_csv_values_per_row(model))
 def test_native_boundary_branches_and_metering_are_checked(self):
  f=example()['forces'][0];L=f['minLength'];v=-.1;x=L-f['restLength'];pressure=f['pressure']*(1+f['gasArea']*x/f['gasVolume'])**(-f['gamma']);gas=-f['gasArea']*pressure
  area=f['compressionMeteringArea'];hydraulic=.5*f['fluidDensity']*f['fluidArea']**3/(area**2*f['dischargeCoefficient']**2)*v*abs(v);state={'id':'oleo','length':L,'extension':x,'rate':v}
  native={'length':L,'rate':v,'pressure':pressure,'meteringArea':area,'elastic':gas+f['stopDamping']*v,'hydraulic':hydraulic,'force':gas+f['stopDamping']*v+hydraulic}
  verified=spatial.validated_oleo_state(f,state,native);_,power=spatial.spring_energy(f,verified);self.assertAlmostEqual(power,hydraulic*v+f['stopDamping']*v*v)
  wrong={**native,'elastic':gas-1234,'force':gas-1234+hydraulic}
  with self.assertRaisesRegex(ValueError,'force disagrees'):spatial.validated_oleo_state(f,state,wrong)
  zero={**native,'rate':0.,'meteringArea':.123,'hydraulic':0.,'elastic':gas,'force':gas}
  with self.assertRaisesRegex(ValueError,'hydraulic force'):spatial.validated_oleo_state(f,{**state,'rate':0.},zero)
  stiff={**f,'stopStiffness':1e9};rounding=.0005
  rounded={**native,'rate':0.,'meteringArea':f['reboundMeteringArea'],'hydraulic':0.,'elastic':gas-rounding,'force':gas-rounding}
  spatial.validated_oleo_state(stiff,{**state,'rate':0.},rounded)
  rounded['elastic']-=.1;rounded['force']-=.1
  with self.assertRaisesRegex(ValueError,'force disagrees'):spatial.validated_oleo_state(stiff,{**state,'rate':0.},rounded)
 def test_no_joint_native_records_are_required_and_checked(self):
  force=example()['forces'][0];model={'joints':[],'forces':[force]};clamp='1 '+' '.join(['0']*12)+'\n';values=[0.]*21;values[12]=.5;values[17]=1e6;values[18]=.0001;values[19]=-1000.;values[0]=-1000.;rod='2 '+' '.join(str(x) for x in values)+'\n'
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp);(path/'result.log').write_text('rod: 2 0 0 0\n');(path/'result.jnt').write_text(clamp+rod);sample={};spatial.parse_joint_reactions(path,model,[sample]);self.assertEqual(sample['_nativeOleo']['oleo']['pressure'],1e6);self.assertNotIn('jointReactions',sample)
   values[0]=float('nan');(path/'result.jnt').write_text(clamp+'2 '+' '.join(str(x) for x in values)+'\n')
   with self.assertRaisesRegex(ValueError,'Non-finite native oleo'):spatial.parse_joint_reactions(path,model,[{}])
   (path/'result.jnt').write_text(clamp)
   with self.assertRaisesRegex(ValueError,'Incomplete native joint output'):spatial.parse_joint_reactions(path,model,[{}])
 def test_native_force_sum_allows_print_rounding_under_cancellation(self):
  f={**example()['forces'][0],'pressure':1e8,'gasArea':1.,'gasVolume':1.,'fluidArea':.01};L=f['restLength'];area=f['reboundMeteringArea'];coefficient=.5*f['fluidDensity']*f['fluidArea']**3/(area**2*f['dischargeCoefficient']**2);rate=math.sqrt((1e8+.00004)/coefficient)
  state={'id':'oleo','length':L,'extension':0.,'rate':rate};native={'length':L,'rate':rate,'pressure':1e8,'meteringArea':area,'elastic':-1e8,'hydraulic':1e8,'force':.00004}
  self.assertAlmostEqual(spatial.validated_oleo_state(f,state,native)['force'],.00004)
  corrupted={**native,'force':.1}
  with self.assertRaisesRegex(ValueError,'force disagrees'):spatial.validated_oleo_state(f,state,corrupted)

if __name__=='__main__':unittest.main()
