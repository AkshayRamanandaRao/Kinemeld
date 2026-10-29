"""Constraint-rank mobility and redundancy diagnostics for spatial assemblies."""
import unittest

import constraint_analysis
import spatial_assembly as spatial


def v(x, y, z):
    return {"x": x, "y": y, "z": z}


def body(identifier, x, z):
    return {"id": identifier, "name": identifier, "mass": 1.0, "inertia": {"xx": 0.01, "yy": 0.01, "zz": 0.01},
            "pose": {"x": x, "y": 0.0, "z": z, "rx": 0.0, "ry": 0.0, "rz": 0.0}, "velocity": dict.fromkeys(("vx", "vy", "vz", "wx", "wy", "wz"), 0.0)}


def hinge(identifier, a, b, anchor_a, anchor_b, kind="revolute"):
    joint = {"id": identifier, "type": kind, "a": a, "b": b, "anchorA": anchor_a, "anchorB": anchor_b}
    if kind in ("revolute", "universal"):
        joint.update(axisA=v(0, 1, 0), axisB=v(0, 1, 0) if kind == "revolute" else v(1, 0, 0))
    return joint


def four_bar(closing="revolute"):
    """Planar four-bar in the X-Z plane: crank, coupler and rocker with origins at their first pins."""
    model = {"kind": "spatial-assembly", "name": "Four-bar", "parameters": {"gravity": v(0, 0, -9.81)},
             "simulation": {"duration": 0.1, "step": 0.001},
             "bodies": [body("crank", 0, 0), body("coupler", 0, 0.1), body("rocker", 0.4, 0)], "joints": [
                 hinge("ground_crank", "ground", "crank", v(0, 0, 0), v(0, 0, 0)),
                 hinge("crank_coupler", "crank", "coupler", v(0, 0, 0.1), v(0, 0, 0), "spherical" if closing == "universal" else "revolute"),
                 hinge("ground_rocker", "ground", "rocker", v(0.4, 0, 0), v(0, 0, 0)),
                 hinge("coupler_rocker", "coupler", "rocker", v(0.4, 0, 0.1), v(0, 0, 0.2), closing)]}
    if closing == "universal":
        # Axis A is normal to the coupler and the hinge axis, so the coupler cannot spin about itself.
        length = (0.4 ** 2 + 0.1 ** 2) ** 0.5
        model["joints"][3]["axisA"] = v(-0.1 / length, 0, 0.4 / length)
        model["joints"][3]["axisB"] = v(0, 1, 0)
    return model


class ConstraintAnalysisTests(unittest.TestCase):
    def test_planar_loop_of_revolutes_is_redundant_on_its_closing_joint(self):
        model = four_bar()
        result = constraint_analysis.analyse(model)
        self.assertEqual(result["grubler"], -2)
        self.assertEqual(result["dof"], 1)
        self.assertEqual(len(result["redundant"]), 3)
        self.assertEqual({item["joint"] for item in result["redundant"]}, {"coupler_rocker"})
        summary = spatial.validate(model)["summary"]
        self.assertEqual(summary["mobility"]["dof"], 1)
        self.assertEqual(len(summary["mobility"]["redundant"]), 3)

    def test_spherical_closure_of_planar_hinges_keeps_one_redundancy(self):
        result = constraint_analysis.analyse(four_bar("spherical"))
        self.assertEqual(result["grubler"], 0)
        self.assertEqual(result["dof"], 1)
        self.assertEqual(result["redundant"], [{"joint": "coupler_rocker", "component": "translation along Y"}])

    def test_revolute_spherical_revolute_universal_loop_is_exact(self):
        result = constraint_analysis.analyse(four_bar("universal"))
        self.assertEqual((result["grubler"], result["dof"], result["redundant"]), (1, 1, []))

    def test_prescribed_slider_motion_counts_as_a_constraint(self):
        model = four_bar("universal")
        model["bodies"].append(body("slider", 1.0, 0.0))
        model["joints"].append({"id": "guide", "type": "prismatic", "a": "ground", "b": "slider", "anchorA": v(1, 0, 0), "anchorB": v(0, 0, 0),
                                "axisA": v(1, 0, 0), "motion": {"amplitude": 0.01, "frequencyHz": 1.0}})
        result = constraint_analysis.analyse(model)
        self.assertEqual((result["constraints"], result["dof"], result["redundant"]), (23, 1, []))

if __name__ == "__main__":
    unittest.main()
