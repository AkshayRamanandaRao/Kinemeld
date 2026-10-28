# Solver setup and verification

Kinemeld generates and runs MBDyn input decks as a separate process. It does
not reproduce MBDyn's solver implementation. The current integration is pinned
to **MBDyn 1.7.3**, the official archived release, for a reproducible baseline.
The project recommends its development branch for newer capabilities; this
prototype does not claim coverage of that branch.

## Tested configuration

The tested configuration uses a WSL Linux distribution with GCC/G++, gfortran,
and a local build in `backend/vendor/mbdyn-1.7.3`. A solver configuration points
to that build through WSL. A different machine must supply its own distribution,
toolchain and solver path.

Run the app from normal Windows PowerShell. The restricted Codex command sandbox
can deny WSL and local socket access; successful host checks must be distinguished
from those sandbox denials.

The source archive came from the download link on the
[official download page](https://www.mbdyn.org/Download.html):

`https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz`

Downloaded SHA-256:
`3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d`.
This is the locally recorded digest of the HTTPS download, not a claimed
publisher signature. The Windows binary link in the installation guide had an
unresolvable host during setup; the current development snapshot host also timed
out. The official archived source remained available.

## Rebuild on an existing Linux/WSL environment

Prerequisites: GCC, G++, GNU make, gfortran, Python 3 and tar. On Ubuntu, the
missing compiler can be installed with `apt-get install gfortran`; review package
changes on your own machine. The build script never installs system packages.

From Windows, replacing the distribution name and path with your own:

```powershell
wsl -d YOUR_DISTRIBUTION -- bash /mnt/path/to/mbdyn-studio/backend/build_solver.sh
```

The script checks the archive digest, compiles with four jobs and uses C++11 plus
the legacy Fortran argument-compatibility flag required by this archived release.
No MBDyn source modification is needed. The script leaves the original source,
license and build logs in place. It generates configure/build logs in
`backend/evidence`; these local artifacts are not included in the public checkout.

For the Windows desktop, create `%LOCALAPPDATA%\MBDynStudio\solver.json` to identify the installed solver. `MBDYN_STUDIO_DATA_DIR` may override that per-user folder. The browser development server continues to use `backend/solver.json` by default. If a desktop user file is absent, the old resource-folder `backend/solver.json` is read as a fallback; a present user file always wins and is never overwritten automatically:

```json
{"mode":"native","executable":"/absolute/path/to/mbdyn"}
```

For Windows with WSL:

```json
{"mode":"wsl","distribution":"YourExistingDistro","executable":"/absolute/linux/path/to/mbdyn"}
```

The HTTP API cannot change this executable or submit arbitrary input-deck text.
Only validated physical parameters enter the generated decks. Files written by
each run are retained in a new `runs/<run-id>` directory under the desktop user-data folder, or under the workspace for browser development. Legacy workspace run artifacts remain readable without being moved. The solver has a
180-second WSL timeout with a 3-second kill grace; the Windows caller has a
185-second outer deadline. Native-mode subprocess execution also has a 185-second
deadline. The app accepts one active solver run at a time.
Timeout exit 124 is reported explicitly and does not imply numerical
nonconvergence; exit 137 can indicate the shutdown grace expired or an external
SIGKILL. Logs and partial native outputs remain in the run folder. Concurrent
compilation and WSL filesystem load can substantially increase elapsed time even
when the model converges. A run that exceeds the bound still returns a failure,
never a successful partial trajectory.

## Supported model families

| Model | Physics | Parameters | Solver representation |
| --- | --- | --- | --- |
| Gravity pendulum | Ideal point mass, massless rigid link, gravity, no friction | mass kg, link length m, release angle deg from vertical down, gravity m/s² | One dynamic structural node, point mass, revolute pin, gravity |
| Damped oscillator | One translating mass, linear spring, linear viscous damper, no gravity | mass kg, stiffness N/m, damping N·s/m, initial displacement m | Clamped support, dynamic body, inline guide plus prismatic orientation constraint, deformable displacement joint |
| Coupled double pendulum | Two point masses, two massless rigid links, gravity, two coupled degrees of freedom | mass1/mass2 kg, length1/length2 m, angle1/angle2 deg from vertical down, gravity m/s² | Two dynamic structural nodes and bodies, one revolute pin and one revolute hinge |
| Quarter-car suspension | Two vertical masses about loaded equilibrium, linear suspension, prescribed road bump | masses, stiffness/damping, bump height/start/duration | Vertical guides, deformable displacement suspension/tire joints, prescribed tire prestrain |
| Landing-gear drop | Two falling masses, quadratic damping, equivalent linear strut spring, unilateral elastic tire contact | masses, stiffness/damping, rest length, drop height/sink speed | Vertical guides, turbulent viscoelastic rod, multilinear tire contact, gravity |
| Gear deployment | Three massive rigid links in a closed four-bar with prescribed main-strut angle | link lengths, pivot/attachment coordinates, masses, angle sweep | Planar joints and imposed rotation with geometric closure verification |

The three introductory examples run for 5 seconds by default. The pendulum and double pendulum use
0.005-second steps; the oscillator uses 0.0025-second steps. The latter was
refined after measurement against its independent reference, as detailed below.
The suspension uses 3 seconds / 0.0005-second steps; drop test uses 1.5 seconds /
0.00025-second steps; deployment uses 3 seconds / 0.01-second steps. Detailed
physics, channels and limitations are in [suspension](industry-suspension.md),
[landing drop](industry-landing-drop.md), and [deployment](industry-gear-deployment.md).

For the oscillator, the body's positive rotational inertia is arbitrary because
all rotations are constrained; only its translational mass enters the modeled
degree of freedom. The spring's zero-force position is X=0. The introductory examples start
with zero velocity. Global X is horizontal, Z is up, and Y is out of the motion
plane. The result's `angle` is in degrees; `velocity` is rad/s for pendulum and
m/s for oscillator. For the double pendulum, `x/y/z`, `angle` and `velocity`
describe the first mass/link. `x2/y2/z2` are the second mass's absolute position;
`angle2` and `velocity2` are the second link's absolute angle and angular rate.
Both angles are measured from vertical down, not relative to the preceding link.
CSV retains all generated output samples. The display may
subsample long runs to approximately 2,001 points, retaining the last point.

The input format follows the version-matched
[MBDyn input manual](https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/documents/mbdyn-input-1.7.3.pdf),
particularly structural nodes, rigid bodies, constraints and constitutive laws.
Decks in `examples/` are original parameterized examples, not copied application
internals. JSON models can be edited and re-exported; imports reject unknown
fields to avoid silently dropping unsupported physics.

## Reference preview versus solver result

**Reference preview** never launches MBDyn. It integrates the nonlinear pendulum
and coupled double-pendulum equations with RK4, and evaluates the damped
oscillator's closed-form solution. The double-pendulum reference solves its
two-by-two Lagrangian mass matrix at each stage; it includes the cross term
between the two angular velocities. Both link lengths and total mechanical
energy are checked independently of the MBDyn output parser.
Suspension and landing-drop previews integrate their coupled Newton equations
with four RK4 substeps per requested sample; deployment preview uses independent
circle-intersection geometry. Reference calculations do not call MBDyn.
It is useful for learning and comparison, but is always identified separately.
**MBDyn** results require a successful solver exit, parseable `.out` and `.mov`
files, aligned output timestamps, finite values and the requested final time.
An unavailable solver or convergence error cannot produce a successful result.
MBDyn 1.7.3 can output one fixed step beyond the nominal end time (a
5-second run at 0.005-second steps can finish at 5.005 seconds). The backend preserves these actual
solver timestamps; `metrics.duration` reports the last recorded time.

Each real run stores the project, generated deck, full console log, native
output, CSV, deck digest and summary. Download links are restricted to known
files in that run. The server binds to 127.0.0.1, rejects other Host/Origin values,
requires JSON for mutations and limits request bodies to 64 KiB.

The local interaction budget is 0.05–30 simulated seconds and at most 20,000
integration steps. Validation bounds numeric parameters and rejects a step that
is too coarse for the model's fastest characteristic rate. A warning recommends
refinement before drawing conclusions from a coarse but permitted step.

## Tests

From the app folder:

```powershell
python -m unittest discover -s backend -p 'test_*.py'
python backend/verify_real.py
python backend/verify_coupled.py
python backend/verify_industry.py
python backend/verify_gear_deployment.py
```

The first command checks invalid inputs, parameter-to-deck changes, reference
period/frequency/decay, the HTTP workflow and same-origin boundaries. The second
requires actual MBDyn and runs the three introductory examples plus changed physical parameters
(six actual simulations, including unequal masses and lengths in the coupled model).
It compares their trajectories with independent references and checks constraint
error or energy decay. Its report is
`backend/evidence/real-solver-verification.json`; only an `ok: true` report proves
those real checks passed. The third command separately checks both links and
measures oscillator time-step convergence; its report is
`backend/evidence/coupled-and-convergence.json`.
The industry script runs six actual simulations (default, changed parameters and
half step for each force model), compares independent reference trajectories,
checks reconstructed forces against MBDyn joint output, and verifies contact
onset/release. Its report is `backend/evidence/industry-verification.json`.
Deployment verification runs default, changed geometry, half step and reversed
sweep against independent circle geometry and checks actual loop closure; see
`backend/evidence/gear-deployment-verification.json`. These commands generate
local reports; the public checkout does not include them.

Measured over 5 seconds, the oscillator's historical 0.005-second step produced
1.223 mm maximum displacement error (1.223% of the 100 mm initial displacement),
which **did not meet** a 1% reference target. Refining to 0.0025 seconds reduced
that error to 0.306 mm (0.306%), a 3.99-fold reduction, and this is now the default.
These are measured example errors, not a universal accuracy guarantee.
The double-pendulum default's maximum reference differences were 0.0777 degrees
for link 1 and 0.0851 degrees for link 2; maximum link-length error was
0.000000673 m. The unequal-mass/length case was also run and checked.

The default suspension/drop displacement errors relative to reference were under
0.004 mm; halving steps reduced wheel error by about 3.97x / 3.85x. A lower-damped
drop variant released tire contact twice and remained within 0.074 mm of its
independent reference. These statements cover the specified reduced force laws.

These checks do not establish arbitrary-mechanism or general contact support,
flexible bodies, fatigue, safety or industry/flight qualification. The drop tire's
one-dimensional unilateral law is the only contact model currently exposed.
The deployment example is an original generic mechanism inspired by a spacecraft
workflow, not an authentic Shuttle geometry or hydraulic/locking simulation.

## License boundary

MBDyn 1.7.3's source copyright headers specify GNU GPL version 2. The archived
package's `COPYING` file is empty and `mbdyn --license` directs users to GNU;
the official GNU text is retained as `backend/MBDyn-GPL-2.0.txt`.
Preserve its notices and provide the corresponding source and license if you
redistribute its binary. The app's original source is licensed separately by its
root LICENSE; linking to an external solver does not erase that solver's terms.

See also the [official installation guide](https://www.mbdyn.org/Installation.html).
