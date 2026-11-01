# Project format

A Kinemeld project is one UTF-8 JSON file with the extension `.mbdyn-studio`, at most 32 MiB.
It holds the physical model, the latest result with its full solver CSV, the view, and the
original CAD files with their attachments, so a project opens identically on another machine.

```json
{
  "format": "mbdyn-studio/1",
  "schemaVersion": 1,
  "model": { "kind": "spatial-assembly", "name": "Wheel-end drop test", "bodies": [], "joints": [] },
  "result": { "source": "MBDyn", "runId": "…", "samples": [], "csvText": "…" },
  "view": { "selection": "node-wheel", "signal": 6, "camera": [1.6, -0.75, -0.28], "study": {} },
  "assets": { "step": { "files": [], "bindings": {} } }
}
```

| Field | Required | Contents |
| --- | --- | --- |
| `format` | yes | Always `mbdyn-studio/1`. |
| `schemaVersion` | no | `1`; files without it are read as version 1. |
| `model` | yes | The physical model. `kind` and `name` are always present; the rest depends on the kind (`spatial-assembly`, `planar-assembly`, the parametric templates, or a pinned upstream example). Units are SI, angles in degrees. |
| `result` | no | The result shown when the project was saved: its source (`MBDyn` or `Reference preview`), run ID, up to 2,001 displayed samples, and for MBDyn runs the full solver CSV (`csvText`). |
| `view` | no | Selection, plot quantity, frame, camera and target, trail and symbol settings, the parameter study set-up (`study`: input path, values, response), and the bounded design-search draft (`designSearch`). |
| `assets` | no | `step`: the original STEP files (bytes, SHA-256, name) and their attachments to bodies with the pose at attachment and an occurrence identity; `reference`: an older visual STL reference. |

On open, Kinemeld validates the model with the same checks as **Validate model**, checks
the saved result against the model, and restores the CAD from the stored files; if any step
fails, the project is not opened and the current one is kept. A result whose model differs
from the project's model opens as stale. Parameter study results and pinned comparison runs
are not saved; the study set-up is.

Models are validated strictly: a model field the release does not know is reported as
*Unsupported field* and the project is not opened, so a model is never solved with part of
it silently ignored. Outside the model, unknown view settings are ignored, and the desktop
app keeps unknown top-level fields when it saves. Its crash-recovery snapshot
(`recovery/autosave.json`, format `kinemeld-recovery/1`) wraps the same document.

## Compatibility

From 1.0 on:

- Every 1.x release opens projects saved by any earlier 1.x release and by 0.2 to 0.9.
- Within 1.x the format stays `mbdyn-studio/1`. Changes are additive: new optional fields
  with defaults that reproduce the earlier behaviour. Fields are not renamed, removed or
  given a new meaning.
- A change that cannot be additive would introduce `mbdyn-studio/2` in a new major version,
  together with a converter from version 1.
- Additions so far: 1.1 added the optional contact fields `friction` (Coulomb coefficient,
  default 0) and `slipVelocity` (m/s, default 0.05).
- Current development adds optional free-revolute `joint.friction`, sphere-pair
  contact, `jointTorques` entries with `type: "servo"`, the `flexible-link` template
  and `view.designSearch`. Omission preserves the earlier rigid-model behavior.
  A saved servo result includes recorded controller metadata and full CSV fields;
  separate native logs/controller traces remain in that machine's run store.
  Design rankings are session data; the project retains their configuration and
  the exported design table retains the evaluated results.
- Compatibility runs forward in time: a project that uses a model feature added in a later
  release opens in that release or newer. An older release refuses it with *Unsupported
  field* rather than solve it without the feature.

`backend/test_project_compatibility.py` validates every project shipped in `examples/` —
the featured studies and engineering examples, several of them unchanged since before 0.2 —
checks them against these rules, and checks that an unknown model field is refused.
