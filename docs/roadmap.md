# Kinemeld development roadmap

Kinemeld is a preview multibody workbench built around a separately configured
MBDyn solver. Items below describe intended work, not commitments or delivery
dates. Every feature should include an example, user documentation, failure
checks, and validation against the solver and an independent reference where
appropriate.

## Current foundation (1.2)

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
- Regularised Coulomb friction on sphere–plane contacts, with friction force, slip and
  dissipated energy in the results and a landing-gear spin-up drag study.
- STEP parts added one file at a time, hole rims read from CAD that writes them as arcs, and
  an end-to-end showcase that builds an aircraft nose gear from its eleven STEP parts.

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
10. **1.1 — Contact friction (released):** regularised Coulomb friction for sphere–plane
    contact, verified against rolling-ball and sliding-block solutions, with a landing-gear
    spin-up drag study.
11. **1.2 — CAD part by part (released):** STEP files added one at a time, hole rims read
    from CAD that writes them as arcs, model names, and an end-to-end showcase on an
    aircraft nose gear built from its eleven STEP parts.

## Execution priorities

Work proceeds through the remaining items with a separate implementation and
verification record for each. On 1 November 2026 the project owner authorized
continuing across the roadmap without approval between items. Report changes,
evidence and remaining limits as work progresses. Released capabilities above
are not pending work. Robotics is the primary use case; the automotive and
nose-gear studies remain useful independent validation cases.

| Priority | Item | Status | Completion checks |
| --- | --- | --- | --- |
| P0 | Refresh the aircraft nose-gear recordings | Complete (1 November 2026) | Clean titles and captions; engineering scope retained in the study guide. Both the featured clip and end-to-end workflow were recorded again; matching MP4/GIF pairs decoded and representative frames inspected. See [verification](verification.md#recording-refresh-1-november-2026). |
| P1 | Preserve edits during asynchronous CAD and project operations | Complete (1 November 2026) | Delayed STEP replacement/append, generated solids, example/project loads, startup restore and autosave preserve newer edits, including typed input before blur. The integrated project-safety suite passes; negative controls reproduce the original failures. See [verification](verification.md#asynchronous-edit-preservation-1-november-2026). |
| P2 | Qualify native project dialogs | Windows complete (1 November 2026); macOS/Linux pending | Twelve automated GUI cases pass against an extracted Windows app using real WebView2/native dialogs: Save/Open, cancellation, overwrite refusal, backups, conflicts, dirty documents, crash recovery and startup/shutdown. Reopened and recovered files retain model, 11 CAD bindings, 501 result samples and full CSV. See [verification](verification.md#windows-native-gui-verification-1-november-2026). |
| P3 | Complete bundled dependency provenance and notices | Complete — audit and unpublished candidates (1 November 2026) | Exact platform inventories, full notices, runtime sources/patches and filtered MBDyn source; 47 audit checks pass. All three candidate packages pass fresh-runner source/hash/service/solver/native checks. Published v1.2.1 assets remain unchanged; historical Y12, macOS SDK and optional private-runtime rights limits are recorded in the [audit](dependency-audit.md). |
| P4 | Strengthen engineering examples, starting with nose gear | Numerical/provenance checks complete (1 November 2026) | Four hash-bound engineering records; 16 real solver runs with three timestep levels and parameter variants; independent robot kinematics/torques and drop/suspension references. Fifteen body mass/COM/tensors match the stated assumptions for 25 CAD occurrences. See [engineering verification](engineering-example-verification.md). Material calibration and hardware correlation remain outside these numerical checks. |
| P5 | Pick cones and tori from CAD | Pending | Cover analytic feature extraction, transformed occurrences, viewport selection, joint/frame placement and project save/reopen with geometric and interface checks. |
| P6 | Extend assistant actions over verified workflows | Pending | Support only capabilities verified above; check proposal review, model validation, Undo and rejection of stale proposals. |

## Longer-term work

After P6, the robotics-focused order is: (1) true stiction and broader contact,
(2) actuator controls and co-simulation, (3) flexible links, and (4) design studies
and optimization. Aerodynamics is outside the active product scope. Each feature
needs its own model contract, editor, solver integration and independent numerical
benchmarks. A solver capability is not an application feature until the complete
workflow has been implemented and tested. Hardware validation still requires
measured data; it cannot be replaced by simulation checks.

## Verification and distribution

The current integration has been exercised with MBDyn 1.7.3 and selected
examples. Other versions, general models, engineering accuracy, production use
and safety-critical qualification remain unverified. Every release package is unpacked
and checked on fresh Linux, macOS and Windows runners before publication (file hashes,
the packaged service, real MBDyn runs and the desktop self-check). The Windows native
dialog suite now passes on a configured development machine; macOS/Linux dialog
tests and clean-machine GUI qualification remain open. P3 inventories and notices
are verified for the standard candidate packages; the audit records unresolved
upstream rights and historical-release limits separately.
Newly assembled solver packages require exact corresponding-source companions,
including runtime sources and distribution patches. Standard public packages
include neither Python nor the CAD runtime; the optional private runtime remains
unqualified for redistribution. P3's candidates were verified without publishing.
