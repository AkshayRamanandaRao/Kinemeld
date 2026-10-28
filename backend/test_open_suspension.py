"""Verify the open suspension's original source bytes and rigid-body connections."""
import base64,hashlib,importlib.util,itertools,json,math,unittest
from pathlib import Path
import spatial_assembly as spatial
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'examples/open-suspension/suspension.mbdyn-studio'
SOURCE=ROOT/'examples/step-suspension'
FILES=[('Assembly 1 - Upper Control Arm_Default-As Machined-.step','0eb1a5b7fd865bfd6b74d8772abf8963841e9d916ad40964e716a65fdf8d7416'),('Assembly 1 - Lower Control Arm_Default-As Machined-.step','b2e09857d05a62b8e657c333da30d7cf65881601f64b22ea5478b033dc826b9e'),('Assembly 1 - Knuckle_Left Knuckle.step','670681b02f1923520f49d46eb6fe0166040eb43869283566f04fba7f2a4313b9'),('Assembly 1 - Hub.step','5a035846fcd27121ac5337484b4f5e791b5deb3349030faff4768eed0c0ffbdb'),('Assembly 1 - Front Tyre.step','a0b7e75748354b03547decf398d0257d79442c051c330956d208136fac7255d0')]
class OpenSuspensionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.project=json.loads(P.read_text(encoding='utf8'))
 def test_original_files_and_valid_loop(self):
  m=self.project['model'];asset=self.project['assets']['step'];self.assertTrue(spatial.validate(m)['valid']);self.assertEqual(len(asset['files']),5)
  self.assertEqual([j['type'] for j in m['joints']],['revolute','revolute','spherical','spherical','revolute'])
  for f,(name,digest) in zip(asset['files'],FILES):
   original=(SOURCE/name).read_bytes();self.assertEqual(hashlib.sha256(original).hexdigest(),digest);self.assertEqual(f['sha256'],digest);self.assertEqual(base64.b64decode(f['data'],validate=True),original)
  bodies={b['id']:b for b in m['bodies']}
  for joint in m['joints']:
   a=spatial.anchor(bodies.get(joint['a']),joint['anchorA']);b=spatial.anchor(bodies[joint['b']],joint['anchorB']);self.assertLess(math.dist(a,b),1e-12,joint['id'])
 def test_hub_alignment_is_the_checked_clearance_position(self):
  m=self.project['model'];knuckle=next(b for b in m['bodies'] if b['id']=='knuckle');wheel=next(b for b in m['bodies'] if b['id']=='wheel');joint=next(j for j in m['joints'] if j['id']=='hub_axis')
  for key,value in zip('xyz',(-.075,-.0875,-.0125)):self.assertAlmostEqual(joint['anchorA'][key],value)
  self.assertAlmostEqual(spatial.anchor(knuckle,joint['anchorA'])[0],-.04);self.assertAlmostEqual(wheel['pose']['x'],-.04)
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_initial_metal_parts_do_not_overlap(self):
  from OCP.STEPControl import STEPControl_Reader
  from OCP.Interface import Interface_Static
  from OCP.IFSelect import IFSelect_RetDone
  from OCP.gp import gp_Trsf
  from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
  from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
  from OCP.BRepGProp import BRepGProp
  from OCP.GProp import GProp_GProps
  Interface_Static.SetCVal_s('xstep.cascade.unit','MM')
  assets=self.project['assets']['step'];bodies={b['id']:b for b in self.project['model']['bodies']};shapes=[]
  for i,(name,_) in enumerate(FILES[:4]):
   reader=STEPControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE/name)),IFSelect_RetDone);reader.TransferRoots()
   bind=assets['bindings'][f'{i}:part-1'];body=bodies[bind['body']];R=spatial.body_rotation(body);origin=[bind['pose'][k] for k in 'xyz'];position=[body['pose'][k] for k in 'xyz']
   t=[1000*(position[j]-sum(R[j][k]*origin[k] for k in range(3))) for j in range(3)];transform=gp_Trsf();transform.SetValues(*[v for j in range(3) for v in (R[j][0],R[j][1],R[j][2],t[j])]);shapes.append(BRepBuilderAPI_Transform(reader.OneShape(),transform,True).Shape())
  for i,j in itertools.combinations(range(len(shapes)),2):
   common=BRepAlgoAPI_Common(shapes[i],shapes[j]);common.Build();self.assertTrue(common.IsDone());props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props);self.assertLess(abs(props.Mass()),1e-4,f'{FILES[i][0]} / {FILES[j][0]}')
if __name__=='__main__':unittest.main()
