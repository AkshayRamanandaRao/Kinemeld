# Linear spring and damper elements in planar assemblies

Planar rigid-body graphs may contain up to 32 axial spring-damper elements.
Choose distinct endpoints (`ground` or a body ID), an attachment position for
each, stiffness in N/m, viscous damping in N·s/m and a positive rest length in
metres. Body anchors are local offsets from their centres of mass; ground
anchors are world coordinates. The initial anchor separation must be at least
1 micrometre so the force direction is defined. Pure springs and pure dampers
are supported; both coefficients cannot be zero. The supported rest length is
at least 1 micrometre because MBDyn's rod law divides by its reference length.

```json
{"id":"spring1","type":"linear-spring-damper","a":"ground","b":"upper_link",
 "anchorA":{"x":1,"z":0},"anchorB":{"x":0,"z":-0.5},
 "stiffness":10,"damping":0.5,"restLength":1.3}
```

The optional `forces` array defaults to empty for older projects. The new
`assembly-spring` example is a rigid pendulum with an anchored spring-damper.
The element exerts axial force `k * (length - restLength) + c * lengthRate`,
positive in tension; forces on its two ends are equal and opposite. MBDyn's
rod constitutive law takes dimensionless strain and strain rate, so the deck
supplies `k * restLength` and `c * restLength`. A stationary internal ground
node is used only if needed and is omitted from motion output.

MBDyn 1.7.3's initial joint assembly can fail for preloaded rods. For graphs
containing these elements the generated deck explicitly skips that step; the
application validates all hinge positions and velocities before export, and
rejects incompatible initial constraints. This is not a general nonlinear
assembly solver. Simulations whose spring endpoints coincide later cannot
produce a meaningful axial direction and are rejected when detected.

Native MBDyn node motion is used to reconstruct each spring's length,
extension, rate and axial force at each output frame. Damping power is
`c * lengthRate²`; accumulated dissipation is trapezoid-integrated from native
sample times. Mechanical energy includes spring potential energy; balance error
compares mechanical energy plus dissipated energy to its initial value. These
reconstructed force channels and energy estimates are not independently sampled
MBDyn load output. CSV includes their full written-frame values; the same
assembly-wide values are repeated on each body's row. Use smaller time steps and
independent physical checks for your specific design.

Four actual local MBDyn 1.7.3 cases were compared against independent RK4
pendulum equations: spring only, damper only, combined spring-damper connected
to ground, and an equal-and-opposite spring-damper connecting two independently
pivoted bodies. Run `python backend/verify_planar_springs.py` to reproduce them
with MBDyn and generate `verification/planar-springs.json`; that local report is
not included in the public checkout.
Contact, nonlinear laws, arbitrary applied loads, loop closure and full 3D
mechanisms remain unsupported in this planar graph.
