"""Validation and native deck coverage for frictionless sphere-plane contact."""
import copy,unittest
import spatial_assembly as sp

class SpherePlaneTests(unittest.TestCase):
    def setUp(self):self.model=copy.deepcopy(next(e['model'] for e in sp.EXAMPLES if e['id']=='spatial-sphere-contact'))
    def test_contract_and_deck(self):
        self.assertTrue(sp.validate(self.model)['valid']);deck=sp.deck(self.model)
        self.assertIn('scalar function: "contact_0"',deck);self.assertIn('deformable displacement joint',deck);self.assertIn('scalar function elastic orthotropic, null, null, "contact_0"',deck)
        old=copy.deepcopy(self.model);old.pop('contacts');self.assertTrue(sp.validate(old)['valid']);self.assertNotIn('contact_0',sp.deck(old))
    def test_invalid_geometry_references_and_time_step(self):
        for field,value in [('radius',0),('radius',True),('stiffness',-1),('center',{'x':0,'y':0}),('planeNormal',{'x':0,'y':0,'z':2}),('body','missing')]:
            model=copy.deepcopy(self.model);model['contacts'][0][field]=value
            with self.subTest(field=field,value=value):self.assertFalse(sp.validate(model)['valid']);self.assertRaises(ValueError,sp.deck,model)
        model=copy.deepcopy(self.model);model['contacts'].append(copy.deepcopy(model['contacts'][0]));self.assertFalse(sp.validate(model)['valid'])
        model=copy.deepcopy(self.model);model['contacts'][0]['stiffness']=1e9;self.assertTrue(any(issue['field']=='simulation.step' for issue in sp.validate(model)['issues']))
    def test_contact_force_reconstruction_at_separation_and_penetration(self):
        model=self.model;body=model['bodies'][0];contact=model['contacts'][0];body['pose']['z']=.08
        center=sp.anchor(body,contact['center']);gap=sum(n*(x-p) for n,x,p in zip(sp.xyz(contact['planeNormal']),center,sp.xyz(contact['planePoint'])))-contact['radius']
        self.assertAlmostEqual(gap,-.02);self.assertAlmostEqual(contact['stiffness']*max(0,-gap),20.)

    def test_contact_timestep_combines_stiffnesses_on_the_same_body(self):
        model=copy.deepcopy(self.model);model['contacts'][0]['stiffness']=20000.
        self.assertTrue(sp.validate(model)['valid'])
        model['contacts']=[{**copy.deepcopy(model['contacts'][0]),'id':f'floor{i}'} for i in range(4)]
        self.assertTrue(any(issue['field']=='simulation.step' and 'combined contacts' in issue['message'] for issue in sp.validate(model)['issues']))
        model['simulation']['step']=.0005;self.assertTrue(sp.validate(model)['valid'])

if __name__=='__main__':unittest.main()
