"""Run every featured study through MBDyn and check it against independent physics.

Usage: python -B backend/verify_featured_studies.py [study-id ...]
Each check compares the solver trajectory with a quantity derived without MBDyn
(gyroscopic theory, conservation laws, closed-form kinematics or static balance).
"""
import json
import math
from pathlib import Path
import sys

import featured
import solver
import spatial_assembly as spatial
from verify_aircraft_nose_kinematics import actual_scissor, independent_scissor

ROOT = Path(__file__).resolve().parents[1]


def load(study_id):
    """The model a featured study opens with, including its catalog overlay."""
    study = next(item for item in featured.catalog() if item["id"] == study_id)
    return featured.project(study)["model"]


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


def aircraft_nose_gear():
    model = load("aircraft-nose-gear")
    samples = solve(model)
    motion = next(j for j in model["joints"] if j["id"] == "oleo")["motion"]
    stroke = [motion["amplitude"] * (1 - math.cos(2 * math.pi * motion["frequencyHz"] * s["time"])) for s in samples]
    slider = max(abs(element(s, "sliders", "oleo")["position"] - q) for s, q in zip(samples, stroke))
    # Independent planar check: the scissor pin lies on two circles about the upper and lower pins.
    scissor = max(math.dist(actual_scissor(s, model), independent_scissor(model, q)) for s, q in zip(samples, stroke))
    fold = [node(s, "upper_link")["rx"] for s in samples]
    return [
        check(slider < 1e-9, f"The strut follows the prescribed {1000 * max(stroke):.0f} mm stroke within {slider:.1e} m."),
        check(scissor < 1e-8, f"The scissor pin matches two-circle linkage geometry within {scissor:.1e} m over the whole stroke."),
        check(max(fold) - min(fold) > 10, f"The upper torque link folds through {max(fold) - min(fold):.1f}°."),
    ]


def oleo_strut():
    model = load("oleo-strut")
    samples = solve(model)
    force = next(f for f in model["forces"] if f["id"] == "oleo")
    error = 0.0
    for s in samples:
        state = element(s, "forces", "oleo")
        ratio = 1 + force["gasArea"] * (state["length"] - force["restLength"]) / force["gasVolume"]
        expected = force["pressure"] * ratio ** (-force["gamma"])
        error = max(error, abs(state["gasPressure"] - expected) / expected)
    lengths = [element(s, "forces", "oleo")["length"] for s in samples]
    pressures = [element(s, "forces", "oleo")["gasPressure"] for s in samples]
    return [
        check(error < 1e-6, f"Native gas pressure follows the polytropic law p₀(V₀/V)^γ within {error:.1e} (relative)."),
        check(max(lengths) - min(lengths) > 0.04, f"The fixture strokes the strut through {1000 * (max(lengths) - min(lengths)):.0f} mm; gas pressure spans {min(pressures) / 1e5:.2f}–{max(pressures) / 1e5:.2f} bar."),
    ]


def wheel_end_drop():
    model = load("wheel-end-drop")
    samples = solve(model)
    g = -model["parameters"]["gravity"]["z"]
    contact = model["contacts"][0]
    wheel = next(b for b in model["bodies"] if b["id"] == contact["body"])
    z0, v0 = wheel["pose"]["z"], wheel["velocity"]["vz"]
    # Free fall until the tyre sphere reaches the floor; first contact time from the quadratic.
    drop = z0 - contact["radius"]
    t_contact = (v0 + math.sqrt(v0 * v0 + 2 * g * drop)) / g
    free = [s for s in samples if s["time"] < t_contact - 1e-9]
    fall = max(abs(node(s, "wheel")["z"] - (z0 + v0 * s["time"] - 0.5 * g * s["time"] ** 2)) for s in free)
    first = next(s["time"] for s in samples if element(s, "contactStates", contact["id"])["penetration"] > 0)

    def energy(s):
        total = element(s, "contactStates", contact["id"])["energy"]
        for body in model["bodies"]:
            n = node(s, body["id"])
            r = rotation(n)
            arm = spatial.mul(r, [body["centerOfMass"][k] for k in "xyz"])
            w = [n["wx"], n["wy"], n["wz"]]
            v = [n[f"v{k}"] + c for k, c in zip("xyz", spatial.cross(w, arm))]
            iw = spatial.mul(world_inertia(body, n), w)
            total += 0.5 * body["mass"] * sum(x * x for x in v) + 0.5 * sum(a * b for a, b in zip(w, iw))
            total += body["mass"] * g * (n["z"] + arm[2])
        return total

    lost = energy(samples[0]) - energy(samples[-1])
    dissipated = element(samples[-1], "contactStates", contact["id"])["dissipatedEnergy"]
    peak = max(element(s, "contactStates", contact["id"])["force"] for s in samples)
    weight = sum(b["mass"] for b in model["bodies"]) * g
    return [
        check(fall < 1e-6, f"Before impact the wheel follows free fall within {fall:.1e} m."),
        check(abs(first - t_contact) <= 2 * model["simulation"]["step"], f"First tyre contact at {first * 1000:.1f} ms matches the free-fall prediction ({t_contact * 1000:.1f} ms)."),
        check(abs(lost - dissipated) < 0.02 * dissipated, f"Mechanical energy lost ({lost:.2f} J) equals contact damping dissipation ({dissipated:.2f} J) within 2 %; peak tyre load {peak / weight:.1f}× weight."),
    ]


def contact_peak(mass, stiffness, damping, speed, g, dt=1e-6):
    """Peak force of a mass meeting a compression-only damped penalty contact at `speed`.

    Independent RK4 of m p'' = m g - k p - c max(0, p') from first touch until release, the
    one-degree-of-freedom form of a vertical drop on the sphere-plane contact law.
    """
    def force(p, w):
        return stiffness * p + damping * max(0.0, w)

    def accel(p, w):
        return g - force(p, w) / mass

    p, w, peak = 0.0, speed, 0.0
    while p >= 0.0:
        peak = max(peak, force(p, w))
        k1p, k1w = w, accel(p, w)
        k2p, k2w = w + 0.5 * dt * k1w, accel(p + 0.5 * dt * k1p, w + 0.5 * dt * k1w)
        k3p, k3w = w + 0.5 * dt * k2w, accel(p + 0.5 * dt * k2p, w + 0.5 * dt * k2w)
        k4p, k4w = w + dt * k3w, accel(p + dt * k3p, w + dt * k3w)
        p += dt * (k1p + 2 * k2p + 2 * k3p + k4p) / 6
        w += dt * (k1w + 2 * k2w + 2 * k3w + k4w) / 6
    return peak


def featured_study(study_id):
    item = next(entry for entry in featured.catalog() if entry["id"] == study_id)
    return item, featured.project(item)["model"], featured.study_values(item)


def wheel_end_tyre_study():
    """Every case of the featured tyre-stiffness study against the one-degree-of-freedom drop."""
    item, model, values = featured_study("wheel-end-drop")
    g = -model["parameters"]["gravity"]["z"]
    contact = model["contacts"][0]
    wheel = next(b for b in model["bodies"] if b["id"] == contact["body"])
    mass = sum(b["mass"] for b in model["bodies"])
    speed = math.sqrt(wheel["velocity"]["vz"] ** 2 + 2 * g * (wheel["pose"]["z"] - contact["radius"]))
    peaks, worst = [], 0.0
    for value in values:
        case = featured.study_case(model, item["study"]["input"], value)
        samples = solve(case)
        peak = max(element(s, "contactStates", contact["id"])["force"] for s in samples)
        reference = contact_peak(mass, value, contact["damping"], speed, g)
        worst = max(worst, abs(peak - reference) / reference)
        peaks.append(peak)
    return [
        check(worst < 0.015, f"Peak tyre load for {len(values)} stiffnesses ({values[0] / 1000:.0f}–{values[-1] / 1000:.0f} kN/m) matches an independent one-degree-of-freedom RK4 drop within {100 * worst:.2f} %."),
        check(all(a < b for a, b in zip(peaks, peaks[1:])), f"Peak tyre load rises with stiffness: {' < '.join(f'{p:.0f}' for p in peaks)} N."),
    ]


def gear_drop_sink_study():
    """Every case of the featured sink-speed study: energy balance, load trend and stroke."""
    item, model, values = featured_study("gear-drop")
    weight = sum(b["mass"] for b in model["bodies"]) * 9.81
    drift, factors, bottomed = 0.0, [], 0.0
    for value in values:
        case = featured.study_case(model, item["study"]["input"], value)
        samples = solve(case)

        def total(s):
            tyre = element(s, "contactStates", "tyre")
            return mechanical_energy(case, s) + s["elasticEnergy"] + s["dissipatedEnergy"] + tyre["energy"] + tyre["dissipatedEnergy"]

        start = total(samples[0])
        kinetic = 0.5 * sum(b["mass"] for b in case["bodies"]) * value * value
        drift = max(drift, max(abs(total(s) - start) for s in samples) / kinetic)
        factors.append(max(element(s, "contactStates", "tyre")["force"] for s in samples) / weight)
        bottomed = min(bottomed, min(element(s, "forces", "oleo")["stopForce"] for s in samples))
    # Cases run in ascending vz, so the fastest descent comes first.
    return [
        check(drift < 0.005, f"For sink speeds {abs(values[-1]):g}–{abs(values[0]):g} m/s the mechanical, stored and dissipated energy balance within {100 * drift:.2f} % of the impact energy."),
        check(all(a > b for a, b in zip(factors, factors[1:])), f"Peak tyre load factor rises with sink speed: {' < '.join(f'{f:.2f}' for f in reversed(factors))}."),
        check(bottomed > -1e-6, "The strut never bottoms on its compression stop, even at the fastest sink speed."),
    ]


STUDIES = {"robot-arm": robot_arm, "gyroscopic-top": gyroscopic_top, "tumbling-handle": tumbling_handle, "chaotic-pendulums": chaotic_pendulums,
           "slider-crank": slider_crank, "gear-drop": gear_drop, "quarter-car": quarter_car,
           "aircraft-nose-gear": aircraft_nose_gear, "oleo-strut": oleo_strut, "wheel-end-drop": wheel_end_drop,
           "wheel-end-drop-study": wheel_end_tyre_study, "gear-drop-study": gear_drop_sink_study}


def main(selected):
    report = {}
    for key in selected or STUDIES:
        report[key] = STUDIES[key]()
        for line in report[key]:
            print(f"[{key}] PASS {line}")
    return report


if __name__ == "__main__":
    main(sys.argv[1:])
