# Planar prismatic joints

A `prismatic` joint in the planar body tree allows one translation along a line
attached to its parent. The child retains a constant relative orientation.
It works with a ground or moving parent, and may coexist with supported planar
revolute joints and linear spring-dampers. It is an ideal bilateral guide: no
travel limit, prescribed motion, actuation, friction or physical contact is
inferred. CAD remains visual geometry attached separately to the child body.

The **Vertical prismatic slider** example is a free rigid body on a vertical
guide under gravity. It has no end stops. It demonstrates the joint; it is not a
model of a full suspension. See [planar assemblies](planar-assembly.md) for body
properties, solver jobs, project storage and general limitations.

## Fields and frames

All units are SI except angles in degrees. Existing revolute objects retain their
schema. A prismatic joint has the same `id`, `parent`, `child`, `parentAnchor`,
`childAnchor` fields, plus `type: "prismatic"` and these required fields:

- `axisAngleDeg`: right-handed rotation about positive Y from the parent's local
  +X direction to the guide axis. Its parent-local XZ unit vector is
  `(cos(axis), -sin(axis))`. Ground has the global reference frame.
- `referenceAngleDeg`: the fixed relative child orientation, `child angle -
  parent angle`, about positive Y. Angles equivalent modulo 360° are identical.
- Parent and child anchors are local to their respective body centers of mass;
  a ground parent anchor is in global coordinates. Unlike a hinge, these points
  may be displaced along the guide axis. Their transverse separation must be
  zero initially; the allowed along-axis coordinate need not be zero.

Initial child-parent angular velocity must be zero, and the moving guide's
transverse relative attachment velocity must be zero. Both constraints are
validated at 1e-7 in their respective rad/rad/s and m/m/s units. Given world
guide `u=(ux,uz)`, its in-plane normal `n=(-uz,ux)`, anchor difference
`d=pB-pA`, and parent angular speed `omegaA`, the constrained values are
`n·d`, `n·(vB-vA) + omegaA*(u·d)`, wrapped child-parent-reference angle, and
child-minus-parent angular velocity. A nonzero value along `u` is allowed.

The sample's `sliders` array reconstructs each slider position and velocity
from native body poses and velocities, as well as signed transverse, relative
angle, transverse velocity, and relative angular velocity residuals. Aggregate
`jointError` and `jointVelocityError` remain in m and m/s, while
`jointAngularError` and `jointAngularVelocityError` are separate in rad and
rad/s. The full-resolution CSV includes each slider's reconstructed channels.
Native MBDyn body trajectories are authoritative; these joint values are derived.

## Solver implementation and verification

The exporter emits one MBDyn `in line` plus one `prismatic` element for each
slider. MBDyn 1.7.3's `prismatic` element alone constrains relative orientation,
not relative translation. A ground slider adds one static node and clamp; labels
are distinct from hinges and spring elements. This combination follows the
[MBDyn 1.7.3 input manual](https://www.mbdyn.org/userfiles/documents/mbdyn-input-1.7.3.pdf).

`python -m unittest discover -s backend -p test_planar_prismatic.py` tests the
schema, frame/velocity invariants, incompatible initial states and deck/CSV
composition. `python backend/verify_planar_prismatic.py` requires the configured
real solver. Its six checked cases include horizontal, rotated and offset
ground guides, a rotating-parent slider against independently integrated RK4
mechanics, a refined time step, and a slider coupled to a linear spring-damper
against a damped-oscillator equation. The verifier generates results and run
identifiers in `verification/planar-prismatic.json`; the local report is not
included in the public checkout.

The checked rotating-parent position error was 2.99e-6 m at 1 ms and improved by
about 3.98× at 0.5 ms. The largest checked transverse residual was below
5.7e-13 m. These comparisons cover the stated cases only; verify step convergence
and initial states for each actual mechanism before interpreting results.
