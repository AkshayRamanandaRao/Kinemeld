# Robotics improvements to consider next

These are follow-on candidates discovered while implementing the active roadmap.
They are separate from its current completion checks. Aerodynamics is excluded.

| Order | Improvement | Concrete benefit | Acceptance checks |
| --- | --- | --- | --- |
| 1 | URDF import with inertial and frame review | Bring an existing robot's links and joints into the editable spatial model without retyping its assembly. | Local files only; explicit unit/frame conversion; positive-definite inertia checks; joint-axis/origin round trips; unsupported mimic, transmission, collision and mesh data reported before review; no guessed mass properties. |
| 2 | Revolute/prismatic stops and backlash | Model robot travel limits and gearbox clearance with native solver elements. | Static engagement and impact benchmarks, reaction/energy accounting, timestep refinement, editor/Undo/project tests; no perfectly rigid impact assumption hidden in a penalty stiffness. |
| 3 | Waypoint trajectories and actuator envelopes | Move beyond one ramped servo target to repeatable robot motions. | Bounded time-ordered waypoints, continuous position/rate, measured tracking/error and torque/speed/power limits; cancellation and replay with the same recorded inputs. |
| 4 | General mesh/timestep comparison in the UI | Make numerical convergence checks available on a user's own study. | Match the same response and physical interval across runs; compare full CSVs; report failure/missing data; preserve all baseline inputs and run provenance. |
| 5 | Flexible-link joints and payload coupling | Turn the initial clamped-beam template into a flexible robot arm assembly. | Explicit beam/rigid joint interfaces, mass/inertia bookkeeping and constraints; rigid-limit and flexible two-link references; no inferred FE/CAD interface assumptions. |

The current contact implementation also leaves normal sphere-pair collision and
frictional plane contact as distinct contracts. Frictional grasping and arbitrary
CAD self-collision need their own numerical references before becoming product
features. Similarly, the trusted local PD peer establishes one tested co-simulation
workflow; arbitrary external controllers and protocols require a separate contract.
