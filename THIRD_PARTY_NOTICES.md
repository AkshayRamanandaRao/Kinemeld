# Third-party notices

Kinemeld's original application code and documentation are MIT-licensed; see
[LICENSE](LICENSE). Each dependency and example retains its own terms. Kinemeld
is an independent project and is not an official MBDyn distribution.

The inventories below identify actual shipped files. An inventory check establishes
their identity and coverage; it does not establish permission where upstream terms
are unclear. See the [dependency audit](docs/dependency-audit.md) for findings,
published-package scope and unresolved redistribution questions.

| Included component | Version and identity | Terms and retained material |
| --- | --- | --- |
| Three.js, loaders and OrbitControls | npm `three@0.186.1`; exact archive and file hashes in [assets.json](notices/assets.json) | MIT; full upstream notice in `frontend/vendor/THREE-LICENSE.txt`. Comment-only local edits are identified in the inventory. |
| IBM Plex Sans and Mono | Sans 3.201 and Mono 2.3; pinned Google Fonts revision and exact font hashes in the asset inventory | SIL OFL 1.1; both complete copyright/license notices in `frontend/fonts`. |
| Rust desktop dependencies | Exact Cargo.lock normal/build closures for Windows x64, Linux x64 and macOS arm64 in [manifest.json](notices/rust/manifest.json) | [Rust notices](notices/rust/README.md) retain full selected license texts, copyright and NOTICE material, exact source identities, the MPL-2.0 `option-ext` source archive and Rust standard-library notices. Includes Apache, MIT, ISC, Unicode, MPL and LLVM-exception terms; these dependencies are not all covered by the application MIT license. |
| Microsoft WebView2 static loader | SDK 1.0.3800.47; byte comparison against the exact Microsoft NuGet archive recorded in the Rust inventory | Microsoft SDK LICENSE and NOTICE are retained separately from the Rust wrapper's MIT notice. The installed WebView2 browser runtime is a system prerequisite, not part of the package. |
| MBDyn | Pinned 1.7.3 archive, SHA-256 `3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d`; separate solver process | GPL-2.0-only; source copyright notices, GPL text and embedded COLAMD attribution retained. New builds disable Y12 because its embedded README does not establish a license grant. Historical binaries are not retroactively cleared. |
| GCC solver support libraries | Exact distribution/source versions, individual binary hashes and build inputs in packaged `solver/DEPENDENCIES.json` | `libgfortran`, `libgcc_s` and `libstdc++`: GPL-3.0-or-later with GCC Runtime Library Exception 3.1. **libquadmath has LGPL terms**, retained separately; it is not covered by a blanket GCC exception label. Complete relevant texts and package copyright notices accompany the solver. |
| Windows solver libraries | Exact Cygwin, libiconv, gettext and GCC packages recorded per DLL | Cygwin: LGPL-3.0-or-later with its documented linking exception and included Newlib notices. libiconv/libintl: LGPL-2.1-or-later. GCC and quadmath terms as above when present. Full notices and matching distribution source archives accompany the build. |
| Reference LAPACK/BLAS, when linked | Exact installed Ubuntu package and source version recorded per library | BSD-3-Clause and retained distribution/upstream copyright notices; corresponding source retained with the solver sources. |
| Upstream MBDyn input decks | Pinned revisions and hashes in [catalog.json](examples/open-source/catalog.json) and the asset inventory | GPL-2.0-only; original notices and full GPL text retained. These model inputs are separate from the application MIT license. |
| Double wishbone STEP parts | Twelve original files from Prammit-06/Double_Wishbone_Suspension_CAD; pinned revision and hashes in their README and the asset inventory | MIT; upstream copyright and complete license retained alongside the files. |
| Aircraft nose-gear STEP assembly and split parts | Aryan Pandharipande's pinned upstream assembly; original and derived-part hashes in the asset inventory | MIT; upstream copyright/license retained. Derived split-part provenance is identified in the inventory. |

Every newly assembled public solver package must have a matching
`Kinemeld-<version>-<platform>-<arch>-solver-sources.tar.gz` companion, with a
checksum. It contains the exact source archives, distribution patches/recipes,
package metadata and build/packaging inputs recorded in `solver/DEPENDENCIES.json`.
Keep that companion available beside its binary package. LGPL shared libraries
remain ordinary replaceable files in `solver/bin` or `solver/lib`.

The new MBDyn corresponding source is the deterministic
`mbdyn-1.7.3-kinemeld-no-y12.tar`, SHA-256
`1fd09e766c30485423d57e0379b5248e095aeec59bcec59a3f4b518e19f0fcc3`.
It removes only eleven unused Y12 Fortran implementations from the pinned official
archive, preserves all retained source bytes, and records the removal hashes in
[mbdyn-source-transform.json](notices/solver/mbdyn-source-transform.json). New
builds compile that same filtered source with Y12 disabled; new releases do not
redistribute the original archive containing those implementations.

Python, `cadquery-ocp`, OpenCascade, GTK/WebKitGTK, WKWebView and the installed
WebView2 runtime are not bundled in standard public release archives. Installing
them separately does not change their terms. The optional private Python/OCP test
bundle remains **redistribution not established**: binary wheels are acquisition
artifacts, not corresponding source, and its nested native libraries need their
own audit. See [runtime-lock/README.md](native/runtime-lock/README.md).

The optional NASA Mars 2020 printable wheel is downloaded separately and is not
shipped in these archives; its source and NASA media-use boundary are in
[examples/reference/README.md](examples/reference/README.md). No endorsement is
implied. Kinemeld's small interface icons and original mechanism geometry were
authored for this project.
