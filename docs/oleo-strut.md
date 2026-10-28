# Nonlinear oleo strut

[Watch the slowed simulation recording](demos/oleo-strut.mp4).

The spatial editor can add an **oleo strut** between two bodies, or between a body and ground. MBDyn's native `shock absorber` constitutive law provides a polytropic gas force, quadratic hydraulic damping with different compression/rebound metering areas, and soft stroke stops. It acts along the line between the selected local attachment points. STEP geometry supplies the visualization; it does not set the strut dimensions, calibration, joint, or forces.

## Worked STEP wheel-end fixture

1. Open `examples/oleo-strut/wheel-oleo.mbdyn-studio`. Its wheel, hub and knuckle use the [original STEP sources](open-wheel-end.md). The ground-to-knuckle slider prescribes a 50 mm displacement cycle; this is an illustrative fixture, not an aircraft gear or calibrated drop test.
2. Select **oleo** under Forces. The reference length is `0.5 m`; reference **absolute** gas pressure is `1 MPa`, gas piston area `0.001 m²`, reference gas volume `0.001 m³`, and polytropic exponent `1.4`. Minimum and maximum lengths are `0.46` and `0.5 m`; the entered `60,000 N/m` stop is a finite penalty, not a hard boundary. Compression and rebound metering areas are `0.00015` and `0.0001 m²`. All values are illustrative.
3. Choose **Validate model**, then **Run simulation**. In Results select **Oleo gas pressure (native)** or **Oleo force components (native / derived)** and choose `oleo`. At roughly `0.25 s` the imposed slider compresses the strut; near the middle of the cycle it passes the minimum length and the stop contributes force. Scrub the timeline, export CSV, and save/reopen the project.
4. To add another element, choose a target body in **Add spring / damper**, then choose **Add oleo strut**. Select it in the model tree, set both attachment points and every physical input, verify initial stroke and joint consistency, and run a convergence study. The defaults are a starting fixture, not supplier data.

![The sourced STEP wheel-end with the oleo inputs and actual solver response](images/oleo-strut.png)

## Law, signs and units

Let `L` be endpoint separation, `v = dL/dt`, `L₀` reference length, `P₀` reference absolute pressure, `A₀` gas piston area, and `V₀` gas volume. With unit kinematic ratio,

`P = P₀ [1 + A₀ (L − L₀) / V₀]^(−γ)` and `Fgas = −A₀ P`.

Positive tension pulls B toward A; gas preload is therefore negative and pushes the endpoints apart. This native model uses **absolute pressure without ambient-pressure subtraction**. For a physical strut, account for back pressure, piston areas, gas volume, seal forces and gas behavior from measured data; this example does not establish them.

`Fhydraulic = 0.5 ρ Af³ / (Am² Cd²) · v |v|`, where `Af` is fluid piston area, `ρ` density, `Cd` discharge coefficient and `Am` the selected metering area. Negative velocity means compression; positive means rebound. The hydraulic force has the sign of `v`, so it opposes relative motion and dissipates `Fhydraulic·v ≥ 0`.

Outside `[minLength,maxLength]`, the stop adds `K (L−limit)` plus `C·v` only when moving farther outside the permitted range. `K` is N/m and `C` is N·s/m. The stop force can act while the soft model is beyond the stroke; no rigid bottom-out geometry is generated. MBDyn's native rod output supplies pressure, hydraulic force, total tension, and the combined elastic-plus-stop force. The gas component is derived as `−A₀P`; the stop component is derived by subtracting gas from the native elastic-plus-stop output. Values use tension-positive signs. The general **Axial tension (native / reconstructed)** plot uses native tension for an oleo and reconstructed tension for a linear spring. Native rod records are checked against body motion and the stated equations before reporting. CSV includes `gasPressure_Pa`, `gasForce_N`, `hydraulicForce_N` and `stopForce_N` for the strut.

## Numerical boundaries

The native law evaluates gas pressure before evaluating stop penalties. To avoid its gas-volume singularity for every nonnegative rod length, validation requires `L₀ A₀/V₀ ≤ 0.9`; consequently gas chambers that violate this condition are unsupported by this implementation. Initial length must be inside the specified stroke. If an endpoint collapses, a solver fails, a reconstructed gas volume is nonpositive, or native output is malformed, the result is rejected rather than fabricated.

Native-force checks allow for the finite precision of separately printed components. Large opposing forces can make a small net force much less precise. Near a stroke limit, either physically possible active or inactive stop branch may be accepted within the rounding tolerance; arbitrary stop forces are rejected. Strong stops and rounded positions may also require closer inspection of the raw output.

The timestep check based on endpoint compliance, gas tangent at minimum stroke and stop terms is only a **heuristic**; it excludes velocity-dependent hydraulic tangent and mechanism coupling. Compare multiple time steps, inspect startup transients and check solver convergence. In the installed MBDyn 1.7.3 source, the native gas tangent appears to have the opposite sign from the force derivative, and its quadratic damping Jacobian omits a factor of two. Either can impair Newton convergence; successful runs do not guarantee convergence for arbitrary parameters. The force outputs themselves were independently compared with the stated equations. Gas and stop energy are reported relative to the reference length; gas potential may be negative away from that reference. Dissipated energy uses trapezoidal integration of hydraulic and outward stop-damping power.

`python -B backend/test_oleo_strut.py` checks validation, both stops, damping signs, energy gradients, the `γ=1` limit and corrupt native records. With locally configured MBDyn 1.7.3, `python -B backend/verify_oleo_strut.py` compares raw native rod force, pressure and hydraulic output against independent equations through compression, rebound and both stops, and repeats at half the time step. Native force differences were below `6×10⁻¹⁰ N`; the maximum energy-balance drift decreased from `0.00273 J` to `0.00132 J`. It also checks a free body with no joints and rejects a corrupted native rod record. `node tests/oleo-strut-ui.mjs` in the source checkout exercises actual STEP, editing, solving, plotting, CSV and save/reopen. These checks are mathematical verification of representative cases, not physical or safety certification.
