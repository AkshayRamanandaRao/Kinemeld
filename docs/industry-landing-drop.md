# Landing-gear drop-test workflow

This original two-body vertical impact model lets you study sink speed, energy absorption, tire load, strut compression and rebound. It represents a reduced engineering problem rather than a particular aircraft, spacecraft, certified landing gear or complete oleo-pneumatic strut.

## What is modeled

A sprung mass and wheel mass fall under gravity with equal initial downward velocity. Both remain on one vertical guide; their orientations are fixed. The spring's uncompressed length separates the masses. The wheel's coordinate is **height above initial tire contact**, not the literal wheel-center height; a rendered wheel radius is only a display offset.

The strut combines an equivalent linear spring with a quadratic hydraulic damping approximation. The tire is elastic in compression and releases completely above the ground. The fixed ground is `z=0`, positive Z upward:

```text
d = zs - zu - L                        strut extension relative to its rest length
dv = vs - vu
Fs = -ks*d - cq*dv*abs(dv)             upward strut force on the sprung mass
Ft = kt*max(-zu, 0)                   unilateral upward ground force
ms*as = Fs - ms*g
mu*au = -Fs + Ft - mu*g
zs(0)=L+h, zu(0)=h, vs(0)=vu(0)=-V
```

The hydraulic coefficient has units **N s²/m²**, unlike the suspension model's linear damping coefficient. The spring is zero preload and linear; it omits actual gas precharge and its polytropic pressure-volume curve. Compression/rebound damping uses the same fixed coefficient. These deliberate approximations make the laws inspectable and parameterized.

Historical basis: [Flügge, NACA-TN-2743, *Landing-Gear Impact*](https://ntrs.nasa.gov/citations/19930083479) describes sprung/unsprung masses, strut and tire elasticity, damping, and touchdown velocity conditions. [Daniels, NASA-CR-201601, *A Method for Landing Gear Modeling and Simulation With Experimental Validation*](https://ntrs.nasa.gov/citations/19960049759) treats a richer two-DOF model with polytropic gas force and velocity-squared hydraulic forces. Our zero-preload linear spring, symmetric constant damper and unilateral linear tire are simplifications, not the validated NASA implementation. Parameters below are illustrative choices, not extracted aircraft data.

## Default inputs and experiment

| Parameter | Value | Unit |
|---|---:|---|
| Sprung / unsprung mass | 600 / 35 | kg |
| Equivalent strut stiffness | 45000 | N/m |
| Quadratic strut damping | 2500 | N s²/m² |
| Tire stiffness | 350000 | N/m |
| Uncompressed strut length | 0.8 | m |
| Initial wheel height above contact | 0.04 | m |
| Initial downward sink velocity | 1.5 | m/s |
| Gravity | 9.81 | m/s² |
| Run duration / step | 1.5 / 0.00025 | s |

1. Open **Landing-gear drop test**. Validate the inputs, noting the force-peak refinement guidance for strong quadratic damping.
2. Run the actual solver. Before contact, both masses must be in free fall and tire force must be zero.
3. Inspect contact time, peak tire force, strut/tire compression and body acceleration. Contact starts at approximately 0.02468 s from the ballistic formula; discrete output records the first loaded sample.
4. Compare sink velocities or damping values. Low damping permits larger rebound; contact can release when the wheel rises above the surface.
5. Halve the time step and compare force peaks. Export decks and CSV for a reproducible comparison.

The default run produced a first loaded sample at 0.02475 s, maximum strut compression 248.455 mm, tire compression 32.928 mm, and peak tire load 11.525 kN. Default damping keeps contact after touchdown in the 1.5 s window. A separately verified changed-parameter case uses lower damping and checks actual contact release; release is a supported law, not a claim that every run rebounds off the ground.

## Solver representation and channels

MBDyn uses two dynamic structural nodes with vertical guide constraints, uniform gravity, a `rod` with `turbulent viscoelastic` law, and a deformable-displacement tire joint with a multilinear scalar function. Rod strain is `(length-L)/L`, so the deck scales physical spring stiffness by `L` and quadratic damping by `L²`. The tire scalar function is `kt*min(z,0)`; its reaction on the wheel is upward and zero when airborne.

`zSprung/zUnsprung` are absolute Z coordinates; velocities/accelerations are signed upward. `suspensionTravel` is extension `d`; `strutCompression=-d` is signed compression, negative during extension. `tireCompression=max(-zu,0)`. `contact` is 0 or 1. `suspensionForce` is upward force on the body, and `tireForce` is upward contact force, both in N. Common `z/value` equals `zSprung`; common `velocity` equals `vSprung`.

Forces and accelerations are reconstructed from the documented constitutive laws and actual solver states. The independent verification also compares these forces with native MBDyn `.jnt` output. They are not experimentally measured loads. `initialEnergy/finalEnergy` include kinetic, strut/tire elastic and gravitational potential energy, using `z=0` as potential datum.

## Verification and limits

`python backend/verify_industry.py` verifies actual default, half-step and changed-parameter solves against an independently integrated Newton-equation reference. It also checks analytical free-fall contact time, nonnegative tire forces, zero force above ground, dissipated energy, rebound release, and native joint-force agreement. It generates `backend/evidence/industry-verification.json`; that local report is not included in the public checkout.

Parameter bounds: body mass 50–10000 kg, wheel mass 5–1000 kg, strut stiffness 5000–1000000 N/m, damping 0–100000 N s²/m², tire stiffness 20000–5000000 N/m, strut length 0.2–2 m, height 0–0.5 m, sink speed 0–5 m/s, gravity 0.1–20 m/s². Common run limits are 0.05–30 s, step 0.0001–0.05 s, at most 20000 steps. Validation checks elastic and conservative damping scales and demands a run beyond first impact.

An energy bound rejects combinations that could compress more than 80% of strut length even without damping. Solver output is also checked against that boundary; there is no silent rod inversion. This is a mathematical validity guard, not a physical stroke-stop model.

Omissions include gas precharge/polytropic stiffening, variable metering, different rebound/compression valves, seal and bearing friction, stroke stops, tire hysteresis, wheel spin-up/braking, oblique impact, pitch/roll, flexibility and material stress. No aircraft load rating, structural safety factor or flight qualification follows from this model.

The constitutive-law and joint syntax follows the pinned official [MBDyn 1.7.3 input manual](https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/documents/mbdyn-input-1.7.3.pdf), sections for rods, turbulent viscoelasticity and scalar-function elastic laws.
