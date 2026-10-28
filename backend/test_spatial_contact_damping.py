"""Validation boundaries for optional compression-only sphere-plane damping."""
import copy
import unittest
import spatial_assembly as sp

class ContactDampingTests(unittest.TestCase):
    def setUp(self):
        self.model=copy.deepcopy(next(item['model'] for item in sp.EXAMPLES if item['id']=='spatial-sphere-contact'))
    def test_legacy_zero_damping_and_positive_damping_decks(self):
        old=sp.deck(self.model);zero=copy.deepcopy(self.model);zero['contacts'][0]['damping']=0.
        self.assertEqual(sp.deck(zero),old)
        zero['contacts'][0]['damping']=10.;self.assertTrue(sp.validate(zero)['valid'])
        deck=sp.deck(zero);self.assertIn('contact_damping_0',deck);self.assertIn('initial status, inactive',deck);self.assertIn('output, no',deck)
        self.assertIn('nlsf viscoelastic, null, "contact_zero"',deck)
    def test_invalid_damping_and_aggregate_timestep(self):
        for value in (-1,True,float('nan'),1e10):
            model=copy.deepcopy(self.model);model['contacts'][0]['damping']=value
            self.assertFalse(sp.validate(model)['valid'])
        self.model['contacts'][0]['damping']=100.;self.assertTrue(sp.validate(self.model)['valid'])
        self.model['contacts']=[{**self.model['contacts'][0],'id':f'contact{i}'} for i in range(3)]
        self.assertTrue(any(item['field']=='simulation.step' for item in sp.validate(self.model)['issues']))
    def test_timestep_accounts_for_combined_stiffness_and_damping(self):
        self.model['simulation']['step']=.004;self.model['contacts'][0]['damping']=1000.**.5
        self.assertTrue(any(item['field']=='simulation.step' for item in sp.validate(self.model)['issues']))
        self.model['simulation']['step']=.002;self.assertTrue(sp.validate(self.model)['valid'])
    def test_contact_csv_preserves_legacy_and_damping_fields(self):
        import tempfile,csv
        from pathlib import Path
        row={'time':0.,'nodes':[{'id':'ball','label':1}],'contactStates':[{'id':'floor','gap':0.,'penetration':0.,'force':0.,'power':0.,'energy':0.,'dampingPower':2.,'dissipatedEnergy':3.}]}
        for key in ('positionError','velocityError','angularError','angularVelocityError'):row[key]=0.
        with tempfile.TemporaryDirectory() as path:
            file=Path(path)/'result.csv';sp.write_csv(file,[row])
            with file.open(encoding='utf8',newline='') as stream:data=next(csv.DictReader(stream))
        self.assertEqual(float(data['contact:floor:dampingPower_W']),2.);self.assertEqual(float(data['contact:floor:dissipatedEnergy_J']),3.)

if __name__=='__main__':unittest.main()
