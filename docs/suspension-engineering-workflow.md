# Engineering workflow for a double-wishbone suspension

This guide separates CAD provenance, multibody idealization, numerical verification and vehicle validation. The supplied [open-source STEP suspension parts](../examples/step-suspension/README.md) are detailed authored CAD, but their publisher does not identify them as an OEM-validated vehicle assembly. Their individual STEP exports do not contain a verified assembly/joint hierarchy. Treat dimensions, material choices, hardpoints and solver results as engineering inputs to be checked, not as manufacturer data.

Start with the [wheel-end torque and drop studies](open-wheel-end.md) and the [inferred closed-loop double-wishbone study](open-suspension.md). They use detailed source parts with explicitly documented idealizations; neither is a validated vehicle suspension.

The application can assemble spatial rigid bodies, joints, spring-dampers, loads, named frames and selected contact idealizations. It can inspect a solved position, solve initial velocity constraints, run MBDyn and measure points. It does not yet provide a complete automated suspension K&C rig, tire force-and-moment model, compliant bushing calibration, general STEP collision or flexible-arm stress analysis. A visual CAD fit alone does not supply those properties.

## 1. Define the vehicle frame and physical interfaces

Record the right-handed vehicle axes and handedness explicitly. For the examples below, use X forward, Y to vehicle left and Z upward. Record whether each component belongs to the left or right corner and define one wheel-axis direction consistently; signs for camber and toe depend on that choice. Do not mix a part's CAD-local axes with the vehicle axes.

A usable hardpoint table should identify, in metres and in a named parent frame:

| Interface | What to establish | Why it matters |
| --- | --- | --- |
| Upper/lower inboard pivots | Two bushing centres on each arm and the line joining each pair | A single ideal revolute joint represents a rigid pivot line only when the two centres are collinear and bushing compliance is intentionally neglected. |
| Upper/lower outer ball joints | Ball-centre locations on the arms and upright | They define the upright's steering axis and constrain the 3D linkage. Verify both sides' local anchors coincide in the initial pose. |
| Steering arm and tie rod | Inner and outer spherical centres, tie-rod length and rack location | Steering compliance and bump steer cannot be inferred from a knuckle image or a model with no tie rod. |
| Wheel bearing and wheel | Bearing axis, wheel-centre location, rotation direction and bearing constraints | A knuckle–hub revolute constraint needs a verified axis and bearing fit. STEP visibility does not make a physical wheel joint. |
| Spring/damper | Chassis and arm attachment centres, free length, preload and orientation | Actual stroke and motion ratio depend on the mounting geometry and linkage position. |
| Tire and road | Loaded radius, contact patch, vertical and lateral tire characteristics, friction and road input | The current sphere-plane penalty law is a normal-contact idealization, not a rolling tire or measured tire force-and-moment model. |

Use known drawings, CAD analytic surfaces or surveyed hardpoints as the evidence for each entry. Where a coordinate is inferred from a CAD surface, retain the measured feature, coordinate system, units and method; do not treat apparent overlap as a verified joint. Treat packaging and kinematic geometry work separately from compliant kinematics and load calibration.

## 2. Turn the CAD assembly into a multibody model

1. Keep the original STEP sources and identify each occurrence. Establish the source units and assembly placements before assigning bodies. For the included authored parts, individual file names, SHA-256 hashes, pinned upstream revision and license are in the [source catalog](../examples/step-suspension/README.md).
2. Attach the arm, upright and hub geometry to their intended bodies. Establish body origins and local named frames at the verified joint centres. If a frame is live-linked to a joint end, changing it also changes that joint's physical anchor/axis; a snapshot must be applied again after editing.
3. Enter mass, body-local centre of mass and full signed inertia about the centre of mass. If using STEP volume integration, document the density assigned to each solid, omitted hardware, shell/overlap assumptions and any off-diagonal terms. A single uniform density is an approximation, not a material certificate.
4. Add joint types and both local anchor/axis definitions from the hardpoint table. A tie rod normally needs its own rigid body and ball-joint connections, while the hub needs a rotational bearing joint. Include only constraints that correspond to the intended physical DOFs; redundant ideal constraints can make MBDyn singular.
5. Specify spring rest length, preload and damping using measured or documented component curves where available. The current linear spring-damper is a local idealization. Compression-only sphere-plane damping is a separate contact law; it is not a hydraulic damper or a tire model.
6. Validate the initial pose and velocity, examine joint residuals and generated deck, then run an actual solver study. The [position/velocity solver](kinematics.md) can help find a consistent initial state; it does not itself establish a load case or prove a unique assembly branch.

## 3. Choose an engineering question and output channels

A kinematics study and a compliance study answer different questions. Common K&C workflows include ride, roll, contact-patch force and steering events. Kinemeld provides some of the building blocks above; it does not yet provide a complete automated K&C rig.

For a wheel-centre point with body-local offset `r`, calculate its world position and velocity as `p = x + Rr` and `v = v_origin + ω × (Rr)`. The [point probe](point-probe.md) reports these values and distance between two points from displayed MBDyn samples. Its CSV may be downsampled; use the ordinary solver CSV for the full-resolution node histories. Probe configuration is session-only.

For a documented wheel-axis unit vector `u` and vehicle-up vector `ez`, wheel-centre vertical travel can be referenced to a specified chassis point. One possible camber convention for an axle initially along +Y is `atan2(u_z, sqrt(u_x² + u_y²))`; one possible toe convention uses the rolling direction `l = u × ez` and `atan2(l_y, l_x)`. The [wheel kinematics measurement](wheel-kinematics.md) calculates these quantities from displayed spatial results relative to a chosen chassis frame. State the sign convention, corner and reference frame with every plot; near a degenerate projection, the angle is undefined. A full axle roll-centre calculation also needs left and right suspension geometry and contact-patch assumptions; a single corner is insufficient.

For the strut, measure length `L` and wheel travel `z` in the chosen configuration. The local motion ratio is `dL/dz`; for a linear spring with small perturbations and fixed geometry, the spring contribution to wheel rate is approximately `k_s (dL/dz)²`. Preload, nonlinear linkage geometry and force direction add terms in a full tangent-stiffness calculation. Do not substitute that approximation for a calibrated K&C result. Suspension geometry and damper asymmetry can interact with tire compliance and ride response, as described in the [SAE quarter-car study](https://saemobilus.sae.org/papers/influence-suspension-kinematics-damper-asymmetry-dynamic-responses-a-vehicle-bump-pothole-excitations-2010-01-1135).

## 4. Verify, then correlate

- Inspect each hardpoint and bearing axis against the source geometry; check both joint-end anchors and joint directions in their parent frames.
- Check positions and velocities at the initial state, constraint residuals throughout motion, force directions and action/reaction where the solver reports them. If the model is singular or overconstrained, fix the modeling assumptions rather than accepting a partial result.
- Repeat with a smaller integration step and compare the actual quantity of interest, including contact force and motion extrema. A valid input or timestep guard alone is not a convergence study.
- Compare the intended measurements with a K&C rig, bench tests, measured inertias, tire data and physical load cases. Document uncertainty, source revision, boundary conditions and correlation error before using the model for a design decision.
- Use an appropriate structural FE workflow for stress, fatigue or buckling of the actual arm; rigid-body motion and a visual STEP surface do not establish structural strength.

The [double-wishbone teaching example](wishbone-3d.md) supplies an executable closed-loop starting point and an independent solver comparison, but it uses original simplified geometry and omits a wheel, steering linkage, tire and compliant bushings. It is not the same assembly as the separately sourced STEP parts and is not a vehicle-validation result.
