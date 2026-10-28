# Native project and solver core

This original Rust crate supplies the Windows desktop application's project lifecycle and typed local API client. It **does not port MBDyn or the Python model generator to Rust**. The native shell retains the existing Three.js frontend; a hidden, owned Python service validates models and invokes the separately installed MBDyn 1.7.3 WSL process. No upstream GPL implementation is copied into this crate.

## Public interface

`BackendService::start(workspace, python)` starts a dedicated Python service on an available `127.0.0.1` port. It returns `client()`, `log_path()`, `is_running()` and `stop()`. The process is launched without a console window on Windows. An existing web workbench service is neither reused nor stopped. The child handle establishes ownership; shutdown never enumerates processes or kills unrelated jobs.

`BackendClient` exposes `health`, `status`, `examples`, `validate`, `validate_model`, `deck`, `deck_model`, `preview`, `run`, `run_model`, `source_catalog`, `run_source` and restricted `download`. Template requests use `Model`; source-model and project validation preserve `serde_json::Value`. Source projects are validated before `run_model` selects their catalog ID. `SimulationResult` is a typed envelope with opaque sample/provenance JSON so arbitrary native node trajectories are retained. Non-2xx responses preserve their entire payload in `Error::Backend { status, payload }`, including failed run IDs and logs.

Calls are blocking; the shell must use a worker thread. The request body limit matches Python's 64 KiB boundary; response/artifact reads are bounded at 64 MiB. The solver request deadline is 210 seconds, allowing the service's existing 180-second solver limit and 185-second outer process deadline. The local server emits explicit `Content-Length`; unsupported HTTP framing is rejected rather than guessed. No external URL, executable string or arbitrary input deck is accepted through the bridge.

The shell should refuse closing while a solver request is busy, then call `stop`. Dropping the service stops its owned Python process. Force-closing the whole desktop application during a solve does not promise instantaneous Linux cancellation; the WSL solver already has its own bounded timeout. Cancellation is not exposed as a supported workflow.

## Portable projects

`ProjectDocument` retains `format: "mbdyn-studio/1"`, `schemaVersion: 1`, raw `model`, optional raw `result`, `view` and unknown top-level JSON properties. Legacy envelopes without `schemaVersion` and raw model JSON are readable. Source catalog IDs, revisions/hashes, trajectories, logs and a full CSV string can be embedded in `result`. The cap is **32 MiB**, tested with a result exceeding 16 MiB. `serde_json` arbitrary-precision/roundtrip features preserve scientific-number values across storage.

`ProjectSession` provides:

```rust
ProjectSession::new(document)
ProjectSession::open(path)
session.document()
session.path()
session.is_dirty()
session.replace_document(document)
session.save()
session.save_as(path, SaveMode::CreateNew)
session.save_as(path, SaveMode::ReplaceExisting)
```

The UI owns path dialogs and explicit overwrite intent. `CreateNew` never replaces a competing file. Ordinary `save` compares the current on-disk bytes with the opened/saved snapshot and rejects external edits. Writes are flushed to a sibling temporary file first. Windows replacement uses `ReplaceFileW` with a unique retained backup; new files use a non-overwriting hard link. The exact pre-save file remains in `.filename.mbdyn-backup-*`. A per-file save lock prevents competing application windows from racing. Failed replacements retain recovery candidates and report their paths. Backups are not automatically deleted.

If the app crashes during saving, inspect the project and adjacent `.mbdyn-new-*` / `.mbdyn-backup-*` files before removing a stale `.mbdyn-save-lock`. No background recovery overwrites a file. The tested target is Windows NTFS; filesystems without hard-link or replacement support return an explicit save error. Non-Windows fallback behavior has not been qualified.

Project structural validation is separate from physical validation. Work in progress may be saved; a candidate opened file can be validated by the backend and represented by the UI before that session replaces the current session. Unsupported formats, malformed files and oversized files leave the current in-memory document untouched.

## Verification

Use the workspace's isolated Rust MSVC toolchain and VS18 x64 developer environment:

```text
cargo test -p mbdyn-studio-core --manifest-path native/Cargo.toml
cargo run -p mbdyn-studio-core --example verify_local --manifest-path native/Cargo.toml -- <workspace> <python-executable>
```

Six focused Windows tests cover Unicode filenames, replacement backups, external-edit conflicts, create-new collision protection, source/legacy projects, exact scientific numbers, >16 MiB stored results, oversized/malformed files, real loopback HTTP failure payloads, and generic trajectory/provenance retention.

The compiled `verify_local.exe` starts an owned service, runs a parameter-edited pendulum, runs the authentic upstream IFToMM spatial slider-crank catalog model, retrieves the full CSVs, saves and reopens both projects without changing their data, and verifies service shutdown. Its machine-readable record is `evidence/windows-host-verification.json`. This demonstrates native Windows core execution; native shell interaction and GUI visual acceptance are separate checks owned by the desktop application.

Platform references: [Microsoft ReplaceFileW](https://learn.microsoft.com/windows/win32/api/winbase/nf-winbase-replacefilew) and [Rust non-overwriting hard-link creation](https://doc.rust-lang.org/stable/std/fs/fn.hard_link.html). Windows canonical paths are deliberately normalized only when launching Python because its WSL drive mapping consumes ordinary drive paths; project file identity retains its canonical form.
