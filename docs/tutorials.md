# First simulations

These examples teach a complete **Model → Validate → Run → Results** cycle.
Open the local application at `http://127.0.0.1:8766` after starting its server as
described in the README. Confirm the solver status before requesting an MBDyn run.

The model uses metres, kilograms, seconds and newtons. Initial pendulum angle is
entered in degrees. Global X is horizontal and Z points upward; these examples
remain in the X–Z plane. Exported samples use the model frame, so a visual ground
offset in the viewport does not change their coordinates.

A **Reference preview** is independent of MBDyn. The oscillator uses a closed-form
solution, whereas the nonlinear pendulum uses an independent Runge–Kutta
integration. Neither proves
that a generated deck ran successfully. Look for the **MBDyn** result source,
run identity and log when reviewing a real solver result.

## 1. Gravity pendulum

Question: how does length change the oscillation period?

Choose **Gravity pendulum** from Examples. This is an ideal point mass on a
massless, rigid link with one ground joint, uniform gravity and zero initial
angular velocity. It has no damping, joint friction or flexible link. The visible
bob size is illustrative; it does not derive inertia from a CAD solid.

| Parameter | Starting value | Meaning |
| --- | --- | --- |
| Mass | 1 kg | Moving point mass |
| Length | 1 m | Pivot-to-mass distance |
| Initial angle | 30° | Measured from vertically downward |
| Gravity | 9.81 m/s² | Acceleration toward negative Z |
| Duration | 5 s | Simulation end time |
| Time step | 0.005 s | Requested integration step |

1. In **Model**, inspect the body, joint and gravity entries. Check the units
   beside the parameters.
2. Select **Validate**. Repair any errors before continuing. Inspect or export
   the generated MBDyn deck to see the numerical inputs.
3. Select **Run**. Keep the run log if the solver fails; a red failure or missing
   executable is not a solved case.
4. In **Results**, scrub the timeline and plot angle. At the initial condition,
   `x = L sin(θ)` and `z = −L cos(θ)`; the mass should follow a circle about the
   pivot. Pendulum velocity is angular velocity in **rad/s**, not m/s.
5. Save/export the project JSON and result CSV. Change length to 2 m. The previous
   output is stale until a new run succeeds; retain its original inputs if comparing.

Independent check: for small angles,

```text
T₀ = 2π √(L/g)
L = 1 m, g = 9.81 m/s²  → T₀ = 2.00607 s
L = 2 m, g = 9.81 m/s²  → T₀ = 2.83701 s
```

The default 30° case is nonlinear; its period should be slightly longer than the
small-angle reference. For a simple numerical check, set the angle to **5°** and
measure one full cycle between same-direction zero crossings. A useful initial
acceptance target is within **1%** of `T₀`, then repeat with steps 0.005 and
0.0025 s to check convergence. This is a test target, not a claim that every run
has already passed it. Doubling mass should leave this ideal pendulum's period
unchanged. The circle residual `abs(sqrt(x² + z²) − L)` tests the joint constraint.

For the undamped ideal model, energy is
`E = ½ m L² ω² + m g L (1 − cos θ)`. Read θ in radians in this formula.
Numerical integration can introduce drift; compare step sizes before interpreting
small energy changes as physical damping.

## 2. Damped oscillator

Question: how do stiffness and damping change motion after release?

Choose **Damped oscillator**. A mass translates along X against a linear spring
and viscous damper. Its equilibrium is `x = 0`; initial velocity is zero. The
guide removes other translations and rotations. There is no gravity-driven
motion, nonlinear spring, contact or dry friction in this model.

| Parameter | Starting value | Meaning |
| --- | --- | --- |
| Mass | 1 kg | Translating mass |
| Stiffness | 100 N/m | Linear spring coefficient |
| Damping | 0.5 N·s/m | Viscous damping coefficient |
| Initial displacement | 0.1 m | Offset from equilibrium |
| Duration | 5 s | Simulation end time |
| Time step | 0.0025 s | Refined default; compare with 0.005 s to assess convergence |

Validate, inspect the deck, run MBDyn and open Results. The displacement should
oscillate around zero with a decaying envelope. The current GUI plots displacement;
export CSV to plot velocity separately, whose unit here is **m/s**.

For these values:

```text
ωn = √(k/m) = 10 rad/s
fn = ωn/(2π) = 1.59155 Hz
ζ  = c/(2√(km)) = 0.025
α  = c/(2m) = 0.25 s⁻¹
ωd = √(ωn² − α²) = 9.99687 rad/s
Td = 2π/ωd = 0.628515 s
x(t) = x₀ exp(−αt) [cos(ωd t) + (α/ωd) sin(ωd t)]
```

That expression assumes the underdamped case and zero initial velocity. Compare
the solver's time-stamped displacement samples against it; halve the step and
check that the discrepancy decreases. A useful initial target is maximum
absolute position error below **1% of the initial displacement** over 5 s, with
an absolute tolerance stated for near-zero initial displacements. This target
must be verified, not inferred from a smooth animation.

Try stiffness 400 N/m with the same mass: the undamped natural frequency doubles.
Try damping 20 N·s/m: the system is critically damped and should return toward
equilibrium without repeated crossings. The underdamped formula above no longer
applies to that case; the reference calculation handles the different regime.
With zero damping, the ideal system conserves mechanical energy.

Measured on the pinned solver: the same default oscillator had maximum position
error **1.223 mm** at a 0.005 s step and **0.306 mm** at 0.0025 s. The coarse run
missed the 1%-of-initial-displacement target; the refined default met it. This
roughly fourfold error reduction is a measured convergence check for this model,
not an accuracy guarantee for other parameters.

## 3. Coupled double pendulum

Question: how does a second moving body change the first body's response?

Choose the double-pendulum example. It has two point masses on massless rigid
links, with two planar revolute joints. The second bob's motion depends on both
links; it is not a second independent pendulum animation.

| Parameter | Starting value |
| --- | --- |
| Mass 1 / mass 2 | 1 kg / 1 kg |
| Length 1 / length 2 | 1 m / 1 m |
| Release angle 1 / release angle 2 | 20° / 45° |
| Gravity | 9.81 m/s² |
| Duration / time step | 5 s / 0.005 s |

Both angles are **absolute angles from vertically downward**, not a relative
joint angle. Initial angular rates are zero. Validate and run; the two plotted
curves show link 1 as solid blue and link 2 as dashed teal. The second body is
teal in the 3D view. Scrub to inspect their simultaneous configurations.

CSV adds `x2`, `y2`, `z2`, `angle2`, `velocity2` and `value2` fields. Positions
are absolute model-frame coordinates; the second angular rate is in rad/s. The
first body's position must satisfy `sqrt(x²+z²)=L1`; the second link must satisfy
`sqrt((x2-x)²+(z2-z)²)=L2`. Check both constraints rather than testing only the
overall distance to ground.

Change mass 2 or length 2 and rerun: both curves should change. A second verified
case uses unequal masses (0.8/0.35 kg) and lengths (1.7/0.9 m). Compare against the
independent coupled-equation RK4 reference, and refine the step before drawing
conclusions from long or sensitive trajectories. There is no damping or contact
in this example. It demonstrates two coupled degrees of freedom, not arbitrary
joint-graph authoring.

## 4–6. Industry studies

These examples represent engineering workflows with explicit reductions. Their
dimensions and coefficients are original teaching values, not measured vehicle,
aircraft or Space Shuttle data. Select one in **Examples**, edit inputs, validate,
inspect its MBDyn deck and run the local solver. **Guide** opens the selected
study's detailed guide with equations, assumptions and parameter experiments.

| Example | Engineering question | Outputs to inspect |
| --- | --- | --- |
| [Quarter-car road bump](industry-suspension.md) | How do suspension damping and tire stiffness trade body motion against wheel load? | Body/wheel displacement, suspension travel, tire load, ride acceleration. |
| [Landing-gear drop test](industry-landing-drop.md) | How does sink velocity change touchdown force and strut compression? | First contact, compression, tire force, airframe acceleration and rebound. |
| [Shuttle-style deployment](industry-gear-deployment.md) | Can the chosen brace lengths close through the full deployment sweep? | Main-strut angle, folding-brace pose, geometric actuator length and closure residual. |

The **Response quantity** selector changes plotted channels while retaining the
same run. Solid blue is the first named channel; dashed teal is the second.
CSV exports all native samples with units in column names, including channels
that are not currently plotted. Forces and accelerations in the first two studies
are derived from solver positions/velocities using their documented force laws.
The deployment actuator length is a kinematic requirement, not a hydraulic force.

The quarter-car viewport offsets the equilibrium coordinates by 1.15 m for the
body and 0.28 m for the wheel. The drop rig offsets both vertical coordinates by
the illustrative tire radius (0.22 m). The deployment adds main-strut length +
0.34 m to Z to place the wheel bay above the display floor. These display offsets
do not alter the solver model or exported coordinates. Wheel/airframe geometry
illustrates the model topology; it is not imported CAD or an extra solved DOF.

## Troubleshooting and reproducibility

| Symptom | Next action |
| --- | --- |
| Invalid mass, length or non-finite input | Repair the named field. Do not replace it with a guessed default. |
| Step too large for model time scale | Reduce the step, or reconsider the physical parameters; keep the same model for comparisons. |
| Solver unavailable | Follow `solver.md`. You can still export the deck and use the separately labelled reference preview. |
| Solver failed or timed out | Read the retained log and deck. Do not interpret partial or old samples as a successful new run. |
| Results marked stale | Rerun after the edit, or explicitly return to the parameters that produced those results. |
| Exported project cannot be imported | Check its format/version and supported model family. Arbitrary `.mbd` deck import is not a supported round trip. |

For a reproducible report, keep project JSON, generated deck, solver version,
log, output CSV, parameter/step changes and the comparison equation or reference.
The tutorials exercise three idealized model families; they do not validate real
hardware, arbitrary mechanisms or all MBDyn elements.

For broader learning, use the official [documentation index](https://www.mbdyn.org/Documentation/Documentation.html)
and [example catalog](https://www.mbdyn.org/Documentation/Examples.html). Use the
input manual matching the executable version shown by your configured solver.
