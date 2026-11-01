# Verification record

This records historical checks performed on a local development version. It is
not a claim of general-purpose CAE qualification or measured usability superiority.
Detailed run directories, GUI reports and local logs are ignored; selected numerical
summaries in `examples/` are retained. The commands below produce fresh evidence on
the target system.

## Robotics roadmap integration (1 November 2026)

The review branch implements P4–P10 with bounded model contracts. These checks
establish the listed numerical and interface cases, not physical calibration.

- [Integrated Linux CI](https://github.com/AkshayRamanandaRao/Kinemeld/actions/runs/41350498026):
  **294 backend tests**, two platform-conditional skips; all **98 JavaScript unit
  checks**, native numerical verifiers and project/robotics GUI workflows pass.
  Asset and Rust notice inventories remain current; no new runtime dependencies
  were added.
- Current packaging and test-helper regression suite: **60 script checks pass**,
  including macOS bundle sealing, external-manifest coverage, signature rejection,
  and a closing Linux accessibility node. The earlier P3 count below is historical.
- P4: [four engineering records](engineering-example-verification.md), 16 actual
  solver runs, CAD mass/COM/tensor assumptions and independent references.
- P5: cones/tori, 13 frontend geometric checks, extraction checks on OCP 7.9 and 8,
  and ordinary/curved CAD GUI round trips with transformed attachments.
- P6: 40 assistant checks; eight proposal/study/result GUI workflows with four
  native runs. Transport is deterministic; live-language-model accuracy is not
  part of this evidence.
- P7: [17 native brake/contact cases](../examples/robot-contact-verification.json),
  existing plane-contact regressions, editor/Undo/plot/CSV/project workflows and
  actual HTTP rejection of an energy-producing native brake startup.
- P8: [nine native controlled cases and two cleanup cases](../examples/rotary-control-verification.json),
  ten unit checks and five GUI workflows. Real native hinge feedback, previous-step
  held torque and native applied couples are cross-checked. Cancel and peer failure
  stop the solver and controller. Linux integration CI and extracted Windows,
  macOS and Linux packages also exercise the real controller and solver.
  WSL transport is explicitly rejected.
- P9: [ten native flexible-link runs](../examples/flexible-link-verification.json),
  six backend/two renderer checks, actual node playback, section/mesh editing,
  full CSV and native artifacts, save/reopen/stale gates and actual process Cancel.
  Static shape, first frequency and mesh/timestep refinements have independent
  references. Flexible joints, general FE import and stress/fatigue are outside
  this initial cantilever contract.
- P10: six unit checks and real GUI candidates ranked from complete CSVs against
  independent RMS integration. Explicit Apply/Undo/Redo, exact baseline CSV,
  configuration save/reopen, bounds, cancellation and the real 30-second stalled-CSV
  deadline are checked. Failed and overflowed responses cannot win. Rankings are
  session data; the configuration and exported table retain the setup/results.
- Existing spatial regression: all nine GUI scripts pass against the native solver.
  Existing and curved CAD GUI scripts pass without page errors. Reports and
  screenshots are retained under `verification/integrated-regression-8794/`.

P2 cross-platform native-dialog qualification is tracked separately below and in
[native GUI testing](native-gui-testing.md). Current work remains unpublished.

## Dependency and license audit (1 November 2026)

P3's [audit record](dependency-audit.md) identifies the three actual v1.2.1
archives, exact runtime/source versions, retained notices and unresolved upstream
rights. All 13 newly collected runtime files match the published originals byte
for byte. The current locked Rust inventory covers 194 registry package versions;
the asset inventory covers 49 assets and 8 notices.

- `python -m unittest discover -s scripts -p 'test_*.py'`: **47 passed**. Missing
  and changed notices/sources, unknown libraries, compiler/source drift, stale or
  unlisted source files, wrong platform metadata and unsafe archives are rejected.
- [Code CI](https://github.com/AkshayRamanandaRao/Kinemeld/actions/runs/41336571338):
  backend **247 tests, two conditional skips**; featured-study/constraint checks;
  native tests/builds on Linux, macOS and Windows. The two Linux-job skips are the
  explicitly enabled WSL cancellation check and Windows launcher diagnostics.
- The optional OCP 8.0.1.1.0 runtime passes **36/36** affected CAD tests in an
  isolated Linux environment after fixing its indexed-shape compatibility alias.
  Seven OCP 7.9 geometry tests also pass locally on Windows.
- [Unpublished package run](https://github.com/AkshayRamanandaRao/Kinemeld/actions/runs/41336308183):
  all nine source-build, package and clean-runner jobs pass. Checks include full
  archive hashes, matching notice/source companions, a fresh packaged service,
  real MBDyn solves and the native WebGL2/project round trip. This is separate
  from the operating-system dialog matrix below.
- The filtered source builds from a fresh tree and passes six actual simulations
  with Naive solver. Eleven unused Y12 implementations are removed from both the
  build source and distributed source archive; the transformation is hash-pinned.

The candidates and their per-platform source archives have SHA-256 sidecars;
[delivery identities](../notices/solver/audit-candidates.json) retain their hashes.
No release was published or historical binary archive replaced. This establishes
the tested artifact identity and workflows; it does not resolve the macOS
SDK-derived binding warning, historical Y12 rights, or the optional private
Python/OCP runtime's redistribution status.

## Windows native GUI verification (1 November 2026)

`npm run test:native-dialogs` passes **12/12 cases with no skips** against an
extracted local Windows package. It connects Playwright to the actual WebView2
viewer and uses a PID-scoped Win32 helper for operating-system dialogs. The native
bridge and dialogs are not replaced with fixtures. Package resources are located
automatically; no source-workspace override is used. All 312 package file hashes
were checked before the run.

Both the pre-solved fixture and the default shipped nose-gear project pass the
complete matrix. The default path runs MBDyn in the actual app before checking
the result round trip.

- Native Open, Save As and reopen retain the model, all 11 STEP bindings, 501
  MBDyn samples and the 3,611,262-byte full CSV. Ordinary Save keeps a byte-exact
  backup. Save As cancellation and overwrite refusal leave prior files unchanged.
- External edits reject Save without overwriting the changed file; a fresh Save As
  succeeds. New asks for a destination again after each cancelled Save and
  autosaves without inheriting the previous file path.
- Declining dirty Open, cancelling its picker, and opening malformed JSON preserve
  current work. A forced process exit is followed by recovery of the full CAD and
  result snapshot; a real recovered Save As matches its pre-crash semantic content.
- Declining Close retains work. Confirmed Close clears the recovery snapshot,
  exits with code zero and stops the owned backend. Separate clean/dirty close
  probes pass with the GUI driver attached and detached. Accepted exit now ignores
  queued application events while the event loop finishes closing.
- Representative native file/confirmation dialogs and the recovered workbench
  were inspected from the GUI-test screenshots. JSON reports and PNGs are generated
  under `tests/evidence/native-dialogs-*`.

The tested executable SHA-256 is
`d7b23b1a8c11c6cec736b66175f778b22afd4b40f00f54035c012f8b84cbbe1d`;
the tested `frontend/app.js` SHA-256 is
`8c939fc7389da07948227ba43a14fbb036a965bb4ae28a6b737d395f92ee8f5b`.
This is a configured Windows machine using its installed Python/CAD runtime and
local WSL MBDyn 1.7.3. The QA archive bundles no Python, CAD runtime or solver.
Clean-machine GUI installation and macOS/Linux native dialogs remain unverified;
this is not a distribution or dependency-license qualification.

## Asynchronous edit preservation (1 November 2026)

- Reproduced a delayed STEP replacement dropping a newer attachment, a delayed
  startup restore replacing a newer edit, and an older autosave reaching the host
  after the active document changed. Regression tests fail when the corresponding
  guards are bypassed in a served test copy; the application source is unchanged
  by these negative controls.
- The final `npm run test:project-safety` passes: 10 CAD/project cases, eight
  startup and pending-input cases, five native-copy identity cases, five autosave
  races, the existing open/rollback/acknowledgement workflows and two bridge tests.
  Model edits, CAD bindings, full solver CSV and recorded results are compared;
  a newer real MBDyn run is included in the autosave checks.
- `npm run check`, changed-script syntax and whitespace checks pass. Normal STEP
  append/Undo/save/reopen and primitive generation/Undo/Redo/solve/save/reopen pass.
- The release-profile Rust suite passes 31 tests, including untitled native
  sessions, rollback to the previous file, recovery-origin finalization, backups,
  external-change rejection and service ownership. One direct helper entry is
  intentionally ignored and exercised through its parent startup tests.

The browser tests above use controlled native bridges for deterministic races.
They are separate from the real Windows dialog suite described in
[the desktop guide](../native/README.md#automated-windows-gui-checks).

## Recording refresh (1 November 2026)

- Re-recorded `aircraft-nose-gear` and `workflow-nose-gear` from real MBDyn 1.7.3
  solutions in headless Chrome on Windows. The featured MP4 is 1280 × 720 / 6.33 s;
  the workflow MP4 is 1280 × 720 / 106.23 s. Matching GIFs are 720 × 406 and
  800 × 450. All four files decoded without errors; representative motion frames
  and the workflow's final MP4/GIF captions were visually inspected.
- Model and featured-overlay changes affect display names only; source CAD bytes,
  bindings, model parameters and solver settings are unchanged. Engineering limits
  remain in the [study guide](aircraft-nose-kinematics.md).
- Ten focused backend tests passed (`test_aircraft_nose_kinematics` and
  `test_featured_studies`), as did `npm run check`, recorder syntax checks and the
  nose-gear browser import, solve, animation and save/reopen regression.
- The existing independent kinematics and timestep verifier passed: maximum
  scissor-point error `4.23 × 10⁻¹⁵ m`, refinement difference `1.01 × 10⁻¹³ m` and
  constraint residual `5.29 × 10⁻¹⁴ m`. These establish numerical consistency of the
  prescribed fixture; they do not validate aircraft hardware loads. Native dialogs
  and the remaining roadmap items were not exercised in this increment.

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

These checks cover the stated cases only, not agreement with other multibody codes,
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
readers, touch gestures, arbitrary assemblies, general contact and flexible assemblies, and
current-development MBDyn remain outside this verification scope.


