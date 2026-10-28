"""Planar prismatic joint schema, kinematic invariants and deck composition."""
import copy
import math
import re
import tempfile
from pathlib import Path
import unittest
import planar_assembly as p
import verify_planar_prismatic as fixtures


class PlanarPrismaticTest(unittest.TestCase):
    def test_ground_slider_allows_nonzero_motion_and_relative_orientation(self):
        model=fixtures.ground();check=p.validate(model)
        self.assertTrue(check['valid'],check['issues'])
        state=p.prismatic_state(model['joints'][0],None,model['bodies'][0])
        self.assertAlmostEqual(state['position'],.2);self.assertAlmostEqual(state['velocity'],.4)
        self.assertAlmostEqual(state['transverse'],0.);self.assertAlmostEqual(state['angle'],0.)

    def test_rotating_guide_transverse_velocity_uses_parent_angular_rate(self):
        model=fixtures.rotating();check=p.validate(model)
        self.assertTrue(check['valid'],check['issues'])
        state=p.prismatic_state(model['joints'][1],model['bodies'][0],model['bodies'][1])
        self.assertAlmostEqual(state['position'],.8);self.assertAlmostEqual(state['velocity'],.2)
        self.assertAlmostEqual(state['transverseVelocity'],0.);self.assertAlmostEqual(state['angularVelocity'],0.)
        damaged=copy.deepcopy(model);damaged['bodies'][1]['velocity']['vx']+=.01
        self.assertFalse(p.validate(damaged)['valid'])

    def test_independent_invalid_geometry_and_motion_are_reported(self):
        cases=[('pose','x',.01,'childAnchor'),('velocity','vx',.01,'childAnchor'),
               ('pose','angleDeg',1.,'referenceAngleDeg'),('velocity','omega',.01,'referenceAngleDeg')]
        for group,key,delta,field in cases:
            with self.subTest(group=group,key=key):
                model=fixtures.ground();model['bodies'][0][group][key]+=delta
                issues=p.validate(model)['issues'];self.assertTrue(any(item['field'].endswith(field) for item in issues),issues)

    def test_joint_type_specific_fields_reject_missing_extra_nonfinite(self):
        for field,value in [('axisAngleDeg',None),('axisAngleDeg',float('nan')),('referenceAngleDeg',True),('axisAngleDeg',361.)]:
            model=fixtures.ground();model['joints'][0][field]=value
            self.assertFalse(p.validate(model)['valid'],(field,value))
        model=fixtures.ground();del model['joints'][0]['axisAngleDeg'];self.assertFalse(p.validate(model)['valid'])
        model=fixtures.rotating();model['joints'][0]['axisAngleDeg']=0.;self.assertFalse(p.validate(model)['valid'])

    def test_deck_has_two_slider_constraints_unique_labels_and_ground_with_spring(self):
        model=fixtures.ground(axis=0.,angle=30.);model['parameters']['gravity']=0.
        model['forces']=[{'id':'spring1','type':'linear-spring-damper','a':'ground','b':'block','anchorA':{'x':-1.,'z':0.},'anchorB':{'x':0.,'z':0.},'stiffness':10.,'damping':.5,'restLength':1.}]
        deck=p.deck(model);ids=re.findall(r'^\s*joint:\s*(\d+),',deck,re.M)
        self.assertEqual(len(ids),4);self.assertEqual(len(set(ids)),4)
        for name in ('in line','prismatic','clamp','rod'):self.assertIn(name,deck)
        self.assertIn('structural nodes: 2;',deck);self.assertIn('joints: 4;',deck)

    def test_revolute_contract_is_not_widened_and_wrapped_angles_are_equivalent(self):
        model=fixtures.ground(angle=180.);model['joints'][0]['referenceAngleDeg']=-180.
        self.assertTrue(p.validate(model)['valid'])
        legacy=copy.deepcopy(p.EXAMPLES[0]['model']);self.assertTrue(p.validate(legacy)['valid'])
        self.assertNotIn('prismatic',p.deck(legacy))

    def test_csv_includes_slider_quantities_only_when_present(self):
        sample={'time':0.,'nodes':[{'id':'body','label':1}],'energy':0.,'jointError':0.,'jointVelocityError':0.,'jointAngularError':0.,'jointAngularVelocityError':0.,
                'sliders':[{'id':'slider','position':.2,'velocity':.4,'transverse':0.,'transverseVelocity':0.,'angle':0.,'angularVelocity':0.}]}
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'result.csv';p.write_csv(file,[sample]);text=file.read_text(encoding='utf8')
        self.assertIn('slider:slider:position_m',text);self.assertIn('jointAngularError_rad',text)

if __name__=='__main__': unittest.main()
