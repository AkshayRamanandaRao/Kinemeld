"""Verify traceable source STEP and independently calculated wheel-end properties."""
import base64,hashlib,importlib.util,json,math,unittest
from pathlib import Path
import spatial_assembly
ROOT=Path(__file__).resolve().parents[1];PROJECT=ROOT/'examples/open-wheel-end/wheel-end.mbdyn-studio';SOURCE=ROOT/'examples/step-suspension'
FILES=[('Assembly 1 - Knuckle_Left Knuckle.step','670681b02f1923520f49d46eb6fe0166040eb43869283566f04fba7f2a4313b9'),('Assembly 1 - Hub.step','5a035846fcd27121ac5337484b4f5e791b5deb3349030faff4768eed0c0ffbdb'),('Assembly 1 - Front Tyre.step','a0b7e75748354b03547decf398d0257d79442c051c330956d208136fac7255d0')]
class OpenWheelTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.project=json.loads(PROJECT.read_text(encoding='utf8'))
 def test_exact_original_step_and_registration(self):
  model=self.project['model'];asset=self.project['assets']['step'];self.assertTrue(spatial_assembly.validate(model)['valid']);self.assertEqual(len(asset['files']),3)
  for item,(name,digest) in zip(asset['files'],FILES):
   data=(SOURCE/name).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),digest);self.assertEqual(item['sha256'],digest);self.assertEqual(base64.b64decode(item['data'],validate=True),data)
  self.assertEqual(asset['bindings']['0:part-1']['pose'],model['bodies'][0]['pose'])
  for index in (1,2):self.assertEqual(asset['bindings'][f'{index}:part-1']['pose'],{'x':0.,'y':0.,'z':0.,'rx':0.,'ry':0.,'rz':0.})
  self.assertEqual(model['joints'][1]['axisA'],{'x':1,'y':0,'z':0})
 def test_drop_keeps_original_cad_and_explicit_surrogate(self):
  drop=json.loads((ROOT/'examples/open-wheel-end/wheel-end-drop.mbdyn-studio').read_text(encoding='utf8'))
  self.assertEqual(drop['assets']['step'],self.project['assets']['step'])
  self.assertTrue(spatial_assembly.validate(drop['model'])['valid'])
  self.assertEqual([j['type'] for j in drop['model']['joints']],['revolute'])
  contact=drop['model']['contacts'][0]
  self.assertEqual((contact['radius'],contact['stiffness'],contact['damping']),(.208,20000.,100.))
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_inferred_hub_registration_has_no_solid_interference(self):
  from OCP.Interface import Interface_Static
  from OCP.STEPControl import STEPControl_Reader
  from OCP.IFSelect import IFSelect_RetDone
  from OCP.gp import gp_Trsf,gp_Vec
  from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
  from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
  from OCP.BRepGProp import BRepGProp
  from OCP.GProp import GProp_GProps
  Interface_Static.SetCVal_s('xstep.cascade.unit','MM')
  def read(name):
   reader=STEPControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE/name)),IFSelect_RetDone);reader.TransferRoots();return reader.OneShape()
  knuckle,hub=(read(FILES[i][0]) for i in (0,1));pose=self.project['model']['bodies'][1]['pose']
  transform=gp_Trsf();transform.SetTranslation(gp_Vec(pose['x']*1000,pose['y']*1000,pose['z']*1000))
  common=BRepAlgoAPI_Common(knuckle,BRepBuilderAPI_Transform(hub,transform,True).Shape());common.Build();self.assertTrue(common.IsDone())
  props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props);self.assertLess(abs(props.Mass()),1e-5)
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_tyre_optimal_bounds_match_contact_surrogate(self):
  from OCP.Interface import Interface_Static
  from OCP.STEPControl import STEPControl_Reader
  from OCP.IFSelect import IFSelect_RetDone
  from OCP.Bnd import Bnd_Box
  from OCP.BRepBndLib import BRepBndLib
  Interface_Static.SetCVal_s('xstep.cascade.unit','MM')
  reader=STEPControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE/FILES[2][0])),IFSelect_RetDone);reader.TransferRoots()
  box=Bnd_Box();BRepBndLib.AddOptimal_s(reader.OneShape(),box,False,False);xmin,ymin,zmin,xmax,ymax,zmax=box.Get()
  for extent in (abs(ymin),abs(ymax),abs(zmin),abs(zmax)):self.assertAlmostEqual(extent/1000,.208,places=5)
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_source_mass_and_composite_tensor(self):
  import step_mass
  calc=[step_mass.calculate((SOURCE/name).read_bytes(),density,'part-1') for (name,_),density in zip(FILES,(7850.,7850.,1100.))]
  model=self.project['model'];knuckle,wheel=model['bodies'];self.assertAlmostEqual(knuckle['mass'],calc[0]['mass'],places=8)
  mass=sum(p['mass'] for p in calc[1:]);center=[sum(p['mass']*p['centerOfMass'][axis] for p in calc[1:])/mass for axis in ('x','y','z')];self.assertAlmostEqual(wheel['mass'],mass,places=8)
  for k,axis in enumerate(('x','y','z')):self.assertAlmostEqual(wheel['centerOfMass'][axis],center[k],places=8)
  expected=[[0.]*3 for _ in range(3)]
  for p in calc[1:]:
   d=[p['centerOfMass'][axis]-center[i] for i,axis in enumerate(('x','y','z'))];rr=sum(x*x for x in d)
   for i in range(3):
    for j in range(3):expected[i][j]+=p['inertia'][i][j]+p['mass']*((rr if i==j else 0)-d[i]*d[j])
  actual=spatial_assembly.inertia_matrix(wheel['inertia'])
  for i in range(3):
   for j in range(3):self.assertAlmostEqual(actual[i][j],expected[i][j],places=8)
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_knuckle_20mm_cylindrical_feature_observed_in_original_step(self):
  from OCP.Interface import Interface_Static
  from OCP.STEPControl import STEPControl_Reader
  from OCP.IFSelect import IFSelect_RetDone
  from OCP.TopExp import TopExp_Explorer
  from OCP.TopAbs import TopAbs_FACE
  from OCP.TopoDS import TopoDS
  from OCP.BRepAdaptor import BRepAdaptor_Surface
  from OCP.GeomAbs import GeomAbs_Cylinder
  Interface_Static.SetCVal_s('xstep.cascade.unit','MM');reader=STEPControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE/FILES[0][0])),IFSelect_RetDone);reader.TransferRoots();it=TopExp_Explorer(reader.OneShape(),TopAbs_FACE);found=False
  while it.More():
   surface=BRepAdaptor_Surface(TopoDS.Face_s(it.Current()))
   if surface.GetType()==GeomAbs_Cylinder:
    cylinder=surface.Cylinder();p=cylinder.Location();a=cylinder.Axis().Direction()
    if abs(cylinder.Radius()/1000-.02)<1e-7 and abs(p.Y()/1000+.0875)<1e-7 and abs(p.Z()/1000)<1e-7 and abs(abs(a.X())-1)<1e-7:found=True
   it.Next()
  self.assertTrue(found,'The chosen feature axis is not present in the source geometry.')
if __name__=='__main__':unittest.main()
