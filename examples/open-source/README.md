# Upstream MBDyn model library

These are real upstream simulation inputs, separate from the application's
original editable templates. `catalog.json` pins repository revisions, source
URLs, per-file SHA-256 digests, dependencies, units and actual compatibility.

The simulation input files in `triangle/`, `srscm/`, `6barmech/`, and the
`original/` and `runnable/` directories of `rotor-ground-resonance/` are
**GPL-2.0-only**, as expressly stated by their original file headers. Preserve
those copyright notices and the supplied [GPL text](GPL-2.0.txt). The parent
application's MIT license does not relicense these third-party inputs.
Catalog metadata, verification scripts and original explanatory documentation
are covered by the application's MIT license. No upstream solver implementation,
model artwork or proprietary CAD geometry is copied into the app code.

| Input | Status with installed MBDyn 1.7.3 |
| --- | --- |
| Parallel manipulator (`triangle`) | Real run completed, 6 nodes, 1001 output frames |
| IFToMM spatial slider-crank (`srscm`) | Real run completed, 3 nodes, 1252 output frames |
| IFToMM double parallelogram (`6barmech`) | Real run completed, 6 nodes including a tracked dummy point, 1252 output frames |
| Helicopter rotor ground resonance | Disabled: initial assembly failed; source, adaptation and diagnostics retained |

The three enabled files are byte-for-byte upstream inputs; only their local
filenames add `.mbd`. The rotor package preserves all original inputs and
separately labels the text-output adaptation. It is **not** an enabled example.

`verification.json` records repeatable runs through the application's catalog
backend. Its run IDs refer to local `runs/` evidence; they are not remote services.
The failure record for the rotor is in its own folder. Verification establishes
source identity, solver completion and complete finite trajectories. It does not
establish accuracy against published reference solutions or industrial fitness.

See [the user guide](../../docs/open-source-examples.md) for loading, result units,
native output downloads, excluded sources and how to repeat the checks.
