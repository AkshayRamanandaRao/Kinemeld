# Landing-gear deployment: a closed four-bar

This original generic mechanism lets you change link lengths, attachment positions and deployment timing, then solve the closed linkage with the installed MBDyn engine. The useful outputs are the wheel path, brace motion, geometric actuator travel demand and closure error. The three moving links have mass, inertia and gravity loading. Deployment is prescribed, so this model does not predict whether a particular hydraulic actuator can deploy an aircraft's gear.

Open **Shuttle-style gear deployment** in the example gallery, validate the project, then choose **Run simulation**. The model and editable deck are also available as `examples/gear-deployment.json` and `examples/gear-deployment.mbd`. The geometric reference preview is a separate calculation and is labeled separately from MBDyn results.

## Public engineering context

NASA's public *Space Transportation System*, HAER No. TX-116, printed pages 191–193 (PDF pages 75–77), describes Discovery's gear deployment: hydraulic actuators released the uplocks, then gravity, strut actuators and aerodynamic loads assisted extension; spring-loaded downlock bungees secured the gear. Retraction occurred during ground processing. [NASA source](https://www.nasa.gov/wp-content/uploads/2015/12/2c.pdf#page=75)

That reference establishes a real deployment problem, not the geometry or drive in this example. This model uses original illustrative dimensions, masses and a three-second angle sweep. It does not reproduce Shuttle hardware, timing, hydraulic circuitry, doors, uplocks, downlocks, pyrotechnics or aerodynamic assistance. The reverse-sweep verification is a generic mechanism check, not a claim that Shuttle gear retracted in flight. No upstream model or proprietary application code was copied.

MBDyn input syntax follows the [1.7.3 input manual](https://www.mbdyn.org/userfiles/documents/mbdyn-input-1.7.3.pdf): cosine drive (section 2.6.4), rigid body (8.4), total joint (8.12.46), and total pin joint (8.12.47).

## Geometry and parameters

Motion is in the X–Z plane, with Z upward. Angles are degrees from the downward vertical, positive toward +X. A is the fixed main pivot at `(0,0)`; D is the fixed brace pivot. The physical loop is **A–B–C–D–A**. The main strut continues from A through B to wheel center W.

| Parameter | Meaning | Default |
| --- | --- | --- |
| `mainLength` | A–W length | 1.1 m |
| `braceAttachment` | A–B distance, inside A–W | 0.45 m |
| `upperBraceLength` | B–C length | 0.55 m |
| `lowerBraceLength` | C–D length | 0.60 m |
| `groundX`, `groundZ` | D position relative to A | 0.65, −0.10 m |
| `actuatorAnchorX`, `actuatorAnchorZ` | Fixed anchor E used to measure E–B | −0.35, 0.15 m |
| `mainMass` | Main strut's distributed mass | 25 kg |
| `upperBraceMass`, `lowerBraceMass` | B–C and C–D link masses | 4, 4 kg |
| `initialAngle`, `finalAngle` | Main-strut sweep | −65°, 0° |
| `gravity` | Downward gravitational acceleration | 9.81 m/s² |
| `duration`, `step` | Deployment time and integration step | 3, 0.01 s |

Each body uses a uniform slender cylindrical link inertia, with illustrative radius 2% of its length. This radius is an inertia approximation, not verified gear geometry. Since the angle is imposed, changing mass or gravity changes constraint reactions rather than the ideal path; reaction loads are not qualified here.

The prescribed angle is

`theta(t) = theta0 + (theta1-theta0)/2 * (1-cos(pi*t/T))`, for `0 <= t <= T`.

The position stays at the endpoint after T. Velocity is zero at both endpoints. Acceleration has a finite discontinuity when the drive stops; this model is intended for path and travel inspection, not actuator-force sizing.

The independent reference computes B from A–B and theta, then intersects a circle centered on B with radius B–C and a circle centered on D with radius C–D. It uses the positive branch perpendicular to B→D. Validation checks the exact extrema of distance B–D across the whole angle interval, not only the endpoints. Unreachable and near-toggle geometries are rejected; singular locking configurations are outside this model. Sweeps must span 1–150 degrees, with at least 100 integration steps.

## What the solver actually does

The exported deck contains three dynamic structural nodes at B, C and D, three massive rigid bodies, and five total-joint elements. A is a grounded pin with an imposed rotation. D is grounded with free planar rotation. The B and C joint constraints enforce the two brace connections; a planar restraint removes out-of-plane movement. This representation avoids redundant spatial constraints in a planar closed loop. Only the main rotation is prescribed: the brace motion is obtained by solving closure in MBDyn.

The parser reads B, C and D from `.mov` output at matching `.out` times. W follows from the rigid A–B–W ratio. Results include `bx`, `bz`, `cx`, `cz`, `wheelX`, `wheelZ`, `angle`, `actuatorLength` and `closureError`, alongside the common sample fields. Actuator length is `|E-B|`; reported travel is its sampled maximum minus minimum. There is no actuator element, pressure, piston area, force or hydraulic efficiency in this example.

`maxConstraintError` checks link-length residuals, the grounded D position and planarity. `maxGeometryError` compares observed B and C against the independent circle calculation. `maxDriveAngleError` compares observed main angle against the intended drive.

## Repeatable verification

From `mbdyn-studio/backend`, run:

```powershell
python -m unittest test_gear_deployment -v
python verify_gear_deployment.py
```

The real-solver script uses the shared `solver.run` application route and `backend/solver.json`, saves raw decks, project inputs, CSV and solver output in `runs/<runId>`, and writes `backend/evidence/gear-deployment-verification.json`. These generated local records are not included in the public checkout. It checks the default mechanism, different dimensions and masses, half-sized time steps, and reverse motion. The evidence includes the module and deck hashes, solver version and asserted tolerances. This verifies the common application runner and parser; HTTP and UI verification are performed separately.

The verified MBDyn 1.7.3 cases had worst geometric error below `7e-8 m`, worst closure error below `1.1e-7 m`, and angle error below `9e-6 degrees`. These residuals include text-output rounding and do not establish aircraft accuracy. MBDyn can output one integration step beyond the requested final time; that observation is retained, with the drive held at its endpoint.

Unverified engineering effects include actual aircraft geometry, hydraulic or aerodynamic deployment dynamics, joint clearance and friction, strength, elastic deformation, doors, locking, contact, failure cases and certification. A calibrated force-driven model and physical test data are required before making equipment performance claims.
