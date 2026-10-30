"""Every project shipped in examples/ opens under the 1.x compatibility rules of docs/project-format.md."""
import json
from pathlib import Path
import unittest

import models
import spatial_assembly as spatial

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = sorted((ROOT / "examples").rglob("*.mbdyn-studio"))
TOP_LEVEL = {"format", "schemaVersion", "model", "result", "view", "assets"}


class ProjectCompatibilityTests(unittest.TestCase):
    def test_the_corpus_is_not_empty(self):
        self.assertGreaterEqual(len(PROJECTS), 10)

    def test_projects_use_format_one_and_validate(self):
        for path in PROJECTS:
            with self.subTest(project=str(path.relative_to(ROOT))):
                self.assertLessEqual(path.stat().st_size, 32 * 1024 * 1024)
                project = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(project["format"], "mbdyn-studio/1")
                self.assertIn(project.get("schemaVersion", 1), (1,))
                self.assertTrue(set(project) <= TOP_LEVEL, sorted(set(project) - TOP_LEVEL))
                model = project["model"]
                self.assertTrue(isinstance(model.get("kind"), str) and isinstance(model.get("name"), str))
                check = models.validate(model)
                self.assertTrue(check["valid"], check.get("issues", [])[:2])
                self.assertTrue(set(project.get("assets") or {}) <= {"step", "reference"})
                self.assertIsInstance(project.get("view") or {}, dict)

    def test_optional_fields_have_defaults(self):
        # A minimal project of the oldest shape: format and model only.
        minimal = {"format": "mbdyn-studio/1", "model": json.loads(PROJECTS[0].read_text(encoding="utf-8"))["model"]}
        self.assertTrue(models.validate(minimal["model"])["valid"])
        self.assertNotIn("schemaVersion", minimal)

    def test_unknown_model_fields_are_refused_rather_than_ignored(self):
        # A model using a feature this release does not know must not be solved without it.
        project = json.loads((ROOT / "examples" / "robot-arm" / "robot-arm.mbdyn-studio").read_text(encoding="utf-8"))
        check = spatial.validate(dict(project["model"], futureOption={"enabled": True}))
        self.assertFalse(check["valid"])
        self.assertIn({"level": "error", "field": "futureOption", "message": "Unsupported field."}, check["issues"])


if __name__ == "__main__":
    unittest.main()
