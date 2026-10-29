"""Run every featured study through MBDyn and check it against independent physics.

Usage: python -B backend/verify_featured_studies.py [study-id ...]
Each check compares the solver trajectory with a quantity derived without MBDyn
(gyroscopic theory, conservation laws, closed-form kinematics or static balance).
"""
import json
import math
from pathlib import Path
import sys

import solver
import spatial_assembly as spatial

ROOT = Path(__file__).resolve().parents[1]


def load(study_id):
    catalog = json.loads((ROOT / "examples" / "featured.json").read_text(encoding="utf-8"))
    study = next(item for item in catalog["studies"] if item["id"] == study_id)
    return json.loads((ROOT / "examples" / study["project"]).read_text(encoding="utf-8"))["model"]


def solve(model):
    result, status = solver.run(model)
    if status != 200 or not result.get("ok"):
        raise AssertionError(f"MBDyn failed: {result.get('error')}")
    return result["samples"]


def node(sample, identifier):
    return next(item for item in sample["nodes"] if item["id"] == identifier)


def element(sample, group, identifier):
    return next(item for item in sample[group] if item["id"] == identifier)


def rotation(n):
    return spatial.rotation(n["rx"], n["ry"], n["rz"])


def world_inertia(body, n):
    r = rotation(n)
    return spatial.matmul(spatial.matmul(r, spatial.inertia_matrix(body["inertia"])), spatial.transpose(r))


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    return message


def gyroscopic_top():
    model = load("gyroscopic-top")
    body = model["bodies"][0]
    samples = solve(model)
    spin = [spatial.mul(spatial.transpose(rotation(node(s, "top"))), [node(s, "top")[k] for k in ("wx", "wy", "wz")])[2] for s in samples]
    # Precession: azimuth of the symmetry axis, unwrapped.
    azimuth, previous, turns = [], None, 0.0
    for s in samples:
        axis = spatial.mul(rotation(node(s, "top")), [0, 0, 1])
        angle = math.atan2(axis[1], axis[0])
        if previous is not None and angle - previous > math.pi:
            turns -= 2 * math.pi
        elif previous is not None and angle - previous < -math.pi:
            turns += 2 * math.pi
        azimuth.append(angle + turns)
        previous = angle
    rate = abs(azimuth[-1] - azimuth[0]) / (samples[-1]["time"] - samples[0]["time"])
    lever = body["centerOfMass"]["z"]
    # Slow root of steady precession, I1 cosθ Ω² − I3 ω3 Ω + m g l = 0, with I1 about the fixed tip.
    i1 = body["inertia"]["xx"] + body["mass"] * lever ** 2
    i3w = body["inertia"]["zz"] * spin[0]
    tilt = math.radians(model["bodies"][0]["pose"]["rx"])
    mgl = body["mass"] * 9.81 * lever
    expected = (i3w - math.sqrt(i3w ** 2 - 4 * i1 * math.cos(tilt) * mgl)) / (2 * i1 * math.cos(tilt))
    return [
        check(max(abs(w - spin[0]) for w in spin) / spin[0] < 0.01, f"Spin about the symmetry axis is conserved within 1 % ({spin[0]:.2f} rad/s)."),
        check(abs(rate - expected) / expected < 0.08, f"Mean precession rate {rate:.3f} rad/s matches steady precession theory ({expected:.3f} rad/s) within 8 %; the fast-top estimate mgl/(I₃ω) = {mgl / i3w:.3f} rad/s is not valid at this spin."),
    ]


def tumbling_handle():
    model = load("tumbling-handle")
    body = model["bodies"][0]
    samples = solve(model)
    momentum = []
    body_x = []
    for s in samples:
        n = node(s, "handle")
        w = [n[k] for k in ("wx", "wy", "wz")]
        momentum.append(spatial.mul(world_inertia(body, n), w))
        body_x.append(spatial.mul(spatial.transpose(rotation(n)), w)[0])
    h0 = math.sqrt(sum(c * c for c in momentum[0]))
    drift = max(math.sqrt(sum((a - b) ** 2 for a, b in zip(h, momentum[0]))) for h in momentum) / h0
    flips = sum(1 for a, b in zip(body_x, body_x[1:]) if a * b < 0 and abs(a - b) > 1e-9)
    return [
        check(drift < 0.005, f"World angular momentum is conserved within {100 * drift:.3f} % (limit 0.5 %)."),
        check(flips >= 3, f"Spin about the intermediate axis reverses {flips} times in {samples[-1]['time']:.0f} s."),
    ]


def chaotic_pendulums():
    model = load("chaotic-pendulums")
    samples = solve(model)
    def gap(s):
        a, b = node(s, "lower1"), node(s, "lower2")
        return math.hypot(a["x"] - b["x"], a["z"] - b["z"])
    early = max(gap(s) for s in samples if s["time"] <= 1.5)
    late = max(gap(s) for s in samples if s["time"] >= 6.0)
    bodies = {b["id"]: b for b in model["bodies"]}
    def energy(s, ids):
        total = 0.0
        for identifier in ids:
            b, n = bodies[identifier], node(s, identifier)
            r = rotation(n)
            c = [n[k] + d for k, d in zip("xyz", spatial.mul(r, [b["centerOfMass"][k] for k in "xyz"]))]
            w = [n[k] for k in ("wx", "wy", "wz")]
            v = [n[k] for k in ("vx", "vy", "vz")]
            vc = [a + d for a, d in zip(v, spatial.cross(w, spatial.mul(r, [b["centerOfMass"][k] for k in "xyz"])))]
            total += 0.5 * b["mass"] * sum(x * x for x in vc) + 0.5 * sum(x * y for x, y in zip(w, spatial.mul(world_inertia(b, n), w))) + b["mass"] * 9.81 * c[2]
        return total
    e0 = energy(samples[0], ("upper1", "lower1"))
    window = [energy(s, ("upper1", "lower1")) for s in samples if s["time"] <= 3.0]
    swing = max(abs(e - e0) for e in window) / (bodies["upper1"]["mass"] + bodies["lower1"]["mass"]) / 9.81
    return [
        check(early < 1e-3, f"The two pendulums agree within {early * 1000:.3f} mm for 1.5 s."),
        check(late > 0.2, f"After 6 s their bobs separate by up to {late:.2f} m: sensitive dependence on initial conditions."),
        check(swing < 0.02, f"Mechanical energy of pendulum A varies by an equivalent height of {swing * 1000:.1f} mm over 3 s (integrator dissipation, limit 20 mm)."),
    ]


def slider_crank():
    model = load("slider-crank")
    samples = solve(model)
    crank_r = next(j for j in model["joints"] if j["id"] == "crank_pin")["anchorA"]["z"]
    positions = [element(s, "sliders", "cylinder_bore")["position"] for s in samples]
    stroke = max(positions) - min(positions)
    lateral = max(abs(node(s, "piston")["x"]) for s in samples)
    steady = [s for s in samples if s["time"] >= samples[-1]["time"] - 1.0]
    motor = sum(element(s, "actuationStates", "motor")["power"] for s in steady) / len(steady)
    damper = sum(element(s, "forces", "pumping_load")["rate"] ** 2 * model["forces"][0]["damping"] for s in steady) / len(steady)
    return [
        check(abs(stroke - 2 * crank_r) < 1e-3, f"Piston stroke {stroke * 1000:.2f} mm equals twice the crank radius ({2000 * crank_r:.1f} mm)."),
        check(lateral < 1e-9, "The loop closure keeps the piston on the bore axis."),
        check(abs(motor - damper) / motor < 0.08, f"At steady speed, mean motor power {motor:.2f} W balances pumping dissipation {damper:.2f} W within 8 %."),
    ]


def gear_drop():
    model = load("gear-drop")
    samples = solve(model)
    weight = sum(b["mass"] for b in model["bodies"]) * 9.81
    oleo = model["forces"][0]
    stroke = max(element(s, "sliders", "oleo_slide")["position"] for s in samples)
    bottomed = min(element(s, "forces", "oleo")["stopForce"] for s in samples)
    final = samples[-1]
    tyre = element(final, "contactStates", "tyre")["force"]
    peak = max(element(s, "contactStates", "tyre")["force"] for s in samples)
    return [
        check(stroke < oleo["maxLength"] - oleo["minLength"], f"Peak stroke {stroke * 1000:.0f} mm stays inside the {1000 * (oleo['maxLength'] - oleo['minLength']):.0f} mm stroke."),
        check(bottomed > -1e-6, "The strut never bottoms on its compression stop."),
        check(abs(tyre - weight) / weight < 0.05, f"Settled tyre load {tyre:.0f} N carries the {weight:.0f} N weight within 5 %; peak load factor {peak / weight:.1f}."),
    ]


def quarter_car():
    model = load("quarter-car")
    samples = solve(model)
    z = [node(s, "wheel")["z"] for s in samples]
    design = model["bodies"][3]["pose"]["z"]
    knuckle = [node(s, "knuckle") for s in samples]
    camber = [k["rx"] for k in knuckle]
    toe = [k["rz"] for k in knuckle]
    return [
        check(min(z) < design - 0.04 and max(z) > design + 0.04, f"Wheel travel spans {1000 * (min(z) - design):.0f} to {1000 * (max(z) - design):+.0f} mm."),
        check(max(toe) - min(toe) < 1.0, f"Bump steer stays within {max(toe) - min(toe):.2f}° over the sweep."),
        check(0.5 < max(camber) - min(camber) < 4.0, f"Camber changes by {max(camber) - min(camber):.2f}° (short-long arm gain)."),
    ]


def mechanical_energy(model, sample):
    bodies = {b["id"]: b for b in model["bodies"]}
    total = 0.0
    for identifier, body in bodies.items():
        n = node(sample, identifier)
        r = rotation(n)
        offset = spatial.mul(r, [body["centerOfMass"][k] for k in "xyz"])
        w = [n[k] for k in ("wx", "wy", "wz")]
        v = [a + b for a, b in zip([n[k] for k in ("vx", "vy", "vz")], spatial.cross(w, offset))]
        height = n["z"] + offset[2]
        total += 0.5 * body["mass"] * sum(x * x for x in v) + 0.5 * sum(x * y for x, y in zip(w, spatial.mul(world_inertia(body, n), w))) + body["mass"] * 9.81 * height
    return total


def robot_arm():
    model = load("robot-arm")
    samples = solve(model)
    work = samples[-1]["rotaryDriveWork"]
    change = mechanical_energy(model, samples[-1]) - mechanical_energy(model, samples[0])
    peak = max(abs(d["torque"]) for s in samples for d in s["rotaryDrives"])
    worst = max(abs(d["angle"] - d["commandedAngle"]) for s in samples for d in s["rotaryDrives"])
    return [
        check(worst < 1e-6, f"All three axes follow their commanded angles within {worst:.1e} rad."),
        check(abs(work - change) < 0.01 * peak, f"Drive work {work:.3f} J equals the change in kinetic and potential energy {change:.3f} J (no dissipation)."),
    ]


STUDIES = {"robot-arm": robot_arm, "gyroscopic-top": gyroscopic_top, "tumbling-handle": tumbling_handle, "chaotic-pendulums": chaotic_pendulums,
           "slider-crank": slider_crank, "gear-drop": gear_drop, "quarter-car": quarter_car}


def main(selected):
    report = {}
    for key in selected or STUDIES:
        report[key] = STUDIES[key]()
        for line in report[key]:
            print(f"[{key}] PASS {line}")
    return report


if __name__ == "__main__":
    main(sys.argv[1:])
