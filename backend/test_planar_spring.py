"""Validated spring/damper model contracts and reconstructed force algebra."""
import copy
import math
import unittest
import planar_assembly as p


def fixture():
    model=copy.deepcopy(p.EXAMPLES[0]['model'])
    model['forces']=[{'id':'spring1','type':'linear-spring-damper','a':'ground','b':'upper_link','anchorA':{'x':1,'z':0},'anchorB':{'x':0,'z':-.5},'restLength':1.3,'stiffness':10,'damping':.5}]
    return model


class SpringTests(unittest.TestCase):
    def test_legacy_and_empty_preserve_deck_and_validation(self):
        baseline=copy.deepcopy(p.EXAMPLES[0]['model'])
        without=p.deck(baseline)
        baseline['forces']=[]
        self.assertTrue(p.validate(baseline)['valid'])
        self.assertEqual(p.deck(baseline),without)

    def test_validation_rejects_bad_references_units_and_unsafe_values(self):
        bad=[('a','unknown'),('b','ground'),('id','bad;command'),('type','torque'),('restLength',0),('restLength',float('nan')),('stiffness',-1),('damping',float('inf')),('damping',True),('anchorA',{'x':0,'z':'bad'})]
        for key,value in bad:
            model=fixture();model['forces'][0][key]=value
            with self.subTest(key=key,value=value): self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['forces'][0]['stiffness']=model['forces'][0]['damping']=0
        self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['forces'][0]['anchorB']={'x':0,'z':.5};model['forces'][0]['anchorA']={'x':0,'z':0}
        self.assertFalse(p.validate(model)['valid'])
        model=fixture();model['forces']*=33
        self.assertFalse(p.validate(model)['valid'])

    def test_rod_deck_preserves_physical_units_and_static_ground(self):
        model=fixture();deck=p.deck(model)
        self.assertTrue(p.validate(model)['valid'])
        self.assertIn('skip initial joint assembly;',deck)
        self.assertIn('structural: 0, static, null, eye, null, null, output, no;',deck)
        self.assertIn('linear viscoelastic, 13, 0.65;',deck)
        self.assertIn('1.3,',deck)

    def test_axial_state_and_velocity_include_rotation_and_reaction(self):
        # Rotating attachment at body-local X=1, body omega=2 rad/s.
        body={'pose':{'x':0,'z':0,'angleDeg':0},'velocity':{'vx':0,'vz':0,'omega':2}}
        force={'id':'s','a':'ground','b':'link','anchorA':{'x':0,'z':2},'anchorB':{'x':1,'z':0},'restLength':1,'stiffness':3,'damping':4}
        state=p.spring_state(force,{'link':body});length=math.sqrt(5)
        self.assertAlmostEqual(state['length'],length)
        self.assertAlmostEqual(state['rate'],4/length)
        self.assertAlmostEqual(state['force'],3*(length-1)+4*4/length)
        swapped={**force,'a':'link','b':'ground','anchorA':force['anchorB'],'anchorB':force['anchorA']}
        self.assertAlmostEqual(p.spring_state(swapped,{'link':body})['force'],state['force'])

if __name__=='__main__':unittest.main()
