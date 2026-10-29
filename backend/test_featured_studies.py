"""Structural checks for the featured study catalog and its saved projects."""
import base64
import hashlib
import json
from pathlib import Path
import unittest

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
                project = json.loads((ROOT / "examples" / study["project"]).read_text(encoding="utf-8"))
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


if __name__ == "__main__":
    unittest.main()
