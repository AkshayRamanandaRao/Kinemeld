# Private Windows Python runtime staging

This is an **opt-in test path**, not an approved redistribution or a clean-machine release. No runtime or solver binaries are included in the repository. The existing local package still works with an explicit `MBDYN_STUDIO_PYTHON` or a Python on `PATH`.

The desktop selects Python in this order: the explicit `MBDYN_STUDIO_PYTHON` value, `runtime/python/python.exe` beside the application resources, then `python` on `PATH`. An empty explicit override or a present but incomplete private runtime produces an error; the application does not silently fall back. The package verifier checks the private runtime before inclusion; startup itself does not repeat a cryptographic inventory check.

`windows-cp312.json` and `requirements-windows-cp312.txt` record 14 exact Windows x86-64 CPython 3.12 wheel names, versions, release metadata and SHA-256 hashes. `resolve.py` generated the lock from public PyPI JSON and checked active Windows 3.12 dependencies against the locked versions. It fetches only metadata and requires the already-installed `packaging` library; it installs nothing. The lock matches versions observed on the development host, not a current security recommendation. A SHA-256 from the same distributor as the artifact identifies bytes; it is not an independent signature or proof that those bytes are safe.

The pinned OCP wheel contains OpenCascade and additional native components. The wheel's Apache metadata is not a complete license statement for those components. Before any redistribution, inventory every included binary and its own sources, licenses and notices, including OpenCascade's LGPL and exception, VTK's bundled libraries, FreeImage and the exact Microsoft Visual C++ runtime; review source/notice and replacement requirements. MBDyn and its example decks have separate GPL obligations. The validator can check that supplied notices exist and match hashes; it cannot determine whether they are accurate or sufficient, or infer legal permission.

## Supply a staged runtime and acquisition artifacts

The lock's historical `sourceArtifacts` field identifies the downloaded embedded-Python ZIP
and binary wheels used to construct the runtime. These are **acquisition artifacts**, not
the corresponding source code of Python, OCP, OpenCascade or the native libraries in those
wheels. Hash and payload checks do not satisfy their source or license obligations. This
private test path remains `redistributionStatus: not-established`; it is excluded from
the standard public release packages audited in P3.

1. Obtain the exact 14 wheel files and `python-3.12.10-embed-amd64.zip` through reviewed sources and put them in `C:\staging\artifacts`. The wheel SHA-256 values must match the committed lock; the Python archive is pinned to the SHA-256 published in its [Python.org SPDX SBOM](https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json). These digest checks identify the artifact but do not independently verify the publisher signature or its security. Retain the original archive and wheels separately from the runtime.
2. On Windows x64 with CPython 3.12.10 and existing pip 26.0.1, create a new isolated runtime from the downloaded artifacts. The command verifies every locked SHA-256, uses offline pip with `--no-index --no-deps --target`, and does not change system Python or PATH. Create the destination parent first; the `python` destination itself must not exist. The generated manifest has empty notice mappings and cannot pass redistribution staging until they are reviewed.

   ```powershell
   New-Item -ItemType Directory -Path C:\staging\app\runtime -Force
   python -B native/runtime-lock/prepare_runtime.py --artifacts C:\staging\artifacts --destination C:\staging\app\runtime\python
   ```

   A successful command reports `artifacts: 15`, `noticeReview: required`, and `redistributionStatus: not-established`. The destination can be used for local testing after the application backend is present at `C:\staging\app\backend`. Its `python312._pth` contains exactly these non-comment lines, in this order-independent set:

   ```text
   python312.zip
   .
   Lib/site-packages
   ../../backend
   ```

   The backend path is needed because embedded Python's `._pth` otherwise replaces normal script-directory discovery. The file must not contain `import site`: real embedded-Python testing showed that enabling it adds the Windows roaming user site. Runtime verification rejects top-level `Lib/site-packages/*.pth` files to avoid introducing unreviewed search paths. The runtime must include `python.exe`, `python312.dll` and `python312.zip`. Staging removes pip's generated `direct_url.json` files, which otherwise reveal the builder's absolute artifact paths, and updates the affected `RECORD` entries. Removed command-line wrappers are also removed from the records; relocated `share/` entries are corrected only after their bytes and sizes match the record. Runtime verification rejects staged `direct_url.json` files.
3. The preparation command generated a draft `runtime-manifest.json`. To generate an additional draft inventory at a new path, use the following command. It hashes the staged runtime without executing or modifying it. Each draft intentionally leaves every notice mapping empty, so it cannot pass the verifier until a reviewer supplies the actual notices.

   ```powershell
   python native/runtime-lock/draft_manifest.py --runtime C:\staging\app\runtime\python --python-archive C:\staging\artifacts\python-3.12.10-embed-amd64.zip --output C:\staging\runtime-manifest-draft.json
   ```

   Put the reviewed `runtime-manifest.json` in the staged runtime. `files` maps every other runtime-relative file to its lowercase SHA-256. `notices` maps `python` and each exact locked package name to one or more nonempty, hashed notice files within the runtime. `nativeNotices` must map each packaged `.exe`, `.dll` and `.pyd` path to its applicable notice files. These mappings are evidence supplied by the packager, not automated legal approval.

   To compare the installed payload bytes with the pinned Python ZIP and every wheel before notice review, run:

   ```powershell
   python -B native/runtime-lock/audit_provenance.py --runtime C:\staging\app\runtime\python --artifacts C:\staging\artifacts > C:\staging\provenance.json
   ```

   For the present locked artifacts, a local preparation reported `ok: true`, `matchedFiles: 3140`, `wheelCount: 14`, and 42 `unprovenFiles`. Those 42 files were pip-generated `RECORD`, `INSTALLER` and `REQUESTED` metadata; inspect the report for the files in your own staging folder. The check verifies each embedded-Python payload except the intentionally configured `._pth`, and each wheel payload except generated `RECORD` and explicitly excluded scripts or headers. It rejects modified or missing payloads, mismatched artifact hashes, unproven importable or native files, and leaked `direct_url.json`. It lists other unproven files instead of asserting their provenance. This check compares distributed archive bytes with installed bytes; it does not verify how the original binaries were built, publisher identity, security or legal notices.
4. Check the inventory locally before invoking the package script:

   ```powershell
   python native/runtime-lock/verify_runtime.py --runtime C:\staging\app\runtime\python --artifacts C:\staging\artifacts
   pwsh -NoProfile -File native/package-windows.ps1 -PrivateRuntimeDirectory C:\staging\app\runtime\python -PrivateRuntimeArtifacts C:\staging\artifacts
   ```

   The verifier rejects missing or changed files, unlisted files, reparse points, unsafe paths, mismatched wheel/acquisition-artifact hashes, missing component/native notice mappings and an incompatible `._pth`. For a private runtime the packaging step additionally runs the archive-to-payload comparison, then rechecks every runtime hash against the verified snapshot while writing the ZIP. Its manifest records matched and unproven file counts; unproven generated metadata and notices still require review. It creates `MBDynStudio-Windows-private-runtime-test.zip` and marks its runtime redistribution status `not-established`. The artifact directory is checked but not included in the ZIP; preserve it independently for provenance. Actual corresponding sources and native notices still need separate acquisition and review.

## Worked isolated runtime check

Copy the application resources into the staged app root and configure an MBDyn solver in its `backend/solver.json` or in the fresh QA data directory. On this Windows host the following exercises the staged interpreter with system Python removed from PATH, checks its child interpreter cannot load the user site, generates and measures an obliquely oriented STEP solid, runs the configured solver, and executes the hidden desktop self-check:

```powershell
New-Item -ItemType Directory -Path C:\staging\qa-data
python -B native/runtime-lock/smoke_runtime.py --app-root C:\staging\app --data-dir C:\staging\qa-data --desktop
```

The QA data directory must exist and must not already contain a `runs` folder; the check creates new run data there and never deletes previous runs. A successful local check reports `noSite: 1`, `childNoSite: 1`, `stepMassKg: 3`, `solverSource: "MBDyn"` and, when `--desktop` is selected, `desktop.ok: true`. Without a configured solver the check fails with its diagnostic instead of substituting a preview. The desktop check uses the application's hidden self-test; it is not an interactive native-dialog test. The preparation and smoke commands are command-line operations, so there is no runtime-staging GUI to screenshot.

The package still needs WebView2 and a separately configured MBDyn solver. A local QA build using the official Python 3.12.10 embedded ZIP and all 14 hash-locked wheels passed isolated Python/OCP import, 3D STEP generation and conversion, a STEP mass calculation, a configured local WSL MBDyn run, and the hidden Windows desktop smoke test. System Python was removed from PATH for those checks, and the private interpreter and its child reported `no_site=1`. This verifies the tested local host only. A release still needs audited notices and corresponding sources; signed artifacts; an OS-enforced read-only install test; and a clean Windows VM install, solve, cancellation, interactive native Save/Open, upgrade and uninstall check. The service and application-owned Python workers use `-B` for bytecode suppression, because an embedded interpreter can ignore `PYTHONDONTWRITEBYTECODE`. A system-Python fixture and real STEP workers passed without resource-tree cache writes. The real embedded runtime was tested as described above; OS-enforced read-only installation remains a release check.

References: [Python embedded distribution](https://docs.python.org/3.12/using/windows.html#the-embeddable-package), [OCP release metadata](https://pypi.org/project/cadquery-ocp/7.9.3.1.1/), [VTK release metadata](https://pypi.org/project/vtk/9.6.2/).
