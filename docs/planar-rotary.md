# Planar rotational springs and time-varying torques

These optional project fields apply to existing planar **revolute** joints in a grounded tree. They work with the same body inertia and STEP-to-body assignments as other planar simulations; the STEP geometry is visual and does not calculate mass or inertia. Existing projects without either field remain unchanged.

```json
"rotationalElements": [
  {"id": "spring1", "joint": "ground_pin", "stiffness": 10.0,
   "damping": 0.5, "restAngleDeg": -20.0}
],
"jointTorques": [
  {"id": "motor1", "joint": "ground_pin", "amplitude": 1.0,
   "frequencyHz": 1.1, "offset": 0.3}
]
```

Angles and rest angles are child relative to parent about positive Y, with rest angles in degrees. Stiffness is N m/rad, damping is N m s/rad, and torque is N m. A spring/damper applies `-stiffness * (angle - rest) - damping * relativeAngularVelocity` to the child and the opposite torque to the parent. Either stiffness or damping can be zero, but not both. Rest angles must lie strictly between -180 and 180 degrees. The initial relative angle minus rest angle must be strictly within ±π, and the native trajectory is rejected if it reaches or crosses that branch or cannot resolve angular motion at 0.1 rad per step. Multiple-turn springs are unsupported.

A joint torque is `offset + amplitude * sin(2 * pi * frequencyHz * time)`, applied to the child and equally and oppositely to a dynamic parent. Ground supplies the reaction otherwise. Frequency must be between 0.001 and 1000 Hz; the simulation must have at least 20 steps per cycle. This is a prescribed **torque**, not prescribed position or a general expression language. Use a smaller time step and convergence studies when the mechanism or forcing demands it. There can be up to 32 elements of each kind, subject to output and simulation limits enforced by validation.

The MBDyn 1.7.3 deck uses a deformable hinge with a linear viscoelastic constitutive law and absolute couples with sine drives. Deformable-hinge preload requires skipping MBDyn's initial joint assembly; the application first checks the supported tree's initial hinge and slider positions and velocities. A failed solve or unsupported trajectory is an error, never a synthetic result.

Native body poses and velocities are used to reconstruct spring angle, angular velocity and torque (`rotationalStates`), actuator torque and power (`actuationStates`), elastic energy and dissipated energy, plus actuator work integrated by trapezoidal quadrature. The CSV includes per-element values and total energy/work. The balance subtracts actuator work and constant-load work, and adds damping dissipation; it also includes axial springs when present. These derived values depend on sampled trajectories and their integration accuracy.

Run `python -m unittest discover -s backend -p 'test_planar*.py'` for validation, output and regression tests. Run `python backend/verify_planar_rotary.py` with the configured MBDyn 1.7.3 installation for actual solver runs compared with independently integrated rigid-body equations. It exercises pure spring, pure damper, time-dependent actuation, coexistence with axial spring and constant load, and two dynamic bodies with equal and opposite torques. The verification is limited to those planar cases and does not establish suitability for contact, flexible bodies, closed loops, general 3D behavior, or industrial design decisions.
