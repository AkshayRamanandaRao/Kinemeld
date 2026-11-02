# Local closed-loop rotary actuators

Open **Two-link robot arm with local closed-loop actuators**, or select a spatial body and choose **Add controlled rotary actuator**. Choose a free revolute joint, edit the gains, target angle, ramp time and torque limit, then validate and run. Ordinary sinusoidal torques and prescribed joint motion remain separate options. Actuator edits use the existing Undo, project save and stale-result checks.

The model entry is:

```json
{"id":"shoulderMotor","joint":"shoulder","type":"servo",
 "kp":5,"kd":1.2,"targetAngleDeg":30,"rampTime":0.8,"torqueLimit":2}
```

`kp` is N m/rad, `kd` is N m s/rad, the target is degrees relative to the initial hinge pose, the ramp is seconds and the limit is N m. The joint starts at rest about its axis. Up to eight controllers are allowed, one per joint. Prescribed motion and cylindrical joints cannot use this controller. Every run retains the usual model, deck, native output, full CSV and log, plus a controller trace and log.

The reference angle is `target × (1 − cos(pi × t/rampTime))/2` during the ramp, then stays at the target. Its speed starts and ends at zero. The command is `clip(kp × (reference − angle) + kd × (referenceSpeed − speed), ±torqueLimit)`. There is no integral term, automatic tuning or gravity compensation. Saturation and load/friction can leave a tracking error. The bundled example uses illustrative rigid-body inputs and zero gravity.

This is actual sampled co-simulation. A separate trusted Python process receives MBDyn's native relative hinge angle `rz`, relative speed `wz` and time over a blocking loopback TCP stream. It sends bounded torque values through a second native stream. Feedback at time `n` determines a command held during step `n+1`; the initial command is zero. It uses no precomputed trajectory replay, external service, arbitrary script or user-supplied endpoint. This follows the pinned [MBDyn 1.7.3 stream input/output interface](https://www.mbdyn.org/userfiles/documents/mbdyn-input-1.7.3.pdf).

The trace distinguishes `commandTorque`/`commandSaturated`, computed from the current feedback for the next step, from `torque`/`saturated`, held during the step that just converged. The final record has `sent:false`. The result parser checks each command against the PD law, each held command against the previous trace row, feedback against native body motion, and applied torque against native `result.frc` couple output. Servo plots and CSV show the held torque. Angle, speed, commanded angle/speed, tracking error, saturation and power are retained at full resolution.

The ramp must span at least 20 steps and finish within the run. Gain/time-step checks use a conservative body-inertia estimate. Commands and observed motion remain bounded; the supported relative-angle branch is within ±180 degrees and observed speed must resolve to at most 0.1 rad per step. A controller failure stops the solver; Cancel stops both processes and retains partial artifacts. The runtime uses fresh ephemeral ports bound to `127.0.0.1`. Standalone deck export is unavailable for servo models: use **Run simulation** for the managed peer and save the project to retain its setup. A completed run's retained deck records the ports from that run and requires its managed peer.

Controlled runs require a native MBDyn executable with socket support. WSL transport is rejected with an actionable message. Windows native MBDyn 1.7.3 has been exercised here; these checks do not qualify another platform's socket build or physical hardware.

Run the checks with an existing native solver:

```powershell
python -m unittest discover -s backend -p test_rotary_control.py -v
python backend/verify_rotary_control.py path/to/mbdyn.exe
$env:MBDYN_CONTROL_TEST_SOLVER = 'path/to/mbdyn.exe'
node tests/rotary-control-ui.mjs
```

The native verifier compares a single inertia with independent exact integration of each held torque, verifies time-step refinement, positive/negative targets, zero command, saturation, tilted axes, a moving-parent two-link arm and positive/negative joint brakes. It also cancels an actual feedback run and injects a disconnect into an owned test copy of the peer, checking that both processes stop. The [retained numerical report](../examples/rotary-control-verification.json) records nine completed cases and these two cleanup cases. A fresh run writes its scoped report under ignored `verification/rotary-control/`. The browser test covers editor changes, Undo/Redo, actual native Run, plots, trace downloads, full CSV, save/reopen, stale results and Cancel.
