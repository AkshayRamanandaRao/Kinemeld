# Robot joint brakes and spherical bumpers

Two small examples in **Examples → 3D & planar assemblies** demonstrate native solver features useful for robotics: **Robot joint brake** and **Robot bumper collision**. All dimensions, masses, friction and damping parameters are illustrative numerical inputs. They are not measured materials, calibrated brakes, a robot safety system, or hardware validation.

## A brake that holds at zero speed

Select a free revolute joint and choose **Joint brake → Discrete Coulomb**. Set its positive coefficient, effective radius and preload from your own engineering data. A prescribed rotary motion and brake cannot share a joint. The hinge must initially have zero relative axial angular velocity.

The generated MBDyn `revolute hinge` uses its native `discrete coulomb` friction model with a constant coefficient and `simple` shape coefficient. This adds a static friction unknown to the solve. The holding torque is

`μ × max(norm(native hinge force), preload) × effective radius`.

Preload is a force in newtons, not a torque. It sets a positive lower bound on normal load; a larger actual hinge force increases the threshold. With the example's μ = 0.5, radius = 0.1 m and preload = 20 N, the unloaded hinge holds up to 1 N·m. The rising 1.5 N·m sine motor torque first crosses that threshold at 0.1161397636 s. The rotor remains stationary before breakaway, then accelerates under motor torque minus friction torque.

Start held below the threshold and ramp applied effort through breakaway. MBDyn 1.7.3 can initialize the wrong friction direction for an abrupt above-threshold load at time zero. Kinemeld rejects a run when native friction produces appreciable energy, identifying the joint, time and power; raw solver files remain available. Initially sliding brakes are rejected by validation. This bounded initialisation contract also applies to gravity, loads and coupled mechanisms; these examples do not qualify every combination or reversal history.

Plots and full-resolution CSV expose signed **Joint friction torque (native)**, relative **Joint friction speed**, positive **Joint friction dissipation power**, and integrated **Joint friction dissipated energy**. Torque is the native friction torque acting on body B about the joint axis. Tiny negative numerical residuals near exact rest can be present; materially negative power fails the run.

## Contact between two moving bodies

Choose **Add sphere-sphere contact**, select two different dynamic bodies, then edit both body-local center vectors and radii. These analytical contact shapes are independent of STEP geometry. The viewport shows both contact spheres at their transformed local centers.

The normal points from the other sphere's center toward the first sphere's center. With center distance `L` and radius sum `R`, gap is `L − R`. The normal force magnitude is `k × max(0, −gap)` plus `c × max(0, −gapRate)` while overlapping. Damping never pulls and is inactive during separation. Both forces act at their respective centers with equal magnitude and opposite direction. Off-center attachments can therefore rotate both rigid bodies.

The native element is an implicit MBDyn `rod` with reference length `R`, compression-only scalar-function elasticity, and optional bistop-gated nonlinear damping. Strain and strain rate are scaled by `R` to preserve the entered N/m and N·s/m units. The native applied normal force is parsed from the joint output. Contact energy and damping loss are independently reconstructed from body motion. Initial coincident centers are rejected; a run that reaches coincidence fails because its normal is undefined. Keep penetration small compared with the radii and refine the timestep.

Only normal sphere-sphere contact is supported. Pair tangential friction fields are rejected. Existing sphere-plane contacts retain their optional regularised Coulomb law and its finite creep; that plane law has no static sticking state. Sphere pairs do not provide arbitrary CAD surface collision, edge contact, frictional grasping or self-collision detection.

## Reproduce the numerical evidence

Run `python -B backend/verify_robot_contact.py` with a real configured MBDyn. It checks zero-load and positive/negative subthreshold holding, both motor torque directions through breakaway at three timesteps, rejection of energy-injecting initialization, and moving-sphere collisions against analytical mechanics and an independent RK4 integration. It checks linear/angular momentum, actual force vectors, contact and brake energy accounting, local centers on rotated bodies, and timestep refinement. Fresh run IDs, solver hash and errors are retained in [robot-contact-verification.json](../examples/robot-contact-verification.json).

`python -B -m unittest discover -s backend -p test_robot_contact.py` checks schema boundaries, native deck laws, reference integrity, timestep/output limits and CSV columns. `node --test tests/robot-contact.test.mjs` checks local sphere transforms and full-resolution brake channels. With a running native-solver server, `MBDYN_STUDIO_URL=http://127.0.0.1:8791 node tests/robot-contact-ui.mjs` exercises the actual browser editor, undo, solves, plots, CSV, saved projects and stale-result gates. No desktop computer automation is used.

The retained MBDyn 1.7.3 run gives these worst errors against independent references:

| Timestep | Brake angular speed error | Brake energy balance | Elastic pair relative-position error | Elastic pair energy balance |
| --- | --- | --- | --- | --- |
| 1 ms | 8.72e-5 rad/s | 1.70e-6 J | 76.2 µm | 8.76e-4 J |
| 0.5 ms | 1.87e-5 rad/s | 4.25e-7 J | 15.5 µm | 2.11e-4 J |
| 0.25 ms | 9.67e-6 rad/s | 1.06e-7 J | 4.65 µm | 5.18e-5 J |

The breakaway sample is within three timesteps of the analytical crossing; refine the step for event timing. Compression-only damping switches discontinuously at first contact, so its convergence is slower: relative-position errors fall from 286 to 119 to 68.1 µm over the same steps. A separate collision with local center offsets and rotated bodies at 0.125 ms gives linear-momentum error 1.38e-9 kg·m/s, angular-momentum error 6.18e-8 N·m·s, and energy balance error 3.80e-4 J. These error bounds describe these benchmark cases and parameter ranges.
