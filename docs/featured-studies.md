# Featured studies

Ten editable 3D assemblies show what the MBDyn solver does well: seven industry-inspired
studies (robotics, automotive suspension and wheel ends, landing gear, machinery) and three
classic rigid-body problems — prescribed motion and inverse dynamics, closed kinematic loops,
gyroscopic coupling, nonlinear force elements, contact and chaotic dynamics.
Open any of them from **Examples → Featured studies**, run it in **Solve**, and
explore it in **Post-processing**. Each project stores a camera, a default plot and
trail settings so the motion is readable immediately.

The aircraft nose gear, oleo strut and wheel-end studies use original open-source STEP
assemblies (see each example's README for source and licence); their catalog entries in
`examples/featured.json` add a study length, prescribed stroke or display preset without
changing the verified project files. The other studies' geometry is generated with
OpenCascade by `examples/studies/build.py`. Every
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
| Robot arm inverse dynamics | Three rotary drives (motor ramp, two oscillations) on revolute joints, measured STEP inertia | Every axis follows its command within 10⁻¹² rad; drive work equals the change in kinetic and potential energy |
| Double-wishbone quarter-car | Closed spatial loop, spherical/revolute joints, preloaded coil-over, stiff tie rod, harmonic wheel-pad force | ±60 mm wheel travel; bump steer 0.64°; camber change 2.1° |
| Oleo-pneumatic gear drop test | Oleo strut (polytropic gas, orifice damping, stops), damped sphere–plane tyre contact, prismatic guides | 183 mm peak stroke without bottoming; settled tyre load within 3 % of weight; peak load factor 6.0 |
| Aircraft nose-gear kinematics | Original 11-part STEP assembly, weld/prismatic/revolute/spherical/universal joints, prescribed 80 mm stroke | Strut follows the stroke to 10⁻¹³ m; scissor pin matches two-circle linkage geometry to 10⁻¹⁴ m; torque links fold 10.5° |
| Oleo strut on a wheel-end fixture | Original STEP wheel end, oleo strut with stops, prescribed fixture stroke | Native gas pressure follows p₀(V₀/V)^γ to 10⁻¹² (relative) over a 50 mm stroke |
| Wheel-end drop test | Original STEP knuckle/hub/tyre, revolute hub bearing, damped sphere–plane tyre contact | Free fall to 10⁻¹⁰ m; first contact 0.4 ms from prediction; energy lost equals contact dissipation within 0.1 % |
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

## Robot arm inverse dynamics

A three-axis arm on a pedestal: a turret turning on a vertical axis, an upper arm and a
forearm carrying a steel payload, each on a revolute joint with a rotary drive. The base
ramps to 45 °/s in one second; the shoulder and elbow oscillate (−25° at 0.3 Hz and 40° at
0.45 Hz). MBDyn imposes the angles and returns the torque each motor must deliver — the
inverse-dynamics question behind motor sizing ([rotary drives](rotary-drives.md)).

**Watch:** the forearm trail and the shoulder torque, which combines gravity load with the
inertia of the swinging forearm. Plot **Rotary drive torque** and choose a joint, or
**Rotary drive work (all drives)**.

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

## Aircraft nose-gear kinematics

The original 11-occurrence nose-gear STEP assembly with six inferred bodies: strut, sliding
piston, upper and lower torque links and two wheels. The featured study prescribes an
80 mm cosine stroke of the shock strut over 2 s (the project file and its own guide keep
the original 10 mm sweep). The torque-link joints are mathematical substitutions chosen to
avoid redundant constraints, and the source solids overlap, so this is a **kinematic
illustration only**; loads are not valid aircraft predictions
([engineering guide](aircraft-nose-kinematics.md)).

**Watch:** the scissor folding as the piston slides into the strut. Plot **Slider position**.

## Oleo strut on a wheel-end fixture

The original wheel-end STEP parts (knuckle, hub and tyre) on a prismatic fixture that
strokes them 50 mm into an oleo-pneumatic strut, with a hub revolute joint. Gas pressure,
asymmetric orifice damping and the stroke stops are illustrative, not a calibrated strut
([engineering guide](oleo-strut.md)).

**Watch:** the stop force engaging mid-stroke. Plot **Oleo force components** and **Oleo gas
pressure**.

## Wheel-end drop test

The same original knuckle, hub and tyre STEP parts dropped from 0.6 m with a 1 m/s downward
velocity onto a rigid floor. The hub turns on a revolute bearing; the tyre is a damped
sphere–plane contact (0.208 m radius, 20 kN/m, 100 N·s/m) at the CAD origin. The rigid tyre
and contact stiffness are approximations ([engineering guide](open-wheel-end.md)).

**Watch:** free fall, three impacts of decreasing height and the knuckle swinging about the
hub after each one. Plot **Contact normal force**. The
[workflow recording](../README.md#from-step-files-to-results-wheel-end-drop-test) builds this
model from the STEP files.

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
