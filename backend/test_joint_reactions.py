"""Native reaction framing, normalization and lossless CSV output."""
import copy
import csv
import tempfile
import unittest
from pathlib import Path

import spatial_assembly as spatial


def record(label, world, width):
    values=[0.]*6+list(world)+[0.]*(width-13)
    return str(label)+' '+' '.join(str(value) for value in values)+'\n'


class JointReactionTest(unittest.TestCase):
    def setUp(self):
        self.model={'joints':[{'id':'ball','type':'spherical'},{'id':'slider','type':'prismatic'},{'id':'weld','type':'weld'}]}
        # MBDyn emits clamp, spherical, in-line, prismatic auxiliary, total joint.
        self.frame=record(1,[0.]*6,13)+record(2,[1,2,3,4,5,6],16)+record(3,[7,8,9,0,0,0],13)+record(5,[0,0,0,10,11,12],13)+record(4,[13,14,15,16,17,18],25)

    def parse(self,text):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'result.jnt').write_text(text,encoding='utf8');(path/'result.log').write_text('sphericalhinge: 2\ninline: 3\nprismatic: 5\ntotaljoint: 4\n',encoding='utf8');samples=[{'time':0},{'time':1}]
            spatial.parse_joint_reactions(path,self.model,samples);return samples

    def test_complete_frames_map_signs_and_prismatic_components(self):
        rows=self.parse(self.frame*2)
        self.assertEqual(rows[0]['jointReactions'],[
            {'id':'ball','force':dict(zip('xyz',[1,2,3])),'moment':dict(zip('xyz',[4,5,6]))},
            {'id':'slider','force':dict(zip('xyz',[-7,-8,-9])),'moment':dict(zip('xyz',[10,11,12]))},
            {'id':'weld','force':dict(zip('xyz',[-13,-14,-15])),'moment':dict(zip('xyz',[-16,-17,-18]))}])
        self.assertEqual(rows[1]['jointReactions'],rows[0]['jointReactions'])

    def test_truncated_reordered_and_corrupt_frames_fail(self):
        bad=[self.frame,self.frame*2+record(1,[0.]*6,13),self.frame.replace(record(3,[7,8,9,0,0,0],13),record(99,[7,8,9,0,0,0],13),1)+self.frame,
             self.frame.replace(record(2,[1,2,3,4,5,6],16),record(2,[float('nan'),2,3,4,5,6],16),1)+self.frame,
             self.frame.replace(record(4,[13,14,15,16,17,18],25),record(4,[13,14,15,16,17,18],13))+self.frame]
        for text in bad:
            with self.subTest(text=text[:30]),self.assertRaises(ValueError):self.parse(text)

    def test_missing_file_and_free_body(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'Missing native joint output'):spatial.parse_joint_reactions(Path(temp),self.model,[{}])
            sample={};spatial.parse_joint_reactions(Path(temp),{'joints':[]},[sample]);self.assertNotIn('jointReactions',sample)

    def test_mismatched_native_joint_type_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);(path/'result.jnt').write_text(self.frame,encoding='utf8');(path/'result.log').write_text('sphericalhinge: 2\ninline: 3\nprismatic: 5\nrevolutehinge: 4\n',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Native joint types'):spatial.parse_joint_reactions(path,self.model,[{}])

    def test_csv_uses_explicit_world_force_and_moment_units(self):
        node=dict(id='body',label=1,x=0,y=0,z=0,rx=0,ry=0,rz=0,vx=0,vy=0,vz=0,wx=0,wy=0,wz=0)
        sample=dict(time=0,nodes=[node],jointReactions=[{'id':'ball','force':dict(zip('xyz',[1,2,3])),'moment':dict(zip('xyz',[4,5,6]))}],positionError=0,velocityError=0,angularError=0,angularVelocityError=0)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:row=next(csv.DictReader(stream))
        self.assertEqual(float(row['jointReaction:ball:force_y_N']),2);self.assertEqual(float(row['jointReaction:ball:moment_z_Nm']),6)

    def test_csv_column_budget_counts_all_repeated_element_components(self):
        model={'joints':[{'type':'revolute'},{'type':'prismatic'},{'type':'cylindrical'}],
               'rotationalElements':[{}],'jointTorques':[{}],'jointForces':[{}],'forces':[{}],'loads':[{}],'contacts':[{}]}
        vec={'x':0.,'y':0.,'z':0.}
        sample={'time':0,'nodes':[],'positionError':0,'velocityError':0,'angularError':0,'angularVelocityError':0,
                'jointReactions':[{'id':str(i),'force':vec,'moment':vec} for i in range(3)],
                'contactStates':[{'id':'contact'}],'cylinders':[dict(id='cylinder',position=0,velocity=0,angle=0,angularVelocity=0)],
                'loadStates':[dict(id='load',force=vec,torque=vec,moment=vec,power=0)],
                'forces':[dict(id='spring',length=0,extension=0,rate=0,force=0)],
                'sliders':[dict(id='slider',position=0,velocity=0,transverse=0,transverseVelocity=0,angle=0,angularVelocity=0)],
                'rotationalStates':[dict(id='rotation',angle=0,velocity=0,torque=0)],
                'actuationStates':[dict(id='torque',torque=0,power=0)],'jointForceStates':[dict(id='effort',force=0,power=0)],
                'loadPower':0,'appliedWork':0,'elasticEnergy':0,'dampingPower':0,'dissipatedEnergy':0,
                'actuationPower':0,'actuationWork':0,'jointForcePower':0,'jointForceWork':0}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'result.csv';spatial.write_csv(path,[sample])
            with path.open(newline='',encoding='utf8') as stream:headers=next(csv.reader(stream))
        self.assertEqual(len(headers)-19,spatial.element_csv_values_per_row(model))

    def test_repeated_joint_reactions_are_budgeted_for_every_body_row(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-revolute'))
        model['simulation']={'duration':1.,'step':.0001};other=copy.deepcopy(model['bodies'][0]);other['id']='other';model['bodies'].append(other)
        template=model['joints'][0];model['joints']=[{**copy.deepcopy(template),'id':f'joint{i}'} for i in range(13)]
        self.assertTrue(spatial.validate(model)['valid'])
        model['joints'].append({**copy.deepcopy(template),'id':'joint13'})
        check=spatial.validate(model);self.assertFalse(check['valid']);self.assertTrue(any('joint-reaction CSV output' in issue['message'] for issue in check['issues']))

    def test_actual_extra_native_samples_cannot_exceed_output_budget(self):
        model=copy.deepcopy(next(item['model'] for item in spatial.EXAMPLES if item['id']=='spatial-revolute'))
        model['simulation']={'duration':.1,'step':.0001};template=model['joints'][0]
        model['joints']=[{**copy.deepcopy(template),'id':f'joint{i}'} for i in range(32)]
        self.assertTrue(spatial.validate(model)['valid'])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);count=8401
            (path/'result.log').write_text('structural node: 1 0 0 0 euler123 0 0 0\n',encoding='utf8')
            (path/'result.out').write_text(''.join(f'Step {i} {i*.1/(count-1):.15g} .0001 1 0 0 0 1\n' for i in range(count)),encoding='utf8')
            (path/'result.mov').write_text('1 0 0 0 0 0 0 0 0 0 0 0 0\n'*count,encoding='utf8')
            with self.assertRaisesRegex(ValueError,'Actual native output exceeds'):spatial.parse_output(path,model)


if __name__=='__main__':unittest.main()
