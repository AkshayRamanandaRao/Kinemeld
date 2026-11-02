# Traceable engineering examples

The robot arm, sourced nose gear, open suspension and original landing drop now
have a machine-readable `engineering.json` beside their saved project. These
records identify the actual input model, CAD bytes, generator, body/CAD frames,
local and world hardpoints, density assumptions, gravity, initial velocities,
prescribed motions and force-law parameters. They distinguish a geometric
observation from an inferred interface or an illustrative input.

| Example | Input record | Numerical reference |
| --- | --- | --- |
| Three-axis robot arm | [robot-arm/engineering.json](../examples/robot-arm/engineering.json) | Serial-chain forward kinematics and independent Jacobian mass-matrix inverse dynamics. |
| Original nose-gear CAD | [open-aircraft-nose-kinematics/engineering.json](../examples/open-aircraft-nose-kinematics/engineering.json) | Prescribed slider displacement and the initial branch of a two-circle torque-link construction. |
| Inferred open suspension | [open-suspension/engineering.json](../examples/open-suspension/engineering.json) | Two-circle arm/upright closure, conditioned on the solved lower-arm coordinate; this is not an independent time-domain dynamics solution. |
| Original two-mass landing drop | [landing-gear-3d/engineering.json](../examples/landing-gear-3d/engineering.json) | Separate RK4 integration of the two-mass equations and an analytic first-contact time. |

The saved titles and visual examples remain concise. Engineering limits live in
the input records and study guides. None of these records supplies missing
hardware measurements, a material certificate or manufacturer-approved loading.

## Repeat the checks

Use a source checkout, Python with the optional OCP runtime, and a configured
MBDyn executable. No browser or desktop automation is needed for these numerical
checks; the existing GUI suites separately exercise CAD/project interaction.

```sh
python -B -m unittest discover -s backend -p test_engineering_examples.py -v
python -B backend/verify_engineering_examples.py robot-arm
python -B backend/verify_engineering_examples.py nose-gear suspension landing-drop
```

With no study arguments the verifier checks all four examples. It writes
`verification/engineering-examples.json`; each actual MBDyn run also retains its
deck, full CSV, solver log and input model in the configured run-data directory.
Set the normal `MBDYN_STUDIO_DATA_DIR` to an isolated writable folder if these
checks should not share the app's history. Put a normal `solver.json` in that
folder; the verifier does not alter the user's solver configuration.

For each example the verifier:

1. Checks the canonical saved-model hash, generator hash with normalized text
   line endings, embedded and retained CAD identities, body mappings and every
   hardpoint. A model or source edit invalidates the corresponding record.
2. Reintegrates each dynamic CAD occurrence at its explicitly recorded assumed
   density, transforms the centre of mass and inertia to body coordinates, and
   combines rigidly grouped parts with the parallel-axis theorem. It compares
   every resulting body mass, centre and full tensor with the saved input.
3. Runs the baseline timestep, half-step and quarter-step, checking the quantity
   against the independent reference and comparing positions at matching times.
   For free suspension/drop dynamics, refinement must reduce the differences.
   Prescribed kinematics can reach roundoff already, so an artificial observed
   convergence order is not assigned to those tiny position differences.
4. Runs an additional changed-input case: half the nose-gear stroke amplitude,
   20% stiffer suspension spring, 20% lower drop speed, or 20% lower robot shoulder
   amplitude. Each changed model gets its own model/deck hashes and run ID.

Comparisons cover the requested nominal time interval. MBDyn can emit a final
sample one step beyond that interval; both its raw sample count/final timestamp
and the compared interval are recorded. The complete solver files remain intact.

The unit checks include negative controls: a changed CAD payload, edited mass,
missing density or hardpoint, displaced linkage, singular circle construction,
or incorrectly aligned refinement grid must fail. The robot reference also
matches the closed-form static gravity moments and a known Cartesian tip pose.

## Recorded numerical evidence

The [retained verification snapshot](../examples/engineering-verification.json)
records a fresh local Windows/Cygwin MBDyn 1.7.3 benchmark, the executable and
reference-script hashes, model/deck hashes and run IDs. It includes **16 actual
solver runs**, not previously generated animations: three baseline resolutions
and one changed-input case per example. All 25 dynamic CAD occurrences were
reintegrated into their 15 rigid bodies at the stated assumed densities.

| Example | Coarse → half → quarter step | Recorded comparison |
| --- | --- | --- |
| Robot arm | 2 → 1 → 0.5 ms | Maximum independent torque error 0.414 → 0.104 → 0.026 mN·m outside the documented acceleration-jump windows; Cartesian FK error below 10⁻¹² m. |
| Nose gear | 1 → 0.5 → 0.25 ms | Slider/two-circle reference error below 5.2 × 10⁻¹⁴ m; matched-time positions are already at the output's roundoff floor. |
| Open suspension | 0.5 → 0.25 → 0.125 ms | Conditional circle-closure error below 5.7 × 10⁻¹⁴ m; consecutive position differences 0.0955 and 0.0251 µm. |
| Landing drop | 0.5 → 0.25 → 0.125 ms | Maximum position error against RK4 40.08 → 10.04 → 2.55 µm; tire-force error 10.02 → 2.51 → 0.638 N. |

Landing-drop peak tire forces are 3,496.59, 3,493.98 and 3,493.78 N. The
analytic first-contact time is 0.1003826 s; the first positive-force output is
at 0.1005 s on these grids. These are results of the supplied idealized case,
not measured aircraft loads. The report also records the changed-case results;
they pass the same independent-reference and residual criteria.

## What the checks mean

These are numerical and input-traceability checks for specific idealizations.
The density integration checks that the stated assumptions were applied; it does
not identify the real material. The robot benchmark tests ideal required torque,
not whether a motor can deliver it. The nose-gear linkage retains its documented
joint substitutions and source overlaps. The suspension has no steering tie rod,
and the landing drop uses an illustrative linear strut and penalty tire law.

Before using a model for a hardware decision, replace assumed inputs with
traceable measurements or supplier data and compare against instrumented tests.
Keep that correlation evidence separate from this numerical verification record.
Updating a hash alone does not validate an edited example: review the assumptions,
hardpoints and reference equations and repeat the checks.
