# Third-party components and reference boundary

The original Kinemeld application, generated model templates and documentation
are MIT-licensed. This is an independent project, not an official MBDyn
distribution. Third-party materials retain their individual licenses below.

| Component | Source and version | License | Included material |
| --- | --- | --- | --- |
| Three.js | https://github.com/mrdoob/three, npm `three@0.186.1` | MIT | Browser modules and OrbitControls in `frontend/vendor`; license alongside them |
| IBM Plex Sans and Mono | https://github.com/IBM/plex; existing openly licensed assets from the user's Enigmiq CAD checkout | SIL Open Font License 1.1 | Font files in `frontend/fonts`, with both OFL notices |
| MBDyn | https://www.mbdyn.org/; pinned archived 1.7.3 integration | GNU GPL version 2, as specified in its source headers | Separate solver process. Excluded from this repository. Linux (and, when built, macOS) release archives contain an unmodified MBDyn 1.7.3 build in `solver/` with `COPYING` and `SOURCE.txt`; the corresponding source archive is attached to every GitHub release. |
| Upstream MBDyn example decks | Revisions, hashes, authors and source URLs in `examples/open-source/catalog.json` | GPL-2.0-only | Separate model input data under `examples/open-source`; original notices and corresponding GPL text are retained. These files are not licensed under the application MIT license. |
| Double wishbone STEP parts | Prammit-06/Double_Wishbone_Suspension_CAD, pinned revision and hashes in `examples/step-suspension/README.md` | MIT, Copyright 2026 Prammit | Twelve original STEP source files and upstream MIT license. |
| Aircraft nose-gear STEP assembly | Aryan Pandharipande, pinned revision and hash in `examples/open-aircraft-nose-gear/README.md` | MIT; upstream notice retained | Original STEP assembly and upstream MIT license. |
| OpenCascade OCP | Locally installed `cadquery-ocp` 7.9.3.1.1 | Package declares Apache-2.0 | Optional local STEP conversion runtime, not bundled; its transitive license and binary redistribution obligations must be audited before a public binary release. |
| NASA Mars 2020 printable wheel | https://github.com/nasa/NASA-3D-Resources, pinned in `examples/reference/README.md` | NASA media usage guidelines | Optional, separately downloaded visual mesh; no NASA endorsement implied. |
| Wry, Tao, RFD and WebView2 bindings | Rust desktop dependencies pinned in `native/Cargo.lock` | Wry Apache-2.0 OR MIT; Tao Apache-2.0; RFD and webview2-com MIT | Rust window, embedded system web view (WebView2, WKWebView or WebKitGTK) and native file dialogs. Transitive dependency licenses remain in their corresponding source packages. On Linux the system WebKitGTK and GTK libraries are used and not redistributed. |

MBDyn acquisition URL, archive digest, rebuild instructions and corresponding
source/license obligations are in [solver.md](docs/solver.md). Its source/build
cache remains on this machine for reproducibility. The app's MIT license does
not replace MBDyn's license; binary redistribution needs the matching source
and notices. The retained GPL text is `backend/MBDyn-GPL-2.0.txt`.

The UI's layout and numerical conventions were independently designed using
general CAE concepts. Fonts retain their notices. The small interface icons
and mechanism geometry were authored for this project.
