"""Pinned, separately licensed upstream input files; no arbitrary deck upload or paths."""

import csv
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import time
import uuid

import solver

ROOT = Path(__file__).resolve().parents[1] / "examples" / "open-source"
FIELDS = ("x", "y", "z", "rx", "ry", "rz", "vx", "vy", "vz", "wx", "wy", "wz")


def catalog():
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))["examples"]


def resolve_entry(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9-]{1,80}", identifier):
        raise ValueError("Choose a known source-example ID; paths and uploaded decks are not accepted.")
    entry = next((item for item in catalog() if item["id"] == identifier), None)
    if entry is None:
        raise ValueError("Unknown source-example ID.")
    if not entry.get("enabled") or entry.get("validation", {}).get("status") != "verified":
        raise ValueError("This source example has not passed a real solver run and is not enabled.")
    return entry


def checked_file(relative, digest):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError("Source-example file is missing or outside the curated library.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError(f"Source-example integrity mismatch: {relative}. Restore the pinned file before running.")
    return path


def validate_model(model):
    try:
        if not isinstance(model, dict) or model.get("kind") != "source-example":
            raise ValueError("Expected a source-example model.")
        if set(model) - {"schemaVersion", "kind", "name", "title", "sourceExampleId", "sourceRevision", "sourceHashes", "parameters", "simulation"}:
            raise ValueError("Unexpected source-example model fields.")
        entry = resolve_entry(model.get("sourceExampleId"))
        if model.get("sourceRevision", entry["source"]["revision"]) != entry["source"]["revision"]:
            raise ValueError("Saved source revision does not match the curated input revision.")
        hashes = [item["sha256"] for item in entry["files"]]
        if model.get("sourceHashes", hashes) != hashes:
            raise ValueError("Saved source hashes do not match the curated input bundle.")
        if model.get("parameters", {}) != {} or model.get("simulation", entry["simulation"]) != entry["simulation"]:
            raise ValueError("Upstream studies are pinned read-only inputs; parameter or time-setting overrides are not supported.")
        for item in entry["files"]:
            checked_file(item["path"], item["sha256"])
        return {"valid": True, "issues": [], "summary": {"nodeCount": len(entry["nodes"]), "duration": entry["simulation"]["duration"],
                "license": entry["license"]["spdx"], "scope": "Pinned upstream input and recorded compatibility; not a fresh solver run."}}
    except (OSError, ValueError) as exc:
        return {"valid": False, "issues": [{"level": "error", "field": "sourceExampleId", "message": str(exc)}], "summary": {}}


def deck_for_model(model):
    check = validate_model(model)
    if not check["valid"]:
        return check
    entry = resolve_entry(model["sourceExampleId"])
    item = next(file for file in entry["files"] if file["runPath"] == entry["entrypoint"])
    return {**check, "deck": checked_file(item["path"], item["sha256"]).read_text(encoding="utf-8"), "filename": entry["entrypoint"]}


def parse_output(directory, entry):
    """Match actual written time steps to complete, finite native structural-node frames."""
    for name in ("result.out", "result.mov", "result.log"):
        if (directory / name).stat().st_size > 64 * 1024 * 1024:
            raise ValueError(f"{name} exceeds the 64-MiB source-example parsing limit.")
    times = []
    with (directory / "result.out").open() as stream:
        for line in stream:
            fields = line.split()
            if len(fields) == 9 and fields[0] == "Step" and fields[8] == "1":
                times.append(float(fields[2]))
    if len(times) < 2 or not all(math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Missing, non-finite or non-increasing output timestamps.")
    duration, step = entry["simulation"]["duration"], entry["simulation"]["step"]
    if times[-1] < duration - step * 0.1 or times[-1] > duration + step * 1.1:
        raise ValueError("Solver did not reach the curated model's requested final time.")
    labels = [node["id"] for node in entry["nodes"]]
    if len(set(labels)) != len(labels):
        raise ValueError("Duplicate node IDs in source-example catalog.")
    orientations = {}
    with (directory / "result.log").open() as stream:
        for line in stream:
            fields = line.split()
            if fields[:2] == ["structural", "node:"] and len(fields) >= 7:
                orientations[int(fields[2])] = fields[6]
    if any(orientations.get(node) != "euler123" for node in labels):
        raise ValueError("Expected native Euler123 orientation output for every curated node.")
    rows = []
    with (directory / "result.mov").open() as stream:
        for line in stream:
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 13:
                raise ValueError("Unexpected native structural-node record width.")
            node_id = int(fields[0])
            values = [float(value) for value in fields[1:]]
            if node_id not in labels or not all(math.isfinite(value) for value in values):
                raise ValueError("Unexpected node or non-finite native node output.")
            rows.append({"id": node_id, **dict(zip(FIELDS, values))})
    if len(rows) != len(times) * len(labels):
        raise ValueError("Time/node output mismatch; incomplete trajectories are not results.")
    samples = []
    for index, timestamp in enumerate(times):
        nodes = rows[index * len(labels):(index + 1) * len(labels)]
        if [node["id"] for node in nodes] != labels:
            raise ValueError("Missing, repeated or reordered node in a native output frame.")
        samples.append({"time": timestamp, "nodes": nodes})
    return samples


def run(identifier, control=None):
    try:
        entry = resolve_entry(identifier)
        sources = [(item, checked_file(item["path"], item["sha256"])) for item in entry["files"]]
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}, 422
    if control and control.requested:
        return {"ok":False,"cancelled":True,"error":"Simulation cancelled before solver launch."}, 409
    info = solver.status()
    if control and control.requested:
        return {"ok":False,"cancelled":True,"error":"Simulation cancelled before solver launch."}, 409
    if not info["available"]:
        return {"ok": False, "error": "MBDyn is unavailable. No source-example result was generated.", "solver": info}, 503
    run_id = uuid.uuid4().hex
    directory = solver.RUNS / run_id
    directory.mkdir(parents=True)
    result = {"ok": False, "source": "MBDyn", "runId": run_id,
              "model": {"kind": "source-example", "name": entry["title"], "title": entry["title"], "sourceExampleId": identifier,
                        "sourceRevision": entry["source"]["revision"], "sourceHashes": [item["sha256"] for item in entry["files"]],
                        "parameters": {}, "simulation": entry["simulation"]},
              "example": entry, "solver": info,
              "files": {key: f"/api/runs/{run_id}/{name}" for key, name in
                        (("deck", "model.mbd"), ("log", "solver.log"), ("csv", "results.csv"), ("project", "project.json"),
                         ("summary", "summary.json"), ("motion", "result.mov"), ("time", "result.out"), ("structure", "result.log"))}}
    start = time.monotonic()
    try:
        for item, source in sources:
            destination = (directory / item["runPath"]).resolve()
            if not destination.is_relative_to(directory.resolve()):
                raise ValueError("Curated run path escapes the run directory.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        main = (directory / entry["entrypoint"]).resolve()
        if not main.is_relative_to(directory.resolve()) or not main.is_file():
            raise ValueError("Curated entrypoint is missing or outside the run directory.")
        # Keep the exact deck downloadable under the existing run-artifact route.
        if main != directory / "model.mbd":
            shutil.copyfile(main, directory / "model.mbd")
        result["deckSha256"] = hashlib.sha256(main.read_bytes()).hexdigest()
        (directory / "project.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
        config = solver.configuration()
        is_wsl=bool(control) and config["mode"] == "wsl"
        argv = solver.command(config, ["-f", entry["entrypoint"], "-o", "result"], directory, bounded=True, cancellable=is_wsl)
        outcome = solver.execute(argv, directory, control=control, wsl=is_wsl)
        result.update(outcome)
        if "error" in outcome:
            raise ValueError(outcome["error"])
        if "MBDyn terminated normally" not in (directory / "solver.log").read_text(errors="replace"):
            raise ValueError("Solver did not report normal termination.")
        samples = parse_output(directory, entry)
        with (directory / "results.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["time", "id", *FIELDS])
            writer.writeheader()
            for sample in samples:
                writer.writerows({"time": sample["time"], **node} for node in sample["nodes"])
        initial = {node["id"]: node for node in samples[0]["nodes"]}
        max_motion = max(math.dist([node[key] for key in ("x", "y", "z")], [initial[node["id"]][key] for key in ("x", "y", "z")])
                         for sample in samples for node in sample["nodes"])
        stride = max(1, math.ceil((len(samples) - 1) / 2000))
        displayed = samples[::stride]
        if displayed[-1] != samples[-1]:
            displayed.append(samples[-1])
        result.update(ok=True, samples=displayed, displaySampleCount=len(displayed),
                      metrics={"duration": samples[-1]["time"], "sampleCount": len(samples), "nodeCount": len(entry["nodes"]),
                               "maxNodeDisplacement": max_motion})
    except (OSError, ValueError, ArithmeticError) as exc:
        result["error"] = str(exc)
    result["elapsedSeconds"] = time.monotonic() - start
    log = directory / "solver.log"
    if log.exists():
        with log.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 12000))
            result["log"] = stream.read().decode("utf-8", errors="replace")
    (directory / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    return result, 200 if result["ok"] else 409 if result.get("cancelled") else 422
