# Changelog

All notable changes to Kinemeld are recorded here. Versions follow
[semantic versioning](https://semver.org/) while the project is in preview (0.x).

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
