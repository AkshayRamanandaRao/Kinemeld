"""Geometry and representation checks independent of installed MBDyn."""

import copy
import math
import unittest

import gear_deployment as gear


class GearDeploymentTests(unittest.TestCase):
    def test_analytic_closed_loop_and_drive_endpoints(self):
        model = copy.deepcopy(gear.DEFAULT)
        self.assertEqual(gear.extra_validation(model)[0], [])
        samples = gear.preview(model)
        self.assertAlmostEqual(samples[0]["angle"], -65)
        self.assertAlmostEqual(samples[-1]["angle"], 0)
        self.assertLess(max(q["closureError"] for q in samples), 1e-12)
        self.assertAlmostEqual(samples[0]["velocity"], 0)
        self.assertAlmostEqual(samples[-1]["velocity"], 0)
        self.assertGreater(gear.metrics(model, samples)["actuatorTravel"], .1)

    def test_unreachable_geometry_and_interior_toggle_are_rejected(self):
        model = copy.deepcopy(gear.DEFAULT)
        model["parameters"]["upperBraceLength"] = .1
        self.assertTrue(gear.extra_validation(model)[0])
        model = copy.deepcopy(gear.DEFAULT)
        model["parameters"].update(initialAngle=-65, finalAngle=65, groundX=0, groundZ=-.45,
                                   upperBraceLength=.55, lowerBraceLength=.55)
        self.assertTrue(gear.extra_validation(model)[0])
        model = copy.deepcopy(gear.DEFAULT)
        model["parameters"]["braceAttachment"] = model["parameters"]["mainLength"]
        self.assertTrue(gear.extra_validation(model)[0])

    def test_observed_brace_error_is_preserved(self):
        model = copy.deepcopy(gear.DEFAULT)
        bx,bz,cx,cz = gear.geometry(model["parameters"], -65)
        rows = {1:[1,bx,0,bz,0,0,0,0,0,0,0,0,0],
                2:[2,cx+.02,0,cz,0,0,0,0,0,0,0,0,0],
                3:[3,.65,0,-.1,0,0,0,0,0,0,0,0,0]}
        actual = gear.parse_sample(model, 0, rows)
        self.assertGreater(actual["closureError"], .001)
        self.assertAlmostEqual(gear.metrics(model, [actual])["maxGeometryError"], .02)
        self.assertTrue(all(math.isfinite(v) for v in actual.values()))


if __name__ == "__main__":
    unittest.main()
