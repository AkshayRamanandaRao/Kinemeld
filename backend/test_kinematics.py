"""Independent position constraints: known analytic models and failure cases."""
import copy
import math
import unittest
from unittest.mock import patch

import kinematics
import spatial_assembly as spatial


def vec(x,y,z):return {'x':x,'y':y,'z':z}
def body(name,x,z,ry):
    return {'id':name,'name':name,'mass':1.,'inertia':{'xx':.1,'yy':.1,'zz':.1},
            'pose':{'x':x,'y':0.,'z':z,'rx':0.,'ry':ry,'rz':0.},
            'velocity':dict.fromkeys(('vx','vy','vz','wx','wy','wz'),0.)}


def slider_crank(angle=20):
    angle_rad=math.radians(angle);pin_x,pin_z=math.cos(angle_rad),math.sin(angle_rad)
    slider_x=pin_x+math.sqrt(4-pin_z*pin_z);rod_angle=math.degrees(math.atan2(pin_z,slider_x-pin_x))
    crank=body('crank',pin_x/2,pin_z/2,-angle);rod=body('rod',(pin_x+slider_x)/2,pin_z/2,rod_angle);slider=body('slider',slider_x,0,0)
    axis=vec(0,1,0)
    def hinge(name,a,b,anchor_a,anchor_b):
        return {'id':name,'type':'revolute','a':a,'b':b,'anchorA':anchor_a,'anchorB':anchor_b,'axisA':axis,'axisB':axis}
    return {'kind':'spatial-assembly','name':'Closed slider crank', 'parameters':{'gravity':vec(0,0,0)},
      'simulation':{'duration':1.,'step':.002},'bodies':[crank,rod,slider],
      'joints':[hinge('base','ground','crank',vec(0,0,0),vec(-.5,0,0)),
                hinge('elbow','crank','rod',vec(.5,0,0),vec(-1,0,0)),
                {'id':'guide','type':'prismatic','a':'ground','b':'slider','anchorA':vec(0,0,0),'anchorB':vec(0,0,0),'axisA':vec(1,0,0)},
                hinge('tip','rod','slider',vec(1,0,0),vec(0,0,0))]}


def request(model):
    variables=[{'body':body,'component':component} for body in ('crank','rod') for component in ('x','z','ry')]
    variables.append({'body':'slider','component':'x'})
    return {'model':model,'variables':variables,'targets':[{'body':'crank','component':'ry','value':-30.}]}


class KinematicsTests(unittest.TestCase):
    def test_closed_slider_crank_matches_independent_geometry_and_preserves_input(self):
        model=slider_crank();self.assertTrue(spatial.validate(model)['valid'])
        before=copy.deepcopy(model);result=kinematics.solve(request(model))
        self.assertTrue(result['ok'],result);self.assertEqual(result['source'],'Independent kinematic position solve')
        self.assertEqual(result['jacobianRank'],7);self.assertLess(result['maxResidual'],1e-7)
        expected=math.cos(math.pi/6)+math.sqrt(4-.25)
        self.assertAlmostEqual(result['model']['bodies'][2]['pose']['x'],expected,places=7)
        self.assertTrue(result['dynamicsValidation']['valid']);self.assertEqual(model,before)

    def test_initial_guess_and_zero_velocity_do_not_overwrite_other_properties(self):
        model=slider_crank();args=request(model)
        args['variables'][0]['initial']=.45;args['variables'][-1]['initial']=2.8
        result=kinematics.solve(args);self.assertTrue(result['ok'],result)
        self.assertEqual(result['model']['bodies'][0]['velocity'],model['bodies'][0]['velocity'])
        self.assertEqual(result['model']['bodies'][0]['inertia'],model['bodies'][0]['inertia'])
        self.assertEqual(result['model']['joints'],model['joints'])

    def test_oblique_slider_and_cylindrical_position_targets(self):
        for example in ('spatial-prismatic','spatial-cylindrical'):
            model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']==example))
            components=('x','y','z') if example=='spatial-prismatic' else kinematics.COMPONENTS
            targets=[{'body':'block','component':'x','value':.36}]
            if example=='spatial-cylindrical':targets.append({'body':'block','component':'ry','value':-5.})
            result=kinematics.solve({'model':model,'variables':[{'body':'block','component':c} for c in components],'targets':targets})
            with self.subTest(example=example):
                self.assertTrue(result['ok'],result);pose=result['model']['bodies'][0]['pose']
                self.assertAlmostEqual(pose['x'],.36,places=6);self.assertAlmostEqual(pose['y'],.48,places=6);self.assertAlmostEqual(pose['z'],0,places=6)
                self.assertTrue(result['dynamicsValidation']['valid'])

    def test_solved_universal_pose_reports_unchanged_incompatible_velocity(self):
        model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-universal'));before=copy.deepcopy(model['bodies'][0]['velocity'])
        result=kinematics.solve({'model':model,'variables':[{'body':'yoke','component':c} for c in kinematics.COMPONENTS],
             'targets':[{'body':'yoke','component':'rx','value':25.},{'body':'yoke','component':'ry','value':-13.}]})
        self.assertTrue(result['ok'],result);self.assertEqual(result['model']['bodies'][0]['velocity'],before)
        self.assertFalse(result['dynamicsValidation']['valid'])
        self.assertTrue(any('angular velocities' in issue['message'] for issue in result['dynamicsValidation']['issues']))

    def test_inconsistent_targets_and_underdetermined_coordinates_never_return_candidate(self):
        model=slider_crank();args=request(model);args['targets'].append({'body':'slider','component':'x','value':5.})
        failed=kinematics.solve(args);self.assertFalse(failed['ok']);self.assertNotIn('model',failed);self.assertGreater(failed['maxResidual'],failed['tolerance'])
        single=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'))
        free={'model':single,'variables':[{'body':'arm','component':key} for key in ('x','z','ry')],'targets':[]}
        under=kinematics.solve(free);self.assertFalse(under['ok']);self.assertEqual(under['reason'],'underdetermined');self.assertLess(under['jacobianRank'],under['unknownCount']);self.assertNotIn('model',under)

    def test_singular_toggle_is_not_reported_as_unique_solution(self):
        model=slider_crank(0);args=request(model);args['targets']=[{'body':'slider','component':'x','value':3.}]
        result=kinematics.solve(args);self.assertFalse(result['ok']);self.assertEqual(result['reason'],'underdetermined');self.assertNotIn('model',result)

    def test_bad_request_is_actionable_and_does_not_mutate(self):
        model=slider_crank();before=copy.deepcopy(model)
        cases=[{'model':model,'variables':[],'targets':[]},
          {'model':model,'variables':[{'body':'missing','component':'x'}],'targets':[]},
          {'model':model,'variables':[{'body':'crank','component':'x'},{'body':'crank','component':'x'}],'targets':[]},
          {'model':model,'variables':[{'body':'crank','component':'x','initial':True}],'targets':[]},
          {'model':model,'variables':[{'body':'crank','component':'x','initial':10**400}],'targets':[]},
          {'model':model,'variables':[{'body':'crank','component':'x'}],'targets':[{'body':'crank','component':'x','value':10**400}]},
          {'model':model,'variables':[{'body':'crank','component':'x'}],'targets':[{'body':'crank','component':'x','value':float('nan')}]},
          {'model':model,'variables':[{'body':'crank','component':'x'}],'targets':[],'extra':True}]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(kinematics.KinematicsError):kinematics.solve(args)
        self.assertEqual(model,before)

    def test_deadline_returns_no_candidate_or_false_rank(self):
        with patch.object(kinematics.time,'monotonic',side_effect=[0.,kinematics.MAX_SECONDS+1]):
            result=kinematics.solve(request(slider_crank()))
        self.assertFalse(result['ok']);self.assertEqual(result['reason'],'time_limit');self.assertIsNone(result['jacobianRank']);self.assertNotIn('model',result)

    def test_slider_crank_velocity_matches_analytic_derivative(self):
        model=slider_crank(30);before=copy.deepcopy(model)
        variables=[{'body':name,'component':component} for name in ('crank','rod') for component in ('vx','vz','wy')]
        variables.append({'body':'slider','component':'vx'})
        result=kinematics.solve({'mode':'velocity','model':model,'variables':variables,
            'targets':[{'body':'crank','component':'wy','value':-1.}]})
        self.assertTrue(result['ok'],result);self.assertEqual(result['jacobianRank'],7)
        expected=-.5-(.5*math.cos(math.pi/6))/math.sqrt(4-.25)
        self.assertAlmostEqual(result['model']['bodies'][2]['velocity']['vx'],expected,places=9)
        self.assertTrue(result['dynamicsValidation']['valid'],result['dynamicsValidation']);self.assertEqual(model,before)
        for solved,original in zip(result['model']['bodies'],model['bodies']):self.assertEqual(solved['pose'],original['pose'])

    def test_velocity_can_repair_angular_step_issue_but_not_other_step_errors(self):
        model=copy.deepcopy(next(e['model'] for e in spatial.EXAMPLES if e['id']=='spatial-revolute'))
        model['bodies'][0]['velocity']['wy']=100.
        args={'mode':'velocity','model':model,'variables':[{'body':'arm','component':key} for key in ('vx','vz','wy')],
              'targets':[{'body':'arm','component':'wy','value':0.}]}
        result=kinematics.solve(args)
        self.assertTrue(result['ok'],result);self.assertTrue(result['dynamicsValidation']['valid'],result['dynamicsValidation'])
        self.assertAlmostEqual(result['model']['bodies'][0]['velocity']['wy'],0.)
        model['simulation']['step']=1e-8
        with self.assertRaisesRegex(kinematics.KinematicsError,'simulation.step'):kinematics.solve(args)

    def test_velocity_inconsistent_underdetermined_invalid_pose_and_bad_inputs(self):
        model=slider_crank(30)
        unknown=[{'body':name,'component':component} for name in ('crank','rod') for component in ('vx','vz','wy')]+[{'body':'slider','component':'vx'}]
        args={'mode':'velocity','model':model,'variables':unknown,'targets':[{'body':'crank','component':'wy','value':-1.},{'body':'slider','component':'vx','value':5.}]}
        result=kinematics.solve(args);self.assertFalse(result['ok']);self.assertEqual(result['reason'],'inconsistent');self.assertNotIn('model',result)
        args['targets']=[];result=kinematics.solve(args);self.assertFalse(result['ok']);self.assertEqual(result['reason'],'underdetermined');self.assertNotIn('model',result)
        bad=copy.deepcopy(model);bad['bodies'][0]['pose']['x']+=.1;args.update(model=bad)
        with self.assertRaisesRegex(kinematics.KinematicsError,'position constraints'):kinematics.solve(args)
        args.update(model=model,variables=[{'body':'crank','component':'vx','initial':True}])
        with self.assertRaises(kinematics.KinematicsError):kinematics.solve(args)

    def test_sliding_joint_accounts_for_rotation_of_parent_frame(self):
        model=slider_crank(30);a,b=model['bodies'][:2]
        a['velocity'].update(wx=0.,wy=2.,wz=0.);b['velocity'].update(wx=0.,wy=2.,wz=0.)
        axis={'x':1.,'y':0.,'z':0.};joint={'id':'guide','type':'prismatic','a':'crank','b':'rod','anchorA':vec(0,0,0),'anchorB':vec(0,0,0),'axisA':axis}
        # Equal angular velocities and rigid parent-frame transport yield zero transverse rate.
        delta=spatial.sub(spatial.anchor(b,joint['anchorB']),spatial.anchor(a,joint['anchorA']))
        transport=spatial.cross(spatial.angular(a),delta)
        b['velocity'].update(dict(zip(('vx','vy','vz'),transport)))
        model['joints']=[joint]
        self.assertLess(max(map(abs,kinematics._velocity_constraints(model,[]))),1e-12)

    def test_rotation_log_does_not_confuse_180_degrees_with_identity(self):
        self.assertAlmostEqual(spatial.norm(kinematics._rotation_vector(spatial.rotation(180,0,0))),math.pi,places=9)
        self.assertLess(spatial.norm(kinematics._rotation_vector(spatial.rotation(0,0,0))),1e-12)


if __name__=='__main__':unittest.main()
