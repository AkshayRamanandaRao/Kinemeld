"""Check a motor-driven revolute in MBDyn against rigid-body dynamics.

Usage: python -B backend/verify_rotary_drive.py
A link with its centre of mass 0.3 m from the hinge is driven by a speed ramp to
3 rad/s. The motor torque MBDyn reports (the hinge reaction about the axis) must equal
I_pivot·α − m·g·l·cos θ, where θ is the prescribed angle.
"""
import math

import solver
import spatial_assembly as spatial
from test_rotary_drive import driven_link


def main():
    motion = {"speedDegPerS": math.degrees(3.0), "rampTime": 0.4}
    model = driven_link(motion)
    model["simulation"] = {"duration": 2.0, "step": 0.001}
    body = model["bodies"][0]
    mass, lever = body["mass"], body["centerOfMass"]["x"]
    pivot_inertia = body["inertia"]["yy"] + mass * lever ** 2
    result, _ = solver.run(model)
    if not result.get("ok"):
        raise AssertionError(result.get("error"))
    worst_angle = worst_torque = 0.0
    for sample in result["samples"]:
        t = sample["time"]
        if min(abs(t), abs(t - motion["rampTime"])) < 5e-3:
            continue  # α jumps at the ramp ends; the implicit integrator settles within a few steps
        drive = sample["rotaryDrives"][0]
        alpha = 3.0 / motion["rampTime"] if t < motion["rampTime"] else 0.0
        expected = pivot_inertia * alpha - mass * 9.81 * lever * math.cos(spatial.rotary_angle(motion, t))
        worst_angle = max(worst_angle, abs(drive["angle"] - drive["commandedAngle"]))
        worst_torque = max(worst_torque, abs(drive["torque"] - expected))
    if worst_angle > 1e-6 or worst_torque > 1e-3:
        raise AssertionError(f"angle error {worst_angle:.3g} rad, torque error {worst_torque:.3g} N·m")
    print(f"PASS driven link: angle follows the commanded law within {worst_angle:.2g} rad; motor torque matches "
          f"I·α − m·g·l·cos θ within {worst_torque:.2g} N·m; drive work {result['metrics']['rotaryDriveWork']:.3f} J.")


if __name__ == "__main__":
    main()
