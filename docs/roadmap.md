# Kinemeld development roadmap

Kinemeld is a preview multibody workbench built around a separately configured
MBDyn solver. Items below describe intended work, not commitments or delivery
 dates. Every feature should include an example, user documentation, failure
checks, and validation against the solver and an independent reference where
appropriate.

## Current foundation

- Editable planar and spatial rigid bodies, selected joints and closed loops,
  forces, springs, dampers, contact and selected prescribed motion.
- Original STEP import, body attachments, explicit-density mass properties,
  project save/reopen, MBDyn deck inspection, simulation and result playback.
- Local assistant proposals for a bounded set of supported model edits.
- Worked suspension, wheel-end, gear and strut demonstrations with documented
  assumptions. These are inferred teaching studies, not validated hardware.

## Next priorities

1. **Reliability and publication:** protect edits during asynchronous CAD and
   project operations, exercise save/open and recovery, qualify native Windows
   dialogs, produce clean-machine builds, and finish dependency and license audits.
2. **Rigid-body modeling:** expand 3D joint and actuation coverage, including
   prescribed rotary motion; improve diagnostics for redundant constraints,
   initial conditions and singular assemblies. Verify moving reference frames,
   real solver output and STEP playback.
3. **Postprocessing:** derive point and wheel measurements from full-resolution
   solver data, retain units, frames and result provenance, and test peaks between
   displayed samples. Improve plots, result comparison and export.
4. **Engineering examples:** extend suspension and landing-gear studies only
   with traceable geometry, hardpoints, material data and loading. Add independent
   checks, convergence evidence and comparison with measurements where available.
5. **Interaction and assistance:** make joints and reference frames easier to
   place and inspect, improve selection and diagnostics, and extend AI actions
   only where the underlying physical and solver behavior is verified.

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
redistributed dependencies and licenses. The local Windows package does not
bundle MBDyn or the CAD runtime.
