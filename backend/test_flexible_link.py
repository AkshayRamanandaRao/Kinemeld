import copy,csv,math,tempfile,unittest
from pathlib import Path
import flexible_link as fl


class FlexibleLinkTests(unittest.TestCase):
    def test_defaults_and_explicit_mesh_choices(self):
        self.assertTrue(fl.validate(fl.DEFAULT)['valid'])
        for nodes in (3,5,9):
            model=copy.deepcopy(fl.DEFAULT);model['parameters']['nodes']=nodes
            self.assertTrue(fl.validate(model)['valid']);self.assertEqual(fl.deck(model).count(' beam3:'),(nodes-1)//2)
        for value in (True,4,7,5.1,10,float('nan')):
            model=copy.deepcopy(fl.DEFAULT);model['parameters']['nodes']=value
            with self.subTest(value=value):self.assertFalse(fl.validate(model)['valid'])

    def test_mass_quadrature_preserves_total_mass_and_second_moment(self):
        for nodes in (3,5,9):
            model=copy.deepcopy(fl.DEFAULT);model['parameters']['nodes']=nodes;L=model['parameters']['length'];weights=fl.nodal_weights(model)
            self.assertAlmostEqual(sum(weights),L);self.assertAlmostEqual(sum(w*(L*i/(nodes-1))**2 for i,w in enumerate(weights)),L**3/3)
            self.assertTrue(all(w>0 for w in weights))

    def test_physical_and_resource_boundaries(self):
        for field,value in [('linearDensity',0),('bendingStiffness',0),('rotaryInertia',0),('tipLoad',100),('rampTime',.001),('dampingTime',-1)]:
            model=copy.deepcopy(fl.DEFAULT);model['parameters'][field]=value
            with self.subTest(field=field):self.assertFalse(fl.validate(model)['valid'])
        model=copy.deepcopy(fl.DEFAULT);model['simulation'].update(duration=30.,step=.0001)
        self.assertTrue(any('node-steps' in issue['message'] for issue in fl.validate(model)['issues']))
        model=copy.deepcopy(fl.DEFAULT);model['parameters']['extra']=1
        self.assertFalse(fl.validate(model)['valid'])

    def test_load_is_smooth_and_stops_ramping(self):
        model=fl.DEFAULT;p=model['parameters'];self.assertEqual(fl.load(model,0),0.)
        self.assertAlmostEqual(fl.load(model,p['rampTime']/2),p['tipLoad']/2)
        self.assertEqual(fl.load(model,p['rampTime']),p['tipLoad']);self.assertEqual(fl.load(model,100),p['tipLoad'])
        deck=fl.deck(model);self.assertIn('linear viscoelastic generic, diag, 200000,50000,50000,5,5,5, proportional, 0.02',deck)
        self.assertIn('method: ms, 0.6;',deck);self.assertNotIn('prescribed',deck)

    def fixture(self,directory):
        model=copy.deepcopy(fl.DEFAULT);model['parameters']['nodes']=3;model['simulation']={'duration':.01,'step':.001};N=3
        directory.joinpath('solver.log').write_text('MBDyn terminated normally\n')
        directory.joinpath('result.log').write_text(''.join(f'structural node: {i} 0 0 0 euler123\n' for i in range(1,N+1))+'beam3: 1 1 0 0 0 2 0 0 0 3 0 0 0\n')
        directory.joinpath('result.out').write_text(''.join(f'Step {i} {i*.001:g} 0 0 0 0 0 1\n' for i in range(11)))
        directory.joinpath('result.mov').write_text(''.join(str(i)+' '+' '.join(map(str,[.25*(i-1),0,0,*([0.]*9)]))+'\n' for _ in range(11) for i in range(1,N+1)))
        directory.joinpath('result.act').write_text(('1 '+' '.join(['0']*12)+'\n')*11)
        directory.joinpath('result.jnt').write_text(('1 '+' '.join(['0']*12)+'\n')*11)
        return model

    def test_complete_native_mesh_and_force_frames_are_required(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);model=self.fixture(directory);samples=fl.parse_output(directory,model)
            self.assertEqual([n['id'] for n in samples[0]['nodes']],['flex1','flex2','flex3'])
            self.assertEqual(len(samples),11)
            for name,replacement in [('result.act','1 0 0\n'),('result.jnt',''),('result.log',''),('solver.log','stopped early')]:
                previous=(directory/name).read_text();(directory/name).write_text(replacement)
                with self.subTest(name=name):self.assertRaises(ValueError,fl.parse_output,directory,model)
                (directory/name).write_text(previous)
            text=(directory/'result.act').read_text();(directory/'result.act').write_text(text.replace('0','nan',1));self.assertRaises(ValueError,fl.parse_output,directory,model)

    def test_full_csv_writes_every_native_node_and_physical_scalar(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder);model=self.fixture(directory);samples=fl.parse_output(directory,model);path=directory/'results.csv';fl.write_csv(path,samples)
            with path.open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),33);self.assertEqual(rows[2]['id'],'flex3');self.assertIn('rootMoment_Nm',rows[0]);self.assertIn('tipSlope_rad',rows[0])


if __name__=='__main__':unittest.main()
