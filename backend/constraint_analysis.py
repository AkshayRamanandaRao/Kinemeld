"""Velocity-level constraint analysis of a spatial assembly at its initial configuration.

Each joint contributes rows of the constraint Jacobian with respect to the bodies'
origin velocities and angular velocities (6 per body, world axes). The rank of that
Jacobian gives the instantaneous mobility, 6·bodies − rank, which unlike the
Grübler–Kutzbach count accounts for the actual joint geometry. Rows that do not raise
the rank are redundant: MBDyn's assembly then has a singular constraint matrix.
Joints are processed in model order, so a redundancy is reported on the joint that
closes the loop.
"""
import math

import spatial_assembly as s

AXIS_NAMES = ("X", "Y", "Z")


def _unit(v):
    n = s.norm(v)
    return [x / n for x in v]


def _label(direction):
    """Name a world direction, using an axis letter when it is aligned with one."""
    for i, name in enumerate(AXIS_NAMES):
        if abs(abs(direction[i]) - 1) < 1e-9:
            return name
    return "(" + ", ".join(f"{x:.2f}" for x in direction) + ")"


def joint_rows(joint, lookup):
    """Constraint rows as (component description, {body id: 6 coefficients})."""
    a, b = lookup.get(joint["a"]), lookup[joint["b"]]
    point = s.anchor(b, joint["anchorB"])
    ra = s.sub(point, s.xyz(a["pose"])) if a else None
    rb = s.sub(point, s.xyz(b["pose"]))
    rows = []

    def translation(direction, text):
        d = _unit(direction)
        entries = {b["id"]: d + s.cross(rb, d)}
        if a:
            entries[a["id"]] = [-x for x in d + s.cross(ra, d)]
        rows.append((text, entries))

    def rotation(direction, text):
        d = _unit(direction)
        entries = {b["id"]: [0.0, 0.0, 0.0] + d}
        if a:
            entries[a["id"]] = [0.0, 0.0, 0.0] + [-x for x in d]
        rows.append((text, entries))

    kind = joint["type"]
    if kind in ("revolute", "prismatic", "cylindrical", "universal"):
        axis = _unit(s.mul(s.body_rotation(a), s.xyz(joint["axisA"])))
        t1, t2, _ = s.basis(axis)
    if kind in ("spherical", "revolute", "universal", "weld"):
        for i, name in enumerate(AXIS_NAMES):
            translation([1.0 if j == i else 0.0 for j in range(3)], f"translation along {name}")
    if kind in ("prismatic", "cylindrical"):
        translation(t1, f"translation across the axis {_label(t1)}")
        translation(t2, f"translation across the axis {_label(t2)}")
        if joint.get("motion"):
            translation(axis, "prescribed translation along the axis")
    if kind in ("revolute", "cylindrical"):
        rotation(t1, f"rotation about {_label(t1)}")
        rotation(t2, f"rotation about {_label(t2)}")
        if kind == "revolute" and joint.get("motion"):
            rotation(axis, "prescribed rotation about the axis")
    if kind == "universal":
        ub = s.mul(s.body_rotation(b), s.xyz(joint["axisB"]))
        normal = s.cross(axis, ub)
        rotation(normal, f"rotation about {_label(_unit(normal))}")
    if kind in ("prismatic", "weld"):
        for i, name in enumerate(AXIS_NAMES):
            rotation([1.0 if j == i else 0.0 for j in range(3)], f"rotation about {name}")
    return rows


def analyse(model):
    """Return mobility, rank and redundant constraint components for a valid spatial model."""
    bodies = model["bodies"]
    lookup = {body["id"]: body for body in bodies}
    column = {body["id"]: 6 * i for i, body in enumerate(bodies)}
    size = 6 * len(bodies)
    scale = max([1.0] + [s.norm(s.xyz(body["pose"])) for body in bodies])
    basis, redundant, total = [], [], 0
    for joint in model["joints"]:
        for text, entries in joint_rows(joint, lookup):
            total += 1
            row = [0.0] * size
            for body_id, values in entries.items():
                start = column[body_id]
                # Scale angular columns by a model length so both blocks are comparable.
                for k, value in enumerate(values):
                    row[start + k] = value * (scale if k >= 3 else 1.0)
            magnitude = math.sqrt(sum(x * x for x in row))
            residual = row[:]
            for vector in basis:
                projection = sum(x * y for x, y in zip(residual, vector))
                residual = [x - projection * y for x, y in zip(residual, vector)]
            remaining = math.sqrt(sum(x * x for x in residual))
            if remaining <= 1e-8 * max(magnitude, 1e-300):
                redundant.append({"joint": joint["id"], "component": text})
            else:
                basis.append([x / remaining for x in residual])
    rank = len(basis)
    return {"constraints": total, "rank": rank, "dof": size - rank, "redundant": redundant,
            "grubler": size - total}
