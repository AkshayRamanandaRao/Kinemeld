# Constraint diagnostics

Closed kinematic loops are where multibody models most often fail. A planar four-bar
built from four revolute joints looks reasonable, but in 3D each revolute removes five
degrees of freedom: the loop over-constrains the mechanism and MBDyn's assembly matrix
becomes singular. Kinemeld checks this before the solver runs.

## What is computed

For a 3D assembly, validation builds the velocity-level constraint Jacobian at the
initial configuration: one row for each scalar condition a joint imposes on the bodies'
origin velocities and angular velocities.

| Joint | Rows |
| --- | --- |
| Spherical | 3 translations |
| Revolute | 3 translations, 2 rotations normal to the axis |
| Universal | 3 translations, 1 rotation about the normal of both axes |
| Cylindrical | 2 translations and 2 rotations normal to the axis |
| Prismatic | 2 translations normal to the axis, 3 rotations (plus 1 along the axis when its motion is prescribed) |
| Weld | 3 translations, 3 rotations |

The rank of this matrix gives the **instantaneous mobility**, 6 × bodies − rank. Unlike
the Grübler–Kutzbach count (6 × bodies − rows), it accounts for the actual geometry: two
parallel hinge axes, for example, constrain the same rotation twice.

Rows that do not increase the rank are **redundant**. Joints are processed in model
order, so the redundancy is reported on the joint that closes the loop, with the
component it duplicates — for example `coupler_rocker (rotation about Z)`.

## Where it appears

- **Solve → Pre-run checks:** mobility and the number of redundant constraints.
- The 3D view header shows the mobility; when it differs from the Grübler count both
  are shown.
- If MBDyn rejects a model that has redundant constraints, the run error lists them and
  suggests a remedy.

Spring-damper elements, contacts and loads are force elements, not constraints, so they
never appear in this analysis. Force elements can still make a model stiff or singular in
other ways; the time-step checks cover those.

## Making a loop exact

Replace joints so that each loop removes exactly the freedoms it must. A common choice
for a link in a planar loop is a **spherical joint at one end and a universal joint at the
other**: together they remove 7 freedoms instead of 10, and the universal joint stops the
link spinning about its own axis. The slider-crank study uses revolute, spherical,
universal and prismatic joints this way; its rank mobility is exactly 1.

## Evidence

`python -B backend/verify_constraint_analysis.py` builds a four-bar three ways and runs
each through MBDyn 1.7.3:

| Closing joints | Grübler | Rank mobility | Redundant rows | MBDyn |
| --- | --- | --- | --- | --- |
| Four revolutes | −2 | 1 | 3 | rejected (singular) |
| Three revolutes + spherical | 0 | 1 | 1 | rejected |
| Revolute, spherical, revolute, universal | 1 | 1 | 0 | solved |

The analysis is instantaneous: it describes the initial configuration. A mechanism can
pass through singular positions later (a slider-crank at dead centre loses the ability to
be driven from the piston, for example) without the initial check flagging them.
