# Rust desktop dependency notices

This bundle covers the locked default-feature `normal,build` dependency graph of
`mbdyn-studio-desktop` for the three release targets. It conservatively retains
build-time dependencies as well; an entry is not a claim that its code is linked.
The inventory contains 194 registry package versions: Windows x64 has 86, Linux
x64 has 160, and macOS arm64 has 85. Per-target lists are in `graphs/`.

`THIRD_PARTY_RUST.txt` preserves the original license, copyright, authors and
NOTICE files found in exact `.crate` archives. Archive SHA-256 values are checked
against `Cargo.lock`. Fourteen crates omit license files from their archives;
their upstream texts are pinned to the crate's `.cargo_vcs_info.json` revision
in `upstream/manifest.json`. Selected alternatives and provenance are recorded
per component in `manifest.json`; unreviewed declarations or missing texts fail
collection. Apache, Unicode and additional conjunctive license texts are retained.

The Linux dependency `option-ext 0.2.0` is MPL-2.0. Its complete, unmodified source
is included as `sources/option-ext-0.2.0.crate` (a gzip tar archive), with its
original MPL license. Its SHA-256 matches the locked published crate. Recipients
can extract and use that source under MPL-2.0; see
[MPL sections 3.1 and 3.2](https://www.mozilla.org/en-US/MPL/2.0/).

The Windows crate `webview2-com-sys` also embeds Microsoft WebView2 SDK loader
libraries. All nine loader payloads match Microsoft's NuGet SDK 1.0.3800.47,
whose BSD-3-Clause license, NOTICE and package metadata are in `upstream/`.
The Windows release links its x64 static loader. The separately installed
WebView2 browser runtime is not part of this bundle. Test-only binary fixtures
from `libloading` and `system-deps` are recorded and excluded from the application.

The exact `objc2` upstream license discusses unresolved questions about Apple
SDK-derived bindings. That warning is retained in the aggregate and upstream
license; collecting these notices does not resolve Apple's SDK redistribution
terms or constitute legal approval of macOS distribution.

`toolchain/` contains the Rust distribution's standard-library copyright notice
and accompanying component license texts. The root `rust-toolchain.toml` pins
Rust 1.99.1, matching the audited release builders. `--check-compiler` compares
the actual compiler release and commit with this manifest, allowing different
host triples. A toolchain change requires regenerating and reviewing the bundle.

Regenerate with Python 3.11+ and the pinned Rust toolchain:

```sh
cargo fetch --manifest-path native/Cargo.toml --locked --target x86_64-pc-windows-msvc --target x86_64-unknown-linux-gnu --target aarch64-apple-darwin
python scripts/collect_rust_notices.py --collect --check-compiler
python scripts/collect_rust_notices.py --check --check-compiler --source-root .
```

Collection reads the verified Cargo cache and official toolchain license files;
it does not download notice text. Updating crates that lack notices requires
reviewing new exact upstream revisions first. Copy this entire directory into
every desktop package, including the MPL source archive. A copied bundle can be
verified offline without Cargo, the Rust toolchain or the original source tree:

```sh
python scripts/collect_rust_notices.py --check --notices PATH_TO_RUST_NOTICES --target x86_64-unknown-linux-gnu
```

The manifest inventories and hashes all bundled files. Canonical copies of the
source manifests, lockfile, project license and toolchain pin are included under
`source-inputs/`; source comparisons normalize CRLF to LF.
