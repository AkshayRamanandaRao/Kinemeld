# Landing-gear dynamics: from a STEP assembly to a defensible study

The supplied [open aircraft nose-gear STEP assembly](../examples/open-aircraft-nose-gear/README.md) provides a detailed dual-wheel strut and torque links. It is a useful engineering CAD source, but it is not a verified MBDyn model, aircraft design approval, or supplier data. The separate [3D drop teaching example](landing-gear-3d.md) demonstrates the software's existing equations with deliberately simplified geometry and parameters; do not combine the two as if they were a calibrated aircraft.

## 1. Define the test before assigning joints

Record whether the question is retraction kinematics, vertical drop, touchdown with spin-up, taxi excitation, or a load-transfer study. Each needs different degrees of freedom and measurement channels. Record coordinate frames, initial state, units, mass supported by this gear, imposed constraints, load history and acceptance criteria. The aircraft's total mass is not automatically the effective mass supported by one gear leg. A test rig's carriage and fixture can add mass and constraints.

For correlation, identify the actual test instrumentation and event timing: carriage displacement and velocity, strut stroke, force plate normal and tangential loads, tire deflection, pressure and acceleration. NASA reports using a dynamic nose-gear drop test to characterize velocity-dependent strut response; see [NASA/TM-2017-219599](https://ntrs.nasa.gov/api/citations/20170007187/downloads/20170007187.pdf). Record sensor locations, coordinate signs, sampling, filtering and uncertainty with every comparison.

## 2. Identify the load path and independent coordinates

For an oleo strut, the outer cylinder transfers load to the airframe; the piston, axle and hub transfer it from the wheel. A torque-link scissor normally resists relative yaw while articulating with strut stroke. Depending on the real assembly, the wheel may rotate about an axle, and steering or retraction can add additional joints. Verify these functions from assembly drawings and hardware, not from the apparent shape alone.

1. Import the original STEP and identify each occurrence using the [source mapping](../examples/open-aircraft-nose-gear/README.md). Keep original placements and source hashes. Establish each body's reference frame and principal connection axes.
2. Measure the bore cylinders and pivot faces from the CAD, confirm the axis direction and coincident centres, and compare them against dimensions or assembly data. A `NAUO` index is an import occurrence, not a guaranteed semantic part name after an upstream revision.
3. Separate the outer strut, piston/hub and torque links into the actual physical bodies. Decide explicitly whether axle, wheel and fasteners are fixed together or can rotate. Include missing bearings, pins and spacers in the mass/clearance assumptions.
4. Enter mass, center of mass and full inertia for each body. Solid-volume integration at a chosen density is an estimate: one density for a wheel containing tire, rim and internal voids does not represent the component's measured mass. Preserve the assumed density, reference axes and omitted parts.
5. Add the joint graph and check its independent coordinates. A planar scissor loop represented by multiple full 3D revolutes can impose redundant constraints and make the MBDyn system singular. The experimental model for the supplied assembly encountered this issue. A [kinematic-only demonstration](aircraft-nose-kinematics.md) substitutes two joint types and retains known source overlaps; it is not a physical pin or load model. Use a justified nonredundant formulation and verify the geometry and constraint rank before interpreting motion or reactions.

No current viewer operation automatically detects general solid collision or assembles mechanical mates. Static intersection checks at one pose do not establish clearance across the whole retraction or compression stroke. Bearings and overlapping sliding surfaces need special interpretation rather than an automatic blanket pass/fail.

## 3. Select force laws consistent with the question

A real oleo-pneumatic unit combines compressed gas, fluid flow through a metering restriction, friction, stops and possibly temperature-dependent behavior. Tire load-deflection, footprint, friction and spin-up are separate physical mechanisms. [NACA TR-1154](https://ntrs.nasa.gov/citations/19930092181) develops an oleo landing-gear impact model and compares selected cases with drop-test data. Those results are not validation of this application's current model.

The current spatial assembly supports a linear axial spring-damper, an illustrative [nonlinear gas and hydraulic oleo law](oleo-strut.md), and sphere-plane penalty contact with optional approach-only damping and [regularised Coulomb friction](contact-friction.md). The oleo uses assumed absolute pressure, polytropic gas behavior, asymmetric metering and soft penalty stops; it is not calibrated to the supplied gear or a substitute for measured component curves. The sphere contact uses an explicitly entered radius, not STEP-surface collision. It has no tire footprint, rolling traction, braking or spin-up. [Joint constraint reactions](joint-reactions.md) can be plotted for a solved model, but they do not include separate applied loads. Frictional tire contact and flexible structure remain absent; do not infer them from the plot or the visual part.

## 4. Worked numerical sanity check

The existing [teaching drop](landing-gear-3d.md) defines a 100 kg upper body and 5 kg wheel body, both starting downward at 1.5 m/s. The wheel center starts 0.20 m above first contact (`z = 0.35 m`, contact radius `0.15 m`). Under the ideal model's common free fall before contact, neglecting air forces and assuming no relative strut motion, the impact speed is

`v² = v₀² + 2 g h = 1.5² + 2 × 9.81 × 0.20`, so `v ≈ 2.485 m/s`.

The corresponding total translational kinetic energy is approximately `½ × 105 × v² = 324 J`. This is a check of that **illustrative model's initial conditions**, not the required energy for an aircraft certification test. After contact, the model splits energy between body kinetic and gravitational potential energy, spring and tire penalty energy, and strut damping. The default documented peak contact force is approximately 3.50 kN for that sample and depends on model parameters, numerical timestep and contact assumptions. It is not an aircraft load-factor prediction or proof of a gear's strength.

In the application, run the teaching model, plot the reconstructed contact normal force and strut response, and use **Point probe** to measure separation between the upper and wheel body origins. Export the recorded data, reduce the timestep, and compare the result with the independent RK4 verification in its guide. Do not equate contact-force peaks with full-aircraft CG acceleration: the modeled masses and missing aircraft pitch, tire spin-up and structural flexibility matter.

## 5. Verification and correlation checklist

- Confirm units, occurrence identities, axis directions and physically consistent assembled pose; inspect the generated deck and solver log. Check constrained initial velocities as well as positions.
- Run at least two timesteps and compare contact onset, peak load, peak stroke, rebound and constraint residual. Convergence of numerical results does not establish physical validity.
- Compare forces and motion against measured time histories using the same reference frames, sensor locations, sampling and filters. Compare onset timing and shape as well as peaks, and record uncertainty and out-of-range conditions.
- Check limits and failure modes omitted by the model: travel stops, bearing loads, tensile-only versus compressive-only contact, damping reversal, friction, structural deformation and fatigue.
- Keep measured values, manufacturer data, inferred geometry and illustrative parameters visibly distinct. Establish physical test and structural analysis evidence before using the model for design or safety decisions.

For a full aircraft, nonlinear tire forces, drag, rotational motion and gear/airframe interaction may dominate the load case. These require additional models and independent data beyond the current example.
