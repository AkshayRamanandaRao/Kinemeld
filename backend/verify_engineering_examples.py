"""Trace engineering example inputs and verify their stated numerical idealizations.

Run from a checkout with configured MBDyn and OCP:
    python -B backend/verify_engineering_examples.py [nose-gear suspension landing-drop robot-arm]
Reports retain exact model/deck hashes and run IDs, never hardware-validation claims.
"""
import argparse
import base64
import copy
import hashlib
import json
import math
from pathlib import Path

from verify_spatial_assembly import run

ROOT = Path(__file__).resolve().parents[1]
STUDIES = {
    "nose-gear": "examples/open-aircraft-nose-kinematics/nose-gear-kinematics.mbdyn-studio",
    "suspension": "examples/open-suspension/suspension.mbdyn-studio",
    "landing-drop": "examples/landing-gear-3d/landing-gear-drop.mbdyn-studio",
    "robot-arm": "examples/robot-arm/robot-arm.mbdyn-studio",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def vector(value):
    return [value[k] for k in "xyz"]


def add(a, b):
    return [x + y for x, y in zip(a, b)]


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def cross(a, b):
    return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]


def transpose(a):
    return [list(row) for row in zip(*a)]


def matvec(a, b):
    return [sum(x*y for x, y in zip(row, b)) for row in a]


def matmul(a, b):
    return [[sum(x*y for x, y in zip(row, col)) for col in zip(*b)] for row in a]


def rotation(pose):
    a, b, c = (math.radians(pose.get(k, 0)) for k in ("rx", "ry", "rz"))
    ca, sa, cb, sb, cc, sc = math.cos(a), math.sin(a), math.cos(b), math.sin(b), math.cos(c), math.sin(c)
    return [[cb*cc, -cb*sc, sb], [ca*sc+sa*sb*cc, ca*cc-sa*sb*sc, -sa*cb],
            [sa*sc-ca*sb*cc, sa*cc+ca*sb*sc, ca*cb]]


def world_point(body, point):
    if body is None:
        return vector(point)
    matrix = body.get("rotationMatrix")
    r = [matrix[i:i+3] for i in (0, 3, 6)] if matrix else rotation(body.get("pose", body))
    return add(vector(body.get("pose", body)), matvec(r, vector(point)))


def check_manifest(study, manifest=None, project=None):
    path = ROOT / STUDIES[study]
    manifest = manifest or json.loads(path.with_name("engineering.json").read_text(encoding="utf-8"))
    project = project or json.loads(path.read_text(encoding="utf-8"))
    model, step = project["model"], project["assets"]["step"]
    if manifest.get("format") != "kinemeld-engineering-example/1" or manifest.get("modelSha256") != digest(model):
        raise ValueError(f"{study}: engineering record no longer identifies the saved model")
    generator = ROOT / manifest["generator"]
    if hashlib.sha256(generator.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != manifest["generatorSha256Lf"]:
        raise ValueError(f"{study}: model generator changed; review and update engineering provenance")
    if manifest.get("hardwareValidation") != "not-performed" or not manifest.get("interpretationLimits"):
        raise ValueError(f"{study}: missing engineering interpretation boundary")
    if len(manifest["assets"]) != len(step["files"]):
        raise ValueError(f"{study}: CAD asset inventory differs")
    for expected, actual in zip(manifest["assets"], step["files"]):
        raw = base64.b64decode(actual["data"], validate=True)
        if actual["name"] != expected["name"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise ValueError(f"{study}: CAD source identity differs: {expected['name']}")
        if expected.get("sourcePath") and (ROOT / expected["sourcePath"]).read_bytes() != raw:
            raise ValueError(f"{study}: embedded CAD differs from retained source")
    if manifest["bindings"] != step["bindings"]:
        raise ValueError(f"{study}: body/CAD frame mapping differs")
    density = manifest["densityAssumptions"]
    expected_density = {key for key, binding in step["bindings"].items() if binding["body"] != "ground"}
    if len(density) != len(expected_density) or {item["binding"] for item in density} != expected_density or any(
            not isinstance(item.get("densityKgM3"), (int, float)) or not 0 < item["densityKgM3"] < 1e6 or
            item.get("body") != step["bindings"][item["binding"]]["body"] or
            not item.get("basis") or "assumption" not in item.get("status", "") for item in density):
        raise ValueError(f"{study}: density assumptions do not cover every dynamic CAD occurrence")
    bodies = {b["id"]: b for b in model["bodies"]}
    points = {(p["joint"], p["end"]): p for p in manifest["hardpoints"]}
    if len(points) != 2*len(model["joints"]):
        raise ValueError(f"{study}: hardpoint table is incomplete")
    for joint in model["joints"]:
        for end in ("A", "B"):
            entry = points[(joint["id"], end)]
            local, body_id = joint["anchor"+end], joint[end.lower()]
            world = world_point(bodies.get(body_id), local)
            if entry["body"] != body_id or entry["localM"] != local or math.dist(world, entry["worldM"]) > 1e-12 or not entry.get("basis"):
                raise ValueError(f"{study}: changed or untraced hardpoint {joint['id']}:{end}")
            if entry.get("axisLocal") != joint.get("axis"+end):
                raise ValueError(f"{study}: changed hardpoint axis {joint['id']}:{end}")
    if manifest["gravityM_s2"] != model["parameters"]["gravity"]:
        raise ValueError(f"{study}: gravity assumption differs")
    if manifest["initialVelocities"] != {b["id"]: b.get("velocity", {}) for b in model["bodies"]}:
        raise ValueError(f"{study}: initial state differs")
    if (manifest["forceLaws"] != model.get("forces", []) or manifest["contacts"] != model.get("contacts", []) or
            manifest["jointMotions"] != {j["id"]: j["motion"] for j in model["joints"] if "motion" in j}):
        raise ValueError(f"{study}: force/contact/motion assumptions differ")
    return manifest, project


def check_cad_mass(manifest, project):
    """Reintegrate each source solid at the explicitly recorded assumed density."""
    import step_mass
    step, grouped = project["assets"]["step"], {}
    for record in manifest["densityAssumptions"]:
        key = record["binding"]
        binding = step["bindings"][key]
        index, part = key.split(":", 1)
        raw = base64.b64decode(step["files"][int(index)]["data"], validate=True)
        witness = step.get("occurrenceWitnesses", {}).get(key)
        measured = step_mass.calculate(raw, record["densityKgM3"], part, witness)
        inverse = transpose(rotation(binding["pose"]))
        center = matvec(inverse, sub(vector(measured["centerOfMass"]), vector(binding["pose"])))
        tensor = matmul(matmul(inverse, measured["inertia"]), transpose(inverse))
        grouped.setdefault(binding["body"], []).append((measured["mass"], center, tensor))
    errors = []
    for body in project["model"]["bodies"]:
        parts = grouped[body["id"]]
        mass = sum(item[0] for item in parts)
        center = [sum(m*c[i] for m, c, _ in parts)/mass for i in range(3)]
        tensor = [[0.]*3 for _ in range(3)]
        for m, c, inertia in parts:
            delta = sub(c, center)
            for i in range(3):
                for j in range(3):
                    tensor[i][j] += inertia[i][j] + m*((sum(x*x for x in delta) if i == j else 0)-delta[i]*delta[j])
        given = body["inertia"]
        target = [[given["xx"], given.get("xy", 0), given.get("xz", 0)],
                  [given.get("xy", 0), given["yy"], given.get("yz", 0)],
                  [given.get("xz", 0), given.get("yz", 0), given["zz"]]]
        mass_error = abs(mass-body["mass"])
        center_error = math.dist(center, vector(body["centerOfMass"]))
        inertia_error = max(abs(tensor[i][j]-target[i][j]) for i in range(3) for j in range(3))
        if mass_error > 1e-6*max(1, mass) or center_error > 1e-7 or inertia_error > 1e-6:
            raise ValueError(f"CAD density integration differs for {body['id']}: {mass_error}, {center_error}, {inertia_error}")
        errors.append({"body": body["id"], "massKg": mass, "massErrorKg": mass_error,
                       "centerErrorM": center_error, "maxInertiaErrorKgM2": inertia_error})
    return errors


def circles(a, b, ra, rb, initial):
    distance = math.dist(a, b)
    if not abs(ra-rb) < distance < ra+rb:
        raise ValueError("Linkage reaches a circle tangency or has no real assembly branch")
    u = [(b[i]-a[i])/distance for i in range(2)]
    along = (ra*ra-rb*rb+distance*distance)/(2*distance)
    height = math.sqrt(max(0, ra*ra-along*along))
    center = [a[i]+along*u[i] for i in range(2)]
    options = [[center[0]+s*height*u[1], center[1]-s*height*u[0]] for s in (-1, 1)]
    return min(options, key=lambda p: math.dist(p, initial))


def nose_error(model, sample):
    bodies, joints = {b["id"]: b for b in model["bodies"]}, {j["id"]: j for j in model["joints"]}
    nodes = {n["id"]: n for n in sample["nodes"]}
    upper, lower = bodies["upper_link"]["pose"], bodies["lower_link"]["pose"]
    motion = joints["oleo"]["motion"]
    q = motion["amplitude"]*(1-math.cos(2*math.pi*motion["frequencyHz"]*sample["time"]))
    a, b = joints["scissor_pin"]["anchorA"], joints["scissor_pin"]["anchorB"]
    reference = circles([upper["y"], upper["z"]], [lower["y"], lower["z"]+q], math.hypot(a["y"], a["z"]),
                        math.hypot(b["y"], b["z"]), [upper["y"]+a["y"], upper["z"]+a["z"]])
    actual = world_point(nodes["upper_link"], a)
    slider = next(s for s in sample["sliders"] if s["id"] == "oleo")["position"]
    return max(math.dist(actual[1:], reference), abs(slider-q))


def suspension_error(model, sample):
    bodies, joints = {b["id"]: b for b in model["bodies"]}, {j["id"]: j for j in model["joints"]}
    nodes = {n["id"]: n for n in sample["nodes"]}
    upper = world_point(bodies["upper"], joints["upper_ball"]["anchorA"])
    lower = world_point(bodies["lower"], joints["lower_ball"]["anchorA"])
    pivot = vector(joints["upper_pivot"]["anchorA"])
    actual_lower = world_point(nodes["lower"], joints["lower_ball"]["anchorA"])
    actual_upper = world_point(nodes["upper"], joints["upper_ball"]["anchorA"])
    reference = circles([pivot[0], pivot[2]], [actual_lower[0], actual_lower[2]],
                        math.hypot(upper[0]-pivot[0], upper[2]-pivot[2]),
                        math.hypot(upper[0]-lower[0], upper[2]-lower[2]), [upper[0], upper[2]])
    return max(math.dist([actual_upper[0], actual_upper[2]], reference), abs(actual_lower[1]-lower[1]), abs(actual_upper[1]-upper[1]))


def drive_state(motion, time):
    if "speedDegPerS" in motion:
        speed, ramp = math.radians(motion["speedDegPerS"]), motion["rampTime"]
        return (speed*time*time/(2*ramp), speed*time/ramp, speed/ramp) if time < ramp else (speed*(time-ramp/2), speed, 0.)
    amplitude, rate = math.radians(motion["amplitudeDeg"]), 2*math.pi*motion["frequencyHz"]
    return amplitude*(1-math.cos(rate*time)), amplitude*rate*math.sin(rate*time), amplitude*rate*rate*math.cos(rate*time)


def arm_geometry(model, q):
    yaw, shoulder, elbow = q
    rz = [[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]]
    def ry(a):
        return [[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]]
    joints = {j["id"]: j for j in model["joints"]}
    base = vector(joints["base_yaw"]["anchorA"])
    shoulder_origin = add(base, matvec(rz, vector(joints["shoulder"]["anchorA"])))
    ru = matmul(rz, ry(shoulder))
    elbow_origin = add(shoulder_origin, matvec(ru, vector(joints["elbow"]["anchorA"])))
    frames = [(base, rz), (shoulder_origin, ru), (elbow_origin, matmul(rz, ry(shoulder+elbow)))]
    axes = [[0, 0, 1], matvec(rz, [0, 1, 0]), matvec(rz, [0, 1, 0])]
    origins = [base, shoulder_origin, elbow_origin]
    return frames, axes, origins


def arm_mass_matrix(model, q):
    frames, axes, origins = arm_geometry(model, q)
    matrix, gravity = [[0.]*3 for _ in range(3)], [0.]*3
    for index, (body, (position, r)) in enumerate(zip(model["bodies"], frames)):
        center = add(position, matvec(r, vector(body["centerOfMass"])))
        inertia = body["inertia"]
        tensor = [[inertia["xx"], inertia.get("xy", 0), inertia.get("xz", 0)],
                  [inertia.get("xy", 0), inertia["yy"], inertia.get("yz", 0)],
                  [inertia.get("xz", 0), inertia.get("yz", 0), inertia["zz"]]]
        world = matmul(matmul(r, tensor), transpose(r))
        jv = [cross(axes[i], sub(center, origins[i])) if i <= index else [0, 0, 0] for i in range(3)]
        jw = [axes[i] if i <= index else [0, 0, 0] for i in range(3)]
        for i in range(3):
            gravity[i] += body["mass"]*(-model["parameters"]["gravity"]["z"])*jv[i][2]
            for j in range(3):
                matrix[i][j] += body["mass"]*sum(a*b for a, b in zip(jv[i], jv[j])) + sum(a*b for a, b in zip(jw[i], matvec(world, jw[j])))
    return matrix, gravity


def arm_torque(model, q, velocity, acceleration):
    matrix, gravity = arm_mass_matrix(model, q)
    derivatives, epsilon = [], 1e-5
    for k in range(3):
        left, right = q.copy(), q.copy()
        left[k] -= epsilon
        right[k] += epsilon
        a, _ = arm_mass_matrix(model, left)
        b, _ = arm_mass_matrix(model, right)
        derivatives.append([[(b[i][j]-a[i][j])/(2*epsilon) for j in range(3)] for i in range(3)])
    return [gravity[i] + sum(matrix[i][j]*acceleration[j] for j in range(3)) +
            sum(.5*(derivatives[k][i][j]+derivatives[j][i][k]-derivatives[i][j][k])*velocity[j]*velocity[k]
                for j in range(3) for k in range(3)) for i in range(3)]


def arm_errors(model, sample):
    drives = {d["id"]: d for d in sample["rotaryDrives"]}
    states = [drive_state(j["motion"], sample["time"]) for j in model["joints"]]
    q, velocity, acceleration = ([state[i] for state in states] for i in range(3))
    frames, _, _ = arm_geometry(model, q)
    nodes = {n["id"]: n for n in sample["nodes"]}
    error = max(math.dist(vector(nodes[b["id"]]), frame[0]) for b, frame in zip(model["bodies"], frames))
    tip = world_point(nodes["forearm"], {"x": .36, "y": 0, "z": 0})
    expected_tip = add(frames[-1][0], matvec(frames[-1][1], [.36, 0, 0]))
    error = max(error, math.dist(tip, expected_tip))
    ramp = model["joints"][0]["motion"]["rampTime"]
    # Acceleration jumps at the ramp ends; compare torque only after a fixed 10 ms settling window.
    torque_error = None
    if min(sample["time"], abs(sample["time"]-ramp)) > .01:
        expected = arm_torque(model, q, velocity, acceleration)
        torque_error = max(abs(drives[j["id"]]["torque"]-tau) for j, tau in zip(model["joints"], expected))
    return error, torque_error


def drop_reference(model, samples):
    upper, wheel = model["bodies"]
    spring, contact = model["forces"][0], model["contacts"][0]
    gravity = -model["parameters"]["gravity"]["z"]
    state = [upper["pose"]["z"], wheel["pose"]["z"], upper["velocity"]["vz"], wheel["velocity"]["vz"]]
    def derivative(y):
        zu, zw, vu, vw = y
        force = spring["stiffness"]*(zu-zw-spring["restLength"]) + spring["damping"]*(vu-vw)
        tire = contact["stiffness"]*max(0, contact["radius"]-zw)
        return [vu, vw, -gravity-force/upper["mass"], -gravity+(force+tire)/wheel["mass"]]
    time, position_error, force_error = 0., 0., 0.
    for sample in samples:
        while sample["time"]-time > 1e-12:
            h = min(1e-5, sample["time"]-time)
            a = derivative(state)
            b = derivative([v+h*x/2 for v, x in zip(state, a)])
            c = derivative([v+h*x/2 for v, x in zip(state, b)])
            d = derivative([v+h*x for v, x in zip(state, c)])
            state = [v+h*(aa+2*bb+2*cc+dd)/6 for v, aa, bb, cc, dd in zip(state, a, b, c, d)]
            time += h
        nodes = {n["id"]: n for n in sample["nodes"]}
        position_error = max(position_error, abs(nodes["upper"]["z"]-state[0]), abs(nodes["wheel"]["z"]-state[1]))
        force_error = max(force_error, abs(sample["contactStates"][0]["force"]-contact["stiffness"]*max(0, contact["radius"]-state[1])))
    z0, speed = wheel["pose"]["z"], -wheel["velocity"]["vz"]
    impact = (math.sqrt(speed*speed+2*gravity*(z0-contact["radius"]))-speed)/gravity
    first = next(s["time"] for s in samples if s["contactStates"][0]["force"] > 0)
    return {"maxReferencePositionErrorM": position_error, "maxReferenceContactForceErrorN": force_error,
            "analyticFirstContactS": impact, "observedFirstContactS": first,
            "contactTimingErrorS": abs(first-impact), "peakContactForceN": max(s["contactStates"][0]["force"] for s in samples)}


def solve_level(study, model):
    result, directory = run(model)
    if not result.get("ok"):
        raise ValueError(f"{study}: actual MBDyn run failed: {result.get('error')}")
    raw_samples = result["samples"]
    result["samples"] = [sample for sample in raw_samples if sample["time"] <= model["simulation"]["duration"]+1e-10]
    info = {"runId": result["runId"], "modelSha256": digest(model), "deckSha256": hashlib.sha256((directory/"model.mbd").read_bytes()).hexdigest(),
            "stepS": model["simulation"]["step"], "samples": len(result["samples"]),
            "solverSamples": len(raw_samples), "solverFinalTimeS": raw_samples[-1]["time"],
            "comparisonFinalTimeS": result["samples"][-1]["time"],
            "maxConstraintResidualM": result["metrics"]["maxConstraintError"]}
    if info["maxConstraintResidualM"] > 1e-7:
        raise ValueError(f"{study}: constraint residual exceeds 1e-7 m")
    if study in ("nose-gear", "suspension"):
        function = nose_error if study == "nose-gear" else suspension_error
        info["maxIndependentKinematicErrorM"] = max(function(model, sample) for sample in result["samples"])
        if info["maxIndependentKinematicErrorM"] > 1e-7:
            raise ValueError(f"{study}: independent linkage geometry mismatch")
    elif study == "landing-drop":
        info.update(drop_reference(model, result["samples"]))
        if info["maxReferencePositionErrorM"] > .001 or info["maxReferenceContactForceErrorN"] > 100 or info["contactTimingErrorS"] > 2*info["stepS"]:
            raise ValueError("Landing drop differs from independent impact/RK4 reference")
    else:
        errors = [arm_errors(model, sample) for sample in result["samples"]]
        info["maxIndependentKinematicErrorM"] = max(e[0] for e in errors)
        info["maxInverseDynamicsTorqueErrorNm"] = max(e[1] for e in errors if e[1] is not None)
        if info["maxIndependentKinematicErrorM"] > 1e-7 or info["maxInverseDynamicsTorqueErrorNm"] > .05:
            raise ValueError(f"Robot arm differs from independent FK/inverse dynamics: {info}")
    track = [[s["time"], *[n[k] for n in s["nodes"] for k in "xyz"]] for s in result["samples"]]
    return info, track


def refinement(a, b):
    if len(b) != 2*len(a)-1:
        raise ValueError("Refinement output is not on a nested time grid")
    worst = 0.
    for left, right in zip(a, b[::2]):
        if abs(left[0]-right[0]) > 1e-10:
            raise ValueError("Refinement output timestamps differ")
        worst = max(worst, max(abs(x-y) for x, y in zip(left[1:], right[1:])))
    return worst


def verify_study(study):
    manifest, project = check_manifest(study)
    cad = check_cad_mass(manifest, project)
    model = project["model"]
    levels, tracks = [], []
    for factor in (1, 2, 4):
        current = copy.deepcopy(model)
        current["simulation"]["step"] /= factor
        info, track = solve_level(study, current)
        levels.append(info)
        tracks.append(track)
    differences = [refinement(tracks[i], tracks[i+1]) for i in (0, 1)]
    if max(differences) > .001:
        raise ValueError(f"{study}: position sensitivity exceeds 1 mm")
    if study in ("suspension", "landing-drop") and differences[1] > .8*differences[0]:
        raise ValueError(f"{study}: timestep refinement did not reduce position differences")
    variant = copy.deepcopy(model)
    if study == "nose-gear":
        next(j for j in variant["joints"] if j["id"] == "oleo")["motion"]["amplitude"] *= .5
        change = "Prescribed stroke amplitude halved"
    elif study == "suspension":
        variant["forces"][0]["stiffness"] *= 1.2
        change = "Illustrative spring stiffness increased 20 percent"
    elif study == "landing-drop":
        for body in variant["bodies"]:
            body["velocity"]["vz"] *= .8
        change = "Both initial downward velocities reduced 20 percent"
    else:
        variant["joints"][1]["motion"]["amplitudeDeg"] *= .8
        change = "Shoulder prescribed amplitude reduced 20 percent"
    varied, _ = solve_level(study, variant)
    return {"ok": True, "study": study, "engineeringRecord": str((ROOT/STUDIES[study]).with_name("engineering.json").relative_to(ROOT)),
            "modelSha256": digest(model), "cadMassChecks": cad, "levels": levels,
            "matchedTimePositionDifferencesM": differences, "variant": {"change": change, **varied},
            "interpretation": manifest["interpretationLimits"], "hardwareValidation": "not-performed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("studies", nargs="*", choices=list(STUDIES))
    parser.add_argument("--output", type=Path, default=ROOT/"verification/engineering-examples.json")
    args = parser.parse_args()
    import solver
    status = solver.status()
    if not status["available"]:
        raise ValueError(f"An actual MBDyn executable is required: {status['detail']}")
    executable = Path(status["path"])
    provenance = {"version": status["version"], "mode": status.get("mode"), "path": status["path"]}
    if executable.is_file():
        provenance["executableSha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    script_hash = hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    report = {"format": "kinemeld-engineering-verification/1", "verifierSha256Lf": script_hash, "solver": provenance, "studies": []}
    for study in args.studies or STUDIES:
        checked = verify_study(study)
        report["studies"].append(checked)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
        print(json.dumps(checked, indent=2), flush=True)
    report["ok"] = all(study["ok"] for study in report["studies"])
    if script_hash != hashlib.sha256(Path(__file__).read_bytes().replace(b"\r\n", b"\n")).hexdigest():
        raise ValueError("Reference code changed during verification; repeat the benchmark")
    args.output.write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
