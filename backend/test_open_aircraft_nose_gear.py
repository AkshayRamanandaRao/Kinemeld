"""Check the pinned nose-gear source and its imported occurrence identities."""
import hashlib
import importlib.util
import re
import unittest
from pathlib import Path

import step_geometry

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'examples/open-aircraft-nose-gear/source-assembly.step'
SHA='b53205b3356f9b98b0edf6d2ba4f8b04f46cc61607cad263857192c1aeb7a575'
NAMES=['Piston','Shaft','Strut','Upper Link','Wheel Hub','Lower Link','flange bolt_M12-1.75 x 45','flange bolt_M12-1.75 x 90','flange bolt_M12-1.75 x 75','Wheel','Wheel']

class OpenNoseGearTest(unittest.TestCase):
 def test_source_hash_and_step_occurrence_product_mapping(self):
  data=SOURCE.read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),SHA)
  text=data.decode('ascii');entities=dict(re.findall(r'#(\d+)\s*=\s*(.*?);',text,re.S))
  found={}
  for entity in entities.values():
   match=re.match(r"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*'NAUO(\d+)'\s*,.*?#\d+\s*,\s*#(\d+)",entity,re.S)
   if match:
    definition=entities[match.group(2)];formation=entities[re.search(r'#(\d+)',definition).group(1)];product=entities[re.search(r'#(\d+)',formation).group(1)]
    found[int(match.group(1))]=re.search(r"PRODUCT\s*\(\s*'([^']+)'",product).group(1)
  self.assertEqual([found[i] for i in range(1,12)],NAMES)

 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_original_assembly_import(self):
  converted=step_geometry.convert_step(SOURCE.read_bytes(),SOURCE.name)
  self.assertIn('millimetre',[unit.lower() for unit in converted['sourceLengthUnits']]);self.assertEqual(len(converted['parts']),11)
  self.assertEqual([part['name'] for part in converted['parts']],[f'NAUO{i}' for i in range(1,12)])
  self.assertEqual([part['productName'] for part in converted['parts']],NAMES)
  self.assertGreater(converted['triangleCount'],10000)
  for wheel in converted['parts'][9:]:
   p=wheel['positions'];self.assertAlmostEqual(max(p[0::3])-min(p[0::3]),.1,places=3);self.assertAlmostEqual(max(p[2::3])-min(p[2::3]),.3,places=3)

 @unittest.skipUnless(importlib.util.find_spec('OCP'),'OpenCascade OCP required')
 def test_documented_initial_intersections(self):
  from OCP.STEPCAFControl import STEPCAFControl_Reader
  from OCP.Interface import Interface_Static
  from OCP.TCollection import TCollection_ExtendedString
  from OCP.TDocStd import TDocStd_Document
  from OCP.TDF import TDF_Label
  from ocp_compat import TDF_LabelSequence
  from OCP.XCAFDoc import XCAFDoc_DocumentTool,XCAFDoc_ShapeTool
  from OCP.TopLoc import TopLoc_Location
  from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
  from OCP.BRepGProp import BRepGProp
  from OCP.GProp import GProp_GProps
  reader=STEPCAFControl_Reader();self.assertEqual(reader.ReadFile(str(SOURCE)),1);Interface_Static.SetCVal_s('xstep.cascade.unit','MM')
  document=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'));self.assertTrue(reader.Transfer(document));tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main());roots=TDF_LabelSequence();tool.GetFreeShapes(roots);parts=[]
  def visit(label,parent):
   referred=TDF_Label();reference=XCAFDoc_ShapeTool.GetReferredShape_s(label,referred);target=referred if reference else label;location=parent.Multiplied(XCAFDoc_ShapeTool.GetLocation_s(label)) if reference else parent
   if XCAFDoc_ShapeTool.IsAssembly_s(target):
    children=TDF_LabelSequence();XCAFDoc_ShapeTool.GetComponents_s(target,children)
    for i in range(1,children.Length()+1):visit(children.Value(i),location)
   else:parts.append(XCAFDoc_ShapeTool.GetShape_s(target).Moved(location))
  for i in range(1,roots.Length()+1):visit(roots.Value(i),TopLoc_Location())
  self.assertEqual(len(parts),11)
  for i,j,expected in [(1,3,9199.426),(3,4,373.706),(4,6,2874.620),(5,10,0.)]:
   with self.subTest(occurrences=(i,j)):
    common=BRepAlgoAPI_Common(parts[i-1],parts[j-1]);common.Build();self.assertTrue(common.IsDone());props=GProp_GProps();BRepGProp.VolumeProperties_s(common.Shape(),props);self.assertAlmostEqual(abs(props.Mass()),expected,delta=.1)

if __name__=='__main__':unittest.main()
