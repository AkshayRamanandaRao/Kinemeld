"""Contract and physical-constraint tests for the spatial MBDyn exporter."""
import copy
import csv
import math
import tempfile
from pathlib import Path
import unittest

import spatial_assembly as spatial


class SpatialAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.model = copy.deepcopy(spatial.EXAMPLES[1]['model'])

    def test_free_body_and_disconnected_joint_cycle_are_valid_graphs(self):
        free=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-free'))
        check=spatial.validate(free);self.assertTrue(check['valid'],check['issues']);self.assertFalse(check['summary']['hasLoops'])
        self.assertIn('joints: 1;',spatial.deck(free)) # The one internal joint clamps the static world node.
        body=copy.deepcopy(free['bodies'][0]);body['id']='other';body['name']='Other';free['bodies'].append(body)
        self.assertTrue(spatial.validate(free)['valid'])
        zero={'x':0.,'y':0.,'z':0.}
        free['joints']=[{'id':name,'type':'spherical','a':'payload','b':'other','anchorA':zero.copy(),'anchorB':zero.copy()} for name in ('first','second')]
        check=spatial.validate(free);self.assertTrue(check['valid'],check['issues']);self.assertTrue(check['summary']['hasLoops'])

    def test_example_and_deck_use_real_spatial_constraints(self):
        self.assertTrue(spatial.validate(self.model)['valid'])
        deck = spatial.deck(self.model)
        self.assertIn('revolute hinge', deck)
        self.assertIn('gravity: uniform', deck)
        self.assertNotIn('planar', deck)
        sphere = spatial.EXAMPLES[0]['model']
        self.assertIn('spherical hinge', spatial.deck(sphere))

    def test_optional_body_local_center_of_mass_is_validated_and_exported(self):
        self.assertIn('body: 1, 1, 1, null,',spatial.deck(self.model))
        self.model['bodies'][0]['centerOfMass']={'x':.2,'y':-.1,'z':.3}
        self.assertTrue(spatial.validate(self.model)['valid'])
        self.assertIn('body: 1, 1, 1, 0.2,-0.1,0.3,',spatial.deck(self.model))
        for value in ({'x':0.,'y':0.},{'x':0.,'y':0.,'z':float('nan')},{'x':0.,'y':0.,'z':0.,'other':1}):
            bad=copy.deepcopy(self.model);bad['bodies'][0]['centerOfMass']=value
            self.assertFalse(spatial.validate(bad)['valid'])

    def test_universal_joint_axes_constraints_and_deck(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-universal'))
        check=spatial.validate(model);self.assertTrue(check['valid'],check['issues'])
        joint=model['joints'][0];body=model['bodies'][0]
        state=spatial.joint_state(joint,None,body)
        self.assertLess(state['angularError'],1e-12);self.assertLess(state['angularVelocityError'],1e-12)
        self.assertIn('cardano hinge',spatial.deck(model))
        bad=copy.deepcopy(model);bad['joints'][0]['axisB']=dict(joint['axisA'])
        self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['bodies'][0]['velocity']['wx']=.25
        self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['joints'][0]['axisB']={'x':0.,'y':0.,'z':0.}
        self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['joints'][0].pop('axisB')
        self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['bodies'][0]['pose']['x']+=.01
        self.assertFalse(spatial.validate(bad)['valid'])

    def test_closed_loop_axle_example_is_valid_and_has_oblique_spin(self):
        example = next(e for e in spatial.EXAMPLES if e['id'] == 'spatial-closed-loop')
        model = example['model']
        result = spatial.validate(model)
        self.assertTrue(result['valid'], result['issues'])
        self.assertTrue(result['summary']['hasLoops'])
        self.assertEqual(len(model['bodies']), 2)
        self.assertEqual([j['type'] for j in model['joints']], ['revolute', 'spherical', 'spherical'])
        axle = model['bodies'][1]
        self.assertAlmostEqual(math.sqrt(axle['velocity']['wy']**2 + axle['velocity']['wz']**2), 1.)
        self.assertNotEqual(axle['velocity']['wy'], 0.)
        self.assertNotEqual(axle['velocity']['wz'], 0.)
        deck = spatial.deck(model)
        self.assertEqual(deck.count('spherical hinge'), 2)
        self.assertEqual(deck.count('revolute hinge'), 1)

    def test_oblique_spatial_prismatic_validates_allowed_motion_and_deck(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-prismatic'))
        result=spatial.validate(model);self.assertTrue(result['valid'],result['issues'])
        state=spatial.joint_state(model['joints'][0],None,model['bodies'][0]);self.assertAlmostEqual(state['position'],.3);self.assertAlmostEqual(state['velocity'],.2)
        deck=spatial.deck(model);self.assertIn('in line',deck);self.assertIn('prismatic',deck);self.assertIn('joints: 3;',deck)
        for field,value in (('axisA',{'x':2.,'y':0.,'z':0.}),('axisA',{'x':0.,'y':0.,'z':0.})):
            bad=copy.deepcopy(model);bad['joints'][0][field]=value;self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['bodies'][0]['pose']['z']=.1;self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['bodies'][0]['velocity']['vz']=.1;self.assertFalse(spatial.validate(bad)['valid'])
        bad=copy.deepcopy(model);bad['bodies'][0]['velocity']['wx']=.1;self.assertFalse(spatial.validate(bad)['valid'])

    def test_moving_prismatic_guide_frame_and_orientation_residual(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-prismatic'))
        b=model['bodies'][0];a=copy.deepcopy(b);a['pose'].update(x=0,y=0,z=0);a['velocity'].update(vx=0,vy=0,vz=0,wx=0,wy=0,wz=1)
        b['velocity'].update(wx=0,wy=0,wz=1)
        r=spatial.body_rotation(a);u=spatial.mul(r,[0,0,1]);d=[.5*x for x in u];velocity=[x+.2*y for x,y in zip(spatial.cross([0,0,1],d),u)]
        b['pose'].update(zip(('x','y','z'),d));b['velocity'].update(zip(('vx','vy','vz'),velocity))
        joint={'id':'guide','type':'prismatic','a':'carrier','b':'block','anchorA':dict.fromkeys(('x','y','z'),0.),'anchorB':dict.fromkeys(('x','y','z'),0.),'axisA':{'x':0.,'y':0.,'z':1.}}
        reference=spatial.matmul(spatial.transpose(spatial.body_rotation(a)),spatial.body_rotation(b));state=spatial.joint_state(joint,a,b,reference)
        self.assertAlmostEqual(state['position'],.5);self.assertAlmostEqual(state['velocity'],.2);self.assertLess(state['velocityError'],1e-12);self.assertLess(state['angularError'],1e-12)
        b['pose']['rx']+=5;self.assertGreater(spatial.joint_state(joint,a,b,reference)['angularError'],.01)

    def test_slider_csv_preserves_quantities_and_units(self):
        node=dict(id='block',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0)
        slider=dict(id='guide',position=.25,velocity=-.5,transverse=1e-8,transverseVelocity=2e-8,angle=3e-8,angularVelocity=4e-8)
        sample=dict(time=0,nodes=[node],sliders=[slider],positionError=1e-8,velocityError=2e-8,angularError=3e-8,angularVelocityError=4e-8)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'results.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['slider:guide:position_m']),.25);self.assertEqual(float(row['slider:guide:velocity_m_s']),-.5)
        self.assertEqual(float(row['slider:guide:transverse_m']),1e-8);self.assertEqual(float(row['slider:guide:angularVelocity_rad_s']),4e-8)

    def test_spatial_force_validation_and_rod_deck(self):
        model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-prismatic'))
        model['forces']=[{'id':'spring','type':'linear-spring-damper','a':'ground','b':'block','anchorA':{'x':-.6,'y':-.8,'z':0},'anchorB':{'x':0,'y':0,'z':0},'stiffness':10.,'damping':1.,'restLength':1.}]
        check=spatial.validate(model);self.assertTrue(check['valid'],check['issues']);deck=spatial.deck(model)
        self.assertIn('skip initial joint assembly;',deck);self.assertIn('rod,',deck);self.assertIn('linear viscoelastic, 10, 1',deck)
        for edit in (
            lambda m:m['forces'][0].update(a='missing'),
            lambda m:m['forces'][0].update(a='block'),
            lambda m:m['forces'][0].update(stiffness=0,damping=0),
            lambda m:m['forces'][0].update(restLength=0),
            lambda m:m['forces'][0].update(type='unsupported'),
            lambda m:m['forces'][0].update(anchorA=copy.deepcopy(m['bodies'][0]['pose'])),
            lambda m:m['forces'].append(copy.deepcopy(m['forces'][0])),
            lambda m:m.update(forces='bad'),
            lambda m:m['forces'][0].update(stiffness=float('nan')),
        ):
            bad=copy.deepcopy(model);edit(bad);self.assertFalse(spatial.validate(bad)['valid'],bad)
        bad=copy.deepcopy(model);bad['forces'][0]['anchorA']={'x':.18,'y':.24,'z':0};self.assertFalse(spatial.validate(bad)['valid'])

    def test_spatial_force_state_uses_rotating_body_local_anchor(self):
        b=copy.deepcopy(self.model['bodies'][0]);b['pose'].update(x=0,y=0,z=0,rx=0,ry=0,rz=0);b['velocity'].update(vx=0,vy=0,vz=0,wx=0,wy=0,wz=1)
        force={'id':'spring','a':'ground','b':'arm','anchorA':{'x':0,'y':1,'z':0},'anchorB':{'x':1,'y':0,'z':0},'stiffness':2.,'damping':.5,'restLength':1.}
        state=spatial.spring_state(force,{'arm':b});self.assertAlmostEqual(state['length'],math.sqrt(2));self.assertAlmostEqual(state['rate'],-1/math.sqrt(2));self.assertAlmostEqual(state['force'],2*(math.sqrt(2)-1)-.5/math.sqrt(2))
        force['anchorA']={'x':1,'y':0,'z':0}
        with self.assertRaisesRegex(ValueError,'collapsed'):spatial.spring_state(force,{'arm':b})

    def test_spatial_force_csv_has_units_and_energy(self):
        node=dict(id='block',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0)
        force=dict(id='spring',length=1.3,extension=.3,rate=.2,force=3.2)
        sample=dict(time=0,nodes=[node],forces=[force],positionError=0,velocityError=0,angularError=0,angularVelocityError=0,elasticEnergy=.45,dampingPower=.04,dissipatedEnergy=0.)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'results.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['force:spring:length_m']),1.3);self.assertEqual(float(row['force:spring:tension_N']),3.2);self.assertEqual(float(row['elasticEnergy_J']),.45)

    def test_spatial_applied_load_validation_and_deck(self):
        model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-prismatic'))
        model['loads']=[{'id':'load','body':'block','frame':'body','point':{'x':.2,'y':0,'z':0},'force':{'x':1,'y':2,'z':3},'torque':{'x':0,'y':1,'z':0},'offset':1.,'amplitude':.5,'frequencyHz':1.}]
        check=spatial.validate(model);self.assertTrue(check['valid'],check['issues']);deck=spatial.deck(model);self.assertIn('forces: 2;',deck);self.assertIn('force: 1, follower, 1, position, reference, node, 0.2,0,0, 1,2,3',deck);self.assertIn('couple: 2, follower, 1, 0,1,0',deck)
        for edit in (
            lambda m:m['loads'][0].update(body='missing'),
            lambda m:m['loads'][0].update(frame='world-ish'),
            lambda m:m['loads'][0].update(force={'x':0,'y':0,'z':0},torque={'x':0,'y':0,'z':0}),
            lambda m:m['loads'][0].update(offset=0,amplitude=0),
            lambda m:m['loads'][0].update(frequencyHz=1000),
            lambda m:m['loads'][0].update(offset=float('nan')),
            lambda m:m['loads'][0].update(point={'x':0,'y':0,'z':0,'extra':1}),
            lambda m:m['loads'].append(copy.deepcopy(m['loads'][0])),
            lambda m:m.update(loads='bad'),
        ):
            candidate=copy.deepcopy(model);edit(candidate);self.assertFalse(spatial.validate(candidate)['valid'],candidate)
        constant=copy.deepcopy(model);constant['loads'][0].update(amplitude=0,frequencyHz=1000);self.assertTrue(spatial.validate(constant)['valid'])
        absolute=copy.deepcopy(model);absolute['loads'][0]['frame']='global';self.assertIn('force: 1, absolute',spatial.deck(absolute))

    def test_spatial_load_csv_records_world_vectors_moment_and_work(self):
        node=dict(id='block',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0)
        load=dict(id='load',force={'x':1,'y':2,'z':3},torque={'x':4,'y':5,'z':6},moment={'x':7,'y':8,'z':9},power=2.5)
        sample=dict(time=0,nodes=[node],loadStates=[load],positionError=0,velocityError=0,angularError=0,angularVelocityError=0,loadPower=2.5,appliedWork=1.)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'results.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['load:load:force_y_N']),2);self.assertEqual(float(row['load:load:moment_z_Nm']),9);self.assertEqual(float(row['appliedWork_J']),1.)

    def test_cylindrical_joint_validates_axis_and_two_free_rates(self):
        model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-cylindrical'))
        result=spatial.validate(model);self.assertTrue(result['valid'],result['issues']);state=spatial.joint_state(model['joints'][0],None,model['bodies'][0]);self.assertAlmostEqual(state['position'],.3);self.assertAlmostEqual(state['velocity'],.2);self.assertLess(state['angularError'],1e-12);self.assertLess(state['angularVelocityError'],1e-12)
        deck=spatial.deck(model);self.assertIn('position constraint, active, active, inactive',deck);self.assertIn('orientation constraint, active, active, inactive',deck)
        for change in (
          lambda m:m['joints'][0].update(axisA={'x':0,'y':0,'z':0}),
          lambda m:m['joints'][0].update(axisB={'x':0,'y':0,'z':1}),
          lambda m:m['bodies'][0]['pose'].update(z=.1),
          lambda m:m['bodies'][0]['velocity'].update(vz=.1),
          lambda m:m['bodies'][0]['velocity'].update(wz=.1),
        ):
          bad=copy.deepcopy(model);change(bad);self.assertFalse(spatial.validate(bad)['valid'])

    def test_cylindrical_csv_exports_independent_motion(self):
        node=dict(id='block',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0)
        joint=dict(id='guide',position=.25,velocity=-.5,angle=5.1,angularVelocity=2.,transverse=0.,transverseVelocity=0.,angularError=0.,angularVelocityError=0.)
        sample=dict(time=0,nodes=[node],cylinders=[joint],positionError=0,velocityError=0,angularError=0,angularVelocityError=0)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'results.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['cylindrical:guide:position_m']),.25);self.assertEqual(float(row['cylindrical:guide:angle_rad']),5.1);self.assertEqual(float(row['cylindrical:guide:angularVelocity_rad_s']),2.)

    def test_bad_input_returns_actionable_errors(self):
        for value in (None, {}, {'kind': 'spatial-assembly'}, [], 'bad'):
            self.assertFalse(spatial.validate(value)['valid'])
        for value in (float('nan'), float('inf'), 10**500, 'x', True):
            model = copy.deepcopy(self.model)
            model['bodies'][0]['pose']['rx'] = value
            result = spatial.validate(model)
            self.assertFalse(result['valid'])
            self.assertIn('bodies.0.pose.rx', [i['field'] for i in result['issues']])
        model = copy.deepcopy(self.model)
        model['bodies'][0]['surprise'] = 1
        self.assertFalse(spatial.validate(model)['valid'])
        with self.assertRaises(ValueError):
            spatial.deck(model)

    def test_rejects_missing_or_incompatible_joint_anchors_and_axis(self):
        self.model['joints'][0]['anchorB']['x'] += .2
        self.assertFalse(spatial.validate(self.model)['valid'])
        self.model = copy.deepcopy(spatial.EXAMPLES[1]['model'])
        self.model['joints'][0]['axisB'] = {'x': 0, 'y': -1, 'z': 0}
        self.assertFalse(spatial.validate(self.model)['valid'])
        self.model = copy.deepcopy(spatial.EXAMPLES[1]['model'])
        self.model['bodies'][0]['velocity']['vx'] = .5
        self.assertFalse(spatial.validate(self.model)['valid'])

    def test_full_inertia_worked_example_is_selectable_and_valid(self):
        item=next(entry for entry in spatial.EXAMPLES if entry['id']=='spatial-full-inertia')
        self.assertEqual(item['model']['bodies'][0]['inertia']['xy'],.02)
        self.assertTrue(spatial.validate(item['model'])['valid'])

    def test_full_body_inertia_is_physically_valid_and_serialized_in_node_axes(self):
        model=copy.deepcopy(self.model);body=model['bodies'][0]
        body['inertia']={'xx':.225,'yy':.275,'zz':.4,'xy':-.04330127018922193,'xz':0.,'yz':0.}
        result=spatial.validate(model);self.assertTrue(result['valid'],result['issues'])
        self.assertIn('sym, 0.225,-0.0433012701892219,0,0.275,0,0.4',spatial.deck(model))
        self.assertGreater(spatial.minimum_inertia_bound(body['inertia']),0.)
        self.assertLessEqual(spatial.minimum_inertia_bound(body['inertia']),.2)
        old=copy.deepcopy(self.model);self.assertTrue(spatial.validate(old)['valid']);self.assertIn('null, diag,',spatial.deck(old))
        for update in ({'xy':.3}, {'xx':1.,'yy':1.,'zz':1.,'xy':.9}, {'xy':float('nan')}, {'xy':True}, {'bad':0}):
            invalid=copy.deepcopy(model);invalid['bodies'][0]['inertia'].update(update)
            with self.subTest(update=update):self.assertFalse(spatial.validate(invalid)['valid'])

    def test_inertia_and_connectivity_are_checked(self):
        self.model['bodies'][0]['inertia']['xx'] = 1.
        self.assertFalse(spatial.validate(self.model)['valid'])
        self.model = copy.deepcopy(spatial.EXAMPLES[1]['model'])
        self.model['joints'][0]['a'] = 'unknown'
        self.assertFalse(spatial.validate(self.model)['valid'])

    def test_euler123_and_local_anchor_math(self):
        r = spatial.rotation(90, 0, 90)
        self.assertTrue(all(abs(a-b) < 1e-12 for a,b in zip(spatial.mul(r,[1,0,0]), [0,0,1])))
        b = self.model['bodies'][0]
        b['pose'].update(rx=20, ry=30, rz=-10)
        self.model['joints'][0]['anchorB'] = dict(zip(('x','y','z'), spatial.mul(spatial.transpose(spatial.body_rotation(b)), [-.5,0,math.sqrt(3)/2])))
        self.model['joints'][0]['axisB'] = dict(zip(('x','y','z'), spatial.mul(spatial.transpose(spatial.body_rotation(b)), [0,1,0])))
        self.assertTrue(spatial.validate(self.model)['valid'])
        self.assertLess(spatial.joint_state(self.model['joints'][0], None, b)['positionError'], 1e-12)


    def test_rotational_elements_validate_and_emit_follower_couples(self):
        model = copy.deepcopy(self.model)
        model['rotationalElements'] = [{'id':'spring','joint':'hinge','stiffness':1.,'damping':.1,'restAngleDeg':20.}]
        model['jointTorques'] = [{'id':'drive','joint':'hinge','amplitude':1.,'frequencyHz':1.,'offset':0.}]
        self.assertTrue(spatial.validate(model)['valid'])
        deck = spatial.deck(model)
        self.assertIn('deformable hinge', deck)
        self.assertIn('couple: 1, follower', deck)
        for mutate in (
            lambda m: m['rotationalElements'][0].update(joint='unknown'),
            lambda m: m['rotationalElements'][0].update(stiffness=-1),
            lambda m: m['rotationalElements'][0].update(damping=0,stiffness=0),
            lambda m: m['rotationalElements'][0].update(restAngleDeg=180),
            lambda m: m['jointTorques'][0].update(frequencyHz=1000),
            lambda m: m['jointTorques'][0].update(amplitude=float('nan')),
            lambda m: m['rotationalElements'].append(copy.deepcopy(m['rotationalElements'][0])),
            lambda m: m.update(jointTorques='wrong'),
        ):
            candidate = copy.deepcopy(model); mutate(candidate)
            self.assertFalse(spatial.validate(candidate)['valid'])

    def test_cylindrical_joint_allows_rotational_spring_and_torque(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-cylindrical'))
        model['rotationalElements']=[{'id':'spring','joint':'guide','stiffness':1.,'damping':.1,'restAngleDeg':15.}]
        model['jointTorques']=[{'id':'drive','joint':'guide','amplitude':.2,'frequencyHz':2.,'offset':.1}]
        self.assertTrue(spatial.validate(model)['valid'])
        deck=spatial.deck(model)
        self.assertIn('deformable hinge',deck);self.assertIn('couple: 1, follower',deck)
        model['joints'][0]['type']='spherical';model['joints'][0].pop('axisA');model['joints'][0].pop('axisB')
        self.assertFalse(spatial.validate(model)['valid'])

    def test_body_to_body_actuation_emits_balanced_followers(self):
        model = copy.deepcopy(self.model)
        other = copy.deepcopy(model['bodies'][0]); other['id'] = 'other'
        model['bodies'].append(other)
        model['joints'].append({'id':'coupling','type':'revolute','a':'arm','b':'other',
          'anchorA':{'x':0.,'y':0.,'z':0.},'anchorB':{'x':0.,'y':0.,'z':0.},
          'axisA':{'x':0.,'y':1.,'z':0.},'axisB':{'x':0.,'y':1.,'z':0.}})
        model['jointTorques'] = [{'id':'drive','joint':'coupling','amplitude':1.,'frequencyHz':1.,'offset':2.}]
        self.assertTrue(spatial.validate(model)['valid'])
        deck = spatial.deck(model)
        self.assertIn('forces: 2;', deck)
        self.assertIn('follower, 2, 0,1,0, sine, 0, 6.28318530717959, 1, forever, 2',deck)
        self.assertIn('follower, 1, 0,1,0, sine, 0, 6.28318530717959, -1, forever, -2',deck)


if __name__ == '__main__':
    unittest.main()
