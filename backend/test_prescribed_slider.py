import copy
import unittest

import kinematics
import spatial_assembly as spatial


class PrescribedSliderTest(unittest.TestCase):
    def setUp(self):
        self.model = copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id'] == 'spatial-prismatic'))
        self.model['bodies'][0]['velocity'].update(vx=0, vy=0)
        self.model['joints'][0]['motion'] = {'amplitude': .1, 'frequencyHz': 1.}

    def test_validation_and_deck(self):
        self.assertTrue(spatial.validate(self.model)['valid'])
        deck = spatial.deck(self.model)
        self.assertIn('joints: 2;', deck)
        self.assertIn('position constraint, active, active, active, single, 0,0,1, cosine', deck)
        self.assertNotIn(', in line,', deck)
        self.assertNotIn(', prismatic,', deck)

    def test_invalid_drives_are_rejected(self):
        changes = [lambda m: m['joints'][0]['motion'].update(amplitude=True),
                   lambda m: m['joints'][0]['motion'].update(frequencyHz=0),
                   lambda m: m['joints'][0]['motion'].update(frequencyHz=100),
                   lambda m: m['joints'][0]['motion'].update(extra=1),
                   lambda m: m['bodies'][0]['velocity'].update(vx=.06, vy=.08),
                   lambda m: m['joints'][0].update(type='weld')]
        for change in changes:
            with self.subTest(change=change):
                model = copy.deepcopy(self.model); change(model)
                self.assertFalse(spatial.validate(model)['valid'])

    def test_velocity_solver_can_repair_initial_axial_speed(self):
        self.model['bodies'][0]['velocity'].update(vx=.12, vy=.16)
        result = kinematics.solve({'mode':'velocity','model':self.model,
            'variables':[{'body':'block','component':'vx'}, {'body':'block','component':'vy'}], 'targets':[]})
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['dynamicsValidation']['valid'], result)
        self.assertAlmostEqual(result['model']['bodies'][0]['velocity']['vx'], 0., places=7)
        self.assertAlmostEqual(result['model']['bodies'][0]['velocity']['vy'], 0., places=7)


if __name__ == '__main__':
    unittest.main()
