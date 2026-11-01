# Flexible robot link

Open **Examples → Templates → Flexible robot link** for a bounded flexible-body study. A uniform link is clamped at its root and loaded in global Z at its tip. MBDyn solves the motion of the actual beam nodes. The display connects those nodes at their actual displacement scale, without a deformation multiplier or a generated bending animation.

This example uses illustrative section properties. No material grade, supplier data, calibration, measured robot, fatigue life or hardware validation is claimed. A flexible link must be studied with appropriate measured or calculated section properties before using its results in design.

## Model and inputs

Choose 3, 5 or 9 structural nodes: one, two or four native **MBDyn `beam3`** elements. Adjacent elements share their end nodes. The first node has a six-constraint clamp; all other nodes have their own translations and rotations. The initial link is straight along global X, starts at rest, and has no gravity or other loads.

| Input | Meaning | Unit |
| --- | --- | --- |
| Link length | Initial root-to-tip distance | m |
| Mass per length | Uniform distributed mass | kg/m |
| Axial stiffness EA | Section axial stiffness | N |
| Shear stiffness GA | Equal stiffness in both transverse directions | N |
| Bending stiffness EI | Equal stiffness about both principal bending axes | N·m² |
| Torsional stiffness GJ | Section torsional stiffness | N·m² |
| Rotary inertia per length | Equal principal bending rotary inertias per unit length; polar value is twice this | kg·m |
| Stiffness damping time | Kelvin–Voigt proportional coefficient, `C = time × K` | s |
| Tip load Z | Final signed global-Z tip force | N |
| Load ramp time | Half-cosine rise from zero to the final constant force | s |

Stiffnesses and mass properties are explicit independent inputs; the app does not infer them from a CAD mesh, density or material name. The rendered tube thickness is a display aid, not a recovered section shape. This family does not connect the flexible link to rigid joints or a robot controller and does not import general finite-element models.

Each quadratic element distributes its mass and rotary inertia to its three nodes with Simpson weights `1:4:1`. Contributions at shared nodes are added. This preserves total mass and the straight link's second mass moment, but it is a lumped inertia model, not a consistent finite-element mass matrix. It changes finite-mesh vibration frequencies; compare mesh refinements.

The beam section law is diagonal, with entries `EA, GA, GA, GJ, EI, EI`. Native geometrically exact beam strains govern the motion. Input validation limits twice the linear static deflection to 10% of length, bounds the radius of gyration to 10% of length, and requires a ramp of at least 20 timesteps. Output that exceeds 15% transverse deflection is rejected. These are scope limits, not strength, stress or safety checks.

The native multistep integrator uses asymptotic spectral radius 0.6 to damp unresolved high-frequency numerical motion and residual tolerance 1e-8. This numerical damping is separate from the entered physical damping time. The first-mode timestep check is a starting point: stiff axial/shear modes, node inertia and mesh changes still require convergence comparisons. A finer undamped mesh at tolerance 1e-9 reached the native solver's iteration limit during development; the documented settings passed the retained cases. Arbitrary parameter combinations are not universally qualified.

## View and results

The clamp and each native node are visible in the viewport. Straight display segments join adjacent solved nodes, so a coarse display does not imply a finely meshed continuous surface. The initial straight line, deflected shape and vibration all come from the saved model and native node frames.

Plots expose **Tip deflection (native)**, **Tip velocity (native)**, **Tip slope (native)**, applied force, and the native clamp's global-Z force and global-Y moment. The clamp output uses MBDyn's load-carried convention: a downward `−1 N` tip load gives about `−1 N` root force and `+0.5 N·m` root moment for a 0.5 m link. These values are distinct from an oppositely signed support force acting on the moving beam.

Full-resolution CSV contains every solver timestep and every node's position, rotation, linear/angular velocity, plus the scalar channels with physical unit suffixes. Raw deck, motion, beam-force and clamp-force artifacts remain downloadable. Acceptance requires a complete, finite native mesh, matching `beam3` connectivity and beam/clamp output frames, a stationary root, and normal solver termination. Partial or cancelled output is retained for diagnosis and is not promoted to a completed trajectory.

Save/reopen retains the model, mesh settings and native node trajectory. Editing a section property or load marks old results stale. The reference Preview button is disabled for this family; a real native solver is required. Run cancellation stops the owned solver process and retains its partial log and files.

## Independent checks

For a small transverse end load `F`, the static reference is

`w(x) = F × [x² × (3L − x)/(6EI) + x/GA]`.

The approximate Euler–Bernoulli first-mode reference is

`f₁ = 1.8751040687²/(2πL²) × sqrt(EI / massPerLength)`.

The frequency reference omits shear deformation, distributed rotary inertia, geometric effects and finite-mesh lumping; these effects explain a nonzero reference difference after numerical refinement. It is not the exact frequency of the native Timoshenko-like beam model.

The retained [flexible-link-verification.json](../examples/flexible-link-verification.json) records fresh native run IDs and solver, generator, verifier, model and deck hashes. With the default 0.5 m link, the static tip reference is −8.34333 mm; the native geometrically nonlinear result is about −8.34095 mm. The largest nodal shape difference is 2.42 µm, or less than 0.03% at the tip. The steady native force is −1 N and root moment about +0.499917 N·m.

| Nodes / beam elements | Measured first frequency | Difference from Euler–Bernoulli reference |
| --- | --- | --- |
| 3 / 1 | 5.02989 Hz | 0.495% |
| 5 / 2 | 4.99594 Hz | 0.184% |
| 9 / 4 | 4.99894 Hz | 0.124% |

Mesh refinement changes the static tip by 27.0 then 2.96 nm, and frequency by 0.03395 then 0.00300 Hz. For the nine-node damped transient, timesteps of 1, 0.5 and 0.25 ms give matched-time deflection differences of 0.516 then 0.129 µm, a refinement ratio of 3.999. A separate upward-load case changes length, mass and stiffness and checks the resulting deflection and clamp loads.

Run `python -B backend/verify_flexible_link.py` with the configured real MBDyn to reproduce the numerical checks. Run `python -B -m unittest discover -s backend -p test_flexible_link.py` for schema, quadrature, output-integrity and CSV checks, and `node --test tests/flexible-link.test.mjs` for direct native-node display and full-resolution channels. With a server on the configured test URL, `node tests/flexible-link-ui.mjs` checks editing, undo, a real solve, plots/exports, downloadable native artifacts, save/reopen, stale gates and actual native process cancellation through the browser GUI. No desktop computer automation is used.
