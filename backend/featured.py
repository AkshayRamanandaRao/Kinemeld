"""Featured studies: saved projects listed in examples/featured.json.

An entry may carry a documented overlay that is applied when the study is opened, so a
verified example project can be shown with a longer study, a larger prescribed motion or a
display preset without changing the project file its own guide and checks refer to. It may
also define a parameter study (an input path, values and a response quantity) that the
interface preloads; the project's view carries it as `study`.
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
    """The project a featured entry opens, with its overlay and parameter study applied."""
    saved = json.loads((EXAMPLES / item["project"]).read_text(encoding="utf-8"))
    result = apply_overlay(saved, item.get("overlay", {}))
    if "study" in item:
        result["view"] = {**(result.get("view") or {}), "study": {key: item["study"][key] for key in ("input", "values", "response")}}
    return result


def _targets(model, path):
    """Containers and keys an input path addresses, as frontend/studies.js resolves them."""
    parts = path.split("/")
    if parts[0] == "parameters":
        items, keys = [model["parameters"]], parts[1:]
    else:
        items, keys = [item for item in model.get(parts[0], []) if parts[1] == "*" or item.get("id") == parts[1]], parts[2:]
    targets = []
    for item in items:
        container = item
        for key in keys[:-1]:
            container = container[key]
        targets.append((container, keys[-1]))
    return targets


def study_value(model, path):
    """The current value of a study input."""
    container, key = _targets(model, path)[0]
    return container[key]


def study_case(model, path, value):
    """A copy of `model` with the study input at `path` set to `value`."""
    result = copy.deepcopy(model)
    targets = _targets(result, path)
    if not targets or any(not isinstance(container.get(key), (int, float)) for container, key in targets):
        raise ValueError(f"Study input {path} does not exist in this model.")
    for container, key in targets:
        container[key] = value
    return result


def study_values(item):
    """Every case of an entry's study in the order the interface runs them: ascending, baseline included."""
    model = project(item)["model"]
    return sorted(set(item["study"]["values"]) | {study_value(model, item["study"]["input"])})
