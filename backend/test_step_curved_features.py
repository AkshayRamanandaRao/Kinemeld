"""Real conical/toroidal STEP features, including placed assembly occurrences."""
import math
from pathlib import Path
import sys
import tempfile
import unittest

import step_geometry

try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCone, BRepPrimAPI_MakeTorus
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


def write_fixture(path):
    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    root = tool.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString("Analytic feature assembly"))
    shapes = {
        "Cone": BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(10, 20, 30), gp_Dir(0, 1, 0)), 20., 10., 40.).Shape(),
        "Torus": BRepPrimAPI_MakeTorus(gp_Ax2(gp_Pnt(60, 40, 30), gp_Dir(1, 0, 0)), 30., 5.).Shape(),
    }
    for name, shape in shapes.items():
        part = tool.AddShape(shape, False)
        TDataStd_Name.Set_s(part, TCollection_ExtendedString(name))
        for placed in (False, True):
            transform = gp_Trsf()
            if placed:
                transform.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.pi / 2)
                transform.SetTranslationPart(gp_Vec(200, 100, -30))
            occurrence = tool.AddComponent(root, part, TopLoc_Location(transform))
            TDataStd_Name.Set_s(occurrence, TCollection_ExtendedString(f"{name} {'placed' if placed else 'original'}"))
    tool.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert writer.Transfer(doc)
    assert writer.Write(str(path)) == IFSelect_RetDone


@unittest.skipUnless(HAS_OCP, "OCP is not installed")
class CurvedFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cones-tori.step"
            write_fixture(path)
            cls.data = path.read_bytes()
            cls.parts = step_geometry.convert_step(cls.data, path.name)["parts"]

    def feature(self, part_name, kind):
        part = next(part for part in self.parts if part["name"] == part_name)
        self.assertTrue(part["occurrenceWitness"])
        self.assertEqual(sum(face["triangles"][1] for face in part["faces"]), len(part["indices"]) // 3)
        return next(face for face in part["faces"] if face["type"] == kind)

    def assertVector(self, value, expected):
        for actual, target in zip(value, expected):
            self.assertAlmostEqual(actual, target, places=8)

    def test_cone_apex_axis_and_angle_include_surface_and_occurrence_placements(self):
        original = self.feature("Cone original", "cone")
        placed = self.feature("Cone placed", "cone")
        self.assertVector(original["apex"], [.01, .1, .03])
        self.assertVector(original["axis"], [0, -1, 0])
        self.assertVector(placed["apex"], [.1, .11, 0])
        self.assertVector(placed["axis"], [1, 0, 0])
        self.assertAlmostEqual(original["semiAngle"], math.atan(.25), places=8)
        self.assertAlmostEqual(placed["semiAngle"], original["semiAngle"], places=10)

    def test_torus_centre_axis_and_both_radii_include_occurrence_placement(self):
        original = self.feature("Torus original", "torus")
        placed = self.feature("Torus placed", "torus")
        self.assertVector(original["centre"], [.06, .04, .03])
        self.assertVector(original["axis"], [1, 0, 0])
        self.assertVector(placed["centre"], [.16, .16, 0])
        self.assertVector(placed["axis"], [0, 1, 0])
        for face in (original, placed):
            self.assertAlmostEqual(face["majorRadius"], .03, places=9)
            self.assertAlmostEqual(face["minorRadius"], .005, places=9)

    def test_cone_widening_branch_has_axis_into_cone_and_virtual_apex(self):
        writer = STEPControl_Writer()
        writer.Transfer(BRepPrimAPI_MakeCone(10., 20., 40.).Shape(), STEPControl_AsIs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widening-cone.step"
            self.assertEqual(writer.Write(str(path)), IFSelect_RetDone)
            part = step_geometry.convert_step(path.read_bytes(), path.name)["parts"][0]
        face = next(face for face in part["faces"] if face["type"] == "cone")
        self.assertVector(face["apex"], [0, 0, -.04])
        self.assertVector(face["axis"], [0, 0, 1])
        self.assertAlmostEqual(face["semiAngle"], math.atan(.25), places=8)

    def test_inch_source_preserves_si_analytic_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inch-cones-tori.step"
            Interface_Static.SetCVal_s("write.step.unit", "INCH")
            try:
                write_fixture(path)
            finally:
                Interface_Static.SetCVal_s("write.step.unit", "MM")
            imported = step_geometry.convert_step(path.read_bytes(), path.name)
        self.assertTrue(any("inch" in unit.lower() for unit in imported["sourceLengthUnits"]))
        for expected, actual in zip(self.parts, imported["parts"]):
            for kind in ("cone", "torus"):
                before = next((face for face in expected["faces"] if face["type"] == kind), None)
                after = next((face for face in actual["faces"] if face["type"] == kind), None)
                if before:
                    for field in ("apex", "centre", "axis"):
                        if field in before:
                            self.assertVector(after[field], before[field])
                    for field in ("semiAngle", "majorRadius", "minorRadius"):
                        if field in before:
                            self.assertAlmostEqual(after[field], before[field], places=8)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--fixture":
        if not HAS_OCP:
            raise SystemExit("The curved CAD fixture requires cadquery-ocp in the test Python environment.")
        path = Path(sys.argv[2])
        path.parent.mkdir(parents=True, exist_ok=True)
        write_fixture(path)
    else:
        unittest.main()
