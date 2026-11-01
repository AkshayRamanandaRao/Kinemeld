# Native project-dialog GUI tests

`Native GUI` builds the normal desktop host, creates a candidate with the release
packager, extracts it, and launches that candidate with a fresh user-data directory.
It exercises the real viewer, production IPC bridge, RFD file dialogs and MBDyn.
No file-picker result, project-open response or solver result is mocked. The
`--smoke` desktop self-check remains a separate, narrower check.

Run [.github/workflows/native-gui.yml](../.github/workflows/native-gui.yml) on the
branch being qualified. It also runs on pull requests that change the host or
dialog tests. Its `solver_run` input identifies a successful audited Release run
containing `solver-linux`, `solver-macos` and `solver-windows` artifacts with their
corresponding sources. The default is audit run `41336308183`; the packager checks
the downloaded solver/source inventory before using it. This avoids a solver
rebuild for every GUI iteration. It does not publish a release.

The three jobs use Ubuntu 24.04, macOS 15 arm64 and Windows. All twelve cases must
pass without skips before a platform is qualified:

1. Real embedded viewer, native bridge and owned solver service start.
2. Native Open → Save As → reopen retains the physical model, original STEP bytes,
   bindings, MBDyn result samples and complete CSV.
3. Cancelled Save As preserves the file and active save destination.
4. Refusing the native overwrite confirmation preserves the existing target.
5. Ordinary Save retains the exact previous bytes in a backup.
6. External disk edits reject Save; Save As retains both versions.
7. New → Save requests a native picker on both cancellation attempts; autosave
   does not inherit the previous path.
8. The real autosave contains CAD, result samples and CSV before a forced crash.
9. Dirty Open refusal and picker cancellation retain the current edits.
10. A malformed file selected through native Open leaves the current work intact.
11. Restart shows the real recovery prompt; recovered work opens unsaved and
    saves through a native destination picker with CAD/results intact.
12. Dirty-close refusal retains the viewer/service. Confirmed normal close exits
    successfully, removes recovery and stops the owned backend.

The fresh Windows runner uses the shared in-app test script and the existing
Win32 helper. It needs an English Windows desktop with WebView2. The helper only
controls the launched application's PID and its owned descendants; it does not
require a browser debugging port. The separately retained
[native-dialog-ui.mjs](../tests/native-dialog-ui.mjs) also connects Playwright to
the actual WebView2 instance over loopback CDP on configured development machines.
For that existing CDP suite, `KINEMELD_NATIVE_EXE`,
`KINEMELD_NATIVE_SOLVER_CONFIG` and `MBDYN_STUDIO_PYTHON` select a packaged app,
an actual native solver and the CAD-enabled Python interpreter.

On all three runners, the host's explicit `--native-gui-test CONFIG.json` mode injects
[gui_test.js](../native/crates/app/src/gui_test.js) into its own viewer. That script
clicks the real DOM controls and checks the resulting UI and saved documents. The
normal bridge and dialog operations are unchanged. The additional `gui-test` IPC
operation is rejected unless that CLI mode is present. Its bounded file helpers
require a marked test root and an exact `root/user-data` data directory, reject
path escapes, and cannot change the test configuration or write into recovery.
Native file choices are still made through visible picker controls.

The macOS supervisor launches the actual `.app` through LaunchServices, using
`open -n -W --env` with explicit isolated data and CAD-Python paths. Its marker
must match the current test root/phase and a fresh native PID. Darwin kqueue
`NOTE_EXITSTATUS` measures that PID's actual exit status; the launch helper's
exit code is not used as a substitute. Crash cleanup checks the owned process
and its descendants. Bundle signing metadata and scoped system logs are retained
for picker-service failures.

The macOS driver runs an AppKit timer in the application's modal run loop. It
operates the app's own `NSOpenPanel`, `NSSavePanel` and alert controls, avoiding
cross-application Accessibility permissions. It fills the live directory/name
controls, selects the file's accessible row where available, and invokes native
Open/Save/Cancel controls or their documented panel action handlers. Overwrite
refusal requires the actual confirmation controls. AppKit captures the app's own
panels; macOS can exclude remote file-service subviews from those screenshots.
The driver is compiled with the system clang and adds no Cargo dependencies.

Linux retains RFD's release-default xdg-desktop-portal backend. A private D-Bus
session and Xvfb display run Openbox, xdg-desktop-portal and its GTK portal. GTK is
the normal portal provider for this test desktop; RFD is not rebuilt with a
different backend. AT-SPI enters the native location field and invokes real
buttons. X11 operations are constrained to the app/portal process groups in this
private display. The test fails if the portal or native controls are unavailable.

For a local Linux run, install the workflow's GTK/WebKit, Xvfb, portal, AT-SPI,
Openbox, xdotool, wmctrl, scrot and Zenity packages, and use a CAD-enabled Python
plus an actual solver configuration:

```sh
export MBDYN_STUDIO_PYTHON=/absolute/path/to/cad-python
dbus-run-session -- xvfb-run -a -s '-screen 0 1600x1000x24' \
  bash tests/native-dialog-linux-session.sh \
  /absolute/path/to/packaged/kinemeld /absolute/path/to/solver.json
```

For macOS:

```sh
MBDYN_STUDIO_PYTHON=/absolute/path/to/cad-python \
  python3 tests/native-dialog-platform.py \
    --exe /absolute/path/to/Kinemeld.app/Contents/MacOS/kinemeld \
    --solver-config /absolute/path/to/solver.json
```

Reports, exact executable/frontend/fixture hashes, native control observations,
screenshots, process IDs and logs are retained under `tests/evidence/` and uploaded
as `native-gui-PLATFORM` workflow artifacts. The fixture in the package is checked
unchanged. A missing runner pass, timeout, failed case or missing native-control
evidence is a qualification failure; adding the harness alone does not establish
macOS/Linux native-dialog support.

Candidate archive and manifest versions retain their complete suffix, while the
macOS bundle version keys use the numeric semantic core required by
[Apple's bundle-version format](https://developer.apple.com/documentation/BundleResources/Information-Property-List/CFBundleVersion)
and [short-version format](https://developer.apple.com/help/glossary/version-number/).
