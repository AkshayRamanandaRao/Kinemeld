"""Small, explicit MBDyn model families; all parameters use SI units except angle."""

import math
import industry_models
import gear_deployment
import planar_assembly
import spatial_assembly

DOUBLE_PENDULUM = {"kind": "double-pendulum", "name": "Coupled double pendulum", "parameters": {"mass1": 1.0, "mass2": 1.0, "length1": 1.0, "length2": 1.0, "angle1": 20.0, "angle2": 45.0, "gravity": 9.81}, "simulation": {"duration": 5.0, "step": 0.005}}

EXAMPLES = [
    {"id": "pendulum", "title": "Gravity pendulum", "description": "A point mass on a massless link, pinned to ground. Learn bodies, joints and gravity.",
     "model": {"kind": "pendulum", "name": "Gravity pendulum", "parameters": {"mass": 1.0, "length": 1.0, "angle": 30.0, "gravity": 9.81}, "simulation": {"duration": 5.0, "step": 0.005}}},
    {"id": "mass-spring", "title": "Damped oscillator", "description": "A translating mass, linear spring and viscous damper. Compare stiffness and damping.",
     "model": {"kind": "mass-spring", "name": "Damped oscillator", "parameters": {"mass": 1.0, "stiffness": 100.0, "damping": 0.5, "displacement": 0.1}, "simulation": {"duration": 5.0, "step": 0.0025}}},
    {"id": "double-pendulum", "title": "Coupled double pendulum", "description": "Two masses and two hinged links exchange energy. Compare coupled motion and joint constraints.", "model": DOUBLE_PENDULUM},
]

RANGES = {
    "pendulum": {"mass": (0.0001, 10000), "length": (0.01, 100), "angle": (-170, 170), "gravity": (0.01, 100)},
    "mass-spring": {"mass": (0.0001, 10000), "stiffness": (0.01, 1000000), "damping": (0, 10000), "displacement": (-10, 10)},
    "double-pendulum": {"mass1": (0.0001, 10000), "mass2": (0.0001, 10000), "length1": (0.01, 100), "length2": (0.01, 100), "angle1": (-170, 170), "angle2": (-170, 170), "gravity": (0.01, 100)},
}
EXAMPLES.extend(industry_models.EXAMPLES)
RANGES.update(industry_models.RANGES)
EXAMPLES.extend(gear_deployment.EXAMPLES)
RANGES.update(gear_deployment.RANGES)
EXAMPLES.extend(planar_assembly.EXAMPLES)
EXAMPLES.extend(spatial_assembly.EXAMPLES)
RANGES[planar_assembly.KIND] = {"gravity": (0, 100)}
FAMILIES = {**{kind:industry_models for kind in industry_models.RANGES}, **{kind:gear_deployment for kind in gear_deployment.RANGES}}


def validate(model):
    if isinstance(model, dict) and model.get("kind") == spatial_assembly.KIND:
        return spatial_assembly.validate(model)
    if isinstance(model, dict) and model.get("kind") == planar_assembly.KIND:
        return planar_assembly.validate(model)
    issues = []
    def issue(field, message, level="error"):
        issues.append({"level": level, "field": field, "message": message})
    if not isinstance(model, dict):
        return {"valid": False, "issues": [{"level": "error", "field": "model", "message": "Supply a model object."}], "summary": {}}
    kind = model.get("kind")
    if not isinstance(kind, str) or kind not in RANGES:
        return {"valid": False, "issues": [{"level": "error", "field": "kind", "message": "Choose a supported model from the example library."}], "summary": {}}
    name = model.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 120 or any(ord(c) < 32 for c in name):
        issue("name", "Use a project name of 1–120 printable characters.")
    for field in model.keys() - {"kind", "name", "parameters", "simulation"}:
        issue(field, "This project field is not supported by this version.")
    p = model.get("parameters")
    simulation = model.get("simulation")
    for group, values, bounds in [("parameters", p, RANGES[kind]), ("simulation", simulation, {"duration": (0.05, 30), "step": (0.0001, 0.05)})]:
        if not isinstance(values, dict):
            issue(group, f"Supply {group} as an object.")
            continue
        for field in values.keys() - bounds.keys():
            issue(f"{group}.{field}", "This parameter is not supported; it will not be silently ignored.")
        for field, (low, high) in bounds.items():
            value = values.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
                issue(f"{group}.{field}", "Enter a finite number.")
            elif not low <= value <= high:
                issue(f"{group}.{field}", f"Use a value between {low:g} and {high:g}.")
    summary = {"kind": kind, "degreesOfFreedom": 2 if kind == "double-pendulum" else 1, "bodies": 2 if kind == "double-pendulum" else 1, "structuralNodes": 1 if kind == "pendulum" else 2, "units": "SI; angles entered in degrees"}
    if any(i["level"] == "error" for i in issues):
        return {"valid": False, "issues": issues, "summary": summary}
    steps = math.ceil(simulation["duration"] / simulation["step"])
    summary["timeSteps"] = steps
    if steps > 20000:
        issue("simulation.step", "This local prototype allows at most 20,000 integration steps. Increase the step or shorten the run.")
    if kind in FAMILIES:
        extra_issues, extra_summary = FAMILIES[kind].extra_validation(model)
        issues.extend(extra_issues)
        summary.update(extra_summary)
        return {"valid": not any(i["level"] == "error" for i in issues), "issues": issues, "summary": summary}
    if kind == "pendulum":
        rate = math.sqrt(p["gravity"] / p["length"])
    elif kind == "double-pendulum":
        rate = 2*math.sqrt(p["gravity"] / min(p["length1"],p["length2"]) * (1+p["mass2"]/p["mass1"]))
    else:
        rate = max(math.sqrt(p["stiffness"] / p["mass"]), p["damping"] / p["mass"])
    if simulation["step"] * rate > 0.2:
        issue("simulation.step", f"Resolve the fastest model time scale: use a step no larger than {0.2/rate:.6g} s.")
    elif simulation["step"] * rate > 0.08:
        issue("simulation.step", "Use a smaller step and compare results to check time-step sensitivity.", "warning")
    if kind == "pendulum":
        summary["smallAnglePeriod"] = 2 * math.pi * math.sqrt(p["length"] / p["gravity"])
        if abs(p["angle"]) > 90:
            issue("parameters.angle", "Large-angle motion is nonlinear; the small-angle period is only a reference.", "warning")
    elif kind == "mass-spring":
        summary["naturalFrequencyHz"] = math.sqrt(p["stiffness"] / p["mass"]) / (2 * math.pi)
        summary["dampingRatio"] = p["damping"] / (2 * math.sqrt(p["stiffness"] * p["mass"]))
    elif max(abs(p["angle1"]),abs(p["angle2"])) > 90:
        issue("parameters.angle2", "Large-angle coupled motion can be sensitive to step size; compare a refined run.", "warning")
    return {"valid": not any(i["level"] == "error" for i in issues), "issues": issues, "summary": summary}


def deck(model):
    if isinstance(model, dict) and model.get("kind") == spatial_assembly.KIND:
        return spatial_assembly.deck(model)
    if isinstance(model, dict) and model.get("kind") == planar_assembly.KIND:
        return planar_assembly.deck(model)
    check = validate(model)
    if not check["valid"]:
        raise ValueError("Model validation failed")
    p, s, kind = model["parameters"], model["simulation"], model["kind"]
    n = lambda value: format(float(value), ".14g")
    header = f"""# Generated by Kinemeld. SI units. Original educational model.
# Model family: {kind}. Parameters are explicitly emitted below.
begin: data;
    problem: initial value;
end: data;
begin: initial value;
    initial time: 0;
    final time: {n(s['duration'])};
    time step: {n(s['step'])};
    max iterations: 30;
    tolerance: 1.e-8;
    derivatives tolerance: 1.e-6;
    derivatives max iterations: 100;
    derivatives coefficient: 1.e-3, auto;
end: initial value;
"""
    if kind in FAMILIES:
        return FAMILIES[kind].deck(model,header)
    if kind == "pendulum":
        a = math.radians(p["angle"])
        x, z = p["length"] * math.sin(a), -p["length"] * math.cos(a)
        return header + f"""# One ideal point mass; its link is massless and rigid.
begin: control data;
    max iterations: 20;
    structural nodes: 1;
    rigid bodies: 1;
    joints: 1;
    gravity;
end: control data;
begin: nodes;
    structural: 1, dynamic, {n(x)}, 0, {n(z)}, eye, null, null;
end: nodes;
begin: elements;
    body: 1, 1, {n(p['mass'])}, null, null;
    joint: 1, revolute pin,
        1, position, {n(-x)}, 0, {n(-z)},
        orientation, 1, 1,0,0, 3, 0,1,0,
        position, null,
        orientation, 1, 1,0,0, 3, 0,1,0;
    gravity: uniform, 0,0,-1, const, {n(p['gravity'])};
end: elements;
"""
    if kind == "double-pendulum":
        a1, a2 = math.radians(p["angle1"]), math.radians(p["angle2"])
        x1, z1 = p["length1"]*math.sin(a1), -p["length1"]*math.cos(a1)
        dx2, dz2 = p["length2"]*math.sin(a2), -p["length2"]*math.cos(a2)
        return header + f"""# Two ideal point masses; both rigid links are massless.
begin: control data;
    max iterations: 20;
    structural nodes: 2;
    rigid bodies: 2;
    joints: 2;
    gravity;
end: control data;
begin: nodes;
    structural: 1, dynamic, {n(x1)},0,{n(z1)}, eye, null, null;
    structural: 2, dynamic, {n(x1+dx2)},0,{n(z1+dz2)}, eye, null, null;
end: nodes;
begin: elements;
    body: 1, 1, {n(p['mass1'])}, null, null;
    body: 2, 2, {n(p['mass2'])}, null, null;
    joint: 1, revolute pin,
        1, position, {n(-x1)},0,{n(-z1)},
        orientation, 1, 1,0,0, 3, 0,1,0,
        position, null,
        orientation, 1, 1,0,0, 3, 0,1,0;
    joint: 2, revolute hinge,
        1, position, null,
        orientation, 1, 1,0,0, 3, 0,1,0,
        2, position, {n(-dx2)},0,{n(-dz2)},
        orientation, 1, 1,0,0, 3, 0,1,0;
    gravity: uniform, 0,0,-1, const, {n(p['gravity'])};
end: elements;
"""
    return header + f"""# Translation along global X; spring rest displacement is zero.
begin: control data;
    max iterations: 20;
    initial stiffness: 1.e12;
    structural nodes: 2;
    rigid bodies: 1;
    joints: 4;
end: control data;
begin: nodes;
    structural: 1, static, null, eye, null, null;
    structural: 2, dynamic, {n(p['displacement'])},0,0, eye, null, null;
end: nodes;
begin: elements;
    body: 1, 2, {n(p['mass'])}, null, diag, 1,1,1;
    joint: 1, clamp, 1, node, node;
    joint: 2, in line, 1, position, null,
        orientation, 1, 0,1,0, 3, 1,0,0, 2, offset, null;
    joint: 3, prismatic, 1, 2;
    joint: 4, deformable displacement joint,
        1, position, null, 2, position, null,
        linear viscoelastic generic,
        diag, {n(p['stiffness'])},0,0,
        diag, {n(p['damping'])},0,0;
end: elements;
"""


def sample(kind, time, position, velocity, angle=0):
    x, y, z = position
    return {"time": time, "x": x, "y": y, "z": z, "angle": angle,
            "velocity": velocity, "value": x if kind == "mass-spring" else angle}


def preview(model):
    """Independent reference calculation; never presented as MBDyn output."""
    if isinstance(model, dict) and model.get("kind") in (planar_assembly.KIND, spatial_assembly.KIND):
        raise ValueError("Authored assemblies require an actual MBDyn run; no reference-preview solver is provided.")
    if not validate(model)["valid"]:
        raise ValueError("Model validation failed")
    p, s, kind = model["parameters"], model["simulation"], model["kind"]
    if kind in FAMILIES:
        return FAMILIES[kind].preview(model)
    count = math.ceil(s["duration"] / s["step"])
    times = [min(i * s["step"], s["duration"]) for i in range(count + 1)]
    values = []
    if kind == "pendulum":
        theta, omega, prev_t = math.radians(p["angle"]), 0.0, 0.0
        def acceleration(theta):
            return -p["gravity"] / p["length"] * math.sin(theta)
        for t in times:
            h = t - prev_t
            k1 = (omega, acceleration(theta))
            k2 = (omega + h*k1[1]/2, acceleration(theta + h*k1[0]/2))
            k3 = (omega + h*k2[1]/2, acceleration(theta + h*k2[0]/2))
            k4 = (omega + h*k3[1], acceleration(theta + h*k3[0]))
            theta += h*(k1[0] + 2*k2[0] + 2*k3[0] + k4[0])/6
            omega += h*(k1[1] + 2*k2[1] + 2*k3[1] + k4[1])/6
            values.append(sample(kind, t, (p["length"]*math.sin(theta), 0, -p["length"]*math.cos(theta)), omega, math.degrees(theta)))
            prev_t = t
    elif kind == "double-pendulum":
        state = [math.radians(p["angle1"]), math.radians(p["angle2"]), 0., 0.]
        m1,m2,l1,l2,g = (p[key] for key in ("mass1","mass2","length1","length2","gravity"))
        def derivative(q):
            a1,a2,w1,w2 = q
            delta = a1-a2
            aa,bb,dd = (m1+m2)*l1*l1, m2*l1*l2*math.cos(delta), m2*l2*l2
            r1 = -m2*l1*l2*math.sin(delta)*w2*w2-(m1+m2)*g*l1*math.sin(a1)
            r2 = m2*l1*l2*math.sin(delta)*w1*w1-m2*g*l2*math.sin(a2)
            determinant = aa*dd-bb*bb
            return [w1,w2,(r1*dd-bb*r2)/determinant,(aa*r2-bb*r1)/determinant]
        previous = 0.
        for t in times:
            h = t-previous
            k1 = derivative(state)
            k2 = derivative([a+h*b/2 for a,b in zip(state,k1)])
            k3 = derivative([a+h*b/2 for a,b in zip(state,k2)])
            k4 = derivative([a+h*b for a,b in zip(state,k3)])
            state = [a+h*(b+2*c+2*d+e)/6 for a,b,c,d,e in zip(state,k1,k2,k3,k4)]
            a1,a2,w1,w2 = state
            x,z = l1*math.sin(a1), -l1*math.cos(a1)
            value = sample(kind,t,(x,0,z),w1,math.degrees(math.atan2(math.sin(a1),math.cos(a1))))
            angle2 = math.degrees(math.atan2(math.sin(a2),math.cos(a2)))
            value.update(x2=x+l2*math.sin(a2),y2=0,z2=z-l2*math.cos(a2),angle2=angle2,velocity2=w2,value2=angle2)
            values.append(value)
            previous = t
    else:
        wn = math.sqrt(p["stiffness"] / p["mass"])
        alpha = p["damping"] / (2*p["mass"])
        x0 = p["displacement"]
        for t in times:
            if abs(alpha-wn) <= 1e-10*wn:
                x = x0 * (1 + wn*t) * math.exp(-wn*t)
                v = -x0 * wn*wn*t*math.exp(-wn*t)
            elif alpha < wn:
                wd = math.sqrt(wn*wn-alpha*alpha)
                x = x0*math.exp(-alpha*t)*(math.cos(wd*t) + alpha/wd*math.sin(wd*t))
                v = -x0*math.exp(-alpha*t)*wn*wn/wd*math.sin(wd*t)
            else:
                root = math.sqrt(alpha*alpha-wn*wn)
                r1, r2 = -wn*wn/(alpha+root), -alpha-root
                c1, c2 = -r2*x0/(r1-r2), r1*x0/(r1-r2)
                x = c1*math.exp(r1*t)+c2*math.exp(r2*t)
                v = c1*r1*math.exp(r1*t)+c2*r2*math.exp(r2*t)
            values.append(sample(kind, t, (x,0,0), v))
    return values


def metrics(model, samples):
    if model["kind"] == spatial_assembly.KIND:
        return spatial_assembly.metrics(model, samples)
    if model["kind"] == planar_assembly.KIND:
        return planar_assembly.metrics(model, samples)
    p, kind = model["parameters"], model["kind"]
    if kind in FAMILIES:
        return FAMILIES[kind].metrics(model,samples)
    energies = []
    for q in samples:
        if kind == "pendulum":
            energy = 0.5*p["mass"]*p["length"]**2*q["velocity"]**2 + p["mass"]*p["gravity"]*p["length"]*(1-math.cos(math.radians(q["angle"])))
        elif kind == "double-pendulum":
            m1,m2,l1,l2,g = (p[key] for key in ("mass1","mass2","length1","length2","gravity"))
            a1,a2,w1,w2 = math.radians(q["angle"]),math.radians(q["angle2"]),q["velocity"],q["velocity2"]
            energy = 0.5*(m1+m2)*l1*l1*w1*w1 + 0.5*m2*l2*l2*w2*w2 + m2*l1*l2*math.cos(a1-a2)*w1*w2
            energy += (m1+m2)*g*l1*(1-math.cos(a1)) + m2*g*l2*(1-math.cos(a2))
        else:
            energy = 0.5*p["mass"]*q["velocity"]**2 + 0.5*p["stiffness"]*q["x"]**2
        energies.append(energy)
    result = {"sampleCount": len(samples), "duration": samples[-1]["time"], "peakValue": max(abs(q["value"]) for q in samples), "valueUnit": "m" if kind == "mass-spring" else "deg", "velocityUnit": "m/s" if kind == "mass-spring" else "rad/s", "initialEnergy": energies[0], "finalEnergy": energies[-1], "energyUnit": "J"}
    if kind == "pendulum":
        result["maxConstraintError"] = max(abs(math.hypot(q["x"],q["z"])-p["length"]) for q in samples)
    elif kind == "double-pendulum":
        result["maxConstraintError"] = max(max(abs(math.hypot(q["x"],q["z"])-p["length1"]),abs(math.hypot(q["x2"]-q["x"],q["z2"]-q["z"])-p["length2"])) for q in samples)
        result["peakValue2"] = max(abs(q["value2"]) for q in samples)
    return result
