# Changelog

All notable changes to Kinemeld are recorded here. Versions follow
[semantic versioning](https://semver.org/); from 1.0, project files follow the compatibility
rules in [docs/project-format.md](docs/project-format.md).

## Unreleased

- Add traceable engineering records for four studies, with 16 fresh solver runs,
  mass/COM/tensor provenance and independent kinematics, torque and drop references.
- Pick analytic cones and tori for joint/frame placement and measurement, including
  transformed STEP occurrences, Undo/Redo and original-CAD project round trips.
- Review assistant proposals for parameter studies, named-frame links and model
  names; summarize actual stored results and reject stale proposals atomically.
- Add native static/sliding revolute brakes and moving sphere-pair normal contact,
  with editor, glyphs, plots, full CSV and numerical/GUI benchmarks. Initial brake
  loading is bounded; energy-producing native startup states fail explicitly.
- Add bounded constrained design search with up to 25 actual MBDyn candidates,
  full-resolution response ranking, explicit Apply/Undo and saved configurations.
- Add torque-limited rotary PD actuators with real native hinge feedback and a
  separate trusted local controller, inspectable command/feedback traces and
  owned process cancellation. Controlled runs use the managed native solver;
  standalone deck export and WSL transport fail with an actionable explanation.
- Add a clamped flexible robot-link template using native beam3 elements and
  actual node playback, section/inertia inputs, root reactions, full CSV and
  mesh/timestep/static/frequency benchmarks.
- Hash the retained native deck bytes consistently on Windows, including CRLF
  newlines, so provenance matches the downloadable input file.
- Audit all three desktop dependency sets, retain missing Rust/Microsoft/solver
  notices, and require exact runtime source packages with distribution patches
  beside solver binaries. Check full archive coverage and reject stale or incomplete
  notices and sources. Build from filtered MBDyn source with unused Y12 implementations
  removed; preserve its provenance and COLAMD/OpenLDAP notices. See the
  [dependency audit](docs/dependency-audit.md) for scope and unresolved rights.
- Keep STEP import working with `cadquery-ocp` 8.0.1 by mapping its renamed
  indexed-shape collection through the existing OCP compatibility module.
- Preserve newer model edits, CAD attachments and solver results when delayed
  imports, generated solids, example loads or project opens finish. Stale autosave
  payloads and acknowledgements cannot replace the active document's recovery state.
- New assemblies and opened examples start as unsaved native documents, with their
  own file identity. Save asks for a destination; cancellation and failed opens keep
  the current document and its recovery origin.
- Added an automated Windows GUI suite for real native dialogs, full project
  round trips, conflicts and crash recovery. Accepted close ignores queued events
  and shuts down the owned service; Windows checks pass, while macOS/Linux dialog
  qualification remains open.
- Refreshed both aircraft nose-gear MP4/GIF pairs with concise model titles and
  captions. Engineering assumptions and interpretation limits remain in the study
  guide. The workflow recorder now generates and checks its GIF alongside its MP4.
- Prioritize the remaining roadmap around robotics multibody dynamics; proceed
  across the authorized items and keep aerodynamics outside the active scope.

## 1.2.1 — Documentation, help text and first launch

- **First launch.** The desktop app waits up to 90 s for its local service and 30 s for the
  solver's first response, instead of 15 s and 10 s. On a fresh install the operating system
  can scan the bundled Python and solver before they first run, which made the first launch
  report that the service could not start or that MBDyn was not configured.
- The in-app help no longer refers to a separate project for finite-element analysis.
- Documentation, code comments and release notes describe CAD behaviour without naming
  other products, and the font notice points to the IBM Plex source only.
- The macOS package is built and checked on macOS 15 (Apple silicon), as GitHub retires its
  macOS 14 build machines; the bundled solver still targets macOS 14.

## 1.2.0 — CAD part by part: the nose-gear showcase

### Pre-processing
- **Add STEP files.** Once CAD is loaded, **STEP parts → Add STEP files** adds files to it, one
  part or several at a time, so an assembly can be brought in part by part. Earlier parts keep
  their attachments and identities, every part is listed with its file name, and Undo removes
  the last addition. **Import STEP files** still replaces the loaded CAD.
- **Hole rims from any CAD system.** Many CAD systems write a hole rim as two or four
  arcs; the importer now joins arcs that complete a circle, so such parts offer their pin holes
  for joint placement and measurement as well as single full circles.

### Demos
- **End-to-end showcase on the aircraft nose gear.** The homepage recording imports the
  eleven original STEP parts one by one, builds the strut, piston, torque-link and wheel
  bodies, attaches the CAD, places every joint on the CAD pin holes, computes mass from the
  solids, prescribes the shock-strut stroke, solves with MBDyn and post-processes the stroke,
  torque-link fold and strut force (`docs/demos/workflow-nose-gear.mp4`).
- **Model name.** A 3D assembly's name can be edited in its properties, so a new model need
  not stay "Untitled 3D assembly".
- The README now plays every showcase recording inline as a GIF; GitHub does not play MP4
  files from a repository, so the full-quality MP4 stays linked beside each one.
- `examples/open-aircraft-nose-gear/parts` holds the nose-gear assembly's eleven parts as
  separate STEP files, written by `split_parts.py` with the source product names.

## 1.1.0 — Contact friction

### Model
- **Friction on sphere-plane contacts.** A contact takes an optional Coulomb friction
  coefficient and a slip velocity (default 0.05 m/s) over which the friction force rises to
  μ × normal force. MBDyn applies it from the contact's own normal force and the slip of the
  contact point, as a force at the sphere centre and its couple, so sliding balls spin up and
  braked wheels drag their axles. Regularised friction has no true stiction: a part held on a
  slope creeps slowly, at a speed the guide states.
- **Validate model** estimates whether the time step resolves the friction near sticking and
  suggests a smaller step or a larger slip velocity.
- Projects without friction are unchanged; the new fields are optional
  ([project format](docs/project-format.md)).

### Post-processing
- Contact friction force (MBDyn's applied force, from `result.frc`), slip speed and friction
  dissipated energy plots at full resolution, with matching CSV columns
  (`frictionForce_N`, `slip_m_s`, `frictionPower_W`, `frictionEnergy_J`).

### Studies
- **Landing-gear spin-up drag** featured study: a wheel spun backwards to a 30 m/s tyre
  surface speed is dropped on a still platform, as drop-test rigs reproduce touchdown, with a
  friction study at μ = 0.3, 0.55 and 0.8. Recorded for the homepage
  (`docs/demos/study-spin-up.mp4`).
- The assistant can set a contact's friction.

### Verification
- `backend/verify_contact_friction.py`: a ball rolling at 5/7 v₀ against RK4, blocks sliding
  to rest and down slopes on general planes, creep on a slope, MBDyn's applied friction
  against μ N tanh(|s| / v_s), and the energy balance.
- The spin-up study is checked for angular momentum, Coulomb drag, the axle reaction and the
  dissipated spin energy in every case.

## 1.0.0 — Self-contained everywhere

### Windows
- **MBDyn bundled on Windows.** The Windows package now carries MBDyn 1.7.3 built in CI with
  Cygwin's GCC, with the Cygwin runtime and GCC DLLs beside `mbdyn.exe`. No WSL, compiler or
  separate solver installation is needed; a configured solver still takes precedence.
- The Windows package passes the same clean-machine check as Linux and macOS before a release
  is published: every file against its manifest, the packaged service with an empty user
  folder, real MBDyn solves of the pendulum and a featured 3D study, and the desktop
  self-check (embedded viewer, MBDyn run, project save and reopen).

### Projects
- **Compatibility promise:** from 1.0, every 1.x release opens projects saved by earlier 1.x
  releases and by 0.2–0.9; changes within 1.x are additive. `docs/project-format.md`
  documents the format and the rules; `backend/test_project_compatibility.py` checks every
  shipped project against them.

### Build
- `scripts/bundle_solver.sh` bundles the DLLs a Cygwin build imports and fails unless the
  bundle starts with only Windows on PATH. The Windows build exposes POSIX declarations to
  `-std=c++11` and archives the Fortran libraries with GNU ar where MBDyn's bundled libtool
  assumes Microsoft's tools.

## 0.9.0 — Interaction II

### Pre-processing
- **Hole rims:** the STEP converter reports every full circular edge (hole rims, shaft ends)
  with centre, axis and radius, under `cadquery-ocp` 7.9 and 8. While picking or dragging,
  rims are drawn on their parts; a rim near the pointer wins over the face it bounds unless
  it is hidden behind a surface. Joints, frames and measurements use its centre and axis.
- **Constrained dragging:** a dragged joint symbol snaps to the CAD feature under the
  pointer, and otherwise slides along its own axis in 1 mm steps. Shift slides along the
  axis even over CAD, Alt moves across it, and joints without a single axis move in the
  plane facing you. Dragging now works in any 3D assembly, with or without CAD.

### Post-processing
- **Measure at the animated pose:** in Post-processing, Measure evaluates features at each
  body's solved pose in the displayed frame and states the time.

### Tests
- `tests/interaction-ii-ui.mjs` places the wheel-end bearing on the hub's Ø55 rim, measures
  the 70 mm between its rims, Shift-drags the bearing along its axis and checks that a
  measurement at an animated frame sits on the displayed rim. Unit tests cover circle
  features, body/world placement and the axis and plane drag geometry;
  `backend/test_step_geometry.py` checks the reported rims.

## 0.8.0 — Studies in the demo set

### Featured parameter studies
- **Landing-gear drop test, sink speed 1.5–3 m/s:** the study opens preloaded; MBDyn solves
  four cases and the peak tyre load rises from 18.0 to 27.5 kN (load factor 5.19 to 7.94).
  In every case mechanical, stored and dissipated energy balance within 0.08 % of the impact
  energy, and the strut never bottoms.
- **Wheel-end drop test, tyre stiffness 10–40 kN/m:** every case's peak contact force matches
  an independent Runge–Kutta solution of the drop on the same contact law within 0.5 %
  (620 to 1,291 N).
- `verify_featured_studies.py` runs every case of both studies.

### Studies
- Featured catalog entries can define a parameter study (input, values, response, label).
  The gallery card says a study is included, the Solve card opens preloaded, and the plot
  switches to the study's response when it finishes.
- Projects save the current study set-up and restore it when reopened.
- **All bodies** inputs sweep an initial velocity that every body shares (a drop or sink
  speed) without breaking joint consistency.

### Demos and guides
- New homepage recording: the landing-gear sink-speed study from the gallery to the animated
  3 m/s case (`tests/record-study-demo.mjs`).
- The guided tour's last step points to the wheel-end tyre-stiffness study.
- The featured study guide documents both studies with their tables; a duplicated robot-arm
  section is merged.

### Tests
- `tests/featured-study-ui.mjs` opens the gear drop, runs its study and saves and reopens the
  set-up; `backend/test_featured_studies.py` checks study definitions and case semantics; the
  tour test checks the preloaded study.

## 0.7.0 — Parameter studies

### Solve
- **Parameter study** card: choose an input to vary — a template parameter, or a physical
  property of an assembly body or element (mass, stiffness, damping, free length, strut gas
  and orifice settings, load and torque amplitudes, drive settings, initial position and
  velocity), with the selected entity preselected — and a list of up to 12 values,
  defaulting to half to double the current one.
- The current value is always solved as the baseline; cases run in ascending order through
  MBDyn with progress, a console log and Cancel, which keeps the cases already solved.

### Post-processing
- Every case of the chosen quantity on one plot, ordered blue to orange, with the animated
  case drawn heavier; one channel at a time for X / Y / Z quantities.
- A table of each case's maximum and minimum (with their times), RMS and final value from
  the full-resolution series, exportable as CSV. Selecting a row animates that case.
- Projects save the baseline result; the study stays in memory for the session.

### Tests
- `tests/studies.test.mjs` (parameter discovery, case models, value parsing, summaries, CSV,
  colours) and `tests/parameter-study-ui.mjs`, which sweeps the wheel-end drop's tyre
  contact stiffness and checks that peak contact force rises with it.

## 0.6.0 — Reliability and CAD

### Desktop
- **Crash-safe autosave:** unsaved work is written to a recovery snapshot in the user-data
  folder once editing pauses (and at least once a minute), through a synced temporary file
  and an atomic rename. Saving or closing normally removes it.
- **Recovery at start-up:** after an unexpected exit, Kinemeld offers the snapshot back.
  Recover opens it as an unsaved project and Save suggests the original file; Discard keeps it
  as `recovery/declined-<time>.json` (newest three kept). Unreadable snapshots are set aside,
  never deleted.

### CAD
- STEP import and mass properties work with **`cadquery-ocp` 8** as well as 7.9:
  `backend/ocp_compat.py` maps the sequence classes OCP 8 moved to `OCP.collections`, and the
  converters use `TopoDS.Face`, which both versions provide. CI now installs OCP 8; the full
  backend suite passes with both.

### Releases
- **Clean-machine checks:** `scripts/check_package.py` unpacks each archive into an empty
  folder, verifies the checksum and every manifest hash, starts the packaged service with a
  fresh user-data folder, solves the pendulum and a featured 3D study with the bundled MBDyn,
  and runs the desktop self-check. The release workflow runs it on fresh Ubuntu 24.04,
  macOS 14 and Windows runners and publishes only when every package passes. A `dry_run`
  input builds and checks without publishing.

### Fixes
- **Self-contained solver bundles.** The first clean-machine run showed that the MBDyn bundled
  in the 0.3–0.5 Linux and macOS archives only ran where the build machine's libraries were
  installed: Linux needed `liblapack3`, and macOS needed Homebrew GCC for `libgcc_s`, which the
  Fortran runtime loads through `@rpath`. `scripts/bundle_solver.sh` now bundles every
  library outside the C/C++ runtime (Linux) or the operating system (macOS), resolves `@rpath`
  references, and fails the build if any reference still points at the build machine. On those
  older releases, install `liblapack3` (Linux) or `brew install gcc` (macOS), or configure MBDyn
  as in `docs/solver.md`.

### Tests
- `RecoveryStore` unit tests (atomic replacement, interrupted writes, size limit, damaged
  snapshots, retention) and `tests/native-recovery-ui.mjs` (recover, discard, autosave
  timing). Desktop bridge mocks answer the new operations; `oversized-save-ui` counts the
  full-resolution plot's CSV read.

## 0.5.0 — Interaction: CAD feature picking

### Pre-processing
- The STEP converter records each face's **analytic geometry** with its triangle range:
  cylinders (axis, centre, radius, length) and planes (point, outward normal), in metres.
- **Place from CAD feature…** in the joint inspector: hover previews a face's axis and bore
  circle with a label such as *Cylinder Ø55.0 mm · axis −x*; a click puts both joint ends on
  the feature, so anchors coincide and revolute, cylindrical and prismatic axes agree by
  construction.
- **Drag-to-edit:** drag a joint symbol in the 3D view and drop it on a face; it snaps to
  that face's axis or plane. Dropping elsewhere leaves the joint unchanged; Esc cancels.
- **Named frames from CAD:** a frame's origin goes on the picked feature with local +Z along
  its axis or normal; linked joint ends follow.
- **Measure** (ruler button or M): distance, x/y/z components and axis angle between two
  picked features.
- Undo and Redo keep the selected entity when it still exists.

### Fixes
- Phone-width layout: the app bar collapses to icons and the view toolbar wraps, so no
  control sits off-screen and the page no longer scrolls sideways at 390 px.
- The run button keeps an accessible name when its label is hidden.

### Tests
- `tests/cad-features.test.mjs` covers face lookup, CAD-to-body placement, joint and frame
  placement and measurement; `tests/cad-picking-ui.mjs` picks, drags, measures and places a
  frame on the wheel-end hub in the browser. `backend/test_step_geometry.py` checks the
  reported cylinder and plane geometry. The UI smoke test is current with the example
  gallery and guide again and passes in full.

## 0.4.0 — Post-processing II

- Plots and statistics read the **full-resolution** solver CSV in the background: every
  integration step, with min/max-per-pixel decimation so short peaks are never lost, the
  time of each peak, and time-weighted RMS.
- **Pinned traces** overlay several bodies, joints or quantities with the same unit.
- **Compare runs**: pin a solution, change the model, run again and see both responses.
- **SVG and PNG export** of the plot with theme colours resolved.
- Hover readouts use each series' own resolution, so they report values between displayed
  samples.
- `tests/post-processing-ui.mjs` checks full-resolution statistics, pinned traces, run
  comparison and plot export in the browser.

## 0.3.0 — Rotary drives and inverse dynamics

### Modelling
- Revolute joints accept a **rotary drive**: a motor law (target speed with a linear speed
  ramp) or an oscillation, both starting at rest. MBDyn imposes the hinge angle through a
  total joint and reports the torque the drive must supply.
- Drive parameters are edited in the joint inspector; validation checks the starting state,
  ramp resolution and per-step rotation, and the constraint analysis counts the extra row.

### Results
- New result quantities per driven joint: measured and commanded angle (unwrapped), speed,
  motor torque, power, and total drive work; all in the CSV export.

### Studies
- **Robot arm inverse dynamics**: turret, shoulder and elbow driven together; the study is
  verified by drive work equalling the change in mechanical energy.
- `backend/verify_rotary_drive.py` checks motor torque against I·α − m·g·l·cos θ.
- `tests/rotary-drive-ui.mjs` exercises the drive editor, a real MBDyn run, torque and angle
  plots, the CSV columns and the stale-result state.
- Robot-arm demo recording on the homepage.

### Fixes
- macOS release archives can bundle MBDyn again: the bundling script no longer stops when a
  runtime library has no Homebrew dependencies.

## 0.2.0 — Professional workspaces, featured studies and desktop releases

### Interface
- Three task-focused workspaces — **Pre-processing**, **Solve** and **Post-processing** —
  replace the single crowded screen; each shows only the panels for its stage.
- One compact app bar with the workspace switcher; toast notifications instead of a banner;
  an opt-in guided tour instead of an automatic one.
- Solve workspace: study settings with step budget, pre-run checklist (inputs, solver, steps,
  Grübler mobility, result state), linked issues, deck inspection and a solver console.
- Post-processing: interactive plot with nice axes, hover readout, click/drag scrubbing and
  per-channel value/min/max/range/RMS; frame stepping, 0.1×–2× speed and loop playback;
  angular velocity in body axes; motion trails with trailing window and body filter; follow
  camera; presentation mode (**P**); measurement tools grouped in the results panel.
- Keyboard shortcuts: 1/2/3 workspaces, F5 run, Space play, ←/→ frames, Home/End, F fit,
  P present, Ctrl+S save, Ctrl+O open.
- Per-body colours for attached CAD, contact planes drawn where the solver places them,
  and a ground grid placed under the motion envelope.
- Joint symbols (revolute, cylindrical, prismatic, spherical, universal, weld) at their
  anchors and axes, coil and strut symbols between force anchors and axis triads for named
  frames, drawn over the CAD and selectable; hover highlighting between the 3D view and the
  model tree with a tooltip.
- **New 3D assembly** command, and a guided tour that builds an automotive wheel-end drop
  test from its STEP parts across the three workspaces, with actions that start the
  assembly, load the parts and open the finished study.
- Examples gallery with sections and a **Featured studies** group that opens complete
  projects (geometry, camera, plot and trail presets) in one click.
- Projects now save the camera, selection, plot and trail settings, including browser exports.

### Modelling diagnostics
- Constraint-rank analysis of 3D assemblies before the solver runs: true mobility at the
  initial configuration and each redundant constraint named by joint and component, shown in
  the Solve checklist and appended to MBDyn failures (`docs/constraint-diagnostics.md`,
  verified by `backend/verify_constraint_analysis.py`).

### Industry demos
- Industry-first homepage: an end-to-end recording that builds the wheel-end drop test from
  the original STEP files through solve and post-processing, and clips of the quarter-car,
  gear drop test, aircraft nose gear, oleo strut fixture, wheel-end drop test and
  slider-crank engine.
- The aircraft nose gear runs an 80 mm shock-strut stroke; the oleo strut fixture and a new
  **Wheel-end drop test** featured study open with framed views and plots. Featured
  catalog entries can carry a documented overlay so verified project files stay unchanged.
- `verify_featured_studies.py` checks the nose gear against two-circle linkage geometry,
  the oleo gas pressure against the polytropic law and the wheel-end drop against free fall
  and the contact energy balance.

### Studies
- Six new MBDyn studies with measured STEP mass properties: double-wishbone quarter-car,
  oleo-pneumatic gear drop test, slider-crank engine run-up, gyroscopic top, tumbling
  T-handle and chaotic double pendulums (`examples/studies/build.py`).
- `backend/verify_featured_studies.py` checks each against independent physics;
  `backend/test_featured_studies.py` guards the saved projects.
- New 30 fps demo recordings captured from real solver output in presentation mode.

### Desktop and distribution
- The native host now builds and runs on Linux (WebKitGTK) and macOS as well as Windows,
  with per-platform user-data folders and `python3` on Unix.
- Release archives for Linux, macOS and Windows, assembled by `scripts/package_release.py`
  with SHA-256 manifests; Linux (and macOS when its CI build succeeds) bundle MBDyn 1.7.3,
  which the backend detects automatically at `solver/bin/mbdyn`.
- GitHub Actions: CI (MBDyn build, backend suite, study verification, native tests on three
  operating systems) and a tag-triggered release workflow that attaches the MBDyn source.

### AI assistant
- The proposal review lists every changed field with its old and new value, so changes a
  request did not ask for are visible before applying.
- After an accepted edit the language model reads back the validation result rather than the
  whole model, saving minutes per request on CPU-only machines.
- Optional `timeoutSeconds` in the assistant settings for CPU-only machines.
- Demo recording of the assistant adding a wheel bearing, tyre contact and drop conditions with
  a real local `qwen3.5:4b` model.

### Fixes
- STEP import documents the supported OpenCascade runtime (`cadquery-ocp` 7.9; 8.x removed
  APIs the importer uses) and pins it in `requirements.txt`.
- `backend/build_solver.sh` works with configurable compilers and without `sha256sum`.

## 0.1.0 — First public preview

Initial release: planar and spatial rigid-body editors, STEP import and attachment,
MBDyn deck generation and execution, result playback and plots, Windows desktop host,
industry-inspired examples and local AI assistant.
