# Multibody workbench capability map

This document describes product boundaries and verification priorities for the standalone workbench. A supported MBDyn element does not automatically mean the editor can author it or that a model has been validated for engineering decisions. The [feature coverage](multibody-feature-map.md) and [roadmap](roadmap.md) provide current details.

## Current foundations

The workbench provides editable planar and spatial rigid-body models, selected joints and loads, STEP visualization and explicit mass-property calculations, project persistence, solver execution, playback and selected result measurements. Solver integration and model families are described in the [solver guide](solver.md), [spatial assembly guide](spatial-assembly.md), and [verification guide](verification.md). Pinned source studies retain their own provenance and license in the [source-study catalog](open-source-examples.md).

Source-backed suspension and landing-gear examples use explicit idealizations. Their CAD and solver trajectories do not establish an OEM design, measured forces, manufacturing fit or certification. See the [suspension study](open-suspension.md) and [aircraft gear study](aircraft-nose-kinematics.md).

## Development priorities

| Area | Remaining work | Required evidence |
| --- | --- | --- |
| Geometry and assemblies | Reliable STEP occurrence identities, transforms, body association, units and explicit mass properties. | Source identity, geometry changes, mass/inertia reference cases, project round trips, undo and failure recovery. |
| Joints and kinematics | Expand supported 3D constraints, frame editing, loop closure, singularity diagnostics and initialization. | Known mechanisms, moving parent frames, valid and invalid initial states, independent reference solutions and solver convergence. |
| Motion and loads | Broaden typed time laws, applied efforts, springs, dampers and constitutive elements. | Unit and frame semantics, initial-state consistency, analytical trajectories, signs and energy/work checks. |
| Contact | Add carefully scoped friction and additional geometric pairs. | Approach and separation, no tensile contact forces, penetration, dissipation, convergence and physically meaningful reference cases. Visual geometry alone is not a contact model. |
| Solver and jobs | Expand solver-version support, diagnostics, cancellation, initialization and study types. | Real solver runs, complete output checks, failure retention, lifecycle cleanup and repeatability. |
| Postprocessing | Full-resolution measurements and exports, comparison, reports and richer typed quantities. | Units, reference frames, provenance, stale-result behavior, data completeness and independent numerical checks. |
| Controls and flexibility | Selected feedback, flexible structures and coupling interfaces. | Validated servo and beam or reduced-order reference cases, initialization, timing, interface mappings and convergence. |
| Industry workflows | Detailed component libraries and calibrated datasets. | Lawful source assets, measured material and load inputs, model assumptions and comparison against suitable experimental or independent reference data. |
| AI assistance | Extend typed authoring only as the underlying model features become reliable. | Explicit proposal review, validation, unsupported-request handling, provider failures, real endpoint connectivity and solver-backed tests. |
| Release quality | Reproducible installation, dependency notices and support on target machines. | Clean-machine installation, native save/open/dialog workflows, security and accessibility checks, and complete distribution-license review. |

## Delivery principles

Use a versioned mechanical model with stable body, joint and load identifiers, explicit frames and units, physically consistent inertia, initial conditions, and preserved solver provenance. Geometry edits should invalidate dependent mesh, mass, joint assumptions and results. A visual CAD constraint is not automatically a verified mechanical joint.

Each new capability needs input validation, a reproducible example, user guidance with an application screenshot, save/reopen, failure-path coverage, and real solver checks appropriate to its behavior. A numerical test of one idealized mechanism does not establish industrial qualification.
