"""Separate immutable application resources from optional per-user writable data."""
import os
from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parents[1]
_setting = os.environ.get("MBDYN_STUDIO_DATA_DIR")
if _setting is not None and (not _setting.strip() or not Path(_setting).is_absolute()):
    raise ValueError("MBDYN_STUDIO_DATA_DIR must be an absolute writable directory.")
DATA_ROOT = Path(_setting).resolve() if _setting is not None else RESOURCE_ROOT
SEPARATE_DATA = DATA_ROOT != RESOURCE_ROOT
RUNS = DATA_ROOT / "runs"
LEGACY_RUNS = RESOURCE_ROOT / "runs"
SOLVER_CONFIG = DATA_ROOT / "solver.json" if SEPARATE_DATA else RESOURCE_ROOT / "backend" / "solver.json"
AGENT_CONFIG = DATA_ROOT / "agent.json" if SEPARATE_DATA else RESOURCE_ROOT / "backend" / "agent.json"
LEGACY_SOLVER_CONFIG = RESOURCE_ROOT / "backend" / "solver.json"
LEGACY_AGENT_CONFIG = RESOURCE_ROOT / "backend" / "agent.json"
TOUR_PREFERENCE = RUNS / "tour-preference.json"
LEGACY_TOUR_PREFERENCE = LEGACY_RUNS / "tour-preference.json"


def existing_config(path, user_path, legacy_path):
    """Prefer an explicit user file, then read the former installation file unchanged."""
    if path == user_path and SEPARATE_DATA and not path.exists() and legacy_path.exists():
        return legacy_path
    return path


def run_directory(run_id, runs=None):
    """Choose one complete run directory; never combine artifacts from different roots."""
    root = RUNS if runs is None else runs
    current = root / run_id
    if root == RUNS and SEPARATE_DATA and not current.exists():
        return LEGACY_RUNS / run_id
    return current
