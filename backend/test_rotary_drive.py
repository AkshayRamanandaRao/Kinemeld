"""Driven revolute joints: schema, laws, deck generation and constraint rows."""
import math
import unittest

import constraint_analysis
import spatial_assembly as spatial


def v(x, y, z):
    return {"x": x, "y": y, "z": z}


def driven_link(motion):
    return {"kind": "spatial-assembly", "name": "Driven link", "parameters": {"gravity": v(0, 0, -9.81)},
            "simulation": {"duration": 1.0, "step": 0.001},
            "bodies": [{"id": "link", "name": "Link", "mass": 2.0, "inertia": {"xx": 0.002, "yy": 0.01, "zz": 0.01},
                        "centerOfMass": v(0.3, 0, 0), "pose": {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0},
                        "velocity": dict.fromkeys(("vx", "vy", "vz", "wx", "wy", "wz"), 0.0)}],
            "joints": [{"id": "motor", "type": "revolute", "a": "ground", "b": "link", "anchorA": v(0, 0, 0), "anchorB": v(0, 0, 0),
                        "axisA": v(0, 1, 0), "axisB": v(0, 1, 0), "motion": motion}]}


class RotaryDriveTests(unittest.TestCase):
    def test_speed_ramp_law_is_smooth_in_angle_and_continuous_in_speed(self):
        motion = {"speedDegPerS": math.degrees(4.0), "rampTime": 0.5}
        self.assertEqual(spatial.rotary_angle(motion, 0.0), 0.0)
        self.assertAlmostEqual(spatial.rotary_angle(motion, 0.25), 4.0 / 1.0 * 0.25 ** 2)
        self.assertAlmostEqual(spatial.rotary_angle(motion, 0.5), 1.0)
        self.assertAlmostEqual(spatial.rotary_angle(motion, 2.0), 4.0 * (2.0 - 0.25))

    def test_oscillation_starts_at_rest(self):
        motion = {"amplitudeDeg": 30.0, "frequencyHz": 2.0}
        self.assertEqual(spatial.rotary_angle(motion, 0.0), 0.0)
        self.assertAlmostEqual(spatial.rotary_angle(motion, 0.25), 2 * math.radians(30.0))

    def test_valid_models_generate_a_driven_total_joint(self):
        for motion, drive in (({"speedDegPerS": 90.0, "rampTime": 0.2}, 'string, "'), ({"amplitudeDeg": 20.0, "frequencyHz": 1.0}, "cosine, 0,")):
            model = driven_link(motion)
            check = spatial.validate(model)
            self.assertTrue(check["valid"], check["issues"])
            self.assertEqual(check["summary"]["mobility"]["dof"], 0)
            deck = spatial.deck(model)
            line = next(text for text in deck.splitlines() if "joint: 2," in text)
            self.assertIn("total joint", line)
            self.assertIn("orientation constraint, active, active, active, single, 0,0,1, " + drive, line)

    def test_invalid_motion_and_initial_spin_are_reported(self):
        model = driven_link({"speedDegPerS": 90.0})
        self.assertIn("joints.0.motion", {i["field"] for i in spatial.validate(model)["issues"]})
        model = driven_link({"speedDegPerS": 90.0, "rampTime": 0.2})
        model["bodies"][0]["velocity"]["wy"] = 1.0
        messages = " ".join(i["message"] for i in spatial.validate(model)["issues"])
        self.assertIn("starts at rest", messages)
        model = driven_link({"speedDegPerS": 90.0, "rampTime": 0.005})
        self.assertIn("joints.0.motion.rampTime", {i["field"] for i in spatial.validate(model)["issues"]})
        model = driven_link({"speedDegPerS": 90.0, "rampTime": 0.2})
        model["joints"][0]["type"] = "spherical"
        del model["joints"][0]["axisA"], model["joints"][0]["axisB"]
        self.assertIn("joints.0.motion", {i["field"] for i in spatial.validate(model)["issues"]})

    def test_drive_adds_one_constraint_row(self):
        rows = constraint_analysis.joint_rows(driven_link({"amplitudeDeg": 10.0, "frequencyHz": 1.0})["joints"][0],
                                              {"link": driven_link({})["bodies"][0]})
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1][0], "prescribed rotation about the axis")


if __name__ == "__main__":
    unittest.main()
