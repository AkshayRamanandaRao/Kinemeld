# Multibody capabilities: coverage and roadmap

This document maps independently specified multibody capabilities to the current workbench and remaining verification. Unless marked current, a feature is planned or being investigated. Solver behavior depends on the configured MBDyn version; the [1.7.3 input manual](https://www.mbdyn.org/userfiles/documents/mbdyn-input-1.7.3.pdf) is the baseline for the documented checks.

The reviewed baseline includes STEP display and manual planar body attachment;
an editable XZ rigid-body graph with revolute and prismatic joints, linear
spring-dampers, gravity, and initial states; real MBDyn results and CSV; six specific template studies including
suspension and landing gear; and three pinned read-only upstream studies. The 3D editor also supports rigid bodies, free bodies, revolute/prismatic/cylindrical/universal/spherical/weld constraints and closed loops with consistent initial states; actual MBDyn detects incompatible or redundant systems. Local position and instantaneous velocity kinematics solvers adjust selected body coordinates or origin velocities to satisfy joint constraints and targets; they do not prove global uniqueness or replace an MBDyn run. Spatial bodies accept a body-local centre-of-mass offset and a physically validated symmetric inertia tensor about that centre. The STEP calculator can apply one or combine multiple attached occurrences at a user-selected uniform density. Planar bodies require diagonal inertia in their body axes. An explicit sphere against a fixed plane supports elastic force, optional compression-only damping and optional regularised Coulomb friction; it is not general STEP-surface contact. Solver checks cover representative loops, not all loop geometries. See the [position-solve worked example](kinematics.md), [two-part STEP mass example](step-mass.md), [sphere contact](spatial-sphere-contact.md) and [named frames](reference-frames.md).
## Bodies, geometry and appearance

| Capability | Current Kinemeld behavior | Needed and acceptance evidence |
| --- | --- | --- |
| Geometry and solid shapes | STEP solids are displayed and manually associated with planar or spatial bodies. Uniform bricks, cylinders, spheres, ellipsoids regular polygon extrusions, simple concave polygon extrusions and complete radial-profile revolutions can generate STEP solids at the body pose; profile holes, partial revolutions and a general B-rep editor remain absent. | Specify dimensions and reference frame in SI, generate visible solids and retain editable parameters. Verify per-shape dimensions, orientation and save/reload; distinguish visual and physical geometry. |
| Mass distribution and general inertia | Spatial bodies accept a body-local centre-of-mass offset and a symmetric inertia matrix about that centre in body axes, including signed off-diagonal entries. Positive definiteness and physically realizable principal moments are checked. Planar bodies use diagonal body-frame inertia. Primitive masses can be calculated from explicit dimensions and density. STEP occurrences can be calculated individually or combined across attached parts at one explicit density; spatial bodies retain the calculated COM offset, while planar bodies require the COM at the body origin. Overlapping solids are counted more than once. | Extend material assignments and continue verifying transformations, composite solids and units. The current calculations do not infer density or prove material quality. |
| Appearance and surface graphics | STEP-derived tessellation and simple material colors; underlying original STEP retained. | Per-part appearance and visibility, preserving original CAD, opacity and asset identity. Materials must not silently alter physical mass, contact or inertia. Test persistence, rendering and large-model limits. |
| Rigid bodies and solids | User-authored planar and spatial rigid bodies have explicit mass and inertia; spatial bodies support non-diagonal tensors. A uniform primitive can create matching STEP geometry and inertia. Imported STEP bindings animate graphics and can also be used for an explicit density-based mass calculation. | Distinguish explicit-inertia bodies from density-derived solids; extend independent frames and planar COM offsets. A uniform physical solid is not implied by a rendered STEP solid. |

## Structure, frames and joints

| Capability | Current Kinemeld behavior | Needed and acceptance evidence |
| --- | --- | --- |
| Model graph and state | Validated planar and spatial graphs, generated MBDyn deck, bounded run, and explicit body IDs. Planar and 3D initial poses and velocities are supported state subsets. No public compiled-model API is provided. | General versioned body/marker/connection graph with stable IDs; an explicit compiled snapshot tied to model revision; state snapshots and validation with actionable diagnostics. Test identity, graph edits, stale results, save/reopen, unsupported combinations and lifecycle failures. |
| Frames and rigid transformations | Fixed world frame and body-local planar or 3D anchor offsets, with Euler123 3D pose. Named spatial frames attached to a body or ground store a parent-local translation and Euler123 rotation; users can copy a frame origin and selected axis into a joint, or explicitly link the joint end so frame edits update it. | Expand named rigid frames to additional uses and frame hierarchy. Continue verifying transforms, units and moving-frame behavior. |
| Rotation representations | The planar editor has one angle about +Y; the spatial editor accepts and returns MBDyn Euler123 angles. Other rotation representations and singularity-free editing are not supported. | Typed, explicitly ordered representations with validated normalization, determinant, axis convention, branch continuity and conversions. Verify identity, 90° rotations, composition, equivalent quaternions and near-singularity cases. |
| Revolute joints | Planar and spatial revolute joints are supported and exercised with actual MBDyn trajectories, including a representative spatial loop. | Extend only after frame semantics are specified; test initial anchor and velocity compatibility, axis orientation, reactions and free rotation. |
| Prismatic and weld joints | Planar and spatial prismatic sliders support ground or moving parents; spatial weld constraints are also supported. | Implement typed joint contracts, 3D marker axes and initial consistency. Test analytic slider, fixed relative transform, non-axis-aligned cases and unwanted-DOF rejection. |
| Spherical, cylindrical, universal and additional joints | Spatial spherical, cylindrical and universal joints are supported. The other listed joint types are not present in the editable graph; documented MBDyn primitives alone do not establish app support or equivalence. | Implement one joint at a time with exact allowed DOFs, frame and singularity semantics; independently verify known pose, freedom/constrained motion, reaction and convergence. Verify real solver version before enabling. |
| Advanced joints | Not present in the editable graph. No automatic mapping or compatibility is claimed. | Research each primitive's signs, offsets, constitutive and coupling behavior, then derive and validate a suitable MBDyn representation. Prove representative analytic linkage behavior and singular/failure handling, and provide a clear unsupported diagnostic where no verified equivalent exists. |

A joint is not merely a visual line. Its two local frames, allowed motion,
initial position/velocity, constraint forces and any internal compliance are
part of the contract. The MBDyn manual's total joint constrains specified
relative motion components; individual products' joint semantics must still be
checked and verified rather than inferred from similar names.

## Forces, gravity and joint actuation

| Capability | Current Kinemeld behavior | Needed and acceptance evidence |
| --- | --- | --- |
| Uniform gravity | Downward gravity magnitude is editable for planar bodies, with +Z upward; the spatial editor accepts a world-coordinate gravity vector. | General 3D gravity vector, explicit frame and dimensions. Verify free fall and independent energy balance in several directions. |
| Linear springs and dampers | Linear axial translational spring-dampers can connect ground and planar or spatial bodies, including two-body connections. Native trajectories, reconstructed loads and energy were checked against independent references. Rotational spring-dampers are supported on planar revolute and spatial revolute or cylindrical joints, subject to the principal ±180° deflection limit and timestep limits. | Named body-frame endpoints, rest state, scalar stiffness/damping and documented signs; real MBDyn output must agree with independent analytic cases and time-step convergence. Test zero damping, equilibrium, dissipation, noncoincident offsets and save/reopen. |
| External forces and torques | Planar bodies support constant global X/Z force and +Y torque at the center of mass. Spatial bodies support forces at body-local points and torques in world or follower body axes, with a bounded sinusoidal time scale; reconstructed power and work are available. Sinusoidal torque at a revolute joint is a separate effort input. | Typed forces and moments with point, frame, units and a safe bounded time law. Verify action/reaction, work and energy; test local/global rotation, impulses/continuity, missing bodies and malformed parameters. |
| Joint internal mechanics | Revolute spring/damper is supported for planar and spatial joints and the spatial cylindrical joint supports rotation about its axis; general joint mechanics and friction are absent. | Pair joint-relative displacement/rotation and velocity with appropriate constitutive laws; verify rest pose, axis convention, energy, units and damping sign in real solver runs. |
| Joint effort and motion actuation | Planar and spatial revolute joints and spatial cylindrical joints support sinusoidal torque effort. Spatial prismatic and cylindrical joints also support sinusoidal axial force effort, with reconstructed work; neither effort prescribes motion. The deployment template separately has its own prescribed motion. | Extend typed effort/motion drives with explicit axes and physically valid units; distinguish prescribed motion from force actuation. Verify torque/force directions, angular work, initial consistency, and overconstraint detection. |
| Acceleration actuation | No generic acceleration actuation. Acceleration or position plots in selected templates are not actuation. | Research actual MBDyn drive semantics by version. Test trajectories against analytic motion, conflicts with imposed constraints, and failure diagnostics before claiming support. |

## Simulation, measurements and kinematics

| Capability | Current Kinemeld behavior | Needed and acceptance evidence |
| --- | --- | --- |
| Dynamics results | Successful real runs expose sampled node motions, selected metrics, animation and full-resolution CSV. Spatial joints provide MBDyn constraint reactions on body B in world axes at the B anchor; separate forces are not included. Errors retain diagnostics; samples may be decimated for display. | Expand typed channels with units and reference frames, accelerations, time histories, and run identity. Verify each exported value against native solver output; mark unsupported channels explicitly. |
| Kinematics solver | The spatial position solver accepts selected body coordinates and targets; the velocity solver handles selected body-origin velocities at a fixed pose. Both report residual and rank diagnostics and offer explicit application. Representative mechanisms and subsequent MBDyn runs were checked. They do not enumerate branches, solve accelerations or guarantee global uniqueness. | Expand named-frame targets, acceleration solving, branch selection and additional mechanisms; continue independent numeric and solver-backed checks. A solved position is not proof that dynamics will run. |
| Frame measurements | A point probe measures two body-local or world points, including named-frame origins, with world position, velocity, separation and rate over displayed MBDyn samples. There is no general frame-variable registry. | Frame-relative position/orientation/velocity quantities with explicit units and frame convention; stable IDs and persistence. Verify rigid transform inverse and multi-body moving-frame cases. |
| Joint measurements | No general named joint-variable registry; body trajectory outputs are not equivalent to an exhaustive joint state. | Extract supported joint coordinates from actual solver data with explicit signs and units; compare against known trajectories and joint constraint residuals. |
| Solver variables and targets | Users select body-coordinate or velocity unknowns, provide initial guesses and set targets in the spatial solvers. Position uses metres and Euler123 degrees; velocities use world-frame m/s and rad/s at the body origin. Named frame definitions can be copied or live-linked to joint ends, but there is no general output-variable registry or unit conversion control. | Expand stable variable IDs and roles, dimensional validation, output quantities and unit handling. Test over/under-specified, inconsistent, redundant and singular systems. |
| Viewer lifecycle | Existing viewer and application-window lifecycle are available; no separate viewer API is provided. | Consistent viewer lifecycle without losing the unsaved model; test document close/reopen and cleanup. |

## Standalone scope

STEP/STP import provides geometry, not automatic recovery of physical constraints or materials. The application runs as a standalone multibody workbench using the configured MBDyn solver. A general video exporter remains optional future postprocessing.

## Work order and exit gates

1. **Planar foundations:** general force/torque and additional validated planar
   joints; maintain STEP binding, model persistence, units and actual MBDyn
   output. Require independent numerical reference cases, edge cases and real
   solver-backed UI workflows.
2. **3D bodies and joints:** 3D frame/rotation/inertia model and representative
   weld, revolute, prismatic and spherical mechanisms. Verify frames, joint DOFs,
   forces and constraint residuals with input permutations and near-singular cases.
3. **Graph assembly and kinematics:** closed loops, initial assembly, target and
   output variables, singularity diagnostics and branch selection. Verify a
   four-bar and slider-crank independently; avoid representing a fixed four-bar
   template as a general loop implementation.
4. **Actuation and postprocessing:** typed time laws, effort/drive inputs,
   frame-aware measurements and complete CSV. Retain execution provenance,
   solver failure details and unchanged user-specified values.
5. **Advanced joints and component libraries:** implement only after specific
   solver mappings are verified against the selected version and analytical or
   published reference problems. CAD appearance, limited numerical tests and
   public documentation alone do not establish industrial design qualification.

Each capability must reach validation, serialization, STEP binding where relevant,
UI controls, generated deck, actual MBDyn output, accessible diagnostics, saved
projects, documentation and a meaningful regression. Solver-version support,
not-yet-implemented features, and engineering validation limits must remain visible.
