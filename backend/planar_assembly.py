"""Original, user-authored planar rigid-body trees; actual MBDyn dynamics only."""

import csv
import math
import re

KIND = "planar-assembly"
MAX_BODIES = 16
MAX_FORCES = 32
MAX_LOADS = 32
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,31}\Z")


def rotate(angle, point):
    """Body-local X/Z to global X/Z for a rotation about positive Y."""
    c, s = math.cos(angle), math.sin(angle)
    return c * point["x"] + s * point["z"], -s * point["x"] + c * point["z"]


def anchor_position(body, anchor):
    if body is None:
        return anchor["x"], anchor["z"]
    x, z = rotate(math.radians(body["pose"]["angleDeg"]), anchor)
    return body["pose"]["x"] + x, body["pose"]["z"] + z


def anchor_velocity(body, anchor):
    if body is None:
        return 0., 0.
    x, z = rotate(math.radians(body["pose"]["angleDeg"]), anchor)
    v = body["velocity"]
    return v["vx"] + v["omega"] * z, v["vz"] - v["omega"] * x


def spring_state(force, bodies):
    """Reconstruct axial state from actual body poses; tension is positive."""
    a, b = bodies.get(force["a"]), bodies.get(force["b"])
    pa, pb = anchor_position(a, force["anchorA"]), anchor_position(b, force["anchorB"])
    va, vb = anchor_velocity(a, force["anchorA"]), anchor_velocity(b, force["anchorB"])
    dx, dz = pb[0] - pa[0], pb[1] - pa[1]
    length = math.hypot(dx, dz)
    if length < 1e-9:
        raise ValueError(f"Spring {force['id']} collapsed to zero length; its force direction is undefined.")
    rate = (dx * (vb[0] - va[0]) + dz * (vb[1] - va[1])) / length
    extension = length - force["restLength"]
    return {"id": force["id"], "length": length, "extension": extension, "rate": rate,
            "force": force["stiffness"] * extension + force["damping"] * rate}


def prismatic_state(joint, parent, child):
    """Return slider coordinate and dimensioned constraint residuals in the parent frame."""
    pa, pb = anchor_position(parent, joint["parentAnchor"]), anchor_position(child, joint["childAnchor"])
    va, vb = anchor_velocity(parent, joint["parentAnchor"]), anchor_velocity(child, joint["childAnchor"])
    parent_angle = parent["pose"]["angleDeg"] if parent else 0.
    omega_a = parent["velocity"]["omega"] if parent else 0.
    angle = math.radians(parent_angle + joint["axisAngleDeg"])
    ux, uz = math.cos(angle), -math.sin(angle)
    nx, nz = -uz, ux
    dx, dz = pb[0] - pa[0], pb[1] - pa[1]
    coordinate = ux * dx + uz * dz
    transverse = nx * dx + nz * dz
    velocity = ux * (vb[0] - va[0]) + uz * (vb[1] - va[1]) - omega_a * transverse
    transverse_velocity = nx * (vb[0] - va[0]) + nz * (vb[1] - va[1]) + omega_a * coordinate
    relative = math.radians(child["pose"]["angleDeg"] - parent_angle - joint["referenceAngleDeg"])
    return {"position": coordinate, "velocity": velocity, "transverse": transverse, "transverseVelocity": transverse_velocity,
            "angle": math.atan2(math.sin(relative), math.cos(relative)),
            "angularVelocity": child["velocity"]["omega"] - omega_a}


def validate(model):
    issues = []
    def issue(field, message, level="error"):
        issues.append({"level": level, "field": field, "message": message})
    def obj(value, fields, path):
        if not isinstance(value, dict):
            issue(path, "Supply an object.")
            return False
        for field in value.keys() - fields:
            issue(f"{path}.{field}".strip("."), "Unsupported field; it will not be ignored.")
        for field in fields - value.keys():
            issue(f"{path}.{field}".strip("."), "Required field is missing.")
        return True
    def numbers(value, bounds, path):
        if not obj(value, set(bounds), path):
            return
        for field, (low, high) in bounds.items():
            number = value.get(field)
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not low <= number <= high:
                issue(f"{path}.{field}", f"Enter a finite number from {low:g} to {high:g}.")
    def identifier(value, path):
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value) or value == "ground":
            issue(path, "Use a unique identifier starting with a letter, followed by letters, digits, _ or - (32 characters maximum); ground is reserved.")
    def name(value, path):
        if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(ord(c) < 32 for c in value):
            issue(path, "Use 1–120 printable characters.")
    summary = {"kind": KIND, "units": "kg, m, s, kg*m^2; pose angle in degrees; angular velocity rad/s", "scope": "Planar XZ rigid-body trees with revolute and prismatic joints"}
    if not obj(model, {"kind", "name", "parameters", "simulation", "bodies", "joints"} | ({key for key in ("forces", "loads", "rotationalElements", "jointTorques") if isinstance(model, dict) and key in model}), ""):
        return {"valid": False, "issues": issues, "summary": summary}
    if model.get("kind") != KIND:
        issue("kind", "Choose planar-assembly.")
    name(model.get("name"), "name")
    numbers(model.get("parameters"), {"gravity": (0, 100)}, "parameters")
    numbers(model.get("simulation"), {"duration": (.01, 30), "step": (.0001, .02)}, "simulation")
    bodies, joints, forces, loads = model.get("bodies"), model.get("joints"), model.get("forces", []), model.get("loads", [])
    rotational, actuators = model.get("rotationalElements", []), model.get("jointTorques", [])
    if not isinstance(bodies, list) or not 1 <= len(bodies) <= MAX_BODIES:
        issue("bodies", "Supply 1–16 rigid bodies.")
    if not isinstance(joints, list) or not 1 <= len(joints) <= MAX_BODIES:
        issue("joints", "Supply one parent joint per body (1–16 joints).")
    if not isinstance(forces, list) or len(forces) > MAX_FORCES:
        issue("forces", "Supply at most 32 spring-damper elements.")
    if not isinstance(loads, list) or len(loads) > MAX_LOADS:
        issue("loads", "Supply at most 32 constant planar loads.")
    for field, values in (("rotationalElements", rotational), ("jointTorques", actuators)):
        if not isinstance(values, list) or len(values) > 32:
            issue(field, "Supply at most 32 elements.")
    if not isinstance(bodies, list) or not isinstance(joints, list) or not isinstance(forces, list) or not isinstance(loads, list) or not isinstance(rotational, list) or not isinstance(actuators, list) or len(bodies) > MAX_BODIES or len(joints) > MAX_BODIES or len(forces) > MAX_FORCES or len(loads) > MAX_LOADS or len(rotational) > 32 or len(actuators) > 32:
        return {"valid": False, "issues": issues, "summary": summary}
    for i, body in enumerate(bodies):
        path = f"bodies.{i}"
        if not obj(body, {"id", "name", "mass", "inertia", "pose", "velocity"}, path):
            continue
        identifier(body.get("id"), path + ".id")
        name(body.get("name"), path + ".name")
        numbers({"mass": body.get("mass")}, {"mass": (.0001, 1e6)}, path)
        numbers(body.get("inertia"), {"xx": (1e-9, 1e9), "yy": (1e-9, 1e9), "zz": (1e-9, 1e9)}, path + ".inertia")
        numbers(body.get("pose"), {"x": (-1000, 1000), "z": (-1000, 1000), "angleDeg": (-360, 360)}, path + ".pose")
        numbers(body.get("velocity"), {"vx": (-1000, 1000), "vz": (-1000, 1000), "omega": (-1000, 1000)}, path + ".velocity")
    for i, joint in enumerate(joints):
        path = f"joints.{i}"
        joint_fields = {"id", "type", "parent", "child", "parentAnchor", "childAnchor"}
        if isinstance(joint, dict) and joint.get("type") == "prismatic":
            joint_fields |= {"axisAngleDeg", "referenceAngleDeg"}
        if not obj(joint, joint_fields, path):
            continue
        identifier(joint.get("id"), path + ".id")
        if joint.get("type") not in ("revolute", "prismatic"):
            issue(path + ".type", "Only planar revolute and prismatic joints are supported; loops and motion drivers are not implemented.")
        if joint.get("type") == "prismatic":
            numbers({key: joint.get(key) for key in ("axisAngleDeg", "referenceAngleDeg")}, {"axisAngleDeg": (-360, 360), "referenceAngleDeg": (-360, 360)}, path)
        for field in ("parent", "child"):
            if not (field == "parent" and joint.get(field) == "ground"):
                identifier(joint.get(field), path + "." + field)
        for field in ("parentAnchor", "childAnchor"):
            numbers(joint.get(field), {"x": (-1000, 1000), "z": (-1000, 1000)}, path + "." + field)
    for i, force in enumerate(forces):
        path = f"forces.{i}"
        if not obj(force, {"id", "type", "a", "b", "anchorA", "anchorB", "stiffness", "damping", "restLength"}, path):
            continue
        identifier(force.get("id"), path + ".id")
        if force.get("type") != "linear-spring-damper":
            issue(path + ".type", "Only linear spring-damper elements are supported.")
        for field in ("a", "b"):
            if force.get(field) != "ground":
                identifier(force.get(field), path + "." + field)
        for field in ("anchorA", "anchorB"):
            numbers(force.get(field), {"x": (-1000, 1000), "z": (-1000, 1000)}, path + "." + field)
        numbers({key: force.get(key) for key in ("stiffness", "damping", "restLength")},
                {"stiffness": (0, 1e9), "damping": (0, 1e9), "restLength": (1e-6, 2000)}, path)
    for i, load in enumerate(loads):
        path = f"loads.{i}"
        if not obj(load, {"id", "body", "fx", "fz", "torque"}, path):
            continue
        identifier(load.get("id"), path + ".id")
        identifier(load.get("body"), path + ".body")
        numbers({key: load.get(key) for key in ("fx", "fz", "torque")},
                {"fx": (-1e9, 1e9), "fz": (-1e9, 1e9), "torque": (-1e9, 1e9)}, path)
    for group, values, fields in (("rotationalElements", rotational, {"stiffness": (0, 1e9), "damping": (0, 1e9), "restAngleDeg": (-180, 180)}),
                                  ("jointTorques", actuators, {"amplitude": (-1e9, 1e9), "frequencyHz": (.001, 1000), "offset": (-1e9, 1e9)})):
        for i, value in enumerate(values):
            path = f"{group}.{i}"
            if not obj(value, {"id", "joint"} | set(fields), path):
                continue
            identifier(value.get("id"), path + ".id")
            identifier(value.get("joint"), path + ".joint")
            numbers({key: value.get(key) for key in fields}, fields, path)
    if issues:
        return {"valid": False, "issues": issues, "summary": summary}
    lookup = {body["id"]: body for body in bodies}
    for group, values in (("bodies", bodies), ("joints", joints), ("forces", forces), ("loads", loads), ("rotationalElements", rotational), ("jointTorques", actuators)):
        seen = set()
        for i, value in enumerate(values):
            if value["id"] in seen:
                issue(f"{group}.{i}.id", "Identifier is repeated in this collection.")
            seen.add(value["id"])
    for i, body in enumerate(bodies):
        inertia = body["inertia"]
        for axis in ("xx", "yy", "zz"):
            if inertia[axis] > sum(value for key, value in inertia.items() if key != axis) * (1 + 1e-12):
                issue(f"bodies.{i}.inertia.{axis}", "Principal inertias must satisfy the triangle inequalities about the body's center of mass.")
    incoming = {}
    for i, joint in enumerate(joints):
        for field in ("parent", "child"):
            if joint[field] not in lookup and not (field == "parent" and joint[field] == "ground"):
                issue(f"joints.{i}.{field}", "Reference does not name a declared body.")
        if joint["child"] in incoming:
            issue(f"joints.{i}.child", "A body must have exactly one parent joint. Closed loops and redundant joints are not supported.")
        incoming[joint["child"]] = (i, joint)
    for i, force in enumerate(forces):
        for field in ("a", "b"):
            if force[field] not in lookup and force[field] != "ground":
                issue(f"forces.{i}.{field}", "Reference does not name ground or a declared body.")
        if force["a"] == force["b"]:
            issue(f"forces.{i}.b", "Connect two different bodies, or ground and a body.")
        if force["stiffness"] == 0 and force["damping"] == 0:
            issue(f"forces.{i}.stiffness", "Set nonzero stiffness or damping.")
    for i, load in enumerate(loads):
        if load["body"] not in lookup:
            issue(f"loads.{i}.body", "Reference must name a declared dynamic body.")
        if load["fx"] == 0 and load["fz"] == 0 and load["torque"] == 0:
            issue(f"loads.{i}.fx", "Set a nonzero force or torque component.")
    joint_lookup = {joint["id"]: joint for joint in joints}
    for group, values in (("rotationalElements", rotational), ("jointTorques", actuators)):
        for i, value in enumerate(values):
            joint = joint_lookup.get(value["joint"])
            if not joint or joint["type"] != "revolute":
                issue(f"{group}.{i}.joint", "Reference an existing revolute joint.")
            if group == "rotationalElements":
                if value["stiffness"] == 0 and value["damping"] == 0:
                    issue(f"{group}.{i}.stiffness", "Set nonzero stiffness or damping.")
                if abs(value["restAngleDeg"]) >= 180:
                    issue(f"{group}.{i}.restAngleDeg", "Use a rest angle strictly between -180 and 180 degrees.")
            elif value["amplitude"] == 0 and value["offset"] == 0:
                issue(f"{group}.{i}.amplitude", "Set a nonzero amplitude or offset.")
            elif value["frequencyHz"] * model["simulation"]["step"] > .05:
                issue(f"{group}.{i}.frequencyHz", "Use at least 20 simulation steps per actuation cycle.")
    for i, body in enumerate(bodies):
        if body["id"] not in incoming:
            issue(f"bodies.{i}.id", "Connect this body to ground through a parent joint.")
    if issues:
        return {"valid": False, "issues": issues, "summary": summary}
    for i, force in enumerate(forces):
        distance = math.dist(anchor_position(lookup.get(force["a"]), force["anchorA"]), anchor_position(lookup.get(force["b"]), force["anchorB"]))
        if distance < 1e-6:
            issue(f"forces.{i}.anchorB", "Spring attachment points must initially be at least 1e-6 m apart so their force direction is defined.")
    for i, element in enumerate(rotational):
        joint = joint_lookup[element["joint"]]
        parent, child = lookup.get(joint["parent"]), lookup[joint["child"]]
        angle = math.radians(child["pose"]["angleDeg"] - (parent["pose"]["angleDeg"] if parent else 0) - element["restAngleDeg"])
        if abs(angle) >= math.pi - 1e-6:
            issue(f"rotationalElements.{i}.restAngleDeg", "Initial relative angle minus rest angle must be strictly within +/-180 degrees; multiple turns are unsupported.")
    for body in bodies:
        seen, current = set(), body["id"]
        while current != "ground":
            if current in seen:
                issue(f"joints.{incoming[current][0]}.parent", "Joint cycle detected. Every body must reach ground through a tree of joints.")
                break
            seen.add(current)
            current = incoming[current][1]["parent"]
    for i, joint in enumerate(joints):
        parent, child = lookup.get(joint["parent"]), lookup[joint["child"]]
        if joint["type"] == "prismatic":
            state = prismatic_state(joint, parent, child)
            if abs(state["transverse"]) > 1e-7:
                issue(f"joints.{i}.childAnchor", f"Slider attachment is {abs(state['transverse']):.6g} m from its guide line; correct its pose or anchors.")
            if abs(state["transverseVelocity"]) > 1e-7:
                issue(f"joints.{i}.childAnchor", f"Slider transverse velocity differs by {abs(state['transverseVelocity']):.6g} m/s; set compatible initial velocities.")
            if abs(state["angle"]) > 1e-7:
                issue(f"joints.{i}.referenceAngleDeg", f"Slider relative orientation differs by {abs(state['angle']):.6g} rad from its reference angle.")
            if abs(state["angularVelocity"]) > 1e-7:
                issue(f"joints.{i}.referenceAngleDeg", f"Slider angular velocities differ by {abs(state['angularVelocity']):.6g} rad/s.")
            continue
        error = math.dist(anchor_position(parent, joint["parentAnchor"]), anchor_position(child, joint["childAnchor"]))
        if error > 1e-7:
            issue(f"joints.{i}.childAnchor", f"Initial attachment points differ by {error:.6g} m. Adjust body pose or local anchors until they coincide within 1e-7 m.")
        error = math.dist(anchor_velocity(parent, joint["parentAnchor"]), anchor_velocity(child, joint["childAnchor"]))
        if error > 1e-7:
            issue(f"joints.{i}.childAnchor", f"Initial attachment velocities differ by {error:.6g} m/s. Set compatible center-of-mass and angular velocities.")
    steps = math.ceil(model["simulation"]["duration"] / model["simulation"]["step"])
    if steps > 20000 or steps * len(bodies) > 160000:
        issue("simulation.step", "Limit a job to 20,000 steps and 160,000 body-steps; shorten the duration or reduce body count before changing accuracy settings.")
    if steps * len(forces) > 160000:
        issue("simulation.step", "Limit a job to 160,000 spring-steps; shorten the duration or reduce the number of spring elements.")
    if steps * len(bodies) * len(loads) > 1600000:
        issue("simulation.step", "Limit a job to 1,600,000 body-load output values; shorten the duration or reduce bodies or loads.")
    if steps * len(bodies) * (len(rotational) + len(actuators)) > 1600000:
        issue("simulation.step", "Limit rotational element and actuator output to 1,600,000 body-values.")
    if any(abs(body["velocity"]["omega"]) * model["simulation"]["step"] > .1 for body in bodies):
        issue("simulation.step", "Resolve initial rotation with at most 0.1 rad per step.")
    summary.update(bodies=len(bodies), structuralNodes=len(bodies), joints=len(joints), forces=len(forces), loads=len(loads), degreesOfFreedom=len(bodies), timeSteps=steps,
                   nodeLabels={body["id"]: i + 1 for i, body in enumerate(bodies)})
    if rotational or actuators:
        summary.update(rotationalElements=len(rotational), jointTorques=len(actuators))
    return {"valid": not issues, "issues": issues, "summary": summary}


def deck(model):
    check = validate(model)
    if not check["valid"]:
        raise ValueError("Planar assembly validation failed: " + "; ".join(item["field"] + ": " + item["message"] for item in check["issues"]))
    number = lambda value: format(float(value), ".15g")
    vector = lambda point: f"{number(point['x'])},0,{number(point['z'])}"
    bodies, joints, simulation, forces, loads = model["bodies"], model["joints"], model["simulation"], model.get("forces", []), model.get("loads", [])
    rotational, actuators = model.get("rotationalElements", []), model.get("jointTorques", [])
    joint_lookup = {joint["id"]: joint for joint in joints}
    load_element_count = sum(int(bool(load["fx"] or load["fz"])) + int(bool(load["torque"])) for load in loads)
    load_element_count += sum(1 + int(joint_lookup[drive["joint"]]["parent"] != "ground") for drive in actuators)
    has_ground = any(force["a"] == "ground" or force["b"] == "ground" for force in forces) or any(joint["type"] == "prismatic" and joint["parent"] == "ground" for joint in joints) or any(joint_lookup[element["joint"]]["parent"] == "ground" for element in rotational)
    slider_count = sum(joint["type"] == "prismatic" for joint in joints)
    labels = {body["id"]: i + 1 for i, body in enumerate(bodies)}
    text = f"""# Original Kinemeld user-authored planar rigid-body tree. SI units.
# Center-of-mass nodes; body-local principal inertia; motion in XZ about Y.
begin: data;
    problem: initial value;
end: data;
begin: initial value;
    initial time: 0;
    final time: {number(simulation['duration'])};
    time step: {number(simulation['step'])};
    max iterations: 40;
    tolerance: 1.e-9;
    derivatives tolerance: 1.e-8;
    derivatives max iterations: 100;
    derivatives coefficient: 1.e-3, auto;
end: initial value;
begin: control data;
    max iterations: 40;
    {'skip initial joint assembly;' if forces or rotational else ''}
    structural nodes: {len(bodies) + int(has_ground)};
    rigid bodies: {len(bodies)};
    joints: {len(joints) + slider_count + len(forces) + len(rotational) + int(has_ground)};
    {f'forces: {load_element_count};' if load_element_count else ''}
    gravity;
    output precision: 12;
end: control data;
begin: nodes;
"""
    if has_ground:
        text += "    structural: 0, static, null, eye, null, null, output, no;\n"
    for body in bodies:
        p, v = body["pose"], body["velocity"]
        angle = math.radians(p["angleDeg"])
        c, s = number(math.cos(angle)), number(math.sin(angle))
        text += f"    # Body ID: {body['id']}\n    structural: {labels[body['id']]}, dynamic, {vector(p)}, 1,{c},0,{number(-math.sin(angle))},2,0,1,0, {number(v['vx'])},0,{number(v['vz'])}, 0,{number(v['omega'])},0;\n"
    text += "end: nodes;\nbegin: elements;\n"
    for body in bodies:
        inertia = body["inertia"]
        label = labels[body["id"]]
        text += f"    body: {label}, {label}, {number(body['mass'])}, null, diag, {number(inertia['xx'])},{number(inertia['yy'])},{number(inertia['zz'])};\n"
    if has_ground:
        text += f"    joint: {len(joints) + 1}, clamp, 0, node, node;\n"
    orientation = "orientation, reference, node, 1,1,0,0,3,0,1,0"
    extra_label = len(joints) + int(has_ground) + 1
    for i, joint in enumerate(joints):
        child = labels[joint["child"]]
        if joint["type"] == "prismatic":
            parent = 0 if joint["parent"] == "ground" else labels[joint["parent"]]
            axis = math.radians(joint["axisAngleDeg"])
            ref = math.radians(joint["referenceAngleDeg"])
            text += (f"    # Slider ID: {joint['id']}; axis angle is relative to the parent frame.\n"
                     f"    joint: {i+1}, in line,\n"
                     f"        {parent}, position, reference, node, {vector(joint['parentAnchor'])}, "
                     f"orientation, reference, node, 1,0,1,0,3,{number(math.cos(axis))},0,{number(-math.sin(axis))},\n"
                     f"        {child}, offset, reference, node, {vector(joint['childAnchor'])};\n"
                     f"    joint: {extra_label}, prismatic,\n"
                     f"        {parent}, orientation, reference, node, eye,\n"
                     f"        {child}, orientation, reference, node, 1,{number(math.cos(ref))},0,{number(math.sin(ref))},2,0,1,0;\n")
            extra_label += 1
            continue
        if joint["parent"] == "ground":
            text += f"    joint: {i+1}, revolute pin,\n        {child}, position, reference, node, {vector(joint['childAnchor'])}, {orientation},\n        position, reference, global, {vector(joint['parentAnchor'])}, orientation, reference, global, 1,1,0,0,3,0,1,0;\n"
        else:
            parent = labels[joint["parent"]]
            text += f"    joint: {i+1}, revolute hinge,\n        {parent}, position, reference, node, {vector(joint['parentAnchor'])}, {orientation},\n        {child}, position, reference, node, {vector(joint['childAnchor'])}, {orientation};\n"
    for i, force in enumerate(forces):
        a, b = (0 if force[side] == "ground" else labels[force[side]] for side in ("a", "b"))
        length = force["restLength"]
        text += (f"    # Linear spring-damper ID: {force['id']}; axial force = k*(length-restLength) + c*lengthRate.\n"
                 f"    joint: {extra_label + i}, rod,\n"
                 f"        {a}, position, reference, node, {vector(force['anchorA'])},\n"
                 f"        {b}, position, reference, node, {vector(force['anchorB'])}, {number(length)},\n"
                 f"        linear viscoelastic, {number(force['stiffness'] * length)}, {number(force['damping'] * length)};\n")
    extra_label += len(forces)
    for i, element in enumerate(rotational):
        joint = joint_lookup[element["joint"]]
        parent = 0 if joint["parent"] == "ground" else labels[joint["parent"]]
        ref = math.radians(element["restAngleDeg"])
        text += (f"    # Rotational spring-damper ID: {element['id']}.\n"
                 f"    joint: {extra_label + i}, deformable hinge,\n"
                 f"        {parent}, orientation, reference, node, eye,\n"
                 f"        {labels[joint['child']]}, orientation, reference, node, 1,{number(math.cos(ref))},0,{number(math.sin(ref))},2,0,1,0,\n"
                 f"        linear viscoelastic generic, diag,0,{number(element['stiffness'])},0, diag,0,{number(element['damping'])},0;\n")
    load_label = 1
    for load in loads:
        text += f"    # Constant global COM load ID: {load['id']}.\n"
        if load["fx"] or load["fz"]:
            text += (f"    force: {load_label}, absolute, {labels[load['body']]}, position, null, component, "
                     f"const, {number(load['fx'])}, const, 0, const, {number(load['fz'])};\n")
            load_label += 1
        if load["torque"]:
            text += f"    couple: {load_label}, absolute, {labels[load['body']]}, 0,1,0, const, {number(load['torque'])};\n"
            load_label += 1
    for drive in actuators:
        joint = joint_lookup[drive["joint"]]
        text += f"    # Sinusoidal joint torque ID: {drive['id']}.\n"
        for body, sign in ((joint["child"], 1), (joint["parent"], -1)):
            if body == "ground":
                continue
            text += (f"    couple: {load_label}, absolute, {labels[body]}, 0,1,0, sine, 0, "
                     f"{number(2 * math.pi * drive['frequencyHz'])}, {number(sign * drive['amplitude'])}, forever, {number(sign * drive['offset'])};\n")
            load_label += 1
    text += f"    gravity: uniform, 0,0,-1, const, {number(model['parameters']['gravity'])};\nend: elements;\n"
    return text


def parse_output(directory, model):
    # Reuse the strict native time/frame/finite-value reader without synthesizing motion.
    from source_catalog import parse_output as native_output
    native = native_output(directory, {"simulation": model["simulation"], "nodes": [{"id": i + 1} for i in range(len(model["bodies"]))]})
    if abs(native[0]["time"]) > 1e-10:
        raise ValueError("Assembly output must include its initial frame at time zero.")
    bodies = model["bodies"]
    forces = model.get("forces", [])
    loads = model.get("loads", [])
    rotational, actuators = model.get("rotationalElements", []), model.get("jointTorques", [])
    joint_lookup = {joint["id"]: joint for joint in model["joints"]}
    previous_time, previous_power, dissipated = None, None, 0.
    previous_load_time, previous_load_power, work = None, None, 0.
    previous_drive_time, previous_drive_power, drive_work = None, None, 0.
    previous_angles = {}
    for sample in native:
        observed = {}
        energy = 0.
        for body, node in zip(bodies, sample["nodes"]):
            if max(abs(node["y"]), abs(node["vy"]), abs(node["wx"]), abs(node["wz"])) > 1e-6:
                raise ValueError("Native result left the supported XZ plane or Y rotation axis.")
            a, b, c = (math.radians(node[key]) for key in ("rx", "ry", "rz"))
            # Euler123 means Rx(a) Ry(b) Rz(c). Its second column must keep
            # the local Y axis aligned with global Y, including Euler branches.
            y_axis = (-math.cos(b) * math.sin(c),
                      math.cos(a) * math.cos(c) - math.sin(a) * math.sin(b) * math.sin(c),
                      math.sin(a) * math.cos(c) + math.cos(a) * math.sin(b) * math.sin(c))
            if max(abs(y_axis[0]), abs(y_axis[1] - 1), abs(y_axis[2])) > 1e-7:
                raise ValueError("Native body orientation is outside the supported rotation about Y.")
            angle = math.degrees(math.atan2(math.sin(b), math.cos(b) * math.cos(c)))
            node.update(label=node["id"], id=body["id"], angleDeg=angle)
            observed[body["id"]] = {"pose": {"x": node["x"], "z": node["z"], "angleDeg": angle},
                                    "velocity": {"vx": node["vx"], "vz": node["vz"], "omega": node["wy"]}}
            energy += .5 * body["mass"] * (node["vx"] ** 2 + node["vz"] ** 2) + .5 * body["inertia"]["yy"] * node["wy"] ** 2
            energy += body["mass"] * model["parameters"]["gravity"] * node["z"]
        errors, velocity_errors, angular_errors, angular_velocity_errors, sliders = [], [], [], [], []
        for joint in model["joints"]:
            parent, child = observed.get(joint["parent"]), observed[joint["child"]]
            if joint["type"] == "prismatic":
                state=prismatic_state(joint,parent,child)
                errors.append(abs(state["transverse"]))
                velocity_errors.append(abs(state["transverseVelocity"]))
                angular_errors.append(abs(state["angle"]))
                angular_velocity_errors.append(abs(state["angularVelocity"]))
                sliders.append({"id":joint["id"],**state})
            else:
                errors.append(math.dist(anchor_position(parent, joint["parentAnchor"]), anchor_position(child, joint["childAnchor"])))
                velocity_errors.append(math.dist(anchor_velocity(parent, joint["parentAnchor"]), anchor_velocity(child, joint["childAnchor"])))
        if sliders:
            sample.update(sliders=sliders, jointAngularError=max(angular_errors), jointAngularVelocityError=max(angular_velocity_errors))
        if forces or rotational:
            states = [spring_state(force, observed) for force in forces]
            elastic = sum(.5 * force["stiffness"] * state["extension"] ** 2 for force, state in zip(forces, states))
            power = sum(force["damping"] * state["rate"] ** 2 for force, state in zip(forces, states))
            rotary_states = []
            for element in rotational:
                joint = joint_lookup[element["joint"]]
                parent, child = observed.get(joint["parent"]), observed[joint["child"]]
                angle = math.radians(child["pose"]["angleDeg"] - (parent["pose"]["angleDeg"] if parent else 0) - element["restAngleDeg"])
                angle = math.atan2(math.sin(angle), math.cos(angle))
                velocity = child["velocity"]["omega"] - (parent["velocity"]["omega"] if parent else 0)
                if abs(angle) >= math.pi - 1e-6 or (element["id"] in previous_angles and abs(angle - previous_angles[element["id"]]) > math.pi) or abs(velocity) * model["simulation"]["step"] > .1:
                    raise ValueError(f"Rotational element {element['id']} crossed or cannot resolve the +/-pi rotation branch; reduce the step or limit travel.")
                previous_angles[element["id"]] = angle
                rotary_states.append({"id": element["id"], "angle": angle, "velocity": velocity, "torque": -element["stiffness"] * angle - element["damping"] * velocity})
                elastic += .5 * element["stiffness"] * angle ** 2
                power += element["damping"] * velocity ** 2
            if previous_time is not None:
                dissipated += (sample["time"] - previous_time) * (power + previous_power) / 2
            previous_time, previous_power = sample["time"], power
            energy += elastic
            sample.update(elasticEnergy=elastic, dampingPower=power, dissipatedEnergy=dissipated)
            if forces:
                sample["forces"] = states
            if rotational:
                sample["rotationalStates"] = rotary_states
        if loads:
            states = []
            for load in loads:
                velocity = observed[load["body"]]["velocity"]
                power = load["fx"] * velocity["vx"] + load["fz"] * velocity["vz"] + load["torque"] * velocity["omega"]
                states.append({"id": load["id"], "power": power})
            load_power = sum(state["power"] for state in states)
            if previous_load_time is not None:
                work += (sample["time"] - previous_load_time) * (load_power + previous_load_power) / 2
            previous_load_time, previous_load_power = sample["time"], load_power
            sample.update(loadStates=states, loadPower=load_power, appliedWork=work)
        if actuators:
            states = []
            for drive in actuators:
                joint = joint_lookup[drive["joint"]]
                parent, child = observed.get(joint["parent"]), observed[joint["child"]]
                velocity = child["velocity"]["omega"] - (parent["velocity"]["omega"] if parent else 0)
                torque = drive["offset"] + drive["amplitude"] * math.sin(2 * math.pi * drive["frequencyHz"] * sample["time"])
                states.append({"id": drive["id"], "torque": torque, "power": torque * velocity})
            drive_power = sum(state["power"] for state in states)
            if previous_drive_time is not None:
                drive_work += (sample["time"] - previous_drive_time) * (drive_power + previous_drive_power) / 2
            previous_drive_time, previous_drive_power = sample["time"], drive_power
            sample.update(actuationStates=states, actuationPower=drive_power, actuationWork=drive_work)
        sample.update(energy=energy, jointError=max(errors), jointVelocityError=max(velocity_errors))
    return native


def metrics(model, samples):
    mass = {body["id"]: body["mass"] for body in model["bodies"]}
    scale = sum(mass[joint["child"]] * model["parameters"]["gravity"] * math.hypot(joint["childAnchor"]["x"], joint["childAnchor"]["z"]) for joint in model["joints"])
    for joint in model["joints"]:
        if joint["type"] == "prismatic":
            positions = [next(value["position"] for value in sample["sliders"] if value["id"] == joint["id"]) for sample in samples]
            scale += mass[joint["child"]] * model["parameters"]["gravity"] * max(abs(value - positions[0]) for value in positions)
    scale += sum(.5 * body["mass"] * (body["velocity"]["vx"] ** 2 + body["velocity"]["vz"] ** 2) + .5 * body["inertia"]["yy"] * body["velocity"]["omega"] ** 2 for body in model["bodies"])
    deviation = max(abs(sample["energy"] - samples[0]["energy"]) for sample in samples)
    if model.get("forces") or model.get("rotationalElements"):
        scale += samples[0]["elasticEnergy"]
    if model.get("loads"):
        scale += max(abs(sample["appliedWork"]) for sample in samples)
    if model.get("jointTorques"):
        scale += max(abs(sample["actuationWork"]) for sample in samples)
    balance_deviation = max(abs(sample["energy"] + sample.get("dissipatedEnergy", 0.) - sample.get("appliedWork", 0.) - sample.get("actuationWork", 0.) - samples[0]["energy"]) for sample in samples)
    result = {"duration": samples[-1]["time"], "sampleCount": len(samples), "bodyCount": len(model["bodies"]),
            "maxConstraintError": max(sample["jointError"] for sample in samples), "maxJointVelocityError": max(sample["jointVelocityError"] for sample in samples),
            "initialEnergy": samples[0]["energy"], "finalEnergy": samples[-1]["energy"], "maxEnergyDeviation": deviation,
            "energyScale": scale, "relativeEnergyDrift": balance_deviation / max(1e-12, scale), "energyUnit": "J", "constraintErrorUnit": "m",
            "validationScope": "Native rigid-body trajectories; hinge closure and conservative energy checks. No contact, flexible-body or industry qualification."}
    if model.get("forces") or model.get("rotationalElements"):
        result.update(dissipatedEnergy=samples[-1]["dissipatedEnergy"], maxEnergyBalanceError=balance_deviation,
                      validationScope="Native rigid-body trajectories; reconstructed spring force and damping energy from poses/velocities. No contact, flexible-body or industry qualification.")
    if any(joint["type"] == "prismatic" for joint in model["joints"]):
        result.update(maxJointAngularError=max(sample["jointAngularError"] for sample in samples),
                      maxJointAngularVelocityError=max(sample["jointAngularVelocityError"] for sample in samples),
                      angularConstraintErrorUnit="rad", angularVelocityConstraintErrorUnit="rad/s",
                      validationScope="Native planar body trajectories; reconstructed hinge, slider and spring constraint/force values. No contact, flexible-body or industry qualification.")
    if model.get("loads"):
        result.update(appliedWork=samples[-1]["appliedWork"], maxEnergyBalanceError=balance_deviation,
                      validationScope=result["validationScope"] + " Constant-load power and work are reconstructed from native body velocities.")
    if model.get("jointTorques"):
        result.update(actuationWork=samples[-1]["actuationWork"], maxEnergyBalanceError=balance_deviation,
                      validationScope=result["validationScope"] + " Sinusoidal joint torque and work are reconstructed from time and relative angular velocity.")
    return result


def write_csv(path, samples):
    keys = ["time", "id", "label", "x", "y", "z", "rx", "ry", "rz", "vx", "vy", "vz", "wx", "wy", "wz", "angleDeg", "energy", "jointError", "jointVelocityError"]
    names = [force["id"] for force in samples[0].get("forces", [])]
    rotary = [element["id"] for element in samples[0].get("rotationalStates", [])]
    drives = [element["id"] for element in samples[0].get("actuationStates", [])]
    for name in names:
        keys += [f"spring:{name}:length_m", f"spring:{name}:extension_m", f"spring:{name}:rate_m_s", f"spring:{name}:force_N"]
    for name in rotary:
        keys += [f"rotational:{name}:angle_rad", f"rotational:{name}:velocity_rad_s", f"rotational:{name}:torque_Nm"]
    if names or rotary:
        keys += ["elasticEnergy_J", "dampingPower_W", "dissipatedEnergy_J"]
    for name in drives:
        keys += [f"actuation:{name}:torque_Nm", f"actuation:{name}:power_W"]
    if drives:
        keys += ["actuationPower_W", "actuationWork_J"]
    loads = [load["id"] for load in samples[0].get("loadStates", [])]
    for name in loads:
        keys += [f"load:{name}:power_W"]
    if loads:
        keys += ["loadPower_W", "appliedWork_J"]
    sliders = [slider["id"] for slider in samples[0].get("sliders", [])]
    for name in sliders:
        keys += [f"slider:{name}:position_m", f"slider:{name}:velocity_m_s", f"slider:{name}:transverse_m", f"slider:{name}:transverseVelocity_m_s", f"slider:{name}:angle_rad", f"slider:{name}:angularVelocity_rad_s"]
    if sliders:
        keys += ["jointAngularError_rad", "jointAngularVelocityError_rad_s"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for sample in samples:
            values = {}
            for force in sample.get("forces", []):
                for quantity, suffix in (("length", "length_m"), ("extension", "extension_m"), ("rate", "rate_m_s"), ("force", "force_N")):
                    values[f"spring:{force['id']}:{suffix}"] = force[quantity]
            for element in sample.get("rotationalStates", []):
                for quantity, suffix in (("angle", "angle_rad"), ("velocity", "velocity_rad_s"), ("torque", "torque_Nm")):
                    values[f"rotational:{element['id']}:{suffix}"] = element[quantity]
            if names or rotary:
                values.update(elasticEnergy_J=sample["elasticEnergy"], dampingPower_W=sample["dampingPower"], dissipatedEnergy_J=sample["dissipatedEnergy"])
            for drive in sample.get("actuationStates", []):
                values[f"actuation:{drive['id']}:torque_Nm"] = drive["torque"]
                values[f"actuation:{drive['id']}:power_W"] = drive["power"]
            if drives:
                values.update(actuationPower_W=sample["actuationPower"], actuationWork_J=sample["actuationWork"])
            for load in sample.get("loadStates", []):
                values[f"load:{load['id']}:power_W"] = load["power"]
            if loads:
                values.update(loadPower_W=sample["loadPower"], appliedWork_J=sample["appliedWork"])
            for slider in sample.get("sliders", []):
                for quantity, suffix in (("position", "position_m"), ("velocity", "velocity_m_s"), ("transverse", "transverse_m"), ("transverseVelocity", "transverseVelocity_m_s"), ("angle", "angle_rad"), ("angularVelocity", "angularVelocity_rad_s")):
                    values[f"slider:{slider['id']}:{suffix}"] = slider[quantity]
            if sliders:
                values.update(jointAngularError_rad=sample["jointAngularError"], jointAngularVelocityError_rad_s=sample["jointAngularVelocityError"])
            for node in sample["nodes"]:
                writer.writerow({**node, **{key: sample[key] for key in ("time", "energy", "jointError", "jointVelocityError")}, **values})


def _rod(identifier, mass, length, angle, anchor):
    local = {"x": 0., "z": length / 2}
    dx, dz = rotate(math.radians(angle), local)
    transverse = mass * (length * length + .03 ** 2) / 12
    return {"id": identifier, "name": identifier.replace("_", " ").title(), "mass": mass,
            "inertia": {"xx": transverse, "yy": transverse, "zz": mass * .03 ** 2 / 6},
            "pose": {"x": anchor[0] - dx, "z": anchor[1] - dz, "angleDeg": angle}, "velocity": {"vx": 0., "vz": 0., "omega": 0.}}


def _examples():
    def model(name, bodies, joints):
        return {"kind": KIND, "name": name, "parameters": {"gravity": 9.81}, "simulation": {"duration": 5., "step": .001}, "bodies": bodies, "joints": joints}
    def joint(identifier, parent, child, parent_anchor, child_anchor):
        return {"id": identifier, "type": "revolute", "parent": parent, "child": child,
                "parentAnchor": {"x": parent_anchor[0], "z": parent_anchor[1]}, "childAnchor": {"x": child_anchor[0], "z": child_anchor[1]}}
    root = _rod("upper_link", 1.2, 1., -8., (0., 0.))
    pin = joint("ground_pin", "ground", root["id"], (0., 0.), (0., .5))
    single = model("Authored rigid pendulum", [root], [pin])
    endpoint = anchor_position(root, {"x": 0., "z": -.5})
    lower = _rod("lower_link", .8, .7, 20., endpoint)
    double = model("Authored two-link chain", [root, lower], [pin, joint("elbow", root["id"], lower["id"], (0., -.5), (0., .35))])
    left = _rod("left_link", .6, .6, -25., anchor_position(root, {"x": -.25, "z": -.4}))
    right = _rod("right_link", .9, .8, 15., anchor_position(root, {"x": .25, "z": -.4}))
    branch = model("Authored branched assembly", [root, left, right], [pin,
        joint("left_hinge", root["id"], left["id"], (-.25, -.4), (0., .3)), joint("right_hinge", root["id"], right["id"], (.25, -.4), (0., .4))])
    sprung = model("Rigid pendulum with spring-damper", [root], [pin])
    sprung["forces"] = [{"id": "spring1", "type": "linear-spring-damper", "a": "ground", "b": root["id"],
                         "anchorA": {"x": 1., "z": 0.}, "anchorB": {"x": 0., "z": -.5},
                         "stiffness": 10., "damping": .5, "restLength": 1.3}]
    slider = model("Vertical prismatic slider", [{"id":"block","name":"Slider block","mass":1.,"inertia":{"xx":.1,"yy":.1,"zz":.01},
        "pose":{"x":0.,"z":-.2,"angleDeg":0.},"velocity":{"vx":0.,"vz":0.,"omega":0.}}],
        [{"id":"slide","type":"prismatic","parent":"ground","child":"block","parentAnchor":{"x":0.,"z":0.},
          "childAnchor":{"x":0.,"z":0.},"axisAngleDeg":90.,"referenceAngleDeg":0.}])
    slider["simulation"]={"duration":1.,"step":.001}
    return [{"id": identifier, "title": value["name"], "description": description, "model": value}
            for identifier, value, description in [("assembly-single", single, "One rigid body with real inertia and a user-defined ground hinge."),
                                                 ("assembly-chain", double, "Two bodies with independent mass, inertia, poses and local attachment points."),
                                                 ("assembly-branch", branch, "A branched three-body graph: two children attached to different points on a parent."),
                                                 ("assembly-spring", sprung, "A rigid pendulum with a ground-to-body linear spring and viscous damper."),
                                                 ("assembly-slider", slider, "One freely sliding rigid body moving along a vertical guide under gravity; no end stops.")]]


EXAMPLES = _examples()
