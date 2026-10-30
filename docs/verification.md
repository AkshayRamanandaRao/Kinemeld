# Verification record — October 2026

This records historical checks performed on a local development version. It is
not a claim of general-purpose CAE qualification or measured usability superiority.
Run records, generated reports and local logs are ignored and are not included in
the public checkout; the commands below produce fresh evidence on the target system.

## Contact friction increment (1.1)

- On 30 October 2026, `backend/verify_contact_friction.py` ran MBDyn 1.7.3 on five cases.
  A ball launched sliding at 2 m/s with μ = 0.3 decelerated at μg to 10⁻³ relative, rolled
  at 5/7 v₀ from 0.193 s (theory 0.194 s), stayed within 3·10⁻⁵ m/s of an independent RK4
  integration and balanced energy to 2·10⁻⁶ J. A block on four corner spheres stopped in
  0.50968 m (theory 0.50968 m) on a horizontal and on a tilted-normal plane, decelerated
  and accelerated on 15° and 25° slopes within 10⁻⁵ m of `g (sin θ − μ cos θ)`, and crept
  at 5.98 mm/s where regularised friction cannot hold it (predicted 5.98 mm/s). In every
  case MBDyn's applied friction (`result.frc`) equalled `μ N tanh(|s| / v_s)` rebuilt from
  the motion.
- `backend/verify_featured_studies.py gear-spin-up gear-spin-up-study` checked the spin-up
  drag study for μ = 0.3, 0.55 and 0.8: angular momentum against the friction impulse,
  Coulomb drag while sliding, the axle's fore-aft reaction and the dissipated spin energy
  all balance within 0.07 %. 246 backend tests passed, and the browser test
  `tests/contact-friction-ui.mjs` solved the study model and read the friction force at
  full resolution.

## Desktop and authored assembly increment

- On 28 October, 76 backend tests passed. Uniform brick, cylinder, sphere and
  ellipsoid STEP generation was checked against CAD volume, centroid and
  inertia; the browser workflow retained existing CAD and tested Undo, save and
  reopen, and a real solve. Assumed dimensions and density do not validate
  other attached STEP parts.
- Six actual MBDyn slider cases, four spring-damper cases and four constant
  force/torque cases were checked against analytic or independently integrated
  references. The slider plus spring and the STEP-solid/slider/spring/load
  combinations also passed end-to-end UI runs. The corresponding verifiers
  generate slider, spring and load reports under `verification/`.
- An actual multi-turn MBDyn sample crossing an Euler-angle branch verifies that
  the attached STEP solid uses the reconstructed planar angle. An oversized
  project regression checks that the save is rejected before desktop IPC and
  that the complete CSV remains downloadable; its native bridge is a fixture.

- On 28 October 2026, 59 Python backend tests passed. The guided first-study
  browser check loaded the STEP pendulum, added a body and revolute hinge,
  edited its mass, validated it and completed a real MBDyn run. Additional
  tour checks covered persistence, reopening, dialog interaction and visible
  handling of a preference-write failure.
- The new geometry picker accepts STEP/STP only. A browser regression rejected
  mixed STEP/STL selection without changing the project, then reopened, saved
  and removed a pre-existing STL visual reference alongside a STEP solid. The
  native project bridge fixture also checked legacy compatibility and a real
  solver result; operating-system file dialogs remain manually unverified.

- STEP checks exercise OpenCascade's assembly occurrence transforms and
  millimetre/inch conversion. Twelve pinned suspension parts were imported,
  saved and reopened; a selected CAD part followed actual MBDyn output while an
  unbound part stayed fixed. A separate two-body test checked attachment Undo,
  body deletion and restore, and rebinding at a paused result frame.
- The original rectangular STEP pendulum's CAD volume, centroid, geometry and
  inertia match the authored MBDyn rigid-body example. Its application button
  loaded the solid with a saved binding, and a real solve animated it in the UI.
  The suspension CAD has not been validated as a double-wishbone dynamics model.

- On 27 October, 58 Python backend tests passed, including agent and assembly boundary tests.
- The rebuilt Rust Windows host's hidden WebView2 self-check loaded the UI,
  ran a real pendulum solve, and saved and reopened its project. The self-check
  writes a local report under `runs/`.
- The assembly UI test added a second rigid body and revolute hinge, solved the
  system in MBDyn 1.7.3, checked native constraint residuals, node plots,
  invalid-mass diagnostics and Undo. Its test generates a report under `tests/evidence/`.
- Native project UI and STL reference browser checks passed. Those UI tests use
  a bridge fixture; native operating-system dialogs have not been manually tested.
- The installed local `qwen3.5:4b` model proposed a validated oscillator setup
  and explicit run request in a real API test; it does not itself run the solver.
  Its local report was written under `backend/evidence/`.
- Deterministic assistant UI checks cover validated edits, Undo, explicit-run
  gating, rejected proposals and concurrent project changes. Their solver call
  is intercepted; this check does not claim a real solve.

These checks cover the stated cases only, not commercial-suite parity,
production validation, or general three-dimensional assemblies.

## Real MBDyn checks

The configured MBDyn 1.7.3 solver completed six regressions: the three default
model families and one changed-parameter case for each. Original decks were
generated from the supplied parameters. Native output timestamps, finite values,
completion and constraints were checked before accepting results.

| Check | Observed result |
| --- | --- |
| Default pendulum, step 0.005 s | Maximum angle difference from independent reference: 0.0476° |
| Default oscillator, refined step 0.0025 s | Maximum position difference: 0.306 mm, 0.306% of its initial displacement |
| Oscillator step refinement, 0.005 → 0.0025 s | Error decreased by 3.99×; the coarser 1.223% case missed the chosen 1% target |
| Default double pendulum, step 0.005 s | Maximum angle differences: 0.0777° and 0.0851° |
| Both double-pendulum link constraints | Maximum length residual: 6.73 × 10⁻⁷ m |
| Double-pendulum energy | Relative change over the checked default run: 0.00855% |
| Unequal masses and lengths | Both coupled link responses and both length constraints passed the stated regression bounds |

Eighteen backend/API tests passed, covering invalid input, parameterized generation,
independent reference behavior, HTTP boundaries and supported model contracts.
Actual child-process tests also cover timeout, forced-stop and other nonzero exits.
Run `backend/verify_real.py` to generate real-check reports locally in
`backend/evidence/` on the target installation.

## Industry model checks

Ten additional real MBDyn runs passed: default, half-step and changed-parameter
cases for the suspension and touchdown models, plus default, changed geometry,
half-step and reverse-kinematic sweeps for the deployment mechanism. The reverse
sweep tests the generic mechanism mathematics; it does not model in-flight
retraction of the Space Shuttle.

| Check | Observed result |
| --- | --- |
| Default quarter-car body / wheel displacement vs independent RK4 | Maximum differences 0.000610 / 0.002285 mm |
| Default landing-drop body / wheel displacement vs independent RK4 | Maximum differences 0.000622 / 0.003970 mm |
| Default drop first tire contact | 0.02475 s; compression-only tire force |
| Half-step wheel-displacement convergence | Error reduced 3.97× for suspension, 3.85× for drop |
| Reconstructed forces vs native MBDyn joint force | Worst difference below 0.033 N across checked parameter cases |
| Changed damping / drop-energy case | Two tire contact releases during rebound; no tensile tire force |
| Four-bar deployment loop closure, four checked cases | Maximum residual 1.05 × 10⁻⁷ m |

Forces and accelerations in the GUI are computed from the native solver state
using the same stated physical constitutive laws; they are not measured vehicle
loads. The independent RK4 force comparison is a separate accuracy check from
agreement with MBDyn's native joint-force output. The deployment is a prescribed
kinematic study with massive links; actuator length does not establish hydraulic
force, downlock performance, or aircraft safety.

Reproduce with `backend/verify_industry.py` and
`backend/verify_gear_deployment.py`. These commands generate local reports under
`backend/evidence/industry-verification.json` and
`backend/evidence/gear-deployment-verification.json`. Together with the six basic
model runs, the final backend regression covers sixteen actual solver cases.

## Browser workflow

The automated browser suite covers model editing, input-linked validation,
undo/redo, 3D orbit and selection, examples, distinct reference previews, actual
MBDyn solves, project/deck/CSV export, project import, stale results, playback,
dark theme and a 390-pixel-wide layout.

The coupled-body check compares both visible body positions against the actual
solver samples, accounting only for the documented visual ground offset. It
checks two distinct plotted curves and all 13 exported channels. Changing the
second link length changes both responses. The CSV regression checks that a
longer run exports all native rows even when the viewport uses fewer samples.

Screenshots and `tests/evidence/ui-verification.json` are generated by `npm test`.
Only an `ok: true` report establishes the checked run's success. These are local
test artifacts, not committed reference output. A headless software WebGL test
does not establish compatibility with every hardware graphics driver.

The industry suite (`npm run test:industry`) separately checks all three real
solver workflows, selectable response quantities, displayed poses against native
coordinates, full CSV rows, linked guides, stale-result behavior and mobile layout.
Its report is `tests/evidence/industry-ui-verification.json`; inspect its `ok`
field before claiming success. The negative-tire-load check confirms the GUI
warns when the quarter-car continuous-contact assumption is violated.

Under concurrent WSL build load, one default suspension run was interrupted by
the original 40-second guard at simulation time 0.8815 s. Its partial log and
failed summary were local runtime artifacts and are not included in the public
checkout. The runner allows 180 seconds with a bounded
shutdown grace; it explicitly reports time limits rather than implying a
convergence failure. This is not a run-time performance guarantee.

No live comparative interaction benchmark was completed. Screen
readers, touch gestures, arbitrary assemblies, general contact, flexible bodies and
current-development MBDyn remain outside this verification scope.


