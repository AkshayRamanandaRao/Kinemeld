"""Spatial axial-effort validation and generated MBDyn contract."""
import copy
import unittest
import spatial_assembly as spatial


def example(name='spatial-prismatic'):
    model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']==name))
    model['jointForces']=[{'id':'drive','joint':'guide','amplitude':2.,'frequencyHz':1.,'offset':1.}]
    return model


class AxialDriveTests(unittest.TestCase):
    def test_prismatic_and_cylindrical_generate_single_internal_follower(self):
        for kind in ('spatial-prismatic','spatial-cylindrical'):
            with self.subTest(kind=kind):
                model=example(kind);self.assertTrue(spatial.validate(model)['valid'])
                deck=spatial.deck(model)
                self.assertIn('forces: 1;',deck);self.assertIn('force: 1, follower internal, 1, position, reference, node,',deck)
                self.assertIn('sine, 0, 6.28318530717959, 2, forever, 1;',deck)

    def test_invalid_joint_shape_frequency_and_duplicate_fail(self):
        for edit in (
            lambda model:model['jointForces'][0].update(joint='missing'),
            lambda model:model['jointForces'][0].update(amplitude=True),
            lambda model:model['jointForces'][0].update(frequencyHz=100),
            lambda model:model['jointForces'].append(copy.deepcopy(model['jointForces'][0])),
            lambda model:model['jointForces'][0].update(unknown=1),
            lambda model:model.update(jointForces={}),
        ):
            model=example();edit(model)
            with self.subTest(model=model):self.assertFalse(spatial.validate(model)['valid'])
        wrong=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'))
        wrong['jointForces']=[{'id':'bad','joint':'hinge','amplitude':1.,'frequencyHz':1.,'offset':0.}]
        self.assertFalse(spatial.validate(wrong)['valid'])

    def test_constant_effort_does_not_require_resolving_an_unused_frequency(self):
        model=example();model['jointForces'][0].update(amplitude=0,frequencyHz=1000)
        self.assertTrue(spatial.validate(model)['valid'])


if __name__=='__main__':unittest.main()
