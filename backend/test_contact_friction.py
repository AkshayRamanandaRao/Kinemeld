"""Validation and native deck coverage for regularised Coulomb friction on sphere-plane contacts."""
import copy,unittest
import spatial_assembly as sp

class ContactFrictionTests(unittest.TestCase):
    def setUp(self):
        self.model=copy.deepcopy(next(e['model'] for e in sp.EXAMPLES if e['id']=='spatial-sphere-contact'))
        self.model['joints']=[];self.model['simulation']['step']=.0005
        self.model['contacts'][0].update(friction=.3,slipVelocity=.02)

    def test_fields_are_optional_and_bounded(self):
        self.assertTrue(sp.validate(self.model)['valid'])
        plain=copy.deepcopy(self.model);[plain['contacts'][0].pop(k) for k in ('friction','slipVelocity')]
        self.assertTrue(sp.validate(plain)['valid']);self.assertNotIn('friction_',sp.deck(plain))
        for field,value in [('friction',-.1),('friction',2.5),('friction',True),('slipVelocity',0.),('slipVelocity',20.)]:
            model=copy.deepcopy(self.model);model['contacts'][0][field]=value
            with self.subTest(field=field,value=value):self.assertFalse(sp.validate(model)['valid']);self.assertRaises(ValueError,sp.deck,model)
        default=copy.deepcopy(self.model);default['contacts'][0].pop('slipVelocity')
        self.assertEqual(sp.slip_velocity(default['contacts'][0]),sp.FRICTION_SLIP_VELOCITY);self.assertIn(f'/{sp.FRICTION_SLIP_VELOCITY:g})',sp.deck(default))

    def test_deck_applies_force_and_couple_without_argument_calls(self):
        deck=sp.deck(self.model)
        self.assertIn('forces: 2;',deck)
        self.assertIn(' force: 1, absolute, 1, position, reference, node, 0,0,0, component, array, 5, element, 2, joint, string, "vx"',deck)
        self.assertIn(' couple: 2, absolute, 1, component, array, 5,',deck)
        self.assertIn('string, "Fz", string, "friction_n_0=max(0.,-Var); 0"',deck)
        self.assertIn('tanh(friction_s_0/0.02)',deck)
        # Element data passed a time argument would flood the log with MBDyn warnings.
        self.assertNotIn('model::drive',deck);self.assertNotIn('drive caller:',deck)

    def test_force_labels_follow_loads(self):
        model=copy.deepcopy(self.model)
        model['loads']=[{'id':'push','body':'ball','frame':'global','point':{'x':0,'y':0,'z':0},'force':{'x':1,'y':0,'z':0},'torque':{'x':0,'y':0,'z':1},'offset':1.,'amplitude':0.,'frequencyHz':1.}]
        model['contacts'].append({**copy.deepcopy(model['contacts'][0]),'id':'wall','friction':0.})
        model['contacts'].append({**copy.deepcopy(model['contacts'][0]),'id':'floor2'})
        self.assertEqual(sp.friction_force_labels(model),{'floor':(3,4),'floor2':(5,6)})
        deck=sp.deck(model);self.assertIn('forces: 6;',deck);self.assertIn(' force: 5, absolute,',deck);self.assertIn(' couple: 6, absolute,',deck)

    def test_step_check_for_stiff_regularisation(self):
        model=copy.deepcopy(self.model);model['contacts'][0]['slipVelocity']=.001
        issue=next(item for item in sp.validate(model)['issues'] if item['field']=='contacts.0.slipVelocity')
        self.assertIn('smaller time step',issue['message']);self.assertIn('larger slip velocity',issue['message'])
        model['simulation']['step']=.0001;model['contacts'][0]['slipVelocity']=.01;self.assertTrue(sp.validate(model)['valid'])

    def test_csv_columns(self):
        plain=copy.deepcopy(self.model);plain['contacts'][0]['friction']=0.
        self.assertEqual(sp.element_csv_values_per_row(self.model)-sp.element_csv_values_per_row(plain),4)

if __name__=='__main__':unittest.main()
