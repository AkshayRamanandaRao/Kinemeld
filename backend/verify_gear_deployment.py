"""Repeatable real MBDyn four-bar checks, including a second geometry and refined step."""

import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import gear_deployment as gear
import solver


def run_case(model, name):
    result, status = solver.run(model)
    assert status == 200 and result.get("ok"), result
    directory = solver.RUNS / result["runId"]
    s = model["simulation"]
    contents = (directory / "model.mbd").read_text(encoding="utf-8")
    metrics = result["metrics"]
    assert s["duration"]-s["step"]*.1 <= metrics["duration"] <= s["duration"]+s["step"]*1.1
    assert metrics["maxConstraintError"] < 2e-5, metrics
    assert metrics["maxGeometryError"] < 2e-5, metrics
    assert metrics["maxDriveAngleError"] < .002, metrics
    record = {"name": name, "passed": True, "model": model, "metrics": metrics, "exitCode": result["exitCode"],
              "deckSha256": result["deckSha256"], "directory": str(directory), "runId": result["runId"],
              "elapsedSeconds": result["elapsedSeconds"]}
    print(json.dumps(record), flush=True)
    return record, contents


def main():
    examples = Path(__file__).resolve().parents[1] / "examples"
    first = copy.deepcopy(gear.DEFAULT)
    records = []
    record, contents = run_case(first, "default")
    records.append(record)
    examples.joinpath("gear-deployment.json").write_text(json.dumps(first, indent=2)+"\n", encoding="utf-8")
    examples.joinpath("gear-deployment.mbd").write_text(contents, encoding="utf-8")
    second = copy.deepcopy(first)
    second["parameters"].update(mainLength=1.35, braceAttachment=.5, upperBraceLength=.7, lowerBraceLength=.65,
                                groundX=.72, groundZ=-.16, initialAngle=-55, finalAngle=8, mainMass=32, upperBraceMass=5)
    records.append(run_case(second, "changed-geometry")[0])
    refined = copy.deepcopy(first)
    refined["simulation"]["step"] /= 2
    records.append(run_case(refined, "refined-step")[0])
    reverse = copy.deepcopy(first)
    reverse["parameters"].update(initialAngle=0, finalAngle=-65)
    records.append(run_case(reverse, "reverse-kinematic-sweep")[0])
    evidence = {"passed": True, "verifiedAtUtc": datetime.now(timezone.utc).isoformat(),
                "sourceModuleSha256": hashlib.sha256(Path(gear.__file__).read_bytes()).hexdigest(),
                "solver": solver.status(), "cases": records,
                "assertedLimits": {"maxConstraintErrorM": 2e-5, "maxGeometryErrorM": 2e-5, "maxDriveAngleErrorDeg": .002},
                "scope": "Shared solver.run application route: original generic prescribed closed four-bar with three moving massive links. Independent circle intersection comparison, changed geometry, reverse sweep and step refinement.",
                "limitations": "No authentic aircraft dimensions, hydraulic force, locks, aero, flexibility, strength or certification claim."}
    Path(__file__).with_name("evidence").joinpath("gear-deployment-verification.json").write_text(json.dumps(evidence, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
