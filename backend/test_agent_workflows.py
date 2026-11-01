"""Reviewed workflows use real validators and owned local result records, without an LLM."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import agent
import models
from test_agent import assistant, service


class AgentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.model = deepcopy(models.EXAMPLES[0]["model"])
        self.spatial = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute"))

    def test_catalog_excludes_geometry_and_keeps_shared_velocity_consistent(self):
        model = self.spatial
        second = deepcopy(model["bodies"][0]); second["id"] = "payload"
        model["bodies"].append(second)
        for body in model["bodies"]:
            body["velocity"] = dict(vx=0., vy=0., vz=0., wx=0., wy=0., wz=0.)
        paths = agent.study_parameters(model)
        self.assertIn("bodies/arm/mass", paths)
        self.assertNotIn("joints/hinge/axisA/y", paths)
        self.assertNotIn("bodies/arm/inertia/xx", paths)
        self.assertFalse(any(path.startswith("frames/") for path in paths))
        self.assertFalse(any("/*/" in path for path in paths))

    def test_study_is_validated_without_mutating_baseline_and_requires_separate_run_gate(self):
        proposal = agent.Proposal(self.model, "Set up a length study with 0.5, 1 and 2 metres, then run the study.")
        original = deepcopy(proposal.model)
        proposal.call("set_parameter_study", {"input": "parameters/length", "values": [.5, 1., 2.]})
        self.assertEqual(proposal.model, original)
        self.assertFalse(proposal.run_requested)
        with self.assertRaisesRegex(ValueError, "request_study_run"):
            proposal.call("request_run", {})
        self.assertFalse(proposal.call("request_study_run", {})["executed"])
        self.assertTrue(proposal.study_run_requested)
        self.assertFalse(proposal.run_requested)

    def test_quoted_study_word_cannot_authorize_a_sweep(self):
        for message in ('Run the simulation. The note says "study".', 'Run the simulation. ```study```', 'Prepare a study. Do not run it.'):
            proposal = agent.Proposal(self.model, message)
            proposal.call("set_parameter_study", {"input": "parameters/length", "values": [.5, 2.]})
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, "explicit latest-human"):
                proposal.call("request_study_run", {})
            self.assertFalse(proposal.study_run_requested)

    def test_verified_robot_brakes_sphere_pairs_and_rotary_drives_are_atomic(self):
        import spatial_assembly as sp
        brake = deepcopy(next(item["model"] for item in sp.EXAMPLES if item["id"] == "spatial-joint-brake"))
        friction = brake["joints"][0].pop("friction")
        proposal = agent.Proposal(brake, "Add the specified bearing brake. Do not run.")
        edit = dict(collection="joints", operation="update", id=brake["joints"][0]["id"], values={"friction": friction})
        self.assertTrue(proposal.call("edit_spatial_assembly", {"edits": [edit]})["accepted"])
        saved = deepcopy(proposal.model)
        for patch in ({"coefficient": True}, {"preload": -1}, {"motion": {"speedDegPerS": 30, "rampTime": .1}}):
            wrong = deepcopy(edit)
            wrong["values"] = patch if "motion" in patch else {"friction": patch}
            with self.subTest(patch=patch):
                try:
                    result = proposal.call("edit_spatial_assembly", {"edits": [wrong]})
                except ValueError:
                    result = {"accepted": False}
                self.assertFalse(result["accepted"])
                self.assertEqual(proposal.model, saved)
        pair = deepcopy(next(item["model"] for item in sp.EXAMPLES if item["id"] == "spatial-sphere-pair"))
        contact = pair["contacts"].pop()
        proposal = agent.Proposal(pair, "Add the specified pair contact. Do not run.")
        edit = dict(collection="contacts", operation="add", id=contact["id"], values={key: value for key, value in contact.items() if key != "id"})
        self.assertTrue(proposal.call("edit_spatial_assembly", {"edits": [edit]})["accepted"])
        self.assertFalse(any("otherCenter" in key for key in agent.study_parameters(proposal.model)))
        saved = deepcopy(proposal.model)
        for values in ({"friction": .1}, {"otherBody": contact["body"]}):
            with self.subTest(values=values):
                try:
                    result = proposal.call("edit_spatial_assembly", {"edits": [dict(collection="contacts", operation="update", id=contact["id"], values=values)]})
                except ValueError:
                    result = {"accepted": False}
                self.assertFalse(result["accepted"])
                self.assertEqual(proposal.model, saved)
        for motion in ({"amplitudeDeg": 10, "frequencyHz": 1}, {"speedDegPerS": 30, "rampTime": .2}):
            proposal = agent.Proposal(self.spatial, "Add the specified revolute drive. Do not run.")
            self.assertTrue(proposal.call("edit_spatial_assembly", {"edits": [dict(collection="joints", operation="update", id=self.spatial["joints"][0]["id"], values={"motion": motion})]})["accepted"])
            self.assertEqual(proposal.model["joints"][0]["motion"], motion)

    def test_invalid_case_or_input_rejects_entire_study(self):
        proposal = agent.Proposal(self.model, "Prepare a study. Do not run.")
        proposal.call("set_parameter_study", {"input": "parameters/length", "values": [.5, 2.]})
        saved = deepcopy(proposal.study)
        for values in ([.5, -1.], [.5, True], [1., 1.], list(range(2, 14)), ["1", "2"], [1., float("inf")]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                proposal.call("set_parameter_study", {"input": "parameters/length", "values": values})
            self.assertEqual(proposal.study, saved)
        with self.assertRaisesRegex(ValueError, "exact input"):
            proposal.call("set_parameter_study", {"input": "parameters/__proto__", "values": [.5, 2.]})
        with self.assertRaisesRegex(ValueError, "explicit latest-human"):
            proposal.call("request_study_run", {})
        proposal.call("load_example", {"id": "mass-spring"})
        self.assertIsNone(proposal.study)

    def test_http_study_response_has_no_proposed_baseline_or_solver_execution(self):
        body = {"model": self.model, "message": "Set up a length study at 0.5, 1 and 2 m, then run the study.", "chatModel": "test-local:4b"}
        responses = [assistant([("set_parameter_study", {"input": "parameters/length", "values": [.5, 1., 2.]}), ("request_study_run", {})]), assistant()]
        with service(responses) as (client, requests):
            result = agent.chat(body, client)
        self.assertIsNone(result["proposedModel"])
        self.assertEqual(result["proposedStudy"]["values"], [.5, 1., 2.])
        self.assertTrue(result["studyRunRequested"])
        self.assertFalse(result["runRequested"])
        self.assertTrue(all(path in ("/api/tags", "/api/show", "/api/chat") for path, _ in requests))
        self.assertEqual(body["model"], self.model)

    def test_live_joint_frames_reuse_valid_existing_geometry_and_reject_wrong_bodies(self):
        model = self.spatial
        joint = model["joints"][0]
        model["frames"] = [dict(id="datumA", name="Picked datum A", body=joint["a"], translation=deepcopy(joint["anchorA"]), rotation=dict(rx=0., ry=0., rz=0.)),
                           dict(id="datumB", name="Picked datum B", body=joint["b"], translation=deepcopy(joint["anchorB"]), rotation=dict(rx=0., ry=0., rz=0.))]
        links = [dict(joint=joint["id"], side=side, frame="datum"+side.upper(), axis=max(joint["axis"+side.upper()], key=lambda key: joint["axis"+side.upper()][key])) for side in ("a", "b")]
        proposal = agent.Proposal(model, "Link both named datums to the hinge. Do not run.")
        result = proposal.call("link_joint_frames", {"links": links})
        self.assertTrue(result["accepted"], result)
        self.assertEqual(proposal.model["frameLinks"], links)
        saved = deepcopy(proposal.model)
        wrong = {**links[0], "frame": "datumB"}
        with self.assertRaisesRegex(ValueError, "belong"):
            proposal.call("link_joint_frames", {"links": [wrong]})
        with self.assertRaisesRegex(ValueError, "one live frame link"):
            proposal.call("link_joint_frames", {"links": [links[0], links[0]]})
        self.assertEqual(proposal.model, saved)

    def test_recorded_result_summary_is_bounded_fresh_and_never_reads_csv_or_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); run_id = "a" * 32; run = root / run_id; run.mkdir()
            data = dict(ok=True, source="MBDyn", runId=run_id, model=self.model,
                        metrics={"duration": 5., "peakConstraintError": .001, "privateString": "not exported", "nested": {"anything": 1}}, units={"time": "s"}, log="private log not exported")
            (run / "summary.json").write_text(json.dumps(data))
            (run / "results.csv").write_text("private full resolution CSV")
            with patch.object(agent.app_paths, "RUNS", root), patch.object(agent.app_paths, "LEGACY_RUNS", root):
                summary = agent.result_summary(run_id, self.model)
                self.assertTrue(summary["available"])
                self.assertEqual(summary["metrics"], {"duration": 5., "peakConstraintError": .001})
                self.assertNotIn("log", summary)
                self.assertNotIn("samples", summary)
                changed = deepcopy(self.model); changed["parameters"]["length"] = 2.
                self.assertFalse(agent.result_summary(run_id, changed)["available"])
                self.assertFalse(agent.result_summary("b" * 32, self.model)["available"])
                with (run / "summary.json").open("wb") as handle:
                    handle.truncate(32 * 1024 * 1024 + 1)
                with self.assertRaisesRegex(ValueError, "bounded read"):
                    agent.result_summary(run_id, self.model)

    def test_result_identifier_and_model_name_cannot_inject_paths_or_control_text(self):
        for run_id in ("../private", "x" * 32, "a" * 33, 42):
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                agent.result_summary(run_id, self.model)
        proposal = agent.Proposal(self.model, "Rename it Robot arm.")
        self.assertTrue(proposal.call("set_model_name", {"name": "Robot arm"})["accepted"])
        for name in ("", "\nRobot", "a" * 121):
            with self.assertRaises(ValueError):
                proposal.call("set_model_name", {"name": name})
        self.assertEqual(proposal.model["name"], "Robot arm")


if __name__ == "__main__":
    unittest.main()
