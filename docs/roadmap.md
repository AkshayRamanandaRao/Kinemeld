# Kinemeld development roadmap

Kinemeld is a preview multibody workbench built around a separately configured
MBDyn solver. Items below describe intended work, not commitments or delivery
 dates. Every feature should include an example, user documentation, failure
checks, and validation against the solver and an independent reference where
appropriate.

## Current foundation (0.2)

- Editable planar and spatial rigid bodies, selected joints and closed loops,
  forces, springs, dampers, oleo struts, contact and selected prescribed motion.
- Original STEP import, body attachments, explicit-density mass properties,
  project save/reopen, MBDyn deck inspection, simulation and result playback.
- Pre-processing, Solve and Post-processing workspaces with interactive plots,
  statistics, motion trails, follow camera and presentation mode.
- Constraint-rank mobility and named redundant constraints before the solver runs.
- Six featured studies verified against independent physics, plus the earlier
  suspension, wheel-end, gear and strut demonstrations with documented assumptions.
- Desktop builds for Linux, macOS and Windows; CI and tagged releases on GitHub.

## Release plan

Each step ships as its own release with an example, documentation and solver evidence.

1. **0.2 — Workspaces and studies (released):** Pre-processing, Solve and
   Post-processing workspaces; six verified featured studies; constraint-rank mobility
   and redundancy diagnostics; desktop builds for Linux, macOS and Windows.
2. **0.3 — Actuation:** prescribed rotary motion for revolute joints (motor speed ramp
   and oscillation) with motor torque, power and work from the solver, and an
   inverse-dynamics robot-arm study.
3. **0.4 — Post-processing II:** statistics and plots from the full-resolution solver
   output with peak-preserving decimation, overlays of several quantities and bodies,
   comparison with a pinned earlier run, and SVG/PNG plot export.
4. **0.5 — Interaction:** joint and frame glyphs in the 3D view (axes, anchors, force
   element lines), hover highlighting between tree, view and properties, and direct
   selection of joints and force elements in the viewport.
5. **0.6 — Reliability and CAD:** support for the current OpenCascade runtime
   (`cadquery-ocp` 8), crash-safe autosave and recovery in the desktop app, and
   clean-machine installation checks for every platform package.

## Further priorities

- **Reliability and publication:** protect edits during asynchronous CAD and
  project operations, exercise save/open and recovery, qualify native dialogs,
  and finish dependency and license audits for every bundled component.
- **Engineering examples:** extend suspension and landing-gear studies only
  with traceable geometry, hardpoints, material data and loading. Add independent
  checks, convergence evidence and comparison with measurements where available.
- **Interaction and assistance:** extend AI actions only where the underlying
  physical and solver behavior is verified.

## Longer-term work

Broader surface contact and friction, flexible bodies, controls and co-simulation,
aerodynamics, design studies and optimization each need their own model contract,
editor, solver integration and numerical benchmarks. A solver capability is not
an application feature until the complete workflow has been implemented and tested.

## Verification and distribution

The current integration has been exercised with MBDyn 1.7.3 and selected
examples. Other versions, general models, engineering accuracy, production use
and safety-critical qualification remain unverified. A public binary needs a
clean-machine installation check, native dialog tests and a complete review of
redistributed dependencies and licenses. Release archives bundle MBDyn 1.7.3 on
Linux (and macOS when its CI build succeeds) with the corresponding source attached;
no package bundles Python or the CAD runtime.
