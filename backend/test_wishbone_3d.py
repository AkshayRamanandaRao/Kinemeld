"""STEP-backed wishbone example integrity and physical property checks."""
import base64,copy,hashlib,importlib.util,json,unittest
from pathlib import Path
import spatial_assembly

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'examples/wishbone-3d'

class WishboneExampleTests(unittest.TestCase):
    def setUp(self):self.project=json.loads((DIR/'wishbone.mbdyn-studio').read_text(encoding='utf8'))

    def test_topology_step_sources_and_bindings(self):
        model=self.project['model'];asset=self.project['assets']['step']
        self.assertTrue(spatial_assembly.validate(model)['valid']);self.assertEqual(len(model['bodies']),3);self.assertEqual(len(model['joints']),4)
        self.assertEqual({j['type'] for j in model['joints']},{'revolute','spherical'})
        self.assertEqual(len(asset['files']),3)
        for i,body in enumerate(model['bodies']):
            item=asset['files'][i];data=(DIR/item['name']).read_bytes();self.assertEqual(base64.b64decode(item['data'],validate=True),data);self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256']);self.assertEqual(asset['bindings'][f'{i}:part-1'],{'body':body['id'],'pose':body['pose']})

    @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP runtime is required')
    def test_masses_and_inertias_match_the_actual_step_solids(self):
        import step_mass
        for body,item,density in zip(self.project['model']['bodies'],self.project['assets']['step']['files'],(2700.,2700.,7800.)):
            result=step_mass.calculate((DIR/item['name']).read_bytes(),density,'part-1');self.assertAlmostEqual(result['mass'],body['mass'],places=7)
            for axis in ('x','y','z'):self.assertAlmostEqual(result['centerOfMass'][axis],body['pose'][axis]+body['centerOfMass'][axis],places=7)
            for i,key in enumerate(('xx','yy','zz')):self.assertAlmostEqual(result['inertia'][i][i],body['inertia'][key],places=7)
            for i,j,key in ((0,1,'xy'),(0,2,'xz'),(1,2,'yz')):self.assertAlmostEqual(result['inertia'][i][j],body['inertia'][key],places=7)
if __name__=='__main__':unittest.main()
