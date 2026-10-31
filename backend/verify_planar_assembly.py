"""Real-solver qualification of the supported graph subset, not a preview solver."""

import copy
import hashlib
import json
import math
from pathlib import Path

import planar_assembly as assembly
import solver

ROOT = Path(__file__).resolve().parents[1]


def rk4(state, derivative, step):
    a = derivative(state)
    b = derivative([x + step * v / 2 for x, v in zip(state, a)])
    c = derivative([x + step * v / 2 for x, v in zip(state, b)])
    d = derivative([x + step * v for x, v in zip(state, c)])
    return [x + step * (v + 2 * w + 2 * y + z) / 6 for x, v, w, y, z in zip(state, a, b, c, d)]


def reference_error(model, samples):
    """Independent single/double rigid-pendulum Lagrange equations; no deck/parser helpers."""
    bodies = model["bodies"]
    gravity = model["parameters"]["gravity"]
    if len(bodies) == 1:
        body = bodies[0]
        mass, inertia, distance = body["mass"], body["inertia"]["yy"], .5
        state = [math.radians(body["pose"]["angleDeg"]), body["velocity"]["omega"]]
        def derivative(q):
            return [q[1], -mass * gravity * distance * math.sin(q[0]) / (inertia + mass * distance ** 2)]
        indices = [0]
    else:
        m1, m2 = bodies[0]["mass"], bodies[1]["mass"]
        d1, d2, length1 = .5, .35, 1.
        aa = bodies[0]["inertia"]["yy"] + m1 * d1 ** 2 + m2 * length1 ** 2
        bb = bodies[1]["inertia"]["yy"] + m2 * d2 ** 2
        cc = m2 * length1 * d2
        state = [math.radians(body["pose"]["angleDeg"]) for body in bodies] + [0., 0.]
        def derivative(q):
            theta1, theta2, omega1, omega2 = q
            delta = theta1 - theta2
            coupling = cc * math.cos(delta)
            rhs1 = -cc * math.sin(delta) * omega2 ** 2 - (m1 * d1 + m2 * length1) * gravity * math.sin(theta1)
            rhs2 = cc * math.sin(delta) * omega1 ** 2 - m2 * d2 * gravity * math.sin(theta2)
            determinant = aa * bb - coupling ** 2
            return [omega1, omega2, (bb * rhs1 - coupling * rhs2) / determinant, (aa * rhs2 - coupling * rhs1) / determinant]
        indices = [0, 1]
    errors, time = [], 0.
    for sample in samples:
        target = sample["time"]
        while target - time > 1e-12:
            step = min(model["simulation"]["step"] / 4, target - time)
            state = rk4(state, derivative, step)
            time += step
        for index in indices:
            error = math.radians(sample["nodes"][index]["angleDeg"]) - state[index]
            errors.append(abs(math.degrees(math.atan2(math.sin(error), math.cos(error)))))
    return max(errors)


def run_case(identifier, model, reference=False):
    before = copy.deepcopy(model)
    result, status = solver.run(model)
    record = {"id": identifier, "runId": result.get("runId"), "ok": result["ok"], "httpStatus": status,
              "exitCode": result.get("exitCode"), "deckSha256": result.get("deckSha256"), "solver": result.get("solver")}
    if not result["ok"]:
        record["error"] = result.get("error")
        print(json.dumps(record), flush=True)
        return record
    directory = solver.RUNS / result["runId"]
    samples = assembly.parse_output(directory, model)
    record["metrics"] = result["metrics"]
    record["modelSha256"] = hashlib.sha256((directory / "project.json").read_bytes()).hexdigest()
    record["checks"] = {
        "originalModelRetained": result["model"] == before and json.loads((directory / "project.json").read_text()) == before,
        "normalTermination": "MBDyn terminated normally" in (directory / "solver.log").read_text(),
        "nodeIdentities": all([node["id"] for node in frame["nodes"]] == [body["id"] for body in model["bodies"]] for frame in samples),
        "hingePositionClosure": result["metrics"]["maxConstraintError"] < 1e-7,
        "hingeVelocityClosure": result["metrics"]["maxJointVelocityError"] < 2e-4,
        "energyDrift": result["metrics"]["relativeEnergyDrift"] < 2e-5,
    }
    if reference:
        record["independentMaxAngleErrorDeg"] = reference_error(model, samples)
        record["checks"]["independentLagrangeMotion"] = record["independentMaxAngleErrorDeg"] < .02
    if identifier == "constant-rotation":
        body = model["bodies"][0]
        errors = [abs(math.atan2(math.sin(math.radians(q["nodes"][0]["angleDeg"]) - body["velocity"]["omega"] * q["time"]),
                                     math.cos(math.radians(q["nodes"][0]["angleDeg"]) - body["velocity"]["omega"] * q["time"]))) for q in samples]
        record["constantRotationMaxErrorRad"] = max(errors)
        record["checks"]["constantRotationAcrossEulerBranches"] = max(errors) < 1e-6
    record["passed"] = all(record["checks"].values())
    print(json.dumps(record), flush=True)
    return record


def main():
    results = [run_case(example["id"], copy.deepcopy(example["model"]), index < 2) for index, example in enumerate(assembly.EXAMPLES)]
    # A fourth independently authored graph exercises initial angular velocity and
    # orientation branches; it is not selected by any model-family special case.
    rotor = copy.deepcopy(assembly.EXAMPLES[0]["model"])
    rotor["name"] = "Zero-gravity centered rigid rotor"
    rotor["simulation"]["step"] = .0005
    rotor["parameters"]["gravity"] = 0.
    rotor["bodies"][0]["pose"] = {"x": 0., "z": 0., "angleDeg": 0.}
    rotor["bodies"][0]["velocity"]["omega"] = 1.3
    rotor["joints"][0]["childAnchor"] = {"x": 0., "z": 0.}
    results.append(run_case("constant-rotation", rotor))
    # The same graph with different serialization order must retain identity and motion.
    reordered = copy.deepcopy(assembly.EXAMPLES[1]["model"])
    reordered["bodies"].reverse()
    reordered["joints"].reverse()
    results.append(run_case("reordered-chain", reordered))
    if results[1].get("ok") and results[-1].get("ok"):
        original = assembly.parse_output(solver.RUNS / results[1]["runId"], assembly.EXAMPLES[1]["model"])
        changed = assembly.parse_output(solver.RUNS / results[-1]["runId"], reordered)
        maximum = max(abs(a[key] - next(b for b in new["nodes"] if b["id"] == a["id"])[key])
                      for old, new in zip(original, changed) for a in old["nodes"] for key in ("x", "z", "angleDeg"))
        results[-1]["maxReorderDifference"] = maximum
        results[-1]["checks"]["serializationOrderInvariant"] = len(original) == len(changed) and maximum < 1e-7
        results[-1]["passed"] = all(results[-1]["checks"].values())
    refined = copy.deepcopy(assembly.EXAMPLES[1]["model"])
    refined["simulation"]["step"] /= 2
    results.append(run_case("refined-chain", refined, True))
    if results[1].get("ok") and results[-1].get("ok"):
        ratio = results[1]["independentMaxAngleErrorDeg"] / max(1e-12, results[-1]["independentMaxAngleErrorDeg"])
        results[-1]["angleErrorRefinementRatio"] = ratio
        results[-1]["checks"]["timeStepConvergence"] = ratio > 3
        results[-1]["passed"] = all(results[-1]["checks"].values())
    report = {"scope": "Actual MBDyn planar rigid-body trees: original single, serial, branched, rotating and reordered graphs.",
              "limitations": "Does not validate contact, loops, prismatic joints, drivers, flexible bodies, physical hardware or agreement with other multibody codes.",
              "passed": all(item.get("passed", False) for item in results), "cases": results}
    path = ROOT / "verification" / "planar-assembly.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(path), "passed": report["passed"]}))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
