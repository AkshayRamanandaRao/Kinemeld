# Windows desktop host

Build the desktop executable using the steps below, then double-click
`Start MBDyn Studio Desktop.cmd` in the project root. The executable is not
included in a fresh checkout. The app needs the project folder, Python 3.10+,
Microsoft WebView2 Runtime and a configured MBDyn solver; see
[solver setup](../docs/solver.md). The assistant additionally needs a local
Ollama model; see [AI agent](../docs/ai-agent.md). STEP import needs
`cadquery-ocp` in the backend's Python environment; it is not bundled with the
executable. See [STEP geometry](../docs/step-geometry.md).

The desktop host is Rust (Tao, Wry and native file dialogs). Its embedded UI uses
WebView2, Three.js and the local Python solver service; it is not an all-Rust
solver or CAD kernel. Files retain the validated model, saved results, STEP sources and body
attachments; older projects with STL references can still be reopened. Native save makes a backup on replacement and detects external
file changes. Interactive OS file dialogs have not yet been manually qualified.

The snapshot check also identifies an existing project through case and hard-link aliases. If the original is missing, it conservatively treats a different-cased name as the same destination even in a case-sensitive Windows directory; choose a more distinct name to save a copy. It detects changes observed before the check; it cannot make noncooperating external writes atomic with the subsequent replacement. Save locks are per path, so concurrent saves through distinct hard-link names are not serialized. Retain replacement backups when coordinating with other writers.

To build on Windows with Rust MSVC and Visual Studio C++ tools installed:

```powershell
cargo build --manifest-path native/Cargo.toml --locked --release -p mbdyn-studio-desktop
Copy-Item native/target/release/mbdyn-studio-desktop.exe native/MBDynStudio.exe
```

A hidden self-check can be run with `native/MBDynStudio.exe --smoke`. A public
binary release still needs packaging, full third-party attribution and installed
workflow qualification. `native/target`, the binary and machine solver config are
excluded from source distribution.

## Application resources and user data

On Windows the desktop reads application resources from the extracted application folder and stores runtime data in `%LOCALAPPDATA%\MBDynStudio`. This includes `runs/` and the WebView2 profile. Set `MBDYN_STUDIO_DATA_DIR` to an absolute writable folder to override this location. If the user-data directory cannot be created, startup reports an error. Browser development without that override retains the existing workspace layout.

Desktop solver and agent settings are `%LOCALAPPDATA%\MBDynStudio\solver.json` and `agent.json`. If a user setting is absent, the application reads the corresponding legacy `backend/solver.json` or `backend/agent.json` from the resource folder without copying, overwriting or deleting it. A present user setting takes precedence, including when invalid. The same read-only fallback applies to the old tour preference. New preferences and runs are written to user data; old run artifacts remain accessible by their existing run URLs. If the same run ID exists in both roots, artifacts come exclusively from the user-data run folder, never a mixture. This is a compatibility fallback, not automatic migration or cleanup.

## Local Windows package

After the executable is built, PowerShell 7 can create an application ZIP with
the desktop executable, Python service, interface, CAD examples and notices:

```powershell
pwsh -NoProfile -File native/package-windows.ps1 -IncludeLocalSolverConfiguration
```

The output is `native/dist/MBDynStudio-Windows-local.zip`. Extract it to a
writable folder and use the included `Start MBDyn Studio Desktop.cmd`. The
switch copies this machine's `backend/solver.json`, which points at the
existing WSL solver path and will generally need changing on another machine.
Without that switch the package starts without an active solver unless a user solver setting or PATH solver is already available; configure it as described in `docs/solver.md`. Python, `cadquery-ocp`, WebView2,
WSL, MBDyn and Ollama are **not** included or installed by this ZIP. Existing
run history, Python caches, build toolchains and agent configuration are never
packaged. `package-manifest.json` records the SHA-256 of each included file.

Before rerunning packaging, move or rename any archive at the fixed output path
that you want to keep: the packaging script deletes the previous archive first.
The archive is a local build, not a self-contained installer or a release with
audited redistribution notices.

## Optional private Python runtime staging

The desktop first honors `MBDYN_STUDIO_PYTHON`, then checks `runtime/python/python.exe`, and otherwise uses `python` on `PATH`. A present incomplete private runtime is reported rather than silently ignored. A supplied runtime can be included in a separately named **test ZIP** only after its file inventory, pinned source-wheel artifacts and component/native notice references pass the packaging checks. The checks establish identity, not redistribution rights or a working clean-machine installation. No Python, OpenCascade or MBDyn runtime is bundled by default. A local QA build of the hash-pinned embedded runtime has exercised STEP and the configured solver without system Python on PATH; this is not a clean-machine release or licensing approval. See [private runtime staging](runtime-lock/README.md) for the worked preparation command, requirements and limitations.

## Project-open confirmation

The desktop keeps the previous project session until the newly opened document
is applied. It confirms the new session with a transaction-specific acknowledgement,
and conservatively treats it as dirty until a second clean-state confirmation.
If a response is delayed or lost, the app retries and reports the pending state;
saving and running wait for confirmation. Edits made during the first wait stay
unsaved. If an editable field has focus, finish editing it before the clean-state
check proceeds. During an unacknowledged clean-state check, controls are temporarily
locked so new input cannot be lost; they unlock when confirmation arrives.

If desktop communication never recovers, an unconfirmed project cannot be saved
through the host; closing may lose unsaved input. The lock covers normal application
input and guarded asynchronous actions; it does not cover injected scripts or other
external process manipulation.
