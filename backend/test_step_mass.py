"""Real STEP occurrence volume and inertia, including API boundary behavior."""
import base64
import http.client
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
import step_mass
import step_geometry
from server import Handler
import test_step_geometry
HAS_OCP = test_step_geometry.HAS_OCP

if HAS_OCP:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec


@unittest.skipUnless(HAS_OCP,"OCP is not installed")
class StepMassTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_step_geometry.StepGeometryTest.setUpClass()
        cls.assembly=test_step_geometry.StepGeometryTest.data;cls.inch=test_step_geometry.StepGeometryTest.inch_data
        cls.assembly_witnesses=[part['occurrenceWitness'] for part in step_geometry.convert_step(cls.assembly)['parts']]
        cls.inch_witnesses=[part['occurrenceWitness'] for part in step_geometry.convert_step(cls.inch)['parts']]
        document=TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF")); tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
        root=tool.NewShape();solid=tool.AddShape(BRepPrimAPI_MakeBox(100.,20.,10.).Shape(),False)
        angle=.63;tr=gp_Trsf();tr.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,0,1)),angle);tr.SetTranslationPart(gp_Vec(400,100,200))
        tool.AddComponent(root,solid,TopLoc_Location(tr));tool.UpdateAssemblies()
        cls.rotated=cls.write(document)
        face_doc=TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        XCAFDoc_DocumentTool.ShapeTool_s(face_doc.Main()).AddShape(BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0,0,0),gp_Dir(0,0,1)),0,100,0,50).Face(),False)
        cls.face=cls.write(face_doc)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()

    @staticmethod
    def write(doc):
        writer=STEPCAFControl_Writer();assert writer.Transfer(doc)
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'fixture.step';assert writer.Write(str(target))==IFSelect_RetDone
            return target.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def test_box_si_units_and_occurrence_selection(self):
        one=step_mass.calculate(self.assembly,1000,'part-1',self.assembly_witnesses[0]);two=step_mass.calculate(self.assembly,1000,'part-2',self.assembly_witnesses[1])
        self.assertAlmostEqual(one['volume'],2e-5,places=12);self.assertAlmostEqual(one['mass'],.02,places=12)
        for actual,expected in zip(one['centerOfMass'].values(),(.15,.01,.005)):self.assertAlmostEqual(actual,expected,places=9)
        for actual,expected in zip(two['centerOfMass'].values(),(.305,.01,-.05)):self.assertAlmostEqual(actual,expected,places=9)
        self.assertAlmostEqual(two['inertia'][0][0],one['inertia'][2][2],places=12)
        self.assertAlmostEqual(two['inertia'][2][2],one['inertia'][0][0],places=12)
        inch=step_mass.calculate(self.inch,1000,'part-2',self.inch_witnesses[1])
        self.assertTrue(any('inch' in unit.lower() for unit in inch['sourceLengthUnits']))
        for key in ('x','y','z'):self.assertAlmostEqual(inch['centerOfMass'][key],two['centerOfMass'][key],places=8)
        for i in range(3):
            for j in range(3):self.assertAlmostEqual(inch['inertia'][i][j],two['inertia'][i][j],places=11)

    def test_oblique_rotation_and_full_tensor_about_com(self):
        data=step_mass.calculate(self.rotated,1000,'part-1');c=math.cos(.63);s=math.sin(.63)
        expect=(.4+c*.05-s*.01,.1+s*.05+c*.01,.205)
        for actual,want in zip(data['centerOfMass'].values(),expect):self.assertAlmostEqual(actual,want,places=9)
        mass=.02;ix=mass*(.02**2+.01**2)/12;iy=mass*(.1**2+.01**2)/12;iz=mass*(.1**2+.02**2)/12
        self.assertAlmostEqual(data['inertia'][0][0],c*c*ix+s*s*iy,places=11)
        self.assertAlmostEqual(data['inertia'][0][1],c*s*(ix-iy),places=11)
        self.assertAlmostEqual(data['inertia'][1][0],data['inertia'][0][1],places=12)
        self.assertAlmostEqual(data['inertia'][2][2],iz,places=11)

    def test_open_surface_and_bad_input_rejected(self):
        with self.assertRaisesRegex(step_mass.StepMassError,'non-solid'):step_mass.calculate(self.face,1000,'part-1')
        for data,density,part in ((b'bad',1000,'part-1'),(self.assembly,0,'part-1'),(self.assembly,float('nan'),'part-1'),(self.assembly,1000,'part-0'),(self.assembly,1000,'part-3')):
            with self.assertRaises(step_mass.StepMassError):step_mass.calculate(data,density,part)

    def test_mass_selection_requires_unique_matching_occurrence(self):
        first,second=self.assembly_witnesses
        self.assertIsNotNone(first);self.assertIsNotNone(second);self.assertNotEqual(first,second)
        self.assertEqual(step_mass.calculate(self.assembly,1000,'part-1',first)['occurrenceWitness'],first)
        with self.assertRaisesRegex(step_mass.StepMassError,'identity'):
            step_mass.calculate(self.assembly,1000,'part-1')
        with self.assertRaisesRegex(step_mass.StepMassError,'does not match'):
            step_mass.calculate(self.assembly,1000,'part-1',second)
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'assembly.step';source.write_bytes(self.assembly)
            from unittest.mock import patch
            with patch.object(step_geometry,'source_occurrence_ids',return_value={}):
                with self.assertRaisesRegex(step_mass.StepMassError,'ambiguous'):
                    step_mass._worker(source,'part-1',1000,first)
                source.write_bytes(self.rotated)
                with self.assertRaisesRegex(step_mass.StepMassError,'ambiguous'):
                    step_mass._worker(source,'part-1',1000)

    def test_http_content_density_selection_and_origin(self):
        def call(headers,data=None):
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=100)
            connection.request('POST','/api/step/mass',body=data or self.assembly,headers=headers)
            response=connection.getresponse();result=(response.status,json.loads(response.read()));connection.close();return result
        witness=base64.b64encode(json.dumps(self.assembly_witnesses[1]).encode()).decode()
        headers={'Content-Type':'application/step','X-Step-Density':'1000','X-Step-Part':'part-2','X-Step-Witness':witness}
        status,result=call(headers);self.assertEqual(status,200);self.assertTrue(result['ok']);self.assertAlmostEqual(result['mass'],.02,places=10)
        self.assertEqual(result['occurrenceWitness'],self.assembly_witnesses[1])
        self.assertEqual(call({**headers,'X-Step-Witness':'%%%bad'})[0],422)
        self.assertEqual(call({key:value for key,value in headers.items() if key!='X-Step-Witness'})[0],422)
        self.assertEqual(call({**headers,'X-Step-Density':'nan'})[0],422)
        self.assertEqual(call({'Content-Type':'application/step'})[0],422)
        self.assertEqual(call({**headers,'Content-Type':'text/plain'})[0],415)
        self.assertEqual(call({**headers,'Origin':'https://example.com'})[0],403)

if __name__=='__main__':unittest.main()
