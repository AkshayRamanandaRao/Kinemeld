# Robot-arm reference model

The featured **Robot arm inverse dynamics** study is an editable, original
three-axis yaw–shoulder–elbow chain. Its purpose is to check Cartesian motion and
the joint torque required by prescribed motion before adding actuator or control
models. It is not a reconstruction of a manufacturer's robot.

The [engineering record](../examples/robot-arm/engineering.json) pins the saved
input and the authoring function in `examples/studies/build.py`. The turret axis
is world +Z at 0.30 m; the shoulder is 0.12 m higher about turret-local +Y; the
elbow is 0.42 m along the upper link, also about local +Y. The forearm beam is
0.36 m long and carries an authored steel-density payload block. The reference
tip is at `(0.36, 0, 0)` in forearm coordinates, at the beam end, not at an
inferred tool centre or the payload's centre.

| Input | Basis |
| --- | --- |
| Turret, yoke and beams | Original parameterized solids at assumed uniform density 2,700 kg/m³. |
| Motor-shaped solids and payload | Original parameterized solids at assumed uniform density 7,850 kg/m³; visual cylinders are rigid mass proxies, not actuator models. |
| Body mass, centre and full inertia | OCP volume integration of those solids, combined about each body centre with the parallel-axis theorem. |
| Base motion | 45°/s target yaw speed with a 1 s linear speed ramp. |
| Shoulder motion | `−25° (1 − cos(2π · 0.3 t))`. |
| Elbow motion | `40° (1 − cos(2π · 0.45 t))`. |
| Gravity | `(0, 0, −9.81) m/s²`. |

All densities, dimensions, prescribed motion and payload shape are authored
inputs. There are no measured motor curves, gearbox efficiencies, backlash,
joint friction, cable forces, flexible links, thermal limits or sensor noise.
An ideal prescribed joint can demand unlimited torque.

## Independent reference

`python -B backend/verify_engineering_examples.py robot-arm` checks the saved
model at 2 ms, 1 ms and 0.5 ms, then changes the shoulder amplitude by 20%.

For angles `q = (yaw, shoulder, elbow)`, the three world rotations are
`Rz(q0)`, `Rz(q0) Ry(q1)` and `Rz(q0) Ry(q1 + q2)`. The forearm origin is the
shoulder point plus `Rz(q0) Ry(q1) (0.42, 0, 0)`. This gives a Cartesian
forward-kinematics reference without using the app's position reconstruction.

For every body, the reference constructs linear Jacobian columns
`Jv_i = axis_i × (COM − jointOrigin_i)` and angular columns `Jw_i = axis_i` for
its upstream joints. It forms

```text
M(q) = Σ [m Jvᵀ Jv + Jwᵀ R I_COM Rᵀ Jw]
τ = M(q) q̈ + C(q, q̇) q̇ + ∂U/∂q
```

The mass-matrix derivatives in the Christoffel terms use a centred 10⁻⁵ rad
difference, independently of the application parser and drive torque code.
Gravity moments are obtained directly from the Jacobians. The reference uses
the complete body inertia tensors, including products of inertia.

Torque comparison excludes the first 10 ms and a fixed ±10 ms window about the
base ramp end, where acceleration jumps. This avoids assigning a smooth
acceleration reference to the implicit solver's discontinuity transient; it does
not establish peak switching torque. The Cartesian reference still covers the
whole requested interval. Unit checks independently recover the static gravity
moments and the `(0, 0.78, 0.42) m` beam-end position at 90° yaw with straight
shoulder and elbow.

See [traceable engineering examples](engineering-example-verification.md) for
input hashes, CAD mass reintegration, refinement, changed cases and report files.
The existing [rotary-drive guide](rotary-drives.md) explains the plotted angle,
speed, torque, power and work channels. Hardware tracking and motor-sizing
validation require actual actuator and test data.

The [recorded four-example benchmark](../examples/engineering-verification.json)
reports robot torque errors of approximately 0.414, 0.104 and 0.026 mN·m at
2, 1 and 0.5 ms. The error reduction is approximately fourfold per halving;
position errors are at output roundoff because the joint angles are prescribed.
The 20% lower-shoulder-amplitude case also matches the independent reference.
These values quantify the specific ideal inverse-dynamics benchmark, not
measurement accuracy or available motor torque.
