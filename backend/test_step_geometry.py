"""STEP tests generate a real multi-occurrence OCCT document; no downloaded asset needed."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import step_geometry

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@unittest.skipUnless(HAS_OCP, "OCP is not installed")
class StepGeometryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
        tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        root = tool.NewShape()
        TDataStd_Name.Set_s(root, TCollection_ExtendedString("Axle assembly"))
        part = tool.AddShape(BRepPrimAPI_MakeBox(100., 20., 10.).Shape(), False)
        TDataStd_Name.Set_s(part, TCollection_ExtendedString("Arm"))
        for i, x in enumerate((100., 300.)):
            transform = gp_Trsf()
            if i:
                transform.SetRotation(gp_Ax1(gp_Pnt(0,0,0),gp_Dir(0,1,0)), math.pi / 2)
                transform.SetTranslationPart(gp_Vec(x, 0., 0.))
            else:
                transform.SetTranslation(gp_Vec(x, 0., 0.))
            occurrence = tool.AddComponent(root, part, TopLoc_Location(transform))
            TDataStd_Name.Set_s(occurrence, TCollection_ExtendedString(f"Arm {i+1}"))
        tool.UpdateAssemblies()
        writer = STEPCAFControl_Writer()
        assert writer.Transfer(doc)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "assembly.step"
            assert writer.Write(str(output)) == IFSelect_RetDone
            cls.data = output.read_bytes()
            Interface_Static.SetCVal_s("write.step.unit", "INCH")
            try:
                inch_writer = STEPCAFControl_Writer()
                assert inch_writer.Transfer(doc)
                inch_output = Path(tmp) / "assembly-inch.step"
                assert inch_writer.Write(str(inch_output)) == IFSelect_RetDone
                cls.inch_data = inch_output.read_bytes()
            finally:
                Interface_Static.SetCVal_s("write.step.unit", "MM")

    def test_real_repeated_occurrences_preserve_positions_and_units(self):
        self.assertTrue(step_geometry.status()["available"])
        result = step_geometry.convert_step(self.data, "assembly.step")
        self.assertEqual(result["units"], "m")
        self.assertEqual(result["byteLength"], len(self.data))
        self.assertEqual(len(result["parts"]), 2)
        self.assertEqual([part["name"] for part in result["parts"]], ["Arm 1", "Arm 2"])
        self.assertTrue(all(part["path"][0] == "Axle assembly" for part in result["parts"]))
        intervals = [(min(p["positions"][0::3]), max(p["positions"][0::3])) for p in result["parts"]]
        for got,want in zip(intervals,[(.1,.2),(.3,.31)]):
            for a,b in zip(got,want): self.assertAlmostEqual(a,b,places=7)
        zs = result["parts"][1]["positions"][2::3]
        self.assertAlmostEqual(min(zs), -.1, places=7)
        self.assertAlmostEqual(max(zs), 0., places=7)
        self.assertGreater(result["triangleCount"],0)
        self.assertTrue(all(len(p["indices"]) % 3 == 0 for p in result["parts"]))

    def test_faces_report_plane_geometry_in_assembly_coordinates(self):
        result = step_geometry.convert_step(self.data, "assembly.step")
        for part in result["parts"]:
            faces = part["faces"]
            self.assertEqual(len(faces), 6)
            self.assertEqual(sum(face["triangles"][1] for face in faces), len(part["indices"]) // 3)
            self.assertTrue(all(face["type"] == "plane" for face in faces))
        first, second = (part["faces"] for part in result["parts"])
        # The first box spans x = 0.1..0.2 m; its +x face lies at x = 0.2 m.
        end = next(face for face in first if face["normal"] == [1.0, 0.0, 0.0])
        self.assertAlmostEqual(end["point"][0], .2, places=9)
        # The second occurrence is turned 90° about y, so its part +x face points along world -z.
        self.assertTrue(any(face["normal"] == [0.0, 0.0, -1.0] for face in second))

    def test_cylinder_faces_report_axis_centre_radius_and_length(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
        from OCP.gp import gp_Ax2
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
        shaft = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(10., 20., 30.), gp_Dir(0, 1, 0)), 5., 40.).Shape()
        writer = STEPControl_Writer()
        writer.Transfer(shaft, STEPControl_AsIs)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shaft.step"
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            part = step_geometry.convert_step(path.read_bytes(), "shaft.step")["parts"][0]
        cylinder = next(face for face in part["faces"] if face["type"] == "cylinder")
        self.assertAlmostEqual(cylinder["radius"], .005, places=9)
        self.assertAlmostEqual(cylinder["length"], .04, places=9)
        self.assertEqual([abs(value) for value in cylinder["axis"]], [0.0, 1.0, 0.0])
        for got, want in zip(cylinder["centre"], (.01, .04, .03)):
            self.assertAlmostEqual(got, want, places=9)
        caps = [face for face in part["faces"] if face["type"] == "plane"]
        self.assertEqual(sorted(face["normal"][1] for face in caps), [-1.0, 1.0])
        # Both end rims are reported once as full circles on the axis; the boxes have none.
        rims = part["edges"]
        self.assertEqual(len(rims), 2)
        self.assertTrue(all(rim["type"] == "circle" and abs(rim["radius"] - .005) < 1e-9 for rim in rims))
        self.assertEqual(sorted(round(rim["centre"][1], 9) for rim in rims), [.02, .06])
        self.assertTrue(all([abs(value) for value in rim["axis"]] == [0.0, 1.0, 0.0] for rim in rims))
        self.assertEqual([part["edges"] for part in step_geometry.convert_step(self.data, "assembly.step")["parts"]], [[], []])

    def test_rims_written_as_arcs_are_merged(self):
        # Each hole rim of the nose-gear strut is written as two half arcs.
        data = (Path(__file__).resolve().parents[1] / "examples/open-aircraft-nose-gear/parts/03-strut.step").read_bytes()
        rims = step_geometry.convert_step(data, "03-strut.step")["parts"][0]["edges"]
        holes = {(round(rim["centre"][0], 6), round(rim["centre"][1], 6)) for rim in rims if abs(rim["radius"] - .0075) < 1e-9}
        # Both faces of each torque-link lug, on the pin axis 616 mm up.
        self.assertTrue({(-.01, -.07), (-.01, .07), (.01, -.07), (.01, .07)} <= holes, holes)
        self.assertTrue(all(abs(abs(rim["axis"][0]) - 1) < 1e-9 for rim in rims if abs(rim["radius"] - .0075) < 1e-9))
        self.assertEqual(len({tuple(rim["centre"]) + (rim["radius"],) for rim in rims}), len(rims))

    def test_inch_source_is_converted_to_same_metre_geometry(self):
        result = step_geometry.convert_step(self.inch_data, "inch.step")
        self.assertTrue(any("inch" in unit.lower() for unit in result["sourceLengthUnits"]))
        xs = result["parts"][0]["positions"][0::3]
        self.assertAlmostEqual(min(xs), .1, places=6)
        self.assertAlmostEqual(max(xs), .2, places=6)

    def test_missing_cad_dependency_is_actionable(self):
        with patch.object(step_geometry.subprocess, "run", side_effect=OSError("unavailable")):
            result = step_geometry.status()
        self.assertFalse(result["available"])
        self.assertIn("OCP", result["detail"])

    def test_bad_file_and_limits_rejected_before_native_import(self):
        for bad in (b"", b"not a step"):
            with self.assertRaises(step_geometry.StepError): step_geometry.convert_step(bad)
        with patch.object(step_geometry, "MAX_STEP_BYTES", 4):
            with self.assertRaises(step_geometry.StepError): step_geometry.convert_step(self.data)
        with self.assertRaises(step_geometry.StepError): step_geometry.convert_step(self.data, "")

if __name__ == "__main__": unittest.main()
