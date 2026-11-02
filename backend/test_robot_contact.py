"""Boundary/deck/output-contract coverage for native robot brakes and sphere pairs."""
import copy,csv,tempfile,unittest
from pathlib import Path
import spatial_assembly as sp
from verify_robot_contact import brake,spheres


class RobotContactTests(unittest.TestCase):
    def test_brake_bounds_and_joint_compatibility(self):
        model=brake();self.assertTrue(sp.validate(model)['valid'])
        for field,value in [('coefficient',0.),('coefficient',True),('radius',0.),('preload',0.),('preload',-1.)]:
            other=copy.deepcopy(model);other['joints'][0]['friction'][field]=value
            with self.subTest(field=field,value=value):self.assertFalse(sp.validate(other)['valid'])
        for edit in ('motion','joint','speed'):
            other=copy.deepcopy(model)
            if edit=='motion':other['joints'][0]['motion']={'speedDegPerS':30.,'rampTime':.1}
            elif edit=='joint':other['joints'][0]['type']='spherical';other['joints'][0].pop('axisA');other['joints'][0].pop('axisB')
            else:other['bodies'][0]['velocity']['wz']=.1
            with self.subTest(edit=edit):self.assertFalse(sp.validate(other)['valid'])

    def test_native_brake_is_discrete_and_csv_budget_counts_every_field(self):
        model=brake();deck=sp.deck(model)
        self.assertIn('friction, 0.1, preload, 20, discrete coulomb, "brake_0", simple',deck)
        self.assertNotIn('tanh',deck)
        plain=copy.deepcopy(model);plain['joints'][0].pop('friction')
        self.assertEqual(sp.element_csv_values_per_row(model)-sp.element_csv_values_per_row(plain),4)
        self.assertNotIn('discrete coulomb',sp.deck(plain))

    def test_pair_schema_and_reference_integrity(self):
        model=spheres();self.assertTrue(sp.validate(model)['valid'])
        for field,value in [('otherBody','missing'),('otherBody','a'),('otherRadius',0.),('friction',0.),('slipVelocity',.1)]:
            other=copy.deepcopy(model);other['contacts'][0][field]=value
            with self.subTest(field=field):self.assertFalse(sp.validate(other)['valid'])
        model['bodies'][1]['pose']['x']=model['bodies'][0]['pose']['x']
        self.assertFalse(sp.validate(model)['valid'])

    def test_pair_uses_local_centers_and_strain_scaled_native_normal_law(self):
        model=spheres(8.);model['contacts'][0]['center']['y']=.02;model['contacts'][0]['otherCenter']['z']=.03
        deck=sp.deck(model)
        self.assertIn('rod, 1, position, reference, node, 0,0.02,0, 2, position, reference, node, 0,0,0.03, 0.2',deck)
        self.assertIn('"contact_0", multilinear, -1,-200,0,0,1,0',deck)
        self.assertIn('"contact_damping_0", multilinear, -1,-1.6,0,0,1,0',deck)
        self.assertIn('string, "L", string, "Var<0.2"',deck)
        self.assertNotIn('forces:',deck)

    def test_two_body_contact_compliance_bounds_step(self):
        model=spheres();model['simulation']['step']=.02
        self.assertTrue(any('Resolve combined contacts' in i['message'] for i in sp.validate(model)['issues']))

    def test_brake_csv_retains_native_signed_torque_speed_and_dissipation(self):
        sample={'time':0.,'positionError':0.,'velocityError':0.,'angularError':0.,'angularVelocityError':0.,'nodes':[{'id':'a','label':'a'}], 'jointFrictionStates':[{'id':'h','torque':-.5,'speed':1.,'power':.5,'dissipatedEnergy':.2}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'out.csv';sp.write_csv(path,[sample])
            with path.open() as stream:row=next(csv.DictReader(stream))
            self.assertEqual([float(row[f'jointFriction:h:{key}']) for key in ('torque_Nm','speed_rad_s','power_W','dissipatedEnergy_J')],[-.5,1.,.5,.2])

    def test_built_in_robot_cases_are_valid(self):
        for name in ('spatial-joint-brake','spatial-sphere-pair'):
            model=next(e['model'] for e in sp.EXAMPLES if e['id']==name)
            with self.subTest(name=name):self.assertTrue(sp.validate(model)['valid'])


if __name__=='__main__':unittest.main()
