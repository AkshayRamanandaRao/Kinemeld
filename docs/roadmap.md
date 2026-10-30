# Kinemeld development roadmap

Kinemeld is a preview multibody workbench built around a separately configured
MBDyn solver. Items below describe intended work, not commitments or delivery
 dates. Every feature should include an example, user documentation, failure
checks, and validation against the solver and an independent reference where
appropriate.

## Current foundation (1.0)

- Editable planar and spatial rigid bodies, selected joints and closed loops,
  forces, springs, dampers, oleo struts, contact and selected prescribed motion.
- Original STEP import, body attachments, explicit-density mass properties,
  project save/reopen, MBDyn deck inspection, simulation and result playback.
- Pre-processing, Solve and Post-processing workspaces with interactive plots,
  statistics, motion trails, follow camera and presentation mode.
- Constraint-rank mobility and named redundant constraints before the solver runs.
- Joint, force-element and frame symbols in the 3D view; hover highlighting between the
  view and the model tree.
- Industry-inspired demos, including an end-to-end STEP-to-results recording, and a guided
  tour that builds a wheel-end drop test.
- Six featured studies verified against independent physics, plus the earlier
  suspension, wheel-end, gear and strut demonstrations with documented assumptions.
- Desktop builds for Linux, macOS and Windows; CI and tagged releases on GitHub.
- Rotary drives on revolute joints with motor torque, power and work from the solver.
- Full-resolution plots and statistics, pinned traces, run comparison and SVG/PNG plot export.
- Joint anchors, joint axes and named frames placed by picking or dragging onto analytic CAD
  faces (cylinders and planes), and in-view distance and angle measurement.
- STEP import with `cadquery-ocp` 7.9 or 8; crash-safe autosave and recovery in the desktop
  app; every release package checked on fresh Linux, macOS and Windows machines.
- Parameter studies: one input solved for several values plus its baseline, every case on
  one plot, and a table of peaks, RMS and final values with CSV export.
- Featured parameter studies on the wheel-end and landing-gear drop tests, verified case by
  case against independent physics and shown in the demo set and guided tour.
- Hole rims picked as well as faces, measurement at the animated pose, and joint symbols
  dragged along or across their axis in 1 mm steps.
- MBDyn bundled on Linux, macOS and Windows; a documented project format with a 1.x
  compatibility promise.

## Release plan

Each step ships as its own release with an example, documentation and solver evidence.

1. **0.2 — Workspaces and studies (released):** Pre-processing, Solve and
   Post-processing workspaces; six verified featured studies; constraint-rank mobility
   and redundancy diagnostics; desktop builds for Linux, macOS and Windows.
2. **0.3 — Actuation (released):** prescribed rotary motion for revolute joints (motor speed ramp
   and oscillation) with motor torque, power and work from the solver, and an
   inverse-dynamics robot-arm study.
3. **0.4 — Post-processing II (released):** statistics and plots from the full-resolution solver
   output with peak-preserving decimation, overlays of several quantities and bodies,
   comparison with a pinned earlier run, and SVG/PNG plot export.
4. **0.5 — Interaction (released):** place joint anchors and frames directly in the 3D view
   by picking CAD features (hole axes, cylinder centres, faces), drag joint symbols onto
   faces with snapping, and in-view distance and angle measurement.
5. **0.6 — Reliability and CAD (released):** support for the current OpenCascade runtime
   (`cadquery-ocp` 8), crash-safe autosave and recovery in the desktop app, and
   clean-machine installation checks for every platform package.
6. **0.7 — Parameter studies (released):** sweep one model input (a stiffness, a damping, a
   mass, a drop velocity) over a list of values, solve every case with MBDyn, overlay the
   responses and tabulate key results such as peak force, with CSV export.
7. **0.8 — Studies in the demo set (released):** featured parameter studies on the
   industry-inspired models — tyre stiffness against wheel-end peak load and sink speed
   against landing-gear tyre load — each opening with its study, checked case by case
   against independent physics and recorded for the homepage.
8. **0.9 — Interaction II (released):** pick circular edges (hole rims) as well as faces,
   measure at the animated pose in Post-processing, and drag joint anchors along an axis or
   within a plane without a target face.
9. **1.0 — Self-contained everywhere (released):** a Windows package with a bundled MBDyn
   built in CI, so no platform needs WSL or a separate solver install, checked like the
   others on a clean machine; a stated project-format compatibility promise from 1.0 on.
10. **1.1 — Contact friction:** regularised Coulomb friction for sphere–plane contact, with
    stick–slip verified against an independent sliding-block solution and a braking or
    skidding wheel study.

## Further priorities

- **Reliability and publication:** protect edits during asynchronous CAD and
  project operations, qualify native dialogs,
  and finish dependency and license audits for every bundled component.
- **Engineering examples:** extend suspension and landing-gear studies only
  with traceable geometry, hardpoints, material data and loading. Add independent
  checks, convergence evidence and comparison with measurements where available.
- **Interaction and assistance:** pick cones and tori; extend AI actions only where the
  underlying physical and solver behavior is verified.

## Longer-term work

Broader surface contact and friction, flexible bodies, controls and co-simulation,
aerodynamics, design studies and optimization each need their own model contract,
editor, solver integration and numerical benchmarks. A solver capability is not
an application feature until the complete workflow has been implemented and tested.

## Verification and distribution

The current integration has been exercised with MBDyn 1.7.3 and selected
examples. Other versions, general models, engineering accuracy, production use
and safety-critical qualification remain unverified. Every release package is unpacked
and checked on fresh Linux, macOS and Windows runners before publication (file hashes,
the packaged service, real MBDyn runs and the desktop self-check); native dialog
tests and a complete review of redistributed dependencies and licenses remain open.
Release archives bundle MBDyn 1.7.3 on Linux, macOS and Windows with the corresponding source
attached; no package bundles Python or the CAD runtime.
