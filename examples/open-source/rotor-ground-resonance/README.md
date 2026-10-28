# Helicopter rotor ground resonance

This is Gianni Cassoni's four-blade rotor on a flexible support, based on a
generic rotor model by Pierangelo Masarati and the Hammond (1974) ground-resonance
study. It is an upstream research model, not an original Studio demonstration,
an aircraft landing-gear model, or a validated aircraft digital twin.

Source: [pinned upstream directory](https://github.com/alexal00/MBDynmodels/tree/3b8c753a497be98efe4f49b5d44f5b0608cdd78b/GR_MBDyn/cassoni_model).
The four input files each explicitly permit redistribution under GPL version 2.
Their notices and complete GPL text are retained. This model's license is
separate from Kinemeld's application license. No CAD geometry, photographs,
video, or third-party assets are included.

## Compatibility

**Unsupported on the installed MBDyn 1.7.3 configuration.** The bounded native
solver test exits with code 1 during initial assembly, before a completed
time step or motion result. The actual diagnostic is:

```text
NaiveSolver: ENOPIV(133)
Initial assembly failed because no pivot element could be found for column 134
(TotalJoint(10000): dof(6) Mz); aborting...
```

The deck reads structural node labels 0, 100, 200, 10000, 11000, 12000, 13000 and
14000. Those observations are an input inventory, not solved motion. The requested
duration is 60 seconds with a 0.001-second time step; no achieved final time is
claimed.

Before enabling this model as a ready-to-run example, diagnose the initial
assembly rank at joint 10000 using an appropriate MBDyn release/configuration
and the upstream author's model assumptions. A newer solver has not been tested
and is not guaranteed to resolve the failure. Record any future changes and
rerun the full verification. No mechanical or numerical settings were altered
to bypass the failure here.

## Contents and reproduction

- `original/`: four exact upstream files, checked against Git blob hashes.
- `runnable/`: the same model with native text output enabled; see
  `MODIFICATIONS.md`. All three includes remain byte-identical.
- `provenance.json`: pinned source URLs, author, license evidence and hashes.
- `verification.json`: actual exit code, solver version, elapsed time, input
  hashes and retained diagnostic text.
- `verify.py`: source-integrity check and bounded solver execution through
  Studio's existing `backend/solver.py` configuration.

From this directory run `python verify.py`. Raw jobs are retained in `.runs/`
and ignored by Git. A failed verification returns a nonzero process status.
No result curves or animations are bundled, because no completed simulation was
obtained with the installed solver.
