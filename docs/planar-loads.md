# Constant planar forces and torques

A planar rigid-body graph may have an optional `loads` array. Each constant load
applies global X and Z force components at the selected body's centre of mass,
and a global positive-Y torque. Forces use N and torque N·m. The components are
signed, so negative values point in the opposite direction. Unlike a follower
load, this force remains aligned with the global axes as the body rotates.

```json
{"id":"load1","body":"upper_link","fx":2.0,"fz":-3.0,"torque":1.0}
```

The body must exist; IDs must be unique among loads; at least one component
must be nonzero. Omitted `loads` means no external loads, keeping older projects
compatible. This first implementation supports up to 32 loads; input components
are finite with absolute magnitude at most 1e9. In addition to existing solver
bounds, a job is limited to 1,600,000 body-load output values to bound repeated
CSV channels. No arbitrary force expression, time driver, body-relative force,
point-offset force, contact or automatic CAD-to-load inference is provided.

MBDyn exports each nonzero global force as an absolute structural force with
zero COM offset; each nonzero torque is an absolute couple about +Y. A load
containing both components generates two force elements. The force does not
replace gravity; it is added to the uniform gravity field and any springs or
dampers already present in the model.

Load power for body COM velocity `(vx,vz)` and angular velocity `ωy` is
`fx*vx + fz*vz + torque*ωy` in watts. The application reconstructs power from
native MBDyn body velocities and trapezoid-integrates it over written times to
obtain applied work in joules; it is not a native MBDyn force-channel sample.
For a damped spring and external loads the energy-balance error compares
`mechanical energy + damping dissipation − applied work` with its initial value.
The full CSV repeats each load's reconstructed power and aggregate work on each
body row. Results depend on solver step size and must be checked for the actual
model.

Independent verification against an analytic free slider and RK4 pendulum
includes torque-only, force-plus-torque and combined spring-damper/load cases.
Reproduce the local MBDyn checks with `python backend/verify_planar_loads.py`;
the command generates `verification/planar-loads.json`, which is not included in
the public checkout. These tests do
not qualify safety-critical models or arbitrary load histories.
