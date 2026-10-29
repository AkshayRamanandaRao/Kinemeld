"""Structural checks for the featured study catalog and its saved projects."""
import base64
import hashlib
import json
from pathlib import Path
import unittest

import featured
import spatial_assembly as spatial
from server import featured_catalog

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "quarter-car": {"forces", "loads"},
    "gear-drop": {"forces", "contacts"},
    "slider-crank": {"forces", "jointTorques"},
    "gyroscopic-top": set(),
    "tumbling-handle": set(),
    "chaotic-pendulums": set(),
    "aircraft-nose-gear": set(),
    "oleo-strut": {"forces"},
    "wheel-end-drop": {"contacts"},
    "robot-arm": set(),
}


class FeaturedStudyTests(unittest.TestCase):
    def test_catalog_lists_existing_unique_projects(self):
        studies = featured_catalog()
        raw = json.loads((ROOT / "examples" / "featured.json").read_text(encoding="utf-8"))["studies"]
        self.assertEqual(len(studies), len(raw), "Every catalog entry must point to an existing project.")
        self.assertEqual(len({s["id"] for s in studies}), len(studies))
        self.assertEqual(len({s["title"] for s in studies}), len(studies))
        self.assertTrue(REQUIRED.keys() <= {s["id"] for s in studies})

    def test_projects_validate_with_their_element_groups_and_geometry(self):
        for study in featured_catalog():
            with self.subTest(study=study["id"]):
                project = featured.project(study)
                model = project["model"]
                self.assertEqual(project["format"], "mbdyn-studio/1")
                check = spatial.validate(model)
                self.assertTrue(check["valid"], check["issues"])
                for group in REQUIRED.get(study["id"], set()):
                    self.assertTrue(model.get(group), f"{study['id']} lost its {group}")
                step = project["assets"]["step"]
                body_ids = {b["id"] for b in model["bodies"]}
                self.assertTrue(set(step["bindings"]) <= set(step["occurrenceWitnesses"]))
                self.assertTrue({b["body"] for b in step["bindings"].values()} <= body_ids)
                for source in step["files"]:
                    data = base64.b64decode(source["data"])
                    self.assertEqual(hashlib.sha256(data).hexdigest(), source["sha256"])
                if study["id"] in REQUIRED:
                    view = project["view"]
                    self.assertEqual(len(view["camera"]), 3)
                    self.assertIsInstance(view["signal"], int)

    def test_overlays_leave_saved_projects_unchanged(self):
        for study in featured_catalog():
            if "overlay" not in study:
                continue
            with self.subTest(study=study["id"]):
                path = ROOT / "examples" / study["project"]
                before = path.read_text(encoding="utf-8")
                opened = featured.project(study)
                self.assertEqual(path.read_text(encoding="utf-8"), before)
                for joint_id, motion in study["overlay"].get("jointMotion", {}).items():
                    self.assertEqual(next(j for j in opened["model"]["joints"] if j["id"] == joint_id)["motion"], motion)
                if "simulation" in study["overlay"]:
                    self.assertEqual(opened["model"]["simulation"], study["overlay"]["simulation"])

    def test_overlay_rejects_unknown_fields_and_unprescribed_joints(self):
        project = {"model": {"joints": [{"id": "hinge", "type": "revolute"}]}}
        with self.assertRaises(ValueError):
            featured.apply_overlay(project, {"camera": [0, 0, 1]})
        with self.assertRaises(ValueError):
            featured.apply_overlay(project, {"jointMotion": {"hinge": {"amplitude": 1, "frequencyHz": 1}}})


if __name__ == "__main__":
    unittest.main()
