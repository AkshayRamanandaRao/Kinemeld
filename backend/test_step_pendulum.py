"""Verify the original solid against the existing pendulum's physical model."""
import json
import math
import unittest
from pathlib import Path
import step_geometry

ROOT = Path(__file__).resolve().parents[1]
STEP = ROOT / "examples" / "step-pendulum" / "pendulum.step"
FIXTURE = ROOT / "examples" / "planar-assembly" / "assembly-single.json"

try:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@unittest.skipUnless(HAS_OCP, "OCP is not installed")
class StepPendulumTest(unittest.TestCase):
    def test_fixture_solid_and_placement(self):
        model = json.loads(FIXTURE.read_text(encoding="utf-8"))
        body, hinge = model["bodies"][0], model["joints"][0]
        self.assertEqual(body["id"], "upper_link")
        self.assertEqual(hinge["parent"], "ground")
        self.assertEqual(hinge["childAnchor"], {"x":0., "z":.5})
        mass, length, width = 1.2, 1., .03
        transverse, axial = mass*(length**2+width**2)/12, mass*2*width**2/12
        self.assertEqual(body["mass"], mass)
        self.assertAlmostEqual(body["inertia"]["xx"], transverse)
        self.assertAlmostEqual(body["inertia"]["yy"], transverse)
        self.assertAlmostEqual(body["inertia"]["zz"], axial)
        theta = math.radians(body["pose"]["angleDeg"])
        self.assertAlmostEqual(body["pose"]["x"] + .5*math.sin(theta), 0.)
        self.assertAlmostEqual(body["pose"]["z"] + .5*math.cos(theta), 0.)
        mesh = step_geometry.convert_step(STEP.read_bytes(), STEP.name)
        self.assertEqual(mesh["units"], "m")
        self.assertEqual(mesh["sourceLengthUnits"], ["millimetre"])
        self.assertEqual(len(mesh["parts"]), 1)
        self.assertEqual(mesh["triangleCount"], 12)
        points = mesh["parts"][0]["positions"]
        expected_extents = [abs(.015*math.cos(theta))+abs(.5*math.sin(theta)),
                            .015,abs(.015*math.sin(theta))+abs(.5*math.cos(theta))]
        center = [body["pose"]["x"], 0., body["pose"]["z"]]
        for axis in range(3):
            self.assertAlmostEqual(min(points[axis::3]), center[axis]-expected_extents[axis], places=9)
            self.assertAlmostEqual(max(points[axis::3]), center[axis]+expected_extents[axis], places=9)
        reader = STEPControl_Reader()
        self.assertEqual(reader.ReadFile(str(STEP)), IFSelect_RetDone)
        self.assertGreater(reader.TransferRoots(), 0)
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(reader.OneShape(), props)
        volume = props.Mass()
        self.assertAlmostEqual(volume, 900000., places=3)  # cubic millimetres
        centroid = props.CentreOfMass()
        self.assertAlmostEqual(centroid.X()*.001, center[0], places=9)
        self.assertAlmostEqual(centroid.Y()*.001, center[1], places=9)
        self.assertAlmostEqual(centroid.Z()*.001, center[2], places=9)
        inertia = props.MatrixOfInertia()
        expected = [math.cos(theta)**2*transverse+math.sin(theta)**2*axial,
                    transverse,math.sin(theta)**2*transverse+math.cos(theta)**2*axial]
        for axis in range(3):
            actual = inertia.Value(axis+1,axis+1)*mass/volume*1e-6
            self.assertAlmostEqual(actual, expected[axis], places=9)


if __name__ == "__main__": unittest.main()
