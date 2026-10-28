"""STEP integrity and geometry-derived mass properties of the illustrative gear."""
import base64,hashlib,importlib.util,json,math,unittest
from pathlib import Path
import spatial_assembly as spatial
ROOT=Path(__file__).resolve().parents[1];DIR=ROOT/'examples/landing-gear-3d'

class LandingGearExampleTests(unittest.TestCase):
 def setUp(self):self.project=json.loads((DIR/'landing-gear-drop.mbdyn-studio').read_text(encoding='utf8'))
 def test_topology_assets_and_bindings(self):
  model=self.project['model'];asset=self.project['assets']['step'];self.assertTrue(spatial.validate(model)['valid']);self.assertEqual(len(model['bodies']),2);self.assertEqual(len(model['joints']),1);self.assertEqual(model['joints'][0]['type'],'prismatic');self.assertEqual(len(model['contacts']),1)
  for i,body in enumerate(model['bodies']):
   item=asset['files'][i];data=(DIR/item['name']).read_bytes();self.assertEqual(base64.b64decode(item['data'],validate=True),data);self.assertEqual(hashlib.sha256(data).hexdigest(),item['sha256']);self.assertEqual(asset['bindings'][f'{i}:part-1'],{'body':body['id'],'pose':body['pose']})
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP runtime is required')
 def test_step_mass_center_and_rotated_full_inertia(self):
  import step_mass
  densities=(100/(math.pi*.09**2*1.1),5/(math.pi*.15**2*.1))
  for body,item,density in zip(self.project['model']['bodies'],self.project['assets']['step']['files'],densities):
   actual=step_mass.calculate((DIR/item['name']).read_bytes(),density,'part-1');self.assertAlmostEqual(actual['mass'],body['mass'],places=7)
   rotation=spatial.body_rotation(body);center=spatial.mul(rotation,spatial.xyz(body['centerOfMass']))
   for i,axis in enumerate(('x','y','z')):self.assertAlmostEqual(actual['centerOfMass'][axis],body['pose'][axis]+center[i],places=7)
   tensor=spatial.matmul(spatial.matmul(rotation,spatial.inertia_matrix(body['inertia'])),spatial.transpose(rotation))
   for i in range(3):
    for j in range(3):self.assertAlmostEqual(actual['inertia'][i][j],tensor[i][j],places=7)
if __name__=='__main__':unittest.main()
