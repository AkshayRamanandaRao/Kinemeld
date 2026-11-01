# Rotary drives (prescribed hinge motion)

A rotary drive imposes the angle of a revolute joint as a function of time, like a
servo or a motor under ideal speed control. MBDyn then computes the motion of the rest
of the mechanism *and* the torque the drive must supply — the inverse-dynamics question
behind motor sizing.

## Drive laws

Select a revolute joint in **Pre-processing** and choose **Rotary drive → Drive law**.

| Law | Parameters | Angle θ(t) | Speed at t = 0 |
| --- | --- | --- | --- |
| Motor: speed with ramp | target speed ω (°/s), ramp time τ (s) | ω t²/(2τ) for t ≤ τ, then ω (t − τ/2) | 0 |
| Oscillation | amplitude A (°), frequency f (Hz) | A (1 − cos 2πft) | 0 |

Both laws start at rest about the hinge, so the joint's two bodies must have the same
initial angular velocity about its axis; validation reports a mismatch. The motor law
reaches its target speed exactly at τ and holds it; its acceleration is constant during
the ramp and zero afterwards. The oscillation swings between 0 and 2A.

Validation also asks for at least 20 time steps per ramp or oscillation cycle and at
most 0.1 rad of rotation per step. A driven hinge removes one more freedom than a free
one; the [constraint diagnostics](constraint-diagnostics.md) count it, so a fully driven
arm has mobility 0.

## Results

In **Post-processing**, choose a driven joint in the joint selector and plot:

- **Rotary drive angle · measured / commanded** — the hinge angle reconstructed from the
  bodies' orientations, unwrapped over full turns, beside the commanded law.
- **Rotary drive speed** — relative angular velocity about the axis.
- **Rotary drive torque (hinge reaction)** — the constraint moment about the hinge axis on
  body B: the torque a motor must deliver.
- **Rotary drive power** and **Rotary drive work (all drives)**.

The CSV export contains `rotaryDrive:<joint>:angle_rad`, `speed_rad_s`, `torque_Nm` and
`power_W` for every solver step.

## How it is solved

The drive is written as an MBDyn `total joint` whose rotation about the hinge axis follows
a drive caller — a `string` expression `c·(ramp(Time)² − ramp(Time − τ)²)` for the motor
law and a `cosine` drive for oscillation. Positions and the other two rotations remain
locked as in a revolute hinge. The reported torque is the joint's reaction moment
projected on the axis.

## Evidence

- `python -B backend/verify_rotary_drive.py` drives a link with its centre of mass 0.3 m
  from the hinge to 3 rad/s. The solver torque matches I·α − m·g·l·cos θ to 6 × 10⁻⁶ N·m
  (samples within 5 ms of the ramp ends, where α jumps, are excluded).
- The **robot arm** featured study drives a turret, shoulder and elbow. Over 6 s the total
  drive work equals the change in kinetic and potential energy (3.345 J both ways), and
  every axis follows its command within 10⁻¹² rad.
- `backend/test_rotary_drive.py` covers the laws, deck generation, validation and the
  constraint row.

An ideal drive delivers whatever torque the motion needs; it does not model motor torque
limits, compliance or control dynamics.

The [robot-arm engineering guide](robot-arm-engineering.md) adds traceable input
records, CAD mass reintegration, three-timestep Cartesian checks and an independent
Jacobian mass-matrix inverse-dynamics comparison, including a changed motion case.
