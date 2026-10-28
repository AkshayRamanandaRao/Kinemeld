# Curated upstream models

The source library contains independently published MBDyn input models with
explicit redistribution grants. These are pinned upstream studies, not the
application's original educational templates and not manufacturer-qualified
vehicle or aircraft models. The library keeps the model inputs visible and
provides real solver motion through a generic structural-node result path.

## Available studies

| Study | Source and purpose | Observed compatibility |
| --- | --- | --- |
| Parallel manipulator — triangle | Pierangelo Masarati's three-actuator manipulator, from an example associated with the 2010 ESA multibody workshop | MBDyn 1.7.3: exit 0, normal termination, 6 nodes, 1001 output frames through 10 s |
| Spatial slider-crank — IFToMM benchmark | Three moving rigid bodies linked by revolute, spherical and Cardano constraints | MBDyn 1.7.3: exit 0, 3 nodes, 1252 frames through 5.004 s |
| Double parallelogram — IFToMM benchmark | Six-bar closed linkage with five moving bodies and one tracked dummy point | MBDyn 1.7.3: exit 0, 6 nodes, 1252 frames through 10.008 s |
| Helicopter rotor ground resonance | Gianni Cassoni's four-blade rotor on flexible support, based on Masarati and the Hammond (1974) research problem | Disabled: initial assembly fails on installed 1.7.3 at TotalJoint 10000, rotational degree of freedom Mz; no solved trajectory |

The first three inputs come from the [official MBDyn examples index](https://www.mbdyn.com/Documentation/Examples.html)
and its linked [MBDyn-web source repository](https://github.com/mmorandi/MBDyn-web/tree/a2ec5b9fb70d2431cb486ef20836bc3887034a37/userfiles/documents/examples),
pinned at `a2ec5b9fb70d2431cb486ef20836bc3887034a37`. Their local `.mbd`
filenames contain unchanged upstream bytes. The slight extra final step in two
runs is native solver behavior; it is retained rather than cropped or relabeled.

The [rotor source package](https://github.com/alexal00/MBDynmodels/tree/3b8c753a497be98efe4f49b5d44f5b0608cdd78b/GR_MBDyn/cassoni_model)
is pinned at `3b8c753a497be98efe4f49b5d44f5b0608cdd78b`. All three included
files are present. A separate, explicitly dated adaptation enables native text
output instead of NetCDF-only output; no mechanics or integration settings were
changed. The local `verify.py` script can reproduce a rotor attempt; generated
verification reports and run artifacts are not included in the public checkout.
Initial positions are an input
inspection, not successful dynamics. Diagnose the constraint rank and compatible
solver configuration before enabling it; a newer solver is not a proven fix.

## License and provenance

Each copied input explicitly grants redistribution under **GNU GPL version 2**
in its own header. The catalog therefore records `GPL-2.0-only`, preserving all
copyright notices and the complete license. These input programs retain their
own license; the application's MIT license does not replace it. Website-level
license summaries are not substituted for the individual model headers.

`examples/open-source/catalog.json` is the machine-readable inventory. Every
record contains the source repository, exact commit, immutable raw URL,
SHA-256 for each included file, entrypoint, dependency list, adaptation notes,
node labels, units and compatibility status. The loader checks every file's
hash before creating a run. Changed or missing pinned files are rejected.

`examples/open-source/verification.json` captures the enabled-model runs,
solver version/path, exact deck hashes, native sample counts, final times and
local run IDs. `backend/verify_source_examples.py` repeats that verification.
The original input files themselves are included as corresponding source.
No solver implementation or binary is included in this library.

## Import and inspect

Choose a source example in the library. Its dimensions, solver settings and
constraints come from the pinned input. This import path intentionally exposes
a read-only upstream study: editing a project JSON cannot silently override its
parameters or integration time. Export the exact deck for expert study in
MBDyn, preserving its license and marking your changes.

The initial display uses real native structural-node positions and a labeled
connection graph. Graph edges connect node origins; they are not exact joint
attachment geometry, solid bodies or a CAD reconstruction. Native model files
remain the authoritative mechanical definition. This distinction matters because
rigid-body reference origins and joint attachment points often differ.

Run an enabled model to obtain native node trajectories. The importer matches
only written time steps from `.out` with all node records in `.mov`, checks node
identity/order and finite values, verifies the orientation representation from
`.log`, and requires the requested final time and normal termination. Partial
or failed output stays diagnostic evidence and is never shown as a successful
simulation. Output display may be sampled down to about 2000 frames; CSV retains
every returned solver output frame.

| Channel | Meaning and unit |
| --- | --- |
| `time` | Solver output time, s |
| `x`, `y`, `z` | Global node-origin coordinates, m |
| `rx`, `ry`, `rz` | Native Euler 1-2-3 angles, **degrees** |
| `vx`, `vy`, `vz` | Global linear velocity, m/s |
| `wx`, `wy`, `wz` | Global angular velocity, rad/s |

Each result includes the exact deck, console log, long-form node CSV, native
motion/time/structure files, source metadata and summary. Displacement metrics
measure node-origin motion from its initial position; they do not represent
stress, joint reaction, structural safety or hardware accuracy.

## API and repeatable checks

`GET /api/source-examples` returns `{examples:[...]}`. Only records with
`enabled:true` and `validation.status:"verified"` may run.

`POST /api/source-run` takes exactly `{"id":"srscm"}`. It accepts a catalog ID,
not an uploaded deck, path, URL, command or solver option. The existing loopback,
same-origin and one-job-at-a-time protections apply. Every job gets a fresh
directory and the existing bounded solver launcher.

`POST /api/validate` and `/api/deck` also understand a model such as
`{"model":{"kind":"source-example","sourceExampleId":"srscm"}}`.
Validation checks the pinned inputs; it does not rerun the solver. Source models
have no synthetic reference preview. Result samples use
`{time,nodes:[{id,x,y,z,rx,ry,rz,vx,vy,vz,wx,wy,wz}]}`.
Saved source projects may also carry `sourceRevision` and the ordered
`sourceHashes` array; when present, both must match the current curated bundle.
The result model includes those pins, empty parameters and the source simulation
settings for faithful project reopening.

From `backend/`, run:

```powershell
python -m unittest test_source_catalog -v
python verify_source_examples.py
```

The tests cover unknown/path IDs, digest mismatches, attempted input overrides,
malformed/incomplete frames, non-finite output, orientation and timestamp
requirements, and actual local HTTP request handling. The verification script
runs each enabled source with the configured real MBDyn solver.

## Sources not bundled as runnable models

The [Sky Engineering examples](https://www.sky-engin.jp/en/MBDynExamples/index.html)
include automotive suspension and robot demonstrations, but an explicit reuse
license for their downloadable inputs was not verified. They remain references;
the existence of a download is not treated as redistribution permission.

The official [22-wheel semitrailer archive](https://github.com/mmorandi/MBDyn-web/blob/a2ec5b9fb70d2431cb486ef20836bc3887034a37/userfiles/documents/examples/semitrailerPub.tar.bz2)
contains a real research model and documents custom `wheel4`, GiNaC, NetCDF and
road-profile preprocessing requirements. Its individual files lack the explicit
license headers used to qualify the bundled inputs, so it is not redistributed
here. Its modified vehicle data also cannot be identified with a particular
manufacturer's truck. The flexible-linkage archive depends on generated mesh
and Octave preprocessing files and was likewise not enabled.

No redistributable landing-gear or automotive-suspension dataset was verified
during this pass. Existing application examples in those domains remain clearly
identified as original generic models. No aircraft manufacturer
geometry or other assets without confirmed reuse permission were copied.

These real input/solver workflows provide a foundation for pre/post processing.
They do not yet provide arbitrary MBDyn parsing into an editable GUI, automatic
CAD inertias, mesh import, joint-reaction plots or comparison against published
benchmark accuracy data.
