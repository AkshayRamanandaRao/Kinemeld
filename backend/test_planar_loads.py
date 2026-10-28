"""Constant planar load validation, MBDyn input and work accounting."""
import copy
import csv
from pathlib import Path
import tempfile
import unittest
import planar_assembly as p
from test_planar_assembly import write_native, native_rows


def fixture():
    model=copy.deepcopy(next(example['model'] for example in p.EXAMPLES if example['id']=='assembly-slider'))
    model['loads']=[{'id':'load1','body':'block','fx':2.,'fz':-3.,'torque':1.}]
    return model


class LoadsTests(unittest.TestCase):
    def test_old_project_and_empty_loads_have_identical_deck(self):
        model=copy.deepcopy(p.EXAMPLES[0]['model']); old=p.deck(model); model['loads']=[]
        self.assertTrue(p.validate(model)['valid']);self.assertEqual(p.deck(model),old)

    def test_bad_loads_are_rejected(self):
        cases=[('body','ground'),('body','unknown'),('id','x; include'),('fx',True),('fx',float('nan')),('fz',float('inf')),('torque',10**400),('torque','1')]
        for key,value in cases:
            model=fixture();model['loads'][0][key]=value
            with self.subTest(key=key,value=value):self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads'][0]['extra']=1;self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads'][0].pop('torque');self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads'][0].update(fx=0,fz=0,torque=0);self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads']*=33;self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads']+=copy.deepcopy(model['loads']);self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['loads']='not a list';self.assertFalse(p.validate(model)['valid'])

    def test_export_uses_global_components_and_positive_y_torque(self):
        model=fixture();deck=p.deck(model)
        self.assertIn('forces: 2;',deck)
        self.assertIn('force: 1, absolute, 1, position, null, component, const, 2, const, 0, const, -3;',deck)
        self.assertIn('couple: 2, absolute, 1, 0,1,0, const, 1;',deck)
        self.assertNotIn('skip initial joint assembly;',deck)

    def test_power_work_and_csv_are_reconstructed_from_native_velocity(self):
        model=fixture();model['loads'][0]={'id':'load1','body':'block','fx':0.,'fz':-3.,'torque':0.}
        row=native_rows(model)[0];row[9]=-2.
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);write_native(directory,model,frames=[[row],[row]],times=[0,model['simulation']['duration']])
            samples=p.parse_output(directory,model)
            self.assertEqual(samples[0]['loadPower'],6.)
            self.assertAlmostEqual(samples[-1]['appliedWork'],6.*model['simulation']['duration'])
            self.assertEqual(samples[-1]['loadStates'],[{'id':'load1','power':6.}])
            metrics=p.metrics(model,samples);self.assertIn('maxEnergyBalanceError',metrics)
            p.write_csv(directory/'result.csv',samples)
            with (directory/'result.csv').open(newline='') as stream: rows=list(csv.DictReader(stream))
            self.assertAlmostEqual(float(rows[-1]['load:load1:power_W']),6.)
            self.assertAlmostEqual(float(rows[-1]['appliedWork_J']),6.*model['simulation']['duration'])

if __name__=='__main__':unittest.main()
