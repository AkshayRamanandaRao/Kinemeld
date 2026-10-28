# First study: STEP parts, bodies and revolute joints

Kinemeld has an optional guided tour. It opens on first use; choose **Don't
show automatically** to turn that off. Use **Tour** in the application header to
open it again. The tour explains the controls without changing your project.

## Load a matched solid and mechanism

1. Start the Windows app, then open **STEP parts** → **Load moving STEP pendulum**.
   This loads a STEP solid and a matching planar rigid body connected to ground.
2. In **MODEL BROWSER**, select **Upper Link**. The Properties panel shows mass,
   principal moments of inertia, the initial centre-of-mass position, rotation,
   linear velocity and angular velocity. Gravity and study duration/time step
   are separate values. Units are metres, kilograms and seconds; initial angle is
   in degrees.
3. To use your own CAD instead, open **STEP parts** → **Import STEP files** and
   choose `.step` or `.stp` files. The application's normal CAD-import picker
   accepts STEP only. File geometry is not an MBDyn body until you define a body
   and attach a part; imported geometry does not assign mass or inertia.

## Add and inspect a joint

1. Select **Upper Link** in the model browser. In **Build assembly**, confirm
   **Attach next body to** is Upper Link and choose **Revolute hinge** and select **Add body + revolute hinge**. Alternatively choose **Prismatic slider** for a guided translating body.
   The new body and its hinge appear in the tree. The application positions the
   initial anchors consistently for this added link.
2. Select the new hinge under **JOINTS**. Its parent can be changed and the
   parent and child anchor coordinates edited. These are offsets in their
   respective body frames; a ground anchor is in global coordinates. Both
   anchor positions and their initial velocities must agree. If you edit one
   without the matching other, **Validate model** reports the mismatch; select
   the issue to find the relevant property.
3. Select the new body to enter its mass and principal moments, pose and initial
   velocity. Use known engineering properties and SI units; these are not
   derived automatically from the CAD file. Undo and redo restore edits.

## Attach CAD, validate and run

1. Open **STEP parts**, choose an imported part and choose the corresponding
   planar body under **Attach to planar body**. Select **Apply attachment**.
   The STEP coordinates are treated as the model's global initial frame. Check
   registration and dimensions yourself; an unattached part stays fixed.
2. Select **Validate model**. Correct all errors; warnings also need engineering
   review. **Inspect MBDyn deck** lets you inspect the generated solver input.
3. Select **Run simulation**. Use the play controls or time slider to inspect
   actual MBDyn motion and the response selector to plot quantities. Save the
   project to retain its STEP sources, body bindings, model and results. Export
   CSV when you need full-resolution numerical data.

The editable graph currently supports rigid bodies, revolute hinges and
prismatic sliders in the XZ plane, gravity, linear axial springs and dampers,
constant global forces and torques at body centers, and initial conditions. It does not support general 3D joints, closed loops,
contact, flexible bodies, CAD-derived mass properties or automatic joint extraction. The double-wishbone STEP files
are an illustrative visual reference, not a validated suspension analysis.

## Uniform solids and spring-dampers

Select a planar body and expand **Calculate mass and inertia from a uniform
solid**. Choose brick, cylinder, sphere or ellipsoid, enter SI dimensions and
density, then either apply the computed mass/inertia or create and attach a
matching STEP solid. These assume a uniform solid centred on the body centre of
mass and aligned to its principal axes. Applying replaces that body's values;
other attached geometry is not included.

Use **Add spring / damper** for a linear axial connection. Select the element
in the model tree to choose its two endpoints, local anchors, rest length,
stiffness and damping. The run plots and CSV reconstruct spring tension from
native body motion. See [spring-damper modeling](planar-springs.md) and
[prismatic sliders](planar-prismatic.md) for frames, assumptions and checks.

Use **Add external force / torque** to apply constant global X/Z force at a body's center of mass and constant +Y torque. [Load frames, power and limits](planar-loads.md) are documented separately.
