"""Rotational input and output boundaries, independent of solver installation."""
import copy
import csv
import math
import tempfile
import unittest
from pathlib import Path
import planar_assembly as planar
from test_planar_assembly import native_rows, write_native


class PlanarRotaryTests(unittest.TestCase):
    def setUp(self):
        self.model=copy.deepcopy(planar.EXAMPLES[0]['model'])
        self.model['simulation']={'duration':1.,'step':.001}
        self.model['rotationalElements']=[{'id':'spring1','joint':'ground_pin','stiffness':10.,'damping':.5,'restAngleDeg':-20.}]
        self.model['jointTorques']=[{'id':'drive1','joint':'ground_pin','amplitude':1.,'frequencyHz':1.1,'offset':.3}]

    def test_validation_and_legacy_deck(self):
        self.assertTrue(planar.validate(self.model)['valid'])
        old=copy.deepcopy(planar.EXAMPLES[0]['model']);empty=copy.deepcopy(old)
        empty.update(rotationalElements=[],jointTorques=[])
        self.assertEqual(planar.deck(old),planar.deck(empty))
        self.assertNotIn('rotationalElements',old)

    def test_invalid_rotary_inputs(self):
        for key,value in [('joint','missing'),('stiffness',float('nan')),('stiffness',True),('restAngleDeg',180.),('unexpected',1)]:
            model=copy.deepcopy(self.model);model['rotationalElements'][0][key]=value
            self.assertFalse(planar.validate(model)['valid'],(key,value))
        model=copy.deepcopy(self.model);model['rotationalElements'][0].update(stiffness=0,damping=0)
        self.assertFalse(planar.validate(model)['valid'])
        model=copy.deepcopy(self.model);model['jointTorques'][0]['frequencyHz']=100.
        self.assertFalse(planar.validate(model)['valid'])
        model=copy.deepcopy(self.model);model['rotationalElements'][0]['restAngleDeg']=175.
        self.assertFalse(planar.validate(model)['valid'])
        model=copy.deepcopy(self.model);model['rotationalElements']*=33
        self.assertFalse(planar.validate(model)['valid'])
        model=copy.deepcopy(planar.EXAMPLES[-1]['model']);model['rotationalElements']=[dict(self.model['rotationalElements'][0],joint='slide')]
        self.assertFalse(planar.validate(model)['valid'])

    def test_native_output_and_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);write_native(path,self.model)
            samples=planar.parse_output(path,self.model)
            state=samples[0]['rotationalStates'][0]
            self.assertAlmostEqual(state['angle'],math.radians(12))
            self.assertAlmostEqual(state['torque'],-10*math.radians(12))
            self.assertAlmostEqual(samples[0]['elasticEnergy'],5*math.radians(12)**2)
            self.assertAlmostEqual(samples[0]['actuationStates'][0]['torque'],.3)
            planar.write_csv(path/'out.csv',samples)
            with (path/'out.csv').open(encoding='utf8',newline='') as stream: row=next(csv.DictReader(stream))
            self.assertAlmostEqual(float(row['rotational:spring1:angle_rad']),math.radians(12))
            self.assertAlmostEqual(float(row['actuation:drive1:torque_Nm']),.3)

    def test_branch_crossing_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp);first=native_rows(self.model);second=copy.deepcopy(first)
            first[0][5]=150.;second[0][5]=-170.
            write_native(path,self.model,[first,second])
            with self.assertRaisesRegex(ValueError,'rotation branch'):
                planar.parse_output(path,self.model)

    def test_equal_opposite_body_torque_deck(self):
        model=copy.deepcopy(planar.EXAMPLES[1]['model'])
        model['jointTorques']=[{'id':'motor','joint':'elbow','amplitude':1.,'frequencyHz':2.,'offset':.3}]
        deck=planar.deck(model)
        self.assertIn('forces: 2;',deck)
        self.assertIn('couple: 1, absolute, 2',deck)
        self.assertIn('couple: 2, absolute, 1',deck)
        self.assertIn('forever, -0.3',deck)

if __name__=='__main__': unittest.main()
