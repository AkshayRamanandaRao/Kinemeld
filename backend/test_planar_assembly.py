"""Planar graph and initial-condition checks independent of an installed solver."""

import copy
import csv
import math
from pathlib import Path
import tempfile
import unittest

import models
import planar_assembly as planar
import solver


def rotate(angle, x, z):
    angle = math.radians(angle)
    return math.cos(angle) * x + math.sin(angle) * z, -math.sin(angle) * x + math.cos(angle) * z


def assembly(count=3, ground_roots=(0,)):
    """Build a chain with independently computed compatible hinge velocities."""
    model = {
        "kind": "planar-assembly", "name": "Moving planar chain",
        "parameters": {"gravity": 9.81},
        "simulation": {"duration": 5, "step": .001},
        "bodies": [], "joints": [],
    }
    for index in range(count):
        angle, omega = -20 + 17 * (index % 4), .2 * (index + 1)
        parent_anchor = {"x": 0, "z": -.5}
        if index in ground_roots:
            parent = "ground"
            parent_anchor = {"x": 2 * index, "z": 0}
            hinge_x, hinge_z, hinge_vx, hinge_vz = 2 * index, 0, 0, 0
        else:
            previous = model["bodies"][-1]
            parent = previous["id"]
            px, pz = rotate(previous["pose"]["angleDeg"], 0, -.5)
            hinge_x = previous["pose"]["x"] + px
            hinge_z = previous["pose"]["z"] + pz
            hinge_vx = previous["velocity"]["vx"] + previous["velocity"]["omega"] * pz
            hinge_vz = previous["velocity"]["vz"] - previous["velocity"]["omega"] * px
        cx, cz = rotate(angle, 0, .5)
        body_id = f"link{index + 1}"
        model["bodies"].append({
            "id": body_id, "name": f"Link {index + 1}", "mass": 1,
            "inertia": {"xx": .1, "yy": .1, "zz": .01},
            "pose": {"x": hinge_x - cx, "z": hinge_z - cz, "angleDeg": angle},
            "velocity": {"vx": hinge_vx - omega * cz, "vz": hinge_vz + omega * cx, "omega": omega},
        })
        model["joints"].append({
            "id": f"pin{index + 1}", "type": "revolute", "parent": parent, "child": body_id,
            "parentAnchor": parent_anchor, "childAnchor": {"x": 0, "z": .5},
        })
    return model


def set_at(model, path, value):
    target = model
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def coincident(model):
    """Keep positions and velocities consistent while testing graph failures."""
    for body in model["bodies"]:
        body["pose"] = {"x": 0, "z": 0, "angleDeg": 0}
        body["velocity"] = {"vx": 0, "vz": 0, "omega": 0}
    for joint in model["joints"]:
        joint["parentAnchor"] = {"x": 0, "z": 0}
        joint["childAnchor"] = {"x": 0, "z": 0}
    return model


def native_rows(model):
    return [[label, body["pose"]["x"], 0, body["pose"]["z"],
             0, body["pose"]["angleDeg"], 0, body["velocity"]["vx"], 0,
             body["velocity"]["vz"], 0, body["velocity"]["omega"], 0]
            for label, body in enumerate(model["bodies"], 1)]


def write_native(directory, model, frames=None, times=None):
    """Synthetic parser fixtures matching native text structure, not solver evidence."""
    times = [0, model["simulation"]["duration"]] if times is None else times
    frames = [native_rows(model) for _ in times] if frames is None else frames
    (directory / "result.out").write_text(
        "# Step Time TStep NIter ResErr SolErr SolConv Out\n" +
        "".join(f"Step {index} {time} 0.001 2 1e-12 0 0 1\n" for index, time in enumerate(times)), encoding="utf-8")
    (directory / "result.log").write_text("output frequency: 1\n" + "".join(
        f"structural node: {label} 0 0 0 euler123 0 0 0\n" for label in range(1, len(model["bodies"]) + 1)), encoding="utf-8")
    (directory / "result.mov").write_text("".join(
        " ".join(str(value) for value in row) + "\n" for frame in frames for row in frame), encoding="utf-8")


class PlanarAssemblyTests(unittest.TestCase):
    def assert_valid(self, model):
        original = copy.deepcopy(model)
        check = planar.validate(model)
        self.assertTrue(check["valid"], check["issues"])
        self.assertIsInstance(check["summary"], dict)
        self.assertEqual(model, original, "Validation must preserve the supplied project.")
        deck = planar.deck(model)
        self.assertIsInstance(deck, str)
        self.assertIn("begin: nodes;", deck)
        self.assertIn("begin: elements;", deck)
        self.assertEqual(model, original, "Deck generation must preserve the supplied project.")
        return deck

    def assert_rejected(self, model):
        check = planar.validate(model)
        self.assertFalse(check["valid"], check)
        errors = [issue for issue in check["issues"] if issue["level"] == "error"]
        self.assertTrue(errors, check)
        for issue in errors:
            self.assertIsInstance(issue["field"], str)
            self.assertTrue(issue["message"])
        with self.assertRaises(ValueError):
            planar.deck(model)

    def test_examples_have_valid_independent_projects(self):
        self.assertEqual(len({example["id"] for example in planar.EXAMPLES}), len(planar.EXAMPLES))
        self.assertTrue({"assembly-single", "assembly-chain", "assembly-branch", "assembly-spring"} <= {example["id"] for example in planar.EXAMPLES})
        for example in planar.EXAMPLES:
            with self.subTest(example=example["id"]):
                self.assertTrue(example["title"])
                self.assertTrue(example["description"])
                self.assert_valid(copy.deepcopy(example["model"]))

    def test_chain_with_rotated_anchors_and_nonzero_velocities(self):
        model = assembly()
        self.assert_valid(model)
        model["bodies"] = [model["bodies"][2], model["bodies"][0], model["bodies"][1]]
        model["joints"] = [model["joints"][1], model["joints"][2], model["joints"][0]]
        self.assert_valid(model)

    def test_multiple_ground_roots_and_branching_are_valid(self):
        self.assert_valid(assembly(4, ground_roots=(0, 2)))
        branch = coincident(assembly())
        branch["joints"][2]["parent"] = "link1"
        self.assert_valid(branch)

    def test_supported_body_count_endpoints_and_overflow(self):
        self.assert_valid(assembly(1))
        self.assert_valid(assembly(16))
        self.assert_rejected(assembly(0))
        self.assert_rejected(assembly(17))

    def test_duplicate_ids_and_multiple_parent_hinges_are_rejected(self):
        for group in ("bodies", "joints"):
            with self.subTest(group=group):
                model = coincident(assembly())
                model[group][1]["id"] = model[group][0]["id"]
                self.assert_rejected(model)
        model = coincident(assembly())
        model["joints"][2]["child"] = "link2"
        self.assert_rejected(model)

    def test_dangling_endpoints_and_reserved_ground_body_are_rejected(self):
        for field, value in (("parent", "absent"), ("child", "absent"), ("child", "ground")):
            with self.subTest(field=field, value=value):
                model = coincident(assembly())
                model["joints"][0][field] = value
                self.assert_rejected(model)
        model = coincident(assembly())
        model["bodies"][0]["id"] = "ground"
        self.assert_rejected(model)

    def test_cycles_and_disconnected_bodies_are_rejected(self):
        model = coincident(assembly())
        model["joints"][0]["parent"] = "link3"
        self.assert_rejected(model)
        model = coincident(assembly())
        model["joints"][1]["parent"] = "link3"
        self.assert_rejected(model)
        model = coincident(assembly())
        model["joints"][1]["parent"] = "link2"
        self.assert_rejected(model)
        model = coincident(assembly())
        model["joints"].pop()
        self.assert_rejected(model)

    def test_unknown_fields_and_unsafe_identifiers_are_rejected(self):
        paths = [(), ("parameters",), ("simulation",), ("bodies", 0),
                 ("bodies", 0, "inertia"), ("bodies", 0, "pose"), ("bodies", 0, "velocity"),
                 ("joints", 0), ("joints", 0, "parentAnchor"), ("joints", 0, "childAnchor")]
        for path in paths:
            with self.subTest(path=path):
                model = assembly()
                set_at(model, (*path, "include"), '"untrusted.mbd";')
                self.assert_rejected(model)
        for group in ("bodies", "joints"):
            for identifier in ('link1; include: "untrusted.mbd";', "link1\n# injected", ""):
                with self.subTest(group=group, identifier=identifier):
                    model = assembly()
                    model[group][0]["id"] = identifier
                    self.assert_rejected(model)
        model = assembly()
        model["joints"][0]["type"] = "spherical"
        self.assert_rejected(model)

    def test_nonfinite_boolean_and_non_numeric_values_are_rejected(self):
        paths = [("parameters", "gravity"), ("simulation", "duration"), ("simulation", "step"),
                 ("bodies", 0, "mass"), ("bodies", 0, "inertia", "xx"),
                 ("bodies", 0, "pose", "x"), ("bodies", 0, "pose", "angleDeg"),
                 ("bodies", 0, "velocity", "vx"), ("bodies", 0, "velocity", "omega"),
                 ("joints", 0, "parentAnchor", "z"), ("joints", 0, "childAnchor", "x")]
        for path in paths:
            for value in (float("nan"), float("inf"), -float("inf"), True, False, 10**400, "1"):
                with self.subTest(path=path, value=value):
                    model = assembly()
                    set_at(model, path, value)
                    self.assert_rejected(model)

    def test_principal_inertias_must_be_positive_and_obey_triangle_inequality(self):
        for axis in ("xx", "yy", "zz"):
            for value in (0, -.1, .3):
                with self.subTest(axis=axis, value=value):
                    model = assembly()
                    model["bodies"][0]["inertia"] = {"xx": .1, "yy": .1, "zz": .1}
                    model["bodies"][0]["inertia"][axis] = value
                    self.assert_rejected(model)

    def test_initial_anchor_position_mismatch_is_rejected(self):
        paths = [("bodies", 0, "pose", "x"), ("bodies", 2, "pose", "z"),
                 ("bodies", 1, "pose", "angleDeg"),
                 ("joints", 1, "parentAnchor", "x"), ("joints", 1, "childAnchor", "z")]
        for path in paths:
            with self.subTest(path=path):
                model = assembly()
                target = model
                for key in path:
                    target = target[key]
                set_at(model, path, target + .1)
                self.assert_rejected(model)

    def test_initial_anchor_velocity_mismatch_is_rejected(self):
        for index in (0, 1, 2):
            for field in ("vx", "vz", "omega"):
                with self.subTest(body=index, field=field):
                    model = assembly()
                    model["bodies"][index]["velocity"][field] += .1
                    self.assert_rejected(model)

    def test_malformed_and_missing_structures_fail_with_diagnostics(self):
        for value in (None, [], "planar-assembly"):
            with self.subTest(value=value):
                self.assert_rejected(value)
        for path, value in ((("bodies",), None), (("joints",), {}),
                            (("bodies", 0), None), (("joints", 0), []),
                            (("bodies", 0, "pose"), []), (("joints", 0, "childAnchor"), None)):
            with self.subTest(path=path):
                model = assembly()
                set_at(model, path, value)
                self.assert_rejected(model)
        for field in ("kind", "parameters", "simulation", "bodies", "joints"):
            with self.subTest(missing=field):
                model = assembly()
                del model[field]
                self.assert_rejected(model)

    def test_production_dispatch_and_explicit_preview_refusal(self):
        catalog = {item["id"]: item for item in models.EXAMPLES}
        for example in planar.EXAMPLES:
            with self.subTest(example=example["id"]):
                model = copy.deepcopy(catalog[example["id"]]["model"])
                self.assertEqual(models.validate(model), planar.validate(model))
                self.assertEqual(models.deck(model), planar.deck(model))
                with self.assertRaisesRegex(ValueError, "actual MBDyn"):
                    models.preview(model)
        model = assembly()
        model["parameters"]["gravity"] = 0
        self.assertTrue(models.validate(model)["valid"])
        self.assertIn("gravity: uniform, 0,0,-1, const, 0;", models.deck(model))
        model["bodies"][0]["mass"] = -1
        self.assertFalse(models.validate(model)["valid"])
        with self.assertRaises(ValueError):
            models.deck(model)
        self.assertIn("gravity", models.RANGES[planar.KIND])

    def test_captured_native_rows_preserve_observed_values(self):
        # MBDyn 1.7.3 run 541536b122c74c669ac1a87731636e3f, retained frames 0 and 10.
        records = [
            "1 6.958655048003e-02 0 -4.951340343708e-01 0 -8 0 0 0 0 0 0 0",
            "1 6.953586795034e-02 0 -4.951411546907e-01 0 -7.994135175603e+00 0 -1.013537560525e-02 0 -1.423395771944e-03 0 2.046967456044e-02 0",
        ]
        model = copy.deepcopy(planar.EXAMPLES[0]["model"])
        model["simulation"] = {"duration": .01, "step": .001}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "result.out").write_text(
                "# Step Time TStep NIter ResErr SolErr SolConv Out\n"
                "Step 0 0 0 1 3.49532106991e-08 0 0 1\n"
                "Step 10 0.01 0.001 1 9.52016243616e-15 0 0 1\n", encoding="utf-8")
            (directory / "result.log").write_text(
                "output frequency: 1\nstructural node: 1 0.0695866 0 -0.495134 euler123 -0 -8 0\n", encoding="utf-8")
            (directory / "result.mov").write_text("\n".join(records) + "\n", encoding="utf-8")
            samples = solver.parse_output(directory, model)
        self.assertEqual([sample["time"] for sample in samples], [0, .01])
        node = samples[-1]["nodes"][0]
        self.assertEqual(node["id"], "upper_link")
        self.assertEqual(node["label"], 1)
        self.assertEqual(node["x"], 6.953586795034e-02)
        self.assertEqual(node["wy"], 2.046967456044e-02)
        self.assertAlmostEqual(node["angleDeg"], -7.994135175603)
        self.assertLess(samples[-1]["jointError"], 1e-10)
        self.assertGreater(samples[-1]["jointVelocityError"], 0)
        self.assertLess(samples[-1]["jointVelocityError"], 1e-6)

    def test_model_ids_metrics_and_csv_survive_native_label_mapping(self):
        model = assembly(2)
        model["simulation"] = {"duration": .01, "step": .001}
        model["bodies"].reverse()
        model["joints"].reverse()
        original = copy.deepcopy(model)
        frames = [native_rows(model), native_rows(model)]
        frames[1][0][1] += .02
        frames[1][0][7] += .04
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            write_native(directory, model, frames)
            samples = solver.parse_output(directory, model)
            self.assertEqual(model, original)
            self.assertEqual([node["id"] for node in samples[0]["nodes"]], ["link2", "link1"])
            self.assertEqual([node["label"] for node in samples[0]["nodes"]], [1, 2])
            calculated = models.metrics(model, samples)
            self.assertEqual(calculated["bodyCount"], 2)
            self.assertEqual(calculated["sampleCount"], 2)
            self.assertAlmostEqual(calculated["maxConstraintError"], .02)
            self.assertAlmostEqual(calculated["maxJointVelocityError"], .04)
            expected_energy = sum(.5 * body["mass"] * (row[7] ** 2 + row[9] ** 2) +
                                  .5 * body["inertia"]["yy"] * row[11] ** 2 +
                                  body["mass"] * model["parameters"]["gravity"] * row[3]
                                  for body, row in zip(model["bodies"], frames[1]))
            self.assertAlmostEqual(calculated["finalEnergy"], expected_energy)
            target = directory / "results.csv"
            planar.write_csv(target, samples)
            with target.open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                self.assertEqual(set(reader.fieldnames), {
                    "time", "id", "label", "x", "y", "z", "rx", "ry", "rz", "vx", "vy", "vz",
                    "wx", "wy", "wz", "angleDeg", "energy", "jointError", "jointVelocityError"})
        self.assertEqual(len(rows), 4)
        self.assertEqual([(float(row["time"]), row["id"], int(row["label"])) for row in rows],
                         [(0, "link2", 1), (0, "link1", 2), (.01, "link2", 1), (.01, "link1", 2)])
        self.assertTrue(all(None not in row and all(value is not None for value in row.values()) for row in rows))
        self.assertAlmostEqual(float(rows[2]["x"]), frames[1][0][1])
        self.assertAlmostEqual(float(rows[2]["energy"]), expected_energy)

    def test_euler123_orientation_branches_recover_planar_angles(self):
        model = coincident(assembly(1))
        model["simulation"] = {"duration": .01, "step": .001}
        branches = [((0, 45, 0), 45), ((180, 60, 180), 120), ((180, -20, 180), -160),
                    ((180, -60, 180), -120), ((180, 0, 180), 180),
                    ((30, 90, -30), 90), ((-30, -90, -30), -90)]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for euler, expected in branches:
                with self.subTest(euler=euler):
                    rows = native_rows(model)
                    rows[0][4:7] = euler
                    write_native(directory, model, [rows, rows])
                    samples = solver.parse_output(directory, model)
                    self.assertAlmostEqual(samples[-1]["nodes"][0]["angleDeg"], expected)

    def test_incomplete_malformed_and_nonfinite_native_frames_are_rejected(self):
        model = assembly(2)
        model["simulation"] = {"duration": .01, "step": .001}
        good = [native_rows(model), native_rows(model)]
        bad = []
        frames = copy.deepcopy(good)
        frames[1].pop()
        bad.append(("missing node", frames))
        frames = copy.deepcopy(good)
        frames[1][1][0] = 1
        bad.append(("repeated node", frames))
        frames = copy.deepcopy(good)
        frames[1].reverse()
        bad.append(("reordered frame", frames))
        frames = copy.deepcopy(good)
        frames[1][0][0] = 99
        bad.append(("unknown node", frames))
        frames = copy.deepcopy(good)
        frames[1][0].pop()
        bad.append(("record width", frames))
        for value in (float("nan"), float("inf"), -float("inf")):
            frames = copy.deepcopy(good)
            frames[1][0][1] = value
            bad.append((str(value), frames))
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for name, frames in bad:
                with self.subTest(damage=name):
                    write_native(directory, model, frames)
                    with self.assertRaises(ValueError):
                        solver.parse_output(directory, model)
            for log in ("", "structural node: 1 0 0 0 phi 0 0 0\nstructural node: 2 0 0 0 phi 0 0 0\n"):
                with self.subTest(log=log):
                    write_native(directory, model, good)
                    (directory / "result.log").write_text(log, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        solver.parse_output(directory, model)

    def test_native_timestamps_require_finite_order_and_complete_interval(self):
        model = assembly(1)
        model["simulation"] = {"duration": .01, "step": .001}
        times = [[0], [0, 0], [0, float("nan")], [0, float("inf")], [0, -.01],
                 [0, .005], [0, .02], [.005, .01], [-.001, .01]]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for values in times:
                with self.subTest(times=values):
                    write_native(directory, model, times=values)
                    with self.assertRaises(ValueError):
                        solver.parse_output(directory, model)

    def test_out_of_plane_native_motion_and_orientation_are_rejected(self):
        model = coincident(assembly(1))
        model["simulation"] = {"duration": .01, "step": .001}
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            for field in (2, 8, 10, 12, 4, 6):
                with self.subTest(column=field):
                    frames = [native_rows(model), native_rows(model)]
                    frames[1][0][field] = .1
                    write_native(directory, model, frames)
                    with self.assertRaises(ValueError):
                        solver.parse_output(directory, model)


if __name__ == "__main__":
    unittest.main()
