# Featured studies

Seven editable 3D assemblies show what the MBDyn solver does well: closed kinematic
loops, gyroscopic coupling, nonlinear force elements, contact and chaotic dynamics.
Open any of them from **Examples → Featured studies**, run it in **Solve**, and
explore it in **Post-processing**. Each project stores a camera, a default plot and
trail settings so the motion is readable immediately.

All geometry is generated with OpenCascade by `examples/studies/build.py`. Every
body's mass, centre of mass and full inertia tensor is measured from its STEP solids
at a stated density and expressed in body axes; static fixtures (stands, frames,
guides) are display-only. The studies are teaching models: dimensions, materials
and loads are representative, not validated hardware.

`python -B backend/verify_featured_studies.py` runs every study through MBDyn and
compares the solution with an independent quantity. `backend/test_featured_studies.py`
checks that each saved project validates and keeps its force elements and geometry.

| Study | Solver features | Independent check (MBDyn 1.7.3) |
| --- | --- | --- |
| Robot arm inverse dynamics | Three rotary drives (motor ramp and oscillations), joint reactions as motor torques | Drive work equals the change in kinetic and potential energy; commands followed within 10⁻¹² rad |
| Double-wishbone quarter-car | Closed spatial loop, spherical/revolute joints, preloaded coil-over, stiff tie rod, harmonic wheel-pad force | ±60 mm wheel travel; bump steer 0.64°; camber change 2.1° |
| Oleo-pneumatic gear drop test | Oleo strut (polytropic gas, orifice damping, stops), damped sphere–plane tyre contact, prismatic guides | 183 mm peak stroke without bottoming; settled tyre load within 3 % of weight; peak load factor 6.0 |
| Slider-crank engine run-up | Spherical + universal + prismatic loop closure, follower drive torque, viscous load | Stroke equals 2 × crank radius to 0.01 mm; steady motor power balances dissipation within 2 % |
| Gyroscopic top | Spherical joint, 120 rad/s spin, full inertia tensor | Spin conserved to 1 %; mean precession 4.66 rad/s vs 4.78 rad/s from steady-precession theory |
| Tumbling T-handle | Free body, zero gravity | World angular momentum conserved; three spin reversals in 12 s |
| Chaotic double pendulums | Two identical revolute chains, 0.001° apart | Agree within 0.08 mm for 1.5 s, then separate by 0.64 m |

## Robot arm inverse dynamics

A turret, upper arm and forearm with a steel payload, about 35 kg in total. The turret
yaws at 45°/s after a 1 s ramp, the shoulder swings up by 50° and back at 0.3 Hz and the
elbow bends by 80° at 0.45 Hz — all prescribed by [rotary drives](rotary-drives.md). MBDyn
returns the torque each motor needs: the shoulder carries 46–88 N·m, mostly against
gravity, while the yaw axis needs only ±5 N·m for inertia and coupling.

**Watch:** the forearm trail, then plot **Rotary drive torque** for each joint and
**Rotary drive power** to see when the shoulder works against gravity and when it brakes.

## Double-wishbone quarter-car

A short-long-arm (SLA) suspension for a left-front corner in vehicle axes (X forward,
Y left, Z up). The lower wishbone pivots at `(0, 0.30, 0.17) m`, the upper at
`(0, 0.42, 0.50) m`; ball joints carry a knuckle that holds a 0.30 m wheel. A
60 kN/m coil-over with 600 N·s/m damping supports a 3.2 kN corner load, and a
wheel-pad actuator adds ±1.6 kN at 0.8 Hz — well below the 4.6 Hz wheel-hop mode,
so the sweep is quasi-static.

The tie rod is an axially stiff (100 kN/m) link from the steering rack to the steering
arm. Its inboard pivot lies on the line through the wishbone pivots and its outboard
pivot on the kingpin line, which keeps bump steer below a degree. The shorter upper arm
produces camber gain in bump.

**Watch:** the knuckle tilting as the arms swing. Plot **Node Euler 1–2–3** for the
knuckle (camber ≈ X, toe ≈ Z), or open **Measure → Wheel kinematics** for camber and
toe against wheel travel.

## Oleo-pneumatic gear drop test

A 289 kg carriage on a vertical guide carries an oleo-pneumatic strut and a 64 kg
piston/axle/wheel assembly. The rig is released 0.18 m above the ground at 2 m/s
sink rate. The strut has 60 cm² gas area, 4 L gas volume at 360 kPa (γ = 1.3),
asymmetric metering (2.4 cm² compression, 1.4 cm² rebound) and 200 mm of stroke.
The tyre is a damped sphere–plane contact (600 kN/m, 1.5 kN·s/m).

**Watch:** the orifice force spike at touchdown, the gas spring taking over as the
strut settles at about 110 mm stroke, and the tyre carrying the full weight. Plot
**Oleo force components**, then switch to **Contact normal force**.

## Slider-crank engine run-up

A steel crank with flywheel, aluminium connecting rod and piston. The loop is closed
by a crank-pin spherical joint, a wrist-pin universal joint and a prismatic bore —
a non-redundant set with exactly one degree of freedom. A constant 2 N·m motor
torque accelerates the crank against a 90 N·s/m pumping load until mean motor power
equals dissipation (about 15 rad/s).

**Watch:** crank speed rising and rippling twice per revolution as the piston
accelerates. Plot **Slider position** for the 120 mm stroke and **Joint reaction
force** at the wrist pin.

## Gyroscopic top

A 1.95 kg steel top spins at 120 rad/s on a spherical tip, tilted 25°. Gravity's
torque makes the axis precess; starting without precession rate it also nutates,
tracing the cusps visible with motion trails. At this spin the fast-top estimate
mgl/(I₃ω) under-predicts the precession by 16 %; the exact steady-precession root
agrees with the solver to 3 %.

## Tumbling T-handle

A free T-handle in zero gravity spinning at 6 rad/s about its intermediate principal
axis, with a 0.03 rad/s perturbation. Rotation about that axis is unstable, so the
handle periodically flips — the Dzhanibekov effect. Plot **Angular velocity in body
axes**: the spin component reverses sign every ~3.4 s while the world angular
momentum stays constant.

## Chaotic double pendulums

Two identical aluminium double pendulums with steel bobs, released at 125° — the
second 0.001° further. They move together for about two seconds, then diverge
completely. Trails show only the two lower links, coloured to match their bodies.
