"""Featured studies: saved projects listed in examples/featured.json.

An entry may carry a documented overlay that is applied when the study is opened, so a
verified example project can be shown with a longer study, a larger prescribed motion or a
display preset without changing the project file its own guide and checks refer to.
"""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
OVERLAY_KEYS = {"name", "simulation", "jointMotion", "view"}


def catalog():
    """Catalog entries whose project file exists inside examples/."""
    entries = json.loads((EXAMPLES / "featured.json").read_text(encoding="utf-8"))["studies"]
    base = EXAMPLES.resolve()
    studies = []
    for item in entries:
        project = (base / item["project"]).resolve()
        if project.is_relative_to(base) and project.suffix == ".mbdyn-studio" and project.is_file():
            studies.append(item)
    return studies


def apply_overlay(project, overlay):
    """Return a copy of a saved project with the entry's overlay applied."""
    unknown = set(overlay) - OVERLAY_KEYS
    if unknown:
        raise ValueError(f"Unknown featured overlay fields: {sorted(unknown)}")
    result = copy.deepcopy(project)
    model = result["model"]
    if "name" in overlay:
        model["name"] = overlay["name"]
    if "simulation" in overlay:
        model["simulation"] = dict(overlay["simulation"])
    joints = {joint["id"]: joint for joint in model.get("joints", [])}
    for joint_id, motion in overlay.get("jointMotion", {}).items():
        if joint_id not in joints or "motion" not in joints[joint_id]:
            raise ValueError(f"Featured overlay changes the motion of {joint_id}, which has no prescribed motion.")
        joints[joint_id]["motion"] = dict(motion)
    if "view" in overlay:
        result["view"] = dict(overlay["view"])
    return result


def project(item):
    """The project a featured entry opens, with its overlay applied."""
    saved = json.loads((EXAMPLES / item["project"]).read_text(encoding="utf-8"))
    return apply_overlay(saved, item.get("overlay", {}))
