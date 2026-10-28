# Multibody analysis workflow

The workbench organizes a study into **Model → Validate → Simulate → Results**. The physical model is exported to the configured MBDyn solver; displayed geometry and results carry separate meanings.

| Stage | User question | Workbench responsibility |
| --- | --- | --- |
| Model | What moves and what connects it? | Define bodies, ground, joints, loads and their units. Import STEP geometry and associate occurrences with authored bodies where needed. |
| Validate | Are the inputs internally consistent? | Identify invalid fields and unsupported combinations without silently replacing values. Constraint validation does not guarantee a successful dynamic solve. |
| Simulate | Which inputs produced the run? | Generate the solver deck, execute the configured MBDyn process, and retain the input snapshot, output and diagnostics. |
| Results | What happened over time? | Display and animate recorded samples, inspect available signals and export data. Mark results stale when the model no longer matches the run. |

A STEP solid is a visual representation until an explicit mass calculation or physical model assigns its properties. CAD shape alone does not create a joint, force, contact model or material specification.

## Practical checks

1. Open a documented example and inspect the body list, assumptions and local frames.
2. Check STEP attachments, mass and inertia, joint anchors, motion inputs and initial conditions.
3. Validate and run MBDyn, then inspect the log and units of selected result channels.
4. Compare key output against an analytical or independently measured reference and refine the time step.
5. Save the project, reopen it and verify the model, geometry associations and result provenance.

For an engineering study, obtain reliable physical dimensions, material properties, loads, boundary conditions and validation data. A successful solver run only establishes the numerical behavior of the authored model; it does not certify the represented hardware.

See the [spatial assembly guide](spatial-assembly.md), [STEP guide](step-geometry.md), [solver guide](solver.md), [verification guide](verification.md) and [roadmap](roadmap.md).
