# Desktop host

The desktop host is a small Rust program (Tao, Wry and native file dialogs) that starts the
local Python service and shows the interface in the operating system's web view: WebView2 on
Windows, WKWebView on macOS and WebKitGTK on Linux. It is not an all-Rust solver or CAD kernel.
Prebuilt archives for all three platforms are published on the
[releases page](https://github.com/AkshayRamanandaRao/Kinemeld/releases); see the main README
for their requirements.

The app needs its resource folder (backend, frontend, examples), Python 3.10+, and an MBDyn
solver — configured as in [solver setup](../docs/solver.md), on `PATH`, or bundled at
`solver/bin/mbdyn` inside the application folder. STEP import needs `cadquery-ocp` 7.9 or 8 in the
backend's Python environment (`pip install -r requirements.txt`). The assistant additionally
needs a local Ollama model; see [AI agent](../docs/ai-agent.md).

Python is found from `MBDYN_STUDIO_PYTHON`, then an application-local runtime
(`runtime/python/python.exe` on Windows, `runtime/python/bin/python3` elsewhere), then
`python` (Windows) or `python3` on `PATH`. On macOS the app reads its resources from
`Kinemeld.app/Contents/Resources/app`; elsewhere it searches the executable's folder and its
parents for `backend/server.py`. `MBDYN_STUDIO_WORKSPACE` overrides both.

## Build

Install Rust (stable) and the platform web-view development files, then build from the
repository root:

- **Linux:** `libwebkit2gtk-4.1-dev libgtk-3-dev libsoup-3.0-dev libxdo-dev` (Debian/Ubuntu names).
- **macOS:** Xcode command-line tools.
- **Windows:** Rust MSVC toolchain and Visual Studio C++ build tools; WebView2 Runtime to run.

```bash
cargo build --manifest-path native/Cargo.toml --locked --release -p mbdyn-studio-desktop
```

The executable is `native/target/release/mbdyn-studio-desktop` (`.exe` on Windows). Run it
from inside a source checkout, or package it with the resources:

```bash
python3 scripts/package_release.py --platform linux --binary native/target/release/mbdyn-studio-desktop --version 0.2.0 --solver build/solver
```

`scripts/bundle_solver.sh path/to/mbdyn build/solver` prepares a relocatable solver folder
(stripped binary, compiler runtime libraries, GPL notice and source pointer). A hidden
self-check runs a real MBDyn job through the embedded viewer and saves and reopens a project:
`kinemeld --smoke` (use `xvfb-run` on a headless Linux machine). It writes
`runs/native-smoke-report-<pid>.json` in the user-data folder.

On Windows the original instructions still apply:

```powershell
cargo build --manifest-path native/Cargo.toml --locked --release -p mbdyn-studio-desktop
Copy-Item native/target/release/mbdyn-studio-desktop.exe native/MBDynStudio.exe
```

Then double-click `Start MBDyn Studio Desktop.cmd` in the project root.

Files retain the validated model, saved results, STEP sources and body attachments; older
projects with STL references can still be reopened. Native save makes a backup on
replacement and detects external file changes.

The snapshot check also identifies an existing project through case and hard-link aliases. If the original is missing, it conservatively treats a different-cased name as the same destination even in a case-sensitive Windows directory; choose a more distinct name to save a copy. It detects changes observed before the check; it cannot make noncooperating external writes atomic with the subsequent replacement. Save locks are per path, so concurrent saves through distinct hard-link names are not serialized. Retain replacement backups when coordinating with other writers.

## Autosave and crash recovery

While a project has unsaved edits, the desktop writes a recovery snapshot once editing pauses
for 15 seconds, and at least once a minute while editing continues. The snapshot is
`recovery/autosave.json` in the user-data folder below. It is written to a temporary file,
flushed to disk and renamed over the previous snapshot, so a crash or power loss during a
write leaves the previous snapshot intact. Saving the project, or closing Kinemeld normally
(including choosing to discard changes), removes it.

If Kinemeld finds a snapshot when it starts, it asks before doing anything else:

- **Recover** opens the autosaved project as unsaved work. Save asks where to write it,
  starting at the original file, rather than overwriting a file that may have changed.
- **Discard** keeps the snapshot as `recovery/declined-<time>.json` and starts fresh.
  Snapshots that cannot be read, or that fail to open, are set aside the same way. The
  newest three are kept; open one with **Open project** to inspect it.

Autosave never replaces a snapshot that is waiting for this decision. A result too large for
a project file is left out of the snapshot; the model, geometry bindings and view are kept.
One snapshot is shared per user, so run one Kinemeld window at a time.

## Checking a release package

`scripts/check_package.py` checks an archive the way a clean machine sees it: it unpacks the
archive into an empty folder, verifies the checksum and every file against
`package-manifest.json`, starts the packaged service with a fresh user-data folder, and,
when MBDyn is bundled, solves the pendulum and a featured 3D study. `--native-smoke` also runs
the desktop self-check (`xvfb-run` on Linux without a display).

```bash
python3 scripts/check_package.py dist/Kinemeld-0.6.0-linux-x86_64.tar.gz --version 0.6.0 --expect-solver --native-smoke
```

The release workflow runs these checks on fresh Ubuntu 24.04, macOS 14 and Windows runners
that have only Python (and, on Linux, `libwebkit2gtk-4.1-0` and Xvfb) installed, and
publishes a release only when every package passes.

## Application resources and user data

The desktop reads application resources from the extracted application folder and stores runtime data in a per-user folder: `%LOCALAPPDATA%\MBDynStudio` on Windows, `~/Library/Application Support/Kinemeld` on macOS and `$XDG_DATA_HOME/kinemeld` (default `~/.local/share/kinemeld`) on Linux. This includes `runs/` and the WebView2 profile. Set `MBDYN_STUDIO_DATA_DIR` to an absolute writable folder to override this location. If the user-data directory cannot be created, startup reports an error. Browser development without that override retains the existing workspace layout.

Desktop solver and agent settings are `solver.json` and `agent.json` in that folder. If a user setting is absent, the application reads the corresponding legacy `backend/solver.json` or `backend/agent.json` from the resource folder without copying, overwriting or deleting it. A present user setting takes precedence, including when invalid. The same read-only fallback applies to the old tour preference. New preferences and runs are written to user data; old run artifacts remain accessible by their existing run URLs. If the same run ID exists in both roots, artifacts come exclusively from the user-data run folder, never a mixture. This is a compatibility fallback, not automatic migration or cleanup.

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
