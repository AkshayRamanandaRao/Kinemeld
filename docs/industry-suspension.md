# Quarter-car road-bump workflow

This is an original, parameterized two-degree-of-freedom engineering model of a vehicle corner. Use it to compare ride acceleration, body motion, suspension travel and tire-load variation. It is not a full suspension linkage, handling model, or manufacturer vehicle.

## Physical model

The sprung mass represents one corner of the body; the unsprung mass represents its wheel and associated moving hardware. Both translate vertically. A linear spring and viscous damper connect them; a linear tire spring connects the wheel to a prescribed road. All coordinates are **upward displacements from the loaded static equilibrium**. Gravity is already balanced in the equations; it is used to reconstruct total tire load.

Let `zs`, `zu` be the two displacements and `r` the road height. With `d = zs - zu` and relative velocity `dv = vs - vu`:

```text
Fs = -ks*d - cs*dv                    upward dynamic force on the body
Ft_dynamic = kt*(r - zu)              dynamic tire force on the wheel
ms*as = Fs
mu*au = -Fs + Ft_dynamic
Ft_total = (ms + mu)*g + Ft_dynamic
```

The road is zero outside the bump and `H/2 * (1 - cos(2*pi*(t-t0)/T))` during it. This has continuous height and slope at entry and exit. MBDyn represents the prescribed road as tire prestrain, so the tire sees `zu-r`. No external body load is invented.

The two-mass equilibrium formulation follows the public [KU Leuven quarter-car model](https://fet-edu-em.pages.gitlab.kuleuven.be/computer-aided-simulation/course-material/t42cms-cas-book/t42cms-cas-lectures/Examples/Quarter_car_suspension/Quarter_car_suspension_model.html). The [University of Michigan model](https://ctms.engin.umich.edu/CTMS/index.php?example=Suspension&section=SystemModeling) supplies the same coupled Newton equations with additional optional actuator/tire-damper terms; those terms are absent here. Parameters below are illustrative choices, not measured vehicle data.

## Default inputs

| Parameter | Value | Unit |
|---|---:|---|
| Sprung mass | 300 | kg |
| Unsprung mass | 40 | kg |
| Suspension stiffness | 18000 | N/m |
| Suspension damping | 1500 | N s/m |
| Tire stiffness | 180000 | N/m |
| Bump height | 0.05 | m |
| Bump duration | 0.25 | s |
| Bump start | 0.5 | s |
| Gravity for static load | 9.81 | m/s² |
| Run duration / step | 3 / 0.0005 | s |

1. Open **Quarter-car road bump** and validate. The estimated undamped natural frequencies are about 1.175 and 11.204 Hz.
2. Run MBDyn. Inspect body/wheel displacement and suspension travel, then tire load and body acceleration.
3. Increase suspension damping or change body mass and rerun. Compare travel reduction against acceleration and settling behavior; more damping is not universally better.
4. Halve the step to check sensitivity, particularly for short bumps and stiff tires.
5. Export the project, original `.mbd` deck, CSV and solver log to keep a reproducible experiment.

## Channels and interpretation

`zSprung/zUnsprung/road/suspensionTravel` are metres; `vSprung/vUnsprung` are m/s; `aSprung/aUnsprung` are m/s². `suspensionForce` is the **dynamic** upward body force in N. `tireForce` is the **total** upward tire force, including static load. Common `z/value` equals `zSprung`; `velocity` equals `vSprung`; common angle is zero. Any visual body/wheel offsets in the GUI are display geometry, not additional physical displacements.

Forces and accelerations are reconstructed from actual solver positions and velocities using the laws above. They are not measurements. The verification script separately compares force reconstruction with MBDyn's `.jnt` forces, so a wrong sign or wrong prestrain interpretation cannot pass solely through the reference ODE.

Reported diagnostics include peak/RMS body acceleration, maximum travel, force peaks and minimum tire load. RMS is over the complete simulated record, not an ISO-weighted ride-comfort measure. A negative total tire load sets `contactAssumptionViolated=true`: this linear model has left its assumed continuous-contact regime. It must not be interpreted as a tensile road force. The model does not automatically switch to a different contact law.

## Verification and bounds

`python backend/verify_industry.py` runs actual defaults, edited parameters and half-step cases for both industry models. It checks independent RK4 motion/forces, MBDyn joint-force consistency, and refinement. It generates `backend/evidence/industry-verification.json`; the associated run IDs retain full CSV and native outputs in `runs/`. These generated files are not included in the public checkout.

The first verified default produced 37.779 mm peak body displacement, 36.964 mm maximum suspension travel, and tire load between 1887.6 and 4870.6 N. The independent body/wheel displacement errors were below 0.003 mm. These are numerical agreement results for this idealized model, not validation against a physical vehicle.

Parameter bounds: body mass 50–5000 kg, wheel mass 5–500 kg, suspension stiffness 1000–300000 N/m, damping 0–30000 N s/m, tire stiffness 10000–3000000 N/m, bump height 0–0.2 m, duration 0.03–3 s, start 0.01–10 s, gravity 0.1–20 m/s². Common run bounds are 0.05–30 s, step 0.0001–0.05 s and at most 20000 steps. Validation additionally requires a complete bump and resolves the fastest modal/damping/road time scale.

Omissions: suspension geometry, camber/toe, pitch/roll, tire enveloping/damping, bump stops, friction and wheel lift. A production vehicle study needs calibrated parameters, more degrees of freedom and experimental correlation.

MBDyn input definitions come from the pinned official [1.7.3 input manual](https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/documents/mbdyn-input-1.7.3.pdf), especially cosine drives, prestrain, deformable displacement joints, and linear viscoelastic laws.
