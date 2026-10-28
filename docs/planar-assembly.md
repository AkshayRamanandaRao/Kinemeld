# Authoring planar rigid-body assemblies

`planar-assembly` is a user-authored graph, not a fixed mechanism template. Add bodies, change their masses and principal inertias, choose initial poses and velocities, and connect local attachment points with revolute hinges or prismatic sliders. The exporter generates actual MBDyn nodes, rigid bodies and joints for every declared object. The same path supports serial chains, branches and multiple independent ground roots.

This planar editor is a foundation for multibody authoring. General 3D joints, closed loops, prescribed motion, contact, friction, flexible bodies, controls, optimization, CAD-to-mass inference and industrial qualification remain outside this planar graph version. Imported STEP solids can be attached to bodies for visualization; they do not create mass, inertia or constraints.

## Coordinate and unit contract

The motion plane is global XZ; every revolute axis is global positive Y. Each body node is its center of mass. The body's initial orientation rotates its local principal-inertia frame about positive Y. The entered diagonal inertias must be about that center of mass, must be positive, and must satisfy the principal-inertia triangle inequalities.

| Fields | Units / meaning |
|---|---|
| `mass` | kg |
| `inertia.xx`, `.yy`, `.zz` | kg m², local principal moments about the center of mass |
| `pose.x`, `pose.z` | m, global center-of-mass position |
| `pose.angleDeg` | degrees, right-handed rotation about positive Y |
| `velocity.vx`, `.vz` | m/s, global center-of-mass velocity |
| `velocity.omega` | rad/s about positive Y |
| `parentAnchor.x/z`, `childAnchor.x/z` | m, body-local offset from its center of mass; the ground parent's anchor is a global point |
| `parameters.gravity` | m/s², downward along global -Z; zero is allowed |
| `simulation.duration`, `.step` | s |

For a local anchor `(a,b)` and angle θ, the global offset is `(cosθ·a + sinθ·b, -sinθ·a + cosθ·b)`. Add the body's center position to obtain its world attachment point. With world offset `(dx,dz)`, its attachment velocity is `(vx + omega·dz, vz - omega·dx)`. Ground has zero velocity.

Both ends of every revolute hinge must initially coincide within 1e-7 m and have velocities agreeing within 1e-7 m/s. The validator reports the offending `joints.i.childAnchor`; it does not move bodies or silently change velocities. A position-only repair is insufficient if initial angular velocities are nonzero.

Prismatic sliders use different initial constraints; see [planar prismatic joints](planar-prismatic.md). Optional axial spring-dampers are described in [planar springs](planar-springs.md).

## Project schema and API

Full editable graph fixtures are in `examples/planar-assembly/assembly-single.json`, `assembly-chain.json` and `assembly-branch.json`. These are original educational models under the application's MIT license, separate from the curated GPL upstream examples.

```json
{
  "kind": "planar-assembly",
  "name": "My mechanism",
  "parameters": {"gravity": 9.81},
  "simulation": {"duration": 5, "step": 0.001},
  "bodies": [{
    "id": "body1", "name": "Body 1", "mass": 1,
    "inertia": {"xx": 0.1, "yy": 0.1, "zz": 0.01},
    "pose": {"x": 0, "z": -0.5, "angleDeg": 0},
    "velocity": {"vx": 0, "vz": 0, "omega": 0}
  }],
  "joints": [{
    "id": "hinge1", "type": "revolute",
    "parent": "ground", "child": "body1",
    "parentAnchor": {"x": 0, "z": 0},
    "childAnchor": {"x": 0, "z": 0.5}
  }]
}
```

Identifiers match `[A-Za-z][A-Za-z0-9_-]{0,31}`; `ground` is reserved. IDs are unique within each collection. Every body must have exactly one incoming parent joint and reach ground without a cycle. Array order does not define the graph. Unknown fields, unsupported joints, dangling references, non-finite values, booleans masquerading as numbers and inconsistent initial conditions are rejected before generating a deck.

The existing routes accept `{ "model": <graph> }`:

- `POST /api/validate`: diagnostics with paths such as `bodies.0.pose.x`, plus `summary.nodeLabels`, a body-ID to MBDyn numeric-label mapping.
- `POST /api/deck`: validated MBDyn input text, with no execution.
- `POST /api/run`: managed execution using the configured solver; exact input graph retained in `result.model` and the run's `project.json`.
- `POST /api/preview`: returns 422 for assemblies. There is no synthetic animation standing in for an assembly solve.

Bounds are 1–16 bodies, one parent joint per body, 20,000 requested integration steps and 160,000 requested body-steps. Duration is 0.01–30 s and step 0.0001–0.02 s. These limits bound local work; they are not an accuracy guarantee. Initial rotation is additionally limited to 0.1 rad per step. Always compare a finer step for the actual mechanism and operating condition. Solver failure and incomplete output remain failed results with retained logs.

## Native results and postprocessing

Every displayed node comes from MBDyn's structural `.mov` output. Samples are:

```json
{
  "time": 0,
  "nodes": [{
    "id": "body1", "label": 1,
    "x": 0, "y": 0, "z": -0.5,
    "rx": 0, "ry": 0, "rz": 0,
    "vx": 0, "vy": 0, "vz": 0,
    "wx": 0, "wy": 0, "wz": 0,
    "angleDeg": 0
  }],
  "energy": -4.905,
  "jointError": 0,
  "jointVelocityError": 0
}
```

`id` is the declared string body ID; `label` is its numeric MBDyn node label. `rx/ry/rz` retain native Euler123 angles in degrees; they are not rotation-vector components. `angleDeg` is the planar Y orientation reconstructed across Euler branches, wrapped to ±180 degrees. Angular velocity is rad/s; position is m and velocity m/s. The run includes explicit `units` and `nodeLabels` metadata. Normal solver termination, complete finite frames, monotonic output times and the expected native orientation representation are required. A final solver frame may exceed the requested duration by one step; its true timestamp is preserved.

`results.csv` has one row per body per full-resolution frame, with columns `time,id,label,x,y,z,rx,ry,rz,vx,vy,vz,wx,wy,wz,angleDeg,energy,jointError,jointVelocityError`. Energy and residuals are assembly totals repeated on each body's row. Display samples may be decimated; the CSV preserves every written frame.

The reported energy is `sum(0.5*m*(vx²+vz²) + 0.5*Iyy*wy² + m*g*z)`. Its datum is world Z=0, so negative energies are expected. `relativeEnergyDrift` is maximum deviation from initial energy divided by `sum(m*g*norm(childAnchor)) + initial kinetic energy`, with a 1e-12 J denominator floor. This avoids dividing by an arbitrarily chosen potential-energy datum; it does not replace a problem-specific accuracy assessment. Hinge position and velocity residuals are reconstructed independently from output poses and velocities.

## Verification

From `backend/` run:

```text
python -m unittest test_planar_assembly -v
python verify_planar_assembly.py
```

The second command requires a real configured MBDyn executable and never falls back to a preview. It writes `verification/planar-assembly.json` with solver version, run IDs, source/deck hashes, observed residuals and explicit checks. That generated report is not included in the public checkout. Cases cover a rigid pendulum, coupled rigid pendulums, a branched assembly, nonzero constant rotation through a full turn, reordered body/joint arrays, and a half-step chain run. Single and coupled pendulums are compared to separate RK4 integrations of their Lagrange equations; branch checks use hinge closure and conservative energy. Reordering must preserve motion by string ID. Refinement must reduce independent motion error. These tests establish this supported subset, not all possible graphs or industrial hardware validity.
