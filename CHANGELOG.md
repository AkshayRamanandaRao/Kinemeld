# Changelog

All notable changes to Kinemeld are recorded here. Versions follow
[semantic versioning](https://semver.org/) while the project is in preview (0.x).

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
- Examples gallery with sections and a **Featured studies** group that opens complete
  projects (geometry, camera, plot and trail presets) in one click.
- Projects now save the camera, selection, plot and trail settings, including browser exports.

### Modelling diagnostics
- Constraint-rank analysis of 3D assemblies before the solver runs: true mobility at the
  initial configuration and each redundant constraint named by joint and component, shown in
  the Solve checklist and appended to MBDyn failures (`docs/constraint-diagnostics.md`,
  verified by `backend/verify_constraint_analysis.py`).

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

### Fixes
- STEP import documents the supported OpenCascade runtime (`cadquery-ocp` 7.9; 8.x removed
  APIs the importer uses) and pins it in `requirements.txt`.
- `backend/build_solver.sh` works with configurable compilers and without `sha256sum`.

## 0.1.0 — First public preview

Initial release: planar and spatial rigid-body editors, STEP import and attachment,
MBDyn deck generation and execution, result playback and plots, Windows desktop host,
industry-inspired examples and local AI assistant.
