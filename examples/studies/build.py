"""Generate the featured Kinemeld studies: STEP geometry, measured mass properties and projects.

Each study is an editable spatial assembly. Solids are created with OpenCascade at their
initial world placement; mass, centre of mass and the full inertia tensor of every body are
measured from those solids at an explicit density, then expressed in body axes. Run with
`python examples/studies/build.py [study ...]` from the repository root.
"""
import base64
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import primitive_step  # noqa: E402
import spatial_assembly as spatial  # noqa: E402
import step_mass  # noqa: E402
from step_example_identity import identify_authored_step  # noqa: E402

OUT = Path(__file__).resolve().parent
STEEL, ALUMINIUM, RUBBER = 7850.0, 2700.0, 1150.0


def v(x, y, z):
    return {"x": float(x), "y": float(y), "z": float(z)}


def euler123(matrix):
    """Inverse of spatial.rotation: Rx(a) Ry(b) Rz(c), degrees."""
    b = math.asin(max(-1.0, min(1.0, matrix[0][2])))
    if abs(math.cos(b)) > 1e-9:
        a = math.atan2(-matrix[1][2], matrix[2][2])
        c = math.atan2(-matrix[0][1], matrix[0][0])
    else:
        a, c = math.atan2(matrix[2][1], matrix[1][1]), 0.0
    return tuple(math.degrees(angle) for angle in (a, b, c))


class Body:
    """A rigid body assembled from primitive solids given in body-local coordinates."""

    def __init__(self, identifier, name, pose, velocity=None):
        self.id, self.name = identifier, name
        self.pose = {"x": 0.0, "y": 0.0, "z": 0.0, "rx": 0.0, "ry": 0.0, "rz": 0.0, **{k: float(val) for k, val in pose.items()}}
        self.velocity = {"vx": 0.0, "vy": 0.0, "vz": 0.0, "wx": 0.0, "wy": 0.0, "wz": 0.0, **{k: float(val) for k, val in (velocity or {}).items()}}
        self.parts = []

    def add(self, shape, dimensions, density, at=(0, 0, 0), rotate=(0, 0, 0), label=""):
        """Place a primitive at a body-local position and Euler123 rotation (degrees)."""
        body_rotation = spatial.rotation(self.pose["rx"], self.pose["ry"], self.pose["rz"])
        world_rotation = spatial.matmul(body_rotation, spatial.rotation(*rotate))
        origin = [self.pose[k] for k in "xyz"]
        centre = [o + d for o, d in zip(origin, spatial.mul(body_rotation, list(at)))]
        rx, ry, rz = euler123(world_rotation)
        spec = {"shape": shape, "dimensions": dimensions, "pose": {"x": centre[0], "y": centre[1], "z": centre[2], "rx": rx, "ry": ry, "rz": rz}}
        data = primitive_step.generate_step(spec)
        measured = step_mass.calculate(data, density, "part-1")
        self.parts.append({"data": data, "measured": measured, "label": label or f"{self.id}-{shape}-{len(self.parts) + 1}"})
        return self

    def model(self):
        mass = sum(p["measured"]["mass"] for p in self.parts)
        centre = [sum(p["measured"]["mass"] * p["measured"]["centerOfMass"][k] for p in self.parts) / mass for k in "xyz"]
        world = [[0.0] * 3 for _ in range(3)]
        for part in self.parts:
            m = part["measured"]["mass"]
            d = [part["measured"]["centerOfMass"][k] - c for k, c in zip("xyz", centre)]
            dd = sum(x * x for x in d)
            for i in range(3):
                for j in range(3):
                    world[i][j] += part["measured"]["inertia"][i][j] + m * ((dd if i == j else 0.0) - d[i] * d[j])
        rotation = spatial.rotation(self.pose["rx"], self.pose["ry"], self.pose["rz"])
        local = spatial.matmul(spatial.matmul(spatial.transpose(rotation), world), rotation)
        offset = spatial.mul(spatial.transpose(rotation), [c - self.pose[k] for c, k in zip(centre, "xyz")])
        inertia = {"xx": local[0][0], "yy": local[1][1], "zz": local[2][2], "xy": local[0][1], "xz": local[0][2], "yz": local[1][2]}
        return {"id": self.id, "name": self.name, "mass": mass, "inertia": inertia, "centerOfMass": dict(zip("xyz", offset)),
                "pose": dict(self.pose), "velocity": dict(self.velocity)}


class Fixture:
    """Static ground geometry (stands, frames, guides) shown with the model but not simulated."""

    def __init__(self):
        self.parts = []

    def add(self, shape, dimensions, at, rotate=(0, 0, 0), label="fixture"):
        rx, ry, rz = euler123(spatial.rotation(*rotate))
        spec = {"shape": shape, "dimensions": dimensions, "pose": {"x": at[0], "y": at[1], "z": at[2], "rx": rx, "ry": ry, "rz": rz}}
        self.parts.append({"data": primitive_step.generate_step(spec), "label": label})
        return self


def project(name, bodies, joints, simulation, gravity=(0, 0, -9.81), view=None, fixture=None, **elements):
    model = {"kind": "spatial-assembly", "name": name, "parameters": {"gravity": v(*gravity)}, "simulation": simulation,
             "bodies": [body.model() for body in bodies], "joints": joints}
    model.update({key: value for key, value in elements.items() if value})
    check = spatial.validate(model)
    if not check["valid"]:
        raise ValueError(f"{name}: " + "; ".join(f"{item['field']}: {item['message']}" for item in check["issues"]))
    files, bindings = [], {}
    for body in bodies:
        for part in body.parts:
            index = len(files)
            files.append({"name": f"{part['label']}.step", "sha256": hashlib.sha256(part["data"]).hexdigest(),
                          "byteLength": len(part["data"]), "data": base64.b64encode(part["data"]).decode("ascii")})
            bindings[f"{index}:part-1"] = {"body": body.id, "pose": dict(body.pose)}
    for part in (fixture.parts if fixture else []):
        files.append({"name": f"{part['label']}.step", "sha256": hashlib.sha256(part["data"]).hexdigest(),
                      "byteLength": len(part["data"]), "data": base64.b64encode(part["data"]).decode("ascii")})
    step = {"schemaVersion": 1, "format": "step", "files": files, "bindings": bindings}
    identify_authored_step(step, {f"{index}:part-1": None for index in range(len(files))})
    document = {"format": "mbdyn-studio/1", "model": model, "assets": {"step": step}}
    if view:
        document["view"] = display_view(model, view)
    return document, check["summary"]


def display_view(model, view):
    """Saved cameras use the viewer's display frame, which recentres body origins and ground anchors."""
    points = [[b["pose"][k] for k in "xyz"] for b in model["bodies"]]
    points += [[j["anchorA"][k] for k in "xyz"] for j in model["joints"] if j["a"] == "ground"]
    for force in model.get("forces", []):
        points += [[force[f"anchor{side.upper()}"][k] for k in "xyz"] for side in "ab" if force[side] == "ground"]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    scale = max(max(h - l for h, l in zip(high, low)), 0.1)
    offset = [-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2] + 0.1 * scale]
    shifted = dict(view)
    for key in ("camera", "target"):
        if key in view:
            shifted[key] = [round(c + o, 6) for c, o in zip(view[key], offset)]
    return shifted


def write(folder, filename, document):
    path = OUT.parent / folder
    path.mkdir(exist_ok=True)
    (path / filename).write_text(json.dumps(document, indent=1) + "\n", encoding="utf8")
    return path / filename


# ---------------------------------------------------------------------------
# Studies


def spinning_top():
    """Heavy symmetric top on a fixed tip: precession with cuspidal nutation."""
    tilt, spin = 25.0, 120.0
    top = Body("top", "Spinning top", {"z": 0.0, "rx": tilt})
    axis = spatial.mul(spatial.rotation(tilt, 0, 0), [0, 0, 1])
    top.velocity.update(wx=spin * axis[0], wy=spin * axis[1], wz=spin * axis[2])
    top.add("regular-extrusion", {"radius": 0.065, "length": 0.018, "sides": 12}, STEEL, at=(0, 0, 0.09), label="flywheel")
    top.add("cylinder", {"radius": 0.006, "length": 0.17}, STEEL, at=(0, 0, 0.085), label="spindle")
    top.add("brick", {"x": 0.03, "y": 0.012, "z": 0.006}, ALUMINIUM, at=(0.05, 0, 0.102), label="marker")
    stand = [{"id": "tip", "type": "spherical", "a": "ground", "b": "top", "anchorA": v(0, 0, 0), "anchorB": v(0, 0, 0)}]
    table = Fixture().add("cylinder", {"radius": 0.13, "length": 0.012}, (0, 0, -0.006), label="table")
    table.add("cylinder", {"radius": 0.012, "length": 0.006}, (0, 0, 0.0), label="pivot-cup")
    return project("Gyroscopic top: precession and nutation", [top], stand, {"duration": 4.0, "step": 0.0005}, fixture=table,
                   view={"camera": [0.2, -0.3, 0.5], "target": [0, 0, 0.08], "signal": 3, "selection": "body", "trails": True, "trailWindow": 0, "trailPoint": "tip"})


def tumbling_handle():
    """Free T-handle in zero gravity spinning near its intermediate principal axis."""
    handle = Body("handle", "T-handle", {"z": 0.0}, {"wx": 6.0, "wy": 0.0, "wz": 0.03})
    handle.add("cylinder", {"radius": 0.014, "length": 0.22}, ALUMINIUM, at=(0, 0, 0), rotate=(0, 90, 0), label="crossbar")
    handle.add("cylinder", {"radius": 0.011, "length": 0.12}, ALUMINIUM, at=(0, 0.074, 0), rotate=(90, 0, 0), label="stem")
    handle.add("sphere", {"radius": 0.022}, STEEL, at=(0, 0.14, 0), label="knob")
    body = handle.model()
    # Shift the body origin to the centre of mass so the free body spins about a fixed point.
    shift = [body["centerOfMass"][k] for k in "xyz"]
    handle.pose.update(x=-shift[0], y=-shift[1], z=0.25 - shift[2])
    handle.parts.clear()
    handle.add("cylinder", {"radius": 0.014, "length": 0.22}, ALUMINIUM, at=(0, 0, 0), rotate=(0, 90, 0), label="crossbar")
    handle.add("cylinder", {"radius": 0.011, "length": 0.12}, ALUMINIUM, at=(0, 0.074, 0), rotate=(90, 0, 0), label="stem")
    handle.add("sphere", {"radius": 0.022}, STEEL, at=(0, 0.14, 0), label="knob")
    # Rigid-body angular velocity about a point that is not the origin also moves the origin.
    com = [handle.pose[k] + c for k, c in zip("xyz", spatial.mul(spatial.rotation(0, 0, 0), shift))]
    w = [handle.velocity[k] for k in ("wx", "wy", "wz")]
    r = [handle.pose[k] - c for k, c in zip("xyz", com)]
    vel = spatial.cross(w, r)
    handle.velocity.update(vx=vel[0], vy=vel[1], vz=vel[2])
    return project("Tumbling T-handle: intermediate-axis instability", [handle], [], {"duration": 12.0, "step": 0.002}, gravity=(0, 0, 0),
                   view={"camera": [0.42, -0.55, 0.42], "target": [0, 0, 0.25], "signal": 4, "selection": "body", "trails": True, "trailWindow": 1.5})


def chaotic_pendulums():
    """Two identical double pendulums released 0.001 degrees apart."""
    l1, l2, pivot, start = 0.32, 0.26, 0.85, 125.0
    bodies, joints = [], []
    for copy, (y, delta) in enumerate(((-0.09, 0.0), (0.09, 0.001))):
        upper = Body(f"upper{copy + 1}", f"Upper link {'AB'[copy]}", {"y": y, "z": pivot, "ry": start + delta})
        upper.add("brick", {"x": 0.024, "y": 0.018, "z": l1 + 0.024}, ALUMINIUM, at=(0, 0, -l1 / 2), label=f"upper-{copy + 1}")
        r = spatial.mul(spatial.rotation(0, start + delta, 0), [0, 0, -l1])
        lower = Body(f"lower{copy + 1}", f"Lower link {'AB'[copy]}", {"x": r[0], "y": y, "z": pivot + r[2], "ry": start + delta})
        lower.add("brick", {"x": 0.022, "y": 0.016, "z": l2 + 0.022}, ALUMINIUM, at=(0, 0, -l2 / 2), label=f"lower-{copy + 1}")
        lower.add("cylinder", {"radius": 0.024, "length": 0.03}, STEEL, at=(0, 0, -l2), rotate=(90, 0, 0), label=f"bob-{copy + 1}")
        bodies += [upper, lower]
        joints += [
            {"id": f"pivot{copy + 1}", "type": "revolute", "a": "ground", "b": upper.id, "anchorA": v(0, y, pivot), "anchorB": v(0, 0, 0), "axisA": v(0, 1, 0), "axisB": v(0, 1, 0)},
            {"id": f"elbow{copy + 1}", "type": "revolute", "a": upper.id, "b": lower.id, "anchorA": v(0, 0, -l1), "anchorB": v(0, 0, 0), "axisA": v(0, 1, 0), "axisB": v(0, 1, 0)},
        ]
    # A single rear post keeps the swing planes unobstructed from the camera side.
    frame = Fixture().add("brick", {"x": 0.04, "y": 0.36, "z": 0.04}, (0, 0.04, pivot + 0.03), label="crossbeam")
    frame.add("brick", {"x": 0.05, "y": 0.05, "z": pivot + 0.05}, (0, 0.22, (pivot + 0.05) / 2), label="post")
    frame.add("brick", {"x": 0.7, "y": 0.08, "z": 0.025}, (0, 0.22, 0.0125), label="foot")
    return project("Chaotic double pendulums: 0.001° apart", bodies, joints, {"duration": 14.0, "step": 0.002}, fixture=frame,
                   view={"camera": [0.55, -2.1, 0.95], "target": [0, 0, 0.55], "signal": 0, "selection": "node-lower2", "trails": True, "trailWindow": 1.2, "trailBodies": ["lower1", "lower2"]})


def slider_crank():
    """Torque-driven single-cylinder slider-crank with flywheel, loop closed by MBDyn."""
    crank_r, rod_l, theta = 0.06, 0.20, 35.0
    # Start away from top dead centre so the drive torque immediately turns the crank.
    pin = spatial.mul(spatial.rotation(0, theta, 0), [0, 0, crank_r])
    deck_z = pin[2] + math.sqrt(rod_l ** 2 - pin[0] ** 2)
    rod_angle = math.degrees(math.atan2(-pin[0], deck_z - pin[2]))
    crank = Body("crank", "Crankshaft and flywheel", {"ry": theta})
    crank.add("cylinder", {"radius": 0.11, "length": 0.025}, STEEL, at=(0, -0.06, 0), rotate=(90, 0, 0), label="flywheel")
    crank.add("cylinder", {"radius": 0.012, "length": 0.07}, STEEL, at=(0, -0.035, 0), rotate=(90, 0, 0), label="main-journal")
    crank.add("brick", {"x": 0.026, "y": 0.014, "z": crank_r + 0.032}, STEEL, at=(0, -0.016, crank_r / 2), label="crank-web")
    crank.add("cylinder", {"radius": 0.01, "length": 0.026}, STEEL, at=(0, -0.006, crank_r), rotate=(90, 0, 0), label="crank-pin")
    rod = Body("rod", "Connecting rod", {"x": pin[0], "z": pin[2], "ry": rod_angle})
    rod.add("brick", {"x": 0.016, "y": 0.012, "z": rod_l}, ALUMINIUM, at=(0, 0, rod_l / 2), label="rod-beam")
    rod.add("cylinder", {"radius": 0.02, "length": 0.014}, ALUMINIUM, at=(0, 0, 0), rotate=(90, 0, 0), label="big-end")
    rod.add("cylinder", {"radius": 0.013, "length": 0.014}, ALUMINIUM, at=(0, 0, rod_l), rotate=(90, 0, 0), label="small-end")
    piston = Body("piston", "Piston", {"z": deck_z})
    piston.add("cylinder", {"radius": 0.045, "length": 0.06}, ALUMINIUM, at=(0, 0, 0.018), label="piston-crown")
    joints = [
        {"id": "main_bearing", "type": "revolute", "a": "ground", "b": "crank", "anchorA": v(0, 0, 0), "anchorB": v(0, 0, 0), "axisA": v(0, 1, 0), "axisB": v(0, 1, 0)},
        {"id": "crank_pin", "type": "spherical", "a": "crank", "b": "rod", "anchorA": v(0, 0, crank_r), "anchorB": v(0, 0, 0)},
        {"id": "wrist_pin", "type": "universal", "a": "rod", "b": "piston", "anchorA": v(0, 0, rod_l), "anchorB": v(0, 0, 0), "axisA": v(1, 0, 0), "axisB": v(0, 1, 0)},
        {"id": "cylinder_bore", "type": "prismatic", "a": "ground", "b": "piston", "anchorA": v(0, 0, deck_z), "anchorB": v(0, 0, 0), "axisA": v(0, 0, 1)},
    ]
    # Constant motor torque against a viscous pumping load on the piston: steady speed ω ≈ 2T / (c r²).
    drive = [{"id": "motor", "joint": "main_bearing", "amplitude": 0.0, "frequencyHz": 1.0, "offset": 2.0}]
    load = [{"id": "pumping_load", "type": "linear-spring-damper", "a": "ground", "b": "piston", "anchorA": v(0, 0, deck_z + 0.25),
             "anchorB": v(0, 0, 0), "stiffness": 0.0, "damping": 90.0, "restLength": 0.25}]
    block = Fixture().add("brick", {"x": 0.32, "y": 0.2, "z": 0.02}, (0, -0.03, -0.14), label="base-plate")
    block.add("brick", {"x": 0.05, "y": 0.03, "z": 0.13}, (0, -0.09, -0.07), label="bearing-pedestal")
    for x in (-0.054, 0.054):
        block.add("brick", {"x": 0.006, "y": 0.05, "z": 0.24}, (x, 0, deck_z + 0.03), label="bore-guide")
    block.add("brick", {"x": 0.12, "y": 0.05, "z": 0.012}, (0, 0, deck_z + 0.156), label="cylinder-head")
    return project("Slider-crank engine: torque-driven run-up", [crank, rod, piston], joints, {"duration": 4.0, "step": 0.0005}, fixture=block,
                   view={"camera": [0.44, 0.66, 0.3], "target": [0, 0, 0.12], "signal": 3, "selection": "body", "trails": True, "trailWindow": 0, "trailBodies": ["rod"]},
                   jointTorques=drive, forces=load)


def gear_drop():
    """Drop test: airframe share on a guide, oleo-pneumatic strut and damped tyre contact."""
    drop, tyre_r = 0.18, 0.22
    axle_z = tyre_r + drop
    strut_len = 0.55
    airframe = Body("airframe", "Airframe share (drop carriage)", {"z": axle_z + strut_len}, {"vz": -2.0})
    airframe.add("brick", {"x": 0.7, "y": 0.42, "z": 0.12}, STEEL, at=(0, 0, 0.30), label="carriage")
    airframe.add("cylinder", {"radius": 0.06, "length": 0.40}, ALUMINIUM, at=(0, 0, -0.05), label="outer-cylinder")
    gear = Body("wheel", "Piston, axle and wheel", {"z": axle_z}, {"vz": -2.0})
    gear.add("cylinder", {"radius": 0.038, "length": 0.42}, STEEL, at=(0, 0, 0.21), label="sliding-piston")
    gear.add("cylinder", {"radius": tyre_r, "length": 0.16}, RUBBER, at=(0, 0, 0), rotate=(90, 0, 0), label="tyre")
    gear.add("cylinder", {"radius": 0.12, "length": 0.17}, ALUMINIUM, at=(0, 0, 0), rotate=(90, 0, 0), label="rim")
    joints = [
        {"id": "drop_guide", "type": "prismatic", "a": "ground", "b": "airframe", "anchorA": v(0, 0, axle_z + strut_len), "anchorB": v(0, 0, 0), "axisA": v(0, 0, 1)},
        {"id": "oleo_slide", "type": "prismatic", "a": "airframe", "b": "wheel", "anchorA": v(0, 0, -strut_len), "anchorB": v(0, 0, 0), "axisA": v(0, 0, 1)},
    ]
    oleo = [{"id": "oleo", "type": "oleo-strut", "a": "wheel", "b": "airframe", "anchorA": v(0, 0, 0), "anchorB": v(0, 0, 0),
             "restLength": strut_len, "pressure": 3.6e5, "gasArea": 0.006, "gasVolume": 0.004, "gamma": 1.3,
             "minLength": strut_len - 0.20, "maxLength": strut_len, "stopStiffness": 2.0e6, "stopDamping": 4.0e3,
             "fluidArea": 0.006, "fluidDensity": 850.0, "dischargeCoefficient": 0.7,
             "compressionMeteringArea": 2.4e-4, "reboundMeteringArea": 1.4e-4}]
    contact = [{"id": "tyre", "body": "wheel", "center": v(0, 0, 0), "radius": tyre_r, "planePoint": v(0, 0, 0), "planeNormal": v(0, 0, 1),
                "stiffness": 6.0e5, "damping": 1.5e3}]
    tower = Fixture()
    for x in (-0.42, 0.42):
        tower.add("brick", {"x": 0.06, "y": 0.06, "z": 1.6}, (x, 0, 0.8), label="drop-tower-column")
    tower.add("brick", {"x": 0.96, "y": 0.08, "z": 0.06}, (0, 0, 1.63), label="drop-tower-head")
    return project("Landing-gear drop test: oleo strut and tyre", [airframe, gear], joints, {"duration": 1.2, "step": 0.0002}, fixture=tower,
                   view={"camera": [1.55, -2.35, 1.05], "target": [0, 0, 0.6], "signal": 18, "selection": "node-wheel", "trails": False},
                   forces=oleo, contacts=contact)


def align_z(direction):
    """Euler123 angles (degrees) that rotate local +Z onto a world direction."""
    z = [c / math.sqrt(sum(d * d for d in direction)) for c in direction]
    seed = [1.0, 0.0, 0.0] if abs(z[0]) < 0.9 else [0.0, 1.0, 0.0]
    x = spatial.cross(seed, z)
    x = [c / math.sqrt(sum(d * d for d in x)) for c in x]
    y = spatial.cross(z, x)
    return euler123([[x[i], y[i], z[i]] for i in range(3)])


def strut(body, a, b, width, depth, density, label):
    """A straight brick member between two body-local points."""
    d = [q - p for p, q in zip(a, b)]
    length = math.sqrt(sum(c * c for c in d))
    body.add("brick", {"x": width, "y": depth, "z": length}, density, at=[(p + q) / 2 for p, q in zip(a, b)], rotate=align_z(d), label=label)


def quarter_car():
    """SLA double wishbone on a wheel-pad rig: vehicle X forward, Y left, Z up (left-front corner)."""
    wc = (0.0, 0.76, 0.30)  # wheel centre
    lo_in, lo_ball = (0.0, 0.30, 0.17), (0.0, 0.68, 0.15)
    up_in, up_ball = (0.0, 0.42, 0.50), (0.0, 0.645, 0.47)
    # Tie-rod pivots sit on the lines through the wishbone pivots (inboard) and ball joints (outboard) to limit bump steer.
    steer_in, steer_out = (-0.13, 0.345, 0.294), (-0.13, 0.667, 0.27)
    spring_top, spring_low = (0.0, 0.50, 0.74), (0.0, 0.56, 0.16)
    rel = lambda point, origin: tuple(p - o for p, o in zip(point, origin))

    lower = Body("lower_arm", "Lower wishbone", dict(zip("xyz", lo_in)))
    for side in (-1, 1):
        strut(lower, (0.13 * side, 0, 0), rel(lo_ball, lo_in), 0.028, 0.022, STEEL, f"lower-arm-{'rear' if side < 0 else 'front'}")
    lower.add("cylinder", {"radius": 0.02, "length": 0.30}, STEEL, at=(0, 0, 0), rotate=(0, 90, 0), label="lower-pivot-tube")
    lower.add("cylinder", {"radius": 0.024, "length": 0.04}, STEEL, at=rel(spring_low, lo_in), label="spring-seat")
    upper = Body("upper_arm", "Upper wishbone", dict(zip("xyz", up_in)))
    for side in (-1, 1):
        strut(upper, (0.10 * side, 0, 0), rel(up_ball, up_in), 0.022, 0.018, STEEL, f"upper-arm-{'rear' if side < 0 else 'front'}")
    upper.add("cylinder", {"radius": 0.016, "length": 0.22}, STEEL, at=(0, 0, 0), rotate=(0, 90, 0), label="upper-pivot-tube")
    knuckle = Body("knuckle", "Knuckle", dict(zip("xyz", wc)))
    strut(knuckle, rel(lo_ball, wc), rel(up_ball, wc), 0.05, 0.035, STEEL, "upright")
    knuckle.add("cylinder", {"radius": 0.03, "length": 0.09}, STEEL, at=(0, -0.045, 0), rotate=(90, 0, 0), label="spindle")
    strut(knuckle, (0, -0.06, -0.03), rel(steer_out, wc), 0.022, 0.022, STEEL, "steering-arm")
    wheel = Body("wheel", "Wheel and tyre", dict(zip("xyz", wc)))
    wheel.add("cylinder", {"radius": 0.30, "length": 0.20}, 250.0, at=(0, 0.02, 0), rotate=(90, 0, 0), label="tyre")
    wheel.add("cylinder", {"radius": 0.20, "length": 0.205}, 450.0, at=(0, 0.02, 0), rotate=(90, 0, 0), label="rim")
    wheel.add("brick", {"x": 0.05, "y": 0.012, "z": 0.24}, ALUMINIUM, at=(0, 0.13, 0), label="spoke-marker")

    joints = [
        {"id": "lower_pivot", "type": "revolute", "a": "ground", "b": "lower_arm", "anchorA": v(*lo_in), "anchorB": v(0, 0, 0), "axisA": v(1, 0, 0), "axisB": v(1, 0, 0)},
        {"id": "upper_pivot", "type": "revolute", "a": "ground", "b": "upper_arm", "anchorA": v(*up_in), "anchorB": v(0, 0, 0), "axisA": v(1, 0, 0), "axisB": v(1, 0, 0)},
        {"id": "lower_ball", "type": "spherical", "a": "lower_arm", "b": "knuckle", "anchorA": v(*rel(lo_ball, lo_in)), "anchorB": v(*rel(lo_ball, wc))},
        {"id": "upper_ball", "type": "spherical", "a": "upper_arm", "b": "knuckle", "anchorA": v(*rel(up_ball, up_in)), "anchorB": v(*rel(up_ball, wc))},
        {"id": "wheel_bearing", "type": "revolute", "a": "knuckle", "b": "wheel", "anchorA": v(0, 0, 0), "anchorB": v(0, 0, 0), "axisA": v(0, 1, 0), "axisB": v(0, 1, 0)},
    ]
    spring_len = math.dist(spring_top, spring_low)
    tie_len = math.dist(steer_in, steer_out)
    corner_load = 3200.0
    forces = [
        # Preloaded coil-over: the free length leaves the static corner load near design ride height.
        {"id": "coilover", "type": "linear-spring-damper", "a": "ground", "b": "lower_arm", "anchorA": v(*spring_top), "anchorB": v(*rel(spring_low, lo_in)),
         "stiffness": 60000.0, "damping": 600.0, "restLength": spring_len + 0.070},
        # The tie rod is an axially stiff link from the steering rack; it fixes steer and creates bump steer.
        {"id": "tie_rod", "type": "linear-spring-damper", "a": "ground", "b": "knuckle", "anchorA": v(*steer_in), "anchorB": v(*rel(steer_out, wc)),
         "stiffness": 1.0e5, "damping": 200.0, "restLength": tie_len},
    ]
    loads = [{"id": "wheel_pad", "body": "wheel", "frame": "global", "point": v(0, 0, 0), "force": v(0, 0, 1), "torque": v(0, 0, 0),
              "offset": corner_load, "amplitude": 1600.0, "frequencyHz": 0.8}]
    chassis = Fixture().add("brick", {"x": 0.7, "y": 0.08, "z": 0.08}, (0, 0.22, 0.17), label="lower-rail")
    chassis.add("brick", {"x": 0.5, "y": 0.08, "z": 0.08}, (0, 0.34, 0.50), label="upper-rail")
    chassis.add("brick", {"x": 0.08, "y": 0.08, "z": 0.62}, (0, 0.30, 0.45), label="tower")
    chassis.add("brick", {"x": 0.16, "y": 0.2, "z": 0.04}, (0, 0.48, 0.78), label="spring-tower")
    chassis.add("brick", {"x": 0.06, "y": 0.06, "z": 0.06}, steer_in, label="steering-rack-end")
    return project("Double-wishbone quarter-car: wheel-travel sweep", [lower, upper, knuckle, wheel], joints, {"duration": 2.5, "step": 0.0004}, fixture=chassis,
                   view={"camera": [1.55, -0.15, 0.8], "target": [0, 0.5, 0.33], "signal": 2, "selection": "node-knuckle", "trails": False},
                   forces=forces, loads=loads)


STUDIES = {
    "quarter-car": ("quarter-car", "quarter-car.mbdyn-studio", quarter_car),
    "spinning-top": ("gyroscopic-top", "gyroscopic-top.mbdyn-studio", spinning_top),
    "tumbling-handle": ("tumbling-handle", "tumbling-handle.mbdyn-studio", tumbling_handle),
    "chaotic-pendulums": ("chaotic-pendulums", "chaotic-pendulums.mbdyn-studio", chaotic_pendulums),
    "slider-crank": ("slider-crank", "slider-crank.mbdyn-studio", slider_crank),
    "gear-drop": ("gear-drop-test", "gear-drop-test.mbdyn-studio", gear_drop),
}


def main(selected):
    for key in selected or STUDIES:
        folder, filename, build = STUDIES[key]
        document, summary = build()
        path = write(folder, filename, document)
        bodies = ", ".join(f"{b['id']} {b['mass']:.3f} kg" for b in document["model"]["bodies"])
        print(f"{key}: {path.relative_to(ROOT)} · {summary['timeSteps']} steps · {bodies}")


if __name__ == "__main__":
    main(sys.argv[1:])
