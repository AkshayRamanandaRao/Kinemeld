"""Original planar landing-gear deployment linkage, solved as a closed four-bar."""

import math

NODE_LABELS = (1, 2, 3)
DEFAULT = {"kind": "gear-deployment", "name": "Shuttle-style gear deployment", "parameters": {
    "mainLength": 1.1, "braceAttachment": 0.45, "upperBraceLength": 0.55,
    "lowerBraceLength": 0.6, "groundX": 0.65, "groundZ": -0.1,
    "actuatorAnchorX": -0.35, "actuatorAnchorZ": 0.15, "mainMass": 25.,
    "upperBraceMass": 4., "lowerBraceMass": 4., "initialAngle": -65.,
    "finalAngle": 0., "gravity": 9.81}, "simulation": {"duration": 3., "step": 0.01}}
EXAMPLES = [{"id": "gear-deployment", "title": "Shuttle-style gear deployment", "description": "An original generic surrogate: closed four-bar deployment with moving link masses and independent geometric closure checks. Dimensions and actuation are illustrative.", "model": DEFAULT}]
RANGES = {"gear-deployment": {
    "mainLength": (0.1, 10), "braceAttachment": (0.05, 10),
    "upperBraceLength": (0.05, 10), "lowerBraceLength": (0.05, 10),
    "groundX": (-10, 10), "groundZ": (-10, 10),
    "actuatorAnchorX": (-10, 10), "actuatorAnchorZ": (-10, 10),
    "mainMass": (0.1, 10000), "upperBraceMass": (0.01, 1000), "lowerBraceMass": (0.01, 1000),
    "initialAngle": (-150, 150), "finalAngle": (-150, 150), "gravity": (0, 30)}}


def geometry(p, angle):
    """Intersect the B and D brace circles, preserving the positive branch."""
    a = math.radians(angle)
    bx, bz = p["braceAttachment"]*math.sin(a), -p["braceAttachment"]*math.cos(a)
    dx, dz = p["groundX"]-bx, p["groundZ"]-bz
    distance = math.hypot(dx, dz)
    upper, lower = p["upperBraceLength"], p["lowerBraceLength"]
    if distance <= abs(upper-lower) or distance >= upper+lower:
        raise ValueError("The brace circles do not intersect away from a toggle.")
    along = (upper*upper-lower*lower+distance*distance)/(2*distance)
    height = math.sqrt(max(0., upper*upper-along*along))
    return bx, bz, bx+along*dx/distance-height*dz/distance, bz+along*dz/distance+height*dx/distance


def extra_validation(model):
    """Check the full angle interval, including its exact distance extrema."""
    p, s = model["parameters"], model["simulation"]
    issues = []
    def error(field, message):
        issues.append({"level": "error", "field": field, "message": message})
    if p["braceAttachment"] >= p["mainLength"]:
        error("parameters.braceAttachment", "Place the brace attachment strictly between the main pivot and wheel.")
    sweep = abs(p["finalAngle"]-p["initialAngle"])
    if sweep < 1 or sweep > 150:
        error("parameters.finalAngle", "Use a deployment sweep between 1 and 150 degrees.")
    low, high = sorted((p["initialAngle"], p["finalAngle"]))
    # Distance B-D is extremal when AB and AD are parallel or antiparallel.
    phase = math.degrees(math.atan2(p["groundX"], -p["groundZ"]))
    angles = [low, high] + [phase+180*k for k in range(-3, 4) if low <= phase+180*k <= high]
    distances = [math.hypot(p["groundX"]-p["braceAttachment"]*math.sin(math.radians(a)),
                            p["groundZ"]+p["braceAttachment"]*math.cos(math.radians(a))) for a in angles]
    upper, lower = p["upperBraceLength"], p["lowerBraceLength"]
    margin = min(min(distances)-abs(upper-lower), upper+lower-max(distances))
    if margin <= .005*min(upper, lower):
        error("parameters.upperBraceLength", "The requested sweep reaches an unreachable or near-toggle brace geometry. Change lengths, ground pivot or angles.")
    if s["step"] > s["duration"]/100:
        error("simulation.step", "Use at least 100 time steps across the deployment motion.")
    summary = {"kind": "gear-deployment", "degreesOfFreedom": 1, "prescribedCoordinates": 1,
               "bodies": 3, "structuralNodes": 3, "units": "SI; angles entered in degrees",
               "minimumClosureMargin": margin, "actuation": "Prescribed main-strut angle; actuator length is kinematic demand only."}
    return issues, summary


def _angle(model, time):
    p, duration = model["parameters"], model["simulation"]["duration"]
    phase = math.pi*min(max(time, 0.), duration)/duration
    delta = p["finalAngle"]-p["initialAngle"]
    return p["initialAngle"]+.5*delta*(1-math.cos(phase)), math.radians(delta)*.5*math.pi/duration*math.sin(phase)


def _sample(model, time, bx, bz, cx, cz, velocity, dx=None, dz=None):
    p = model["parameters"]
    dx = p["groundX"] if dx is None else dx
    dz = p["groundZ"] if dz is None else dz
    angle = math.degrees(math.atan2(bx, -bz))
    ratio = p["mainLength"]/p["braceAttachment"]
    wx, wz = ratio*bx, ratio*bz
    closure = max(abs(math.hypot(bx, bz)-p["braceAttachment"]),
                  abs(math.hypot(cx-bx, cz-bz)-p["upperBraceLength"]),
                  abs(math.hypot(cx-dx, cz-dz)-p["lowerBraceLength"]),
                  math.hypot(dx-p["groundX"], dz-p["groundZ"]))
    return {"time": time, "x": wx, "y": 0., "z": wz, "value": angle, "angle": angle,
            "velocity": velocity, "bx": bx, "bz": bz, "cx": cx, "cz": cz,
            "wheelX": wx, "wheelZ": wz, "actuatorLength": math.hypot(bx-p["actuatorAnchorX"], bz-p["actuatorAnchorZ"]),
            "closureError": closure}


def preview(model):
    """Return analytic circle-intersection positions, never MBDyn output."""
    s = model["simulation"]
    result = []
    for i in range(math.ceil(s["duration"]/s["step"])+1):
        t = min(i*s["step"], s["duration"])
        angle, velocity = _angle(model, t)
        result.append(_sample(model, t, *geometry(model["parameters"], angle), velocity))
    return result


def parse_sample(model, time, rows):
    """Decode B, C and D node observations from MBDyn structural output."""
    b, c, d = (rows[label] for label in NODE_LABELS)
    radius2 = b[1]*b[1]+b[3]*b[3]
    if radius2 <= 1e-20:
        raise ValueError("The main gear link collapsed to its ground pivot.")
    value = _sample(model, time, b[1], b[3], c[1], c[3], (-b[3]*b[7]+b[1]*b[9])/radius2, d[1], d[3])
    value["closureError"] = max(value["closureError"], abs(b[2]), abs(c[2]), abs(d[2]))
    return value


def metrics(model, samples):
    """Compare observed linkage positions with the prescribed independent geometry."""
    errors = []
    angle_errors = []
    for q in samples:
        angle, _ = _angle(model, q["time"])
        bx, bz, cx, cz = geometry(model["parameters"], angle)
        errors.append(max(math.hypot(q["bx"]-bx, q["bz"]-bz), math.hypot(q["cx"]-cx, q["cz"]-cz)))
        angle_errors.append(abs(q["angle"]-angle))
    lengths = [q["actuatorLength"] for q in samples]
    return {"sampleCount": len(samples), "duration": samples[-1]["time"],
            "peakValue": max(abs(q["value"]) for q in samples), "valueUnit": "deg", "velocityUnit": "rad/s",
            "initialAngle": samples[0]["angle"], "finalAngle": samples[-1]["angle"],
            "actuatorTravel": max(lengths)-min(lengths), "actuatorLengthMin": min(lengths), "actuatorLengthMax": max(lengths),
            "maxConstraintError": max(q["closureError"] for q in samples),
            "maxGeometryError": max(errors), "maxDriveAngleError": max(angle_errors),
            "geometryErrorUnit": "m", "angleErrorUnit": "deg",
            "validationScope": "Prescribed planar kinematics and rigid-link closure; no hydraulic force, locks or aircraft certification."}


def deck(model, header):
    """Emit original rigid-body and ideal planar-joint input for MBDyn 1.7.3."""
    p, s = model["parameters"], model["simulation"]
    bx, bz, cx, cz = geometry(p, p["initialAngle"])
    dx, dz = p["groundX"], p["groundZ"]
    n = lambda value: format(float(value), ".14g")
    def vector(x, z):
        return f"{n(x)},0,{n(z)}"
    def body(label, mass, vx, vz, cgx, cgz):
        # A uniform slender link; a radius of 2% of length gives finite axial inertia.
        length2 = vx*vx+vz*vz
        axial = mass*.0004*length2/2
        transverse = mass*(length2+3*.0004*length2)/12
        xx = transverse+(axial-transverse)*vx*vx/length2
        zz = transverse+(axial-transverse)*vz*vz/length2
        xz = (axial-transverse)*vx*vz/length2
        return f"    body: {label}, {label}, {n(mass)}, {vector(cgx,cgz)}, sym, {n(xx)},0,{n(xz)},{n(transverse)},0,{n(zz)};\n"
    wx, wz = bx*p["mainLength"]/p["braceAttachment"], bz*p["mainLength"]/p["braceAttachment"]
    text = header + """# Original generic four-bar A-B-C-D. A=(0,0,0); nodes 1=B, 2=C, 3=D.
# Planar total joints remove redundant spatial constraints in the closed loop.
# Node 1 is driven only in rotation; nodes 2 and 3 obey physical closure.
begin: control data;
    max iterations: 30;
    initial stiffness: 1.e12;
    structural nodes: 3;
    rigid bodies: 3;
    joints: 5;
    gravity;
end: control data;
begin: nodes;
"""
    for label, x, z in ((1,bx,bz),(2,cx,cz),(3,dx,dz)):
        text += f"    structural: {label}, dynamic, {vector(x,z)}, eye, null, null;\n"
    text += "end: nodes;\nbegin: elements;\n"
    text += body(1,p["mainMass"],wx,wz,wx/2-bx,wz/2-bz)
    text += body(2,p["upperBraceMass"],bx-cx,bz-cz,(bx-cx)/2,(bz-cz)/2)
    text += body(3,p["lowerBraceMass"],cx-dx,cz-dz,(cx-dx)/2,(cz-dz)/2)
    text += f"""    joint: 1, total pin joint,
        1, position, {vector(-bx,-bz)}, position, null,
        position constraint, active,active,active, null,
        orientation constraint, active,active,active,
        single, 0,1,0, cosine, 0, {n(math.pi/s['duration'])}, {n(-math.radians(p['finalAngle']-p['initialAngle'])/2)}, half, 0;
    joint: 2, total pin joint,
        2, position, null, position, {vector(cx,cz)},
        position constraint, inactive,active,inactive, null,
        orientation constraint, active,inactive,active, null;
    joint: 3, total pin joint,
        3, position, null, position, {vector(dx,dz)},
        position constraint, active,active,active, null,
        orientation constraint, active,inactive,active, null;
    joint: 4, total joint,
        1, position, null,
        2, position, {vector(bx-cx,bz-cz)},
        position constraint, active,inactive,active, null;
    joint: 5, total joint,
        2, position, null,
        3, position, {vector(cx-dx,cz-dz)},
        position constraint, active,inactive,active, null;
    gravity: uniform, 0,0,-1, const, {n(p['gravity'])};
end: elements;
"""
    return text
