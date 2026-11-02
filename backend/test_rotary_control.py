"""Actuator schema, trusted PD law and retained-evidence boundaries."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent
import rotary_control as control
import solver
import spatial_assembly as spatial
from verify_rotary_control import rotor, robot_arm


class RotaryControlTests(unittest.TestCase):
    def test_reference_starts_at_rest_finishes_and_has_signed_units(self):
        actuator=rotor()['jointTorques'][0]
        self.assertEqual(control.reference(actuator,0),(0.,0.))
        self.assertEqual(control.reference(actuator,.4),(math.pi/6,0.))
        self.assertEqual(control.reference(actuator,2),(math.pi/6,0.))
        negative={**actuator,'targetAngleDeg':-30.}
        self.assertEqual(control.reference(negative,.2),tuple(-value for value in control.reference(actuator,.2)))

    def test_pd_uses_feedback_and_bounded_signed_torque(self):
        actuator=rotor(limit=.1)['jointTorques'][0]
        self.assertEqual(control.command(actuator,0,0,0)['commandTorque'],0.)
        self.assertEqual(control.command(actuator,.4,0,0)['commandTorque'],.1)
        self.assertEqual(control.command(actuator,.4,2,0)['commandTorque'],-.1)
        self.assertTrue(control.command(actuator,.4,0,0)['commandSaturated'])
        self.assertEqual(control.command(actuator,.4,math.pi/6,0)['commandTorque'],0.)

    def test_exact_schema_and_parameter_resolution_bounds(self):
        model=rotor();self.assertTrue(spatial.validate(model)['valid'])
        self.assertTrue(spatial.validate(robot_arm())['valid'])
        for key,value in [('kp',True),('kp',0.),('kd',-1.),('targetAngleDeg',171),('rampTime',.001),('rampTime',2.),('torqueLimit',0.),('offset',0.),('endpoint','http://remote')]:
            candidate=deepcopy(model);candidate['jointTorques'][0][key]=value
            with self.subTest(key=key,value=value):self.assertFalse(spatial.validate(candidate)['valid'])
        candidate=deepcopy(model);candidate['simulation']['step']=.02
        self.assertFalse(spatial.validate(candidate)['valid'])

    def test_joint_compatibility_and_duplicate_controllers(self):
        model=rotor()
        for kind in ('cylindrical','weld','spherical'):
            candidate=deepcopy(model);candidate['joints'][0]['type']=kind
            with self.subTest(kind=kind):self.assertFalse(spatial.validate(candidate)['valid'])
        for edit in ('motion','speed','duplicate','missing'):
            candidate=deepcopy(model)
            if edit=='motion':candidate['joints'][0]['motion']=dict(speedDegPerS=30.,rampTime=.2)
            elif edit=='speed':candidate['bodies'][0]['velocity']['wz']=1.
            elif edit=='duplicate':candidate['jointTorques'].append({**candidate['jointTorques'][0],'id':'another'})
            else:candidate['jointTorques'][0]['joint']='absent'
            with self.subTest(edit=edit):self.assertFalse(spatial.validate(candidate)['valid'])

    def test_deck_requires_managed_ports_and_uses_actual_native_feedback(self):
        model=rotor()
        with self.assertRaisesRegex(ValueError,'managed local peer'):spatial.deck(model)
        deck=spatial.deck(model,control_ports=[12345,23456])
        self.assertIn('receive first, no',deck);self.assertIn('initial values, 0',deck)
        self.assertIn('abort if broken',deck);self.assertIn('file, 9001, 1, amplitude, 1',deck)
        self.assertIn('drive, element, 2, joint, string, "rz", direct',deck)
        self.assertIn('drive, element, 2, joint, string, "wz", direct',deck)
        self.assertNotIn('sine,',deck)
        for ports in ([0,23456],[True,23456],[12345]):
            with self.subTest(ports=ports),self.assertRaises(ValueError):spatial.deck(model,control_ports=ports)

    def test_assistant_actuator_edits_remain_typed_atomic_and_reviewed(self):
        model=rotor();actuator=model['jointTorques'].pop()
        proposal=agent.Proposal(model,'Add this rotary actuator. Do not run.')
        edit=dict(collection='jointTorques',operation='add',id=actuator['id'],values={key:value for key,value in actuator.items() if key!='id'})
        self.assertTrue(proposal.call('edit_spatial_assembly',{'edits':[edit]})['accepted'])
        saved=deepcopy(proposal.model)
        self.assertFalse(proposal.call('edit_spatial_assembly',{'edits':[dict(collection='jointTorques',operation='update',id='servo',values={'torqueLimit':-1})]})['accepted'])
        self.assertEqual(proposal.model,saved);self.assertFalse(proposal.run_requested)
        with self.assertRaises(ValueError):proposal.call('edit_spatial_assembly',{'edits':[dict(collection='jointTorques',operation='update',id='servo',values={'kp':True})]})

    def test_wsl_rejection_does_not_launch_a_peer_or_solver(self):
        with patch.object(solver,'configuration',return_value=dict(mode='wsl',executable='/usr/bin/mbdyn',distribution='test')),patch.object(solver,'status',return_value={'available':True}),patch.object(solver,'execute') as execute:
            result,code=solver.run(rotor())
        self.assertEqual(code,422);self.assertIn('native local',result['error']);execute.assert_not_called()

    def test_flexible_template_assistant_edits_preserve_its_family(self):
        import flexible_link
        model=deepcopy(flexible_link.EXAMPLES[0]['model'])
        proposal=agent.Proposal(model,'Change the flexible link density. Do not run.')
        fields=agent.study_parameters(model)
        self.assertIn('parameters/linearDensity',fields)
        result=proposal.call('set_parameters',{'values':{'linearDensity':model['parameters']['linearDensity']*1.1}})
        self.assertTrue(result['accepted']);self.assertEqual(proposal.model['kind'],flexible_link.KIND)
        self.assertEqual(set(proposal.model),set(model));self.assertFalse(proposal.run_requested)

    def test_full_csv_keeps_servo_fields_and_saturation_is_numeric(self):
        sample=dict(time=0.,positionError=0.,velocityError=0.,angularError=0.,angularVelocityError=0.,nodes=[dict(id='rotor',label='Robot rotor')],servoStates=[dict(id='servo',angle=.2,speed=.3,desiredAngle=.4,desiredSpeed=.5,error=.2,torque=.1,saturated=True,power=.03)])
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'result.csv';spatial.write_csv(path,[sample])
            with path.open(encoding='utf-8') as stream:rows=list(csv.DictReader(stream))
        self.assertEqual(rows[0]['servo:servo:saturated'],'1')
        self.assertEqual(float(rows[0]['servo:servo:torque_Nm']),.1)
        self.assertEqual(float(rows[0]['servo:servo:desiredAngle_rad']),.4)

    def test_recorded_feedback_rejects_corrupt_schema_law_and_native_torque(self):
        model=rotor(target=0.);model['simulation']['duration']=.02;model['jointTorques'][0]['rampTime']=.02
        samples=[dict(time=i*.001,nodes=[dict.fromkeys(('rx','ry','rz','wx','wy','wz'),0.)]) for i in range(21)]
        state=dict(id='servo',angle=0.,speed=0.,desiredAngle=0.,desiredSpeed=0.,error=0.,torque=0.,saturated=False,power=0.,commandTorque=0.,commandSaturated=False)
        rows=[dict(time=sample['time'],sent=i<20,servoStates=[deepcopy(state)]) for i,sample in enumerate(samples)]
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);trace=directory/'controller-trace.jsonl';couples=directory/'result.frc'
            def write(records):trace.write_text(''.join(json.dumps(row)+'\n' for row in records),encoding='utf-8')
            couples.write_text('1 1 0 0 0\n'*21,encoding='utf-8');write(rows)
            control.read_trace(directory,model,deepcopy(samples))
            for edit in ('schema','law','power','time','boolean'):
                other=deepcopy(rows)
                if edit=='schema':other[0]['servoStates'][0].pop('speed')
                elif edit=='law':other[0]['servoStates'][0]['commandTorque']=.01
                elif edit=='power':other[0]['servoStates'][0]['power']=1.
                elif edit=='time':other[0]['time']=.01
                else:other[0]['servoStates'][0]['angle']=False
                write(other)
                with self.subTest(edit=edit),self.assertRaises(ValueError):control.read_trace(directory,model,deepcopy(samples))
            write(rows);couples.write_text('1 1 0 0 1\n'*21,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'applied servo torque'):control.read_trace(directory,model,deepcopy(samples))


if __name__=='__main__':unittest.main()
