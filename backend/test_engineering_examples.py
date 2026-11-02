"""Engineering provenance and independent-reference failure checks, without a solver."""
import copy
import hashlib
import json
import math
import unittest

import verify_engineering_examples as engineering


class EngineeringExampleTests(unittest.TestCase):
    def record(self, study):
        path = engineering.ROOT / engineering.STUDIES[study]
        return json.loads(path.with_name("engineering.json").read_text()), json.loads(path.read_text())

    def test_all_saved_records_identify_sources_and_hardpoints(self):
        for study in engineering.STUDIES:
            with self.subTest(study=study):
                manifest, _ = engineering.check_manifest(study)
                self.assertEqual(manifest["hardwareValidation"], "not-performed")

    def test_retained_evidence_matches_current_inputs_and_reference(self):
        evidence = json.loads((engineering.ROOT / "examples/engineering-verification.json").read_text())
        script = engineering.ROOT / "backend/verify_engineering_examples.py"
        self.assertEqual(evidence["verifierSha256Lf"], hashlib.sha256(script.read_bytes().replace(b"\r\n", b"\n")).hexdigest())
        self.assertEqual({study["study"] for study in evidence["studies"]}, set(engineering.STUDIES))
        for study in evidence["studies"]:
            _, project = self.record(study["study"])
            self.assertEqual(study["modelSha256"], engineering.digest(project["model"]))
            self.assertTrue(study["ok"])
            self.assertEqual(len(study["levels"]), 3)
            self.assertEqual(study["hardwareValidation"], "not-performed")

    def test_newer_model_or_asset_cannot_reuse_old_evidence(self):
        manifest, project = self.record("nose-gear")
        changed = copy.deepcopy(project)
        changed["model"]["bodies"][0]["mass"] *= 2
        with self.assertRaisesRegex(ValueError, "saved model"):
            engineering.check_manifest("nose-gear", manifest, changed)
        project["assets"]["step"]["files"][0]["data"] = "Y2hhbmdlZA=="
        with self.assertRaisesRegex(ValueError, "CAD source identity"):
            engineering.check_manifest("nose-gear", manifest, project)

    def test_missing_assumption_or_changed_hardpoint_is_rejected(self):
        for key in ("hardpoints", "densityAssumptions"):
            manifest, project = self.record("suspension")
            manifest[key].pop()
            with self.assertRaisesRegex(ValueError, "incomplete|density assumptions"):
                engineering.check_manifest("suspension", manifest, project)
        manifest, project = self.record("suspension")
        manifest["hardpoints"][0]["worldM"][0] += .001
        with self.assertRaisesRegex(ValueError, "hardpoint"):
            engineering.check_manifest("suspension", manifest, project)

    def test_loading_and_material_labels_cannot_misstate_the_model(self):
        manifest, project = self.record("landing-drop")
        manifest["forceLaws"][0]["stiffness"] *= 2
        with self.assertRaisesRegex(ValueError, "force/contact/motion"):
            engineering.check_manifest("landing-drop", manifest, project)
        manifest, project = self.record("robot-arm")
        manifest["densityAssumptions"][0]["body"] = "forearm"
        with self.assertRaisesRegex(ValueError, "density assumptions"):
            engineering.check_manifest("robot-arm", manifest, project)

    def test_circle_branch_and_singularity(self):
        point = engineering.circles([0, 0], [2, 0], math.sqrt(2), math.sqrt(2), [1, 1])
        self.assertLess(math.dist(point, [1, 1]), 1e-12)
        with self.assertRaisesRegex(ValueError, "tangency"):
            engineering.circles([0, 0], [2, 0], 1, 1, [1, 0])

    def test_kinematic_negative_controls_detect_displaced_link(self):
        for study, evaluate in (("nose-gear", engineering.nose_error), ("suspension", engineering.suspension_error)):
            _, project = self.record(study)
            model = project["model"]
            sample = {"time": 0, "nodes": [{"id": b["id"], **b["pose"]} for b in model["bodies"]],
                      "sliders": [{"id": "oleo", "position": 0}]}
            self.assertLess(evaluate(model, sample), 1e-12)
            identifier = "upper_link" if study == "nose-gear" else "upper"
            next(n for n in sample["nodes"] if n["id"] == identifier)["z"] += .001
            self.assertGreater(evaluate(model, sample), .0005)

    def test_robot_reference_matches_static_gravity_and_known_tip(self):
        _, project = self.record("robot-arm")
        model = project["model"]
        torque = engineering.arm_torque(model, [0, 0, 0], [0, 0, 0], [0, 0, 0])
        upper, fore = model["bodies"][1:]
        self.assertAlmostEqual(torque[0], 0, places=9)
        self.assertAlmostEqual(torque[1], -9.81*(upper["mass"]*upper["centerOfMass"]["x"] + fore["mass"]*(.42+fore["centerOfMass"]["x"])), places=8)
        self.assertAlmostEqual(torque[2], -9.81*fore["mass"]*fore["centerOfMass"]["x"], places=8)
        frames, _, _ = engineering.arm_geometry(model, [math.pi/2, 0, 0])
        tip = engineering.add(frames[-1][0], engineering.matvec(frames[-1][1], [.36, 0, 0]))
        self.assertLess(math.dist(tip, [0, .78, .42]), 1e-12)

    def test_robot_mass_matrix_is_symmetric_positive_definite(self):
        _, project = self.record("robot-arm")
        matrix, _ = engineering.arm_mass_matrix(project["model"], [.7, -.4, .9])
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(matrix[i][j], matrix[j][i], places=12)
        for velocity in ([1, 0, 0], [0, 1, 0], [0, 0, 1], [1, -2, 3]):
            self.assertGreater(sum(x*y for x, y in zip(velocity, engineering.matvec(matrix, velocity))), 0)

    def test_nested_grid_rejects_wrong_output_times(self):
        self.assertAlmostEqual(engineering.refinement([[0, 0], [1, 1]], [[0, 0], [.5, .6], [1, 1.1]]), .1)
        with self.assertRaisesRegex(ValueError, "timestamps"):
            engineering.refinement([[0, 0], [1, 1]], [[0, 0], [.5, .6], [1.01, 1.1]])


if __name__ == "__main__":
    unittest.main()
