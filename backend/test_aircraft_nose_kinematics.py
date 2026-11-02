"""Validate traceable source geometry and the explicitly inferred linkage."""
import base64,hashlib,importlib.util,json,math,unittest
from pathlib import Path
import spatial_assembly as spatial

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'examples/open-aircraft-nose-gear/source-assembly.step'
PROJECT=ROOT/'examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio'
SHA='b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575'
SHIFT={'x':1.3624089479151387,'y':.1404889931316861,'z':.6763863684055106}
GROUPS={'strut':[3],'slider':[1,2,5],'upper_link':[4,7],'lower_link':[6,8,9],'left_wheel':[10],'right_wheel':[11]}

class NoseGearKinematicsTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.project=json.loads(PROJECT.read_text(encoding='utf8'))
 def test_source_bytes_poses_and_display_name(self):
  p=self.project;model=p['model'];asset=p['assets']['step'];data=SOURCE.read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),SHA);self.assertEqual(base64.b64decode(asset['files'][0]['data'],validate=True),data)
  self.assertEqual(model['name'],'Aircraft nose-gear kinematics');self.assertNotRegex(model['name'],r'KINEMATIC ONLY|loads invalid|source overlaps');self.assertEqual(model['parameters']['gravity'],dict.fromkeys('xyz',0));self.assertTrue(spatial.validate(model)['valid'])
  for body in model['bodies']:
   for i in GROUPS[body['id']]:
    binding=asset['bindings'][f'0:part-{i}'];self.assertEqual(binding['body'],body['id'])
    for axis in 'xyz':self.assertAlmostEqual(binding['pose'][axis]-body['pose'][axis],SHIFT[axis],places=12)
  self.assertEqual(len(asset['bindings']),11)
 def test_joint_types_motion_and_analytic_linkage_branch(self):
  from verify_aircraft_nose_kinematics import independent_scissor
  model=self.project['model'];joints={j['id']:j for j in model['joints']};self.assertEqual([j['type'] for j in model['joints']],['weld','prismatic','revolute','spherical','universal','revolute','revolute'])
  self.assertEqual(joints['oleo']['motion'],{'amplitude':.005,'frequencyHz':1});bodies={b['id']:b for b in model['bodies']}
  for joint in model['joints']:
   state=spatial.joint_state(joint,bodies.get(joint['a']),bodies[joint['b']]);self.assertLess(state['positionError'],1e-9)
  point=independent_scissor(model,0);upper=bodies['upper_link']['pose'];offset=joints['scissor_pin']['anchorA'];self.assertLess(math.dist(point,[upper['y']+offset['y'],upper['z']+offset['z']]),1e-12)
  self.assertTrue(all(math.isfinite(v) for v in independent_scissor(model,.01)))
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_assumed_material_properties_match_source_occurrences(self):
  import step_mass
  data=SOURCE.read_bytes();parts=[step_mass.calculate(data,2700.,f'part-{i}',self.project['assets']['step']['occurrenceWitnesses'][f'0:part-{i}']) for i in (1,2,5)]
  slider=next(b for b in self.project['model']['bodies'] if b['id']=='slider');self.assertAlmostEqual(slider['mass'],sum(p['mass'] for p in parts),places=8)
  for axis in 'xyz':
   center=sum(p['mass']*p['centerOfMass'][axis] for p in parts)/slider['mass']-SHIFT[axis]-slider['pose'][axis]
   self.assertAlmostEqual(slider['centerOfMass'][axis],center,places=8)
 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_selected_pin_lines_are_observed_in_source_bores(self):
  from OCP.STEPCAFControl import STEPCAFControl_Reader
  from OCP.Interface import Interface_Static
  from OCP.TCollection import TCollection_ExtendedString
  from OCP.TDocStd import TDocStd_Document
  from OCP.TDF import TDF_Label
  from ocp_compat import TDF_LabelSequence
  from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
  from OCP.TopLoc import TopLoc_Location
  from OCP.TopExp import TopExp_Explorer
  from OCP.TopAbs import TopAbs_FACE
  from OCP.TopoDS import TopoDS
  from OCP.BRepAdaptor import BRepAdaptor_Surface
  from OCP.GeomAbs import GeomAbs_Cylinder
  reader=STEPCAFControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE)),1);Interface_Static.SetCVal_s('xstep.cascade.unit','MM');document=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'));self.assertTrue(reader.Transfer(document));tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main());roots=TDF_LabelSequence();tool.GetFreeShapes(roots);parts=[]
  def visit(label,parent):
   referred=TDF_Label();reference=XCAFDoc_ShapeTool.GetReferredShape_s(label,referred);target=referred if reference else label;location=parent.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label)) if reference else parent
   if XCAFDoc_ShapeTool.IsAssembly_s(target):
    children=TDF_LabelSequence();XCAFDoc_ShapeTool.GetComponents_s(target,children)
    for i in range(1,children.Length()+1):visit(children.Value(i),location)
   else:parts.append(XCAFDoc_ShapeTool.GetShape_s(target).Moved(location))
  for i in range(1,roots.Length()+1):visit(roots.Value(i),TopLoc_Location())
  model=self.project['model'];body={b['id']:b for b in model['bodies']};joints={j['id']:j for j in model['joints']}
  for ident,indices in [('upper_pin',(3,4)),('scissor_pin',(4,6)),('lower_pin',(5,6))]:
   joint=joints[ident];origin=spatial.anchor(body.get(joint['a']),joint['anchorA']);y,z=(1000*(origin[n]+SHIFT[axis]) for n,axis in ((1,'y'),(2,'z')))
   for index in indices:
    found=False;explorer=TopExp_Explorer(parts[index-1],TopAbs_FACE)
    while explorer.More():
     surface=BRepAdaptor_Surface(TopoDS.Face(explorer.Current()))
     if surface.GetType()==GeomAbs_Cylinder:
      cylinder=surface.Cylinder();p=cylinder.Location();direction=cylinder.Axis().Direction()
      if abs(cylinder.Radius()-7.5)<1e-3 and abs(abs(direction.X())-1)<1e-6 and abs(p.Y()-y)<1e-3 and abs(p.Z()-z)<1e-3:found=True
     explorer.Next()
    self.assertTrue(found,f'{ident} missing 7.5 mm bore line in occurrence {index}')

if __name__=='__main__':unittest.main()
