# Dependency and license audit — 1 November 2026

P3 covers the current locked desktop dependency graph and the actual **v1.2.1**
Linux x64, macOS arm64 and Windows x64 release archives. The original application
remains MIT-licensed. Third-party terms are retained separately in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Evidence and scope

The three published archives were downloaded from GitHub and verified against
GitHub's asset SHA-256 values before extraction:

| v1.2.1 asset | SHA-256 |
| --- | --- |
| Linux x64 `.tar.gz` | `df746d85fc14bd7131529ecc7d09cd84e3508d1351996f1e59ff4279970a4725` |
| macOS arm64 `.zip` | `5c44add69add494e065fd116229eb25a04868ca0f2a068db7fe85ca21178748c` |
| Windows x64 `.zip` | `47fd7ab5120c7193d5ac091185a0c4db76cc5ae6c81f33de0aa830c65578a576` |

[Published release](https://github.com/AkshayRamanandaRao/Kinemeld/releases/tag/v1.2.1),
[original release build](https://github.com/AkshayRamanandaRao/Kinemeld/actions/runs/41233514444).
The original build logs identify Rust 1.99.1 and the unchanged Cargo.lock. This
review does not certify every older release, every optional user installation,
or legal permission where the upstream package itself leaves it unclear.

## Repairs

- **Rust:** 194 registry package versions in the normal/build dependency union:
  Windows 86, Linux 160, macOS 85. The inventory conservatively includes build-only
  dependencies; it does not assert that every listed crate is linked. Retained
  complete selected license/copyright/NOTICE text, including Apache conjunctions,
  Unicode data, missing exact-VCS license files and Rust standard-library notices.
  The exact MPL-2.0 `option-ext` crate source is included. Microsoft WebView2's
  static loader has its own SDK LICENSE/NOTICE and verified NuGet byte provenance.
  [Inventory and instructions](../notices/rust/README.md).
- **Assets:** pinned upstream source identities for 49 assets and 8 notices across
  10 components: Three.js, IBM Plex fonts, STEP originals/derived parts and MBDyn
  input decks. Existing MIT/OFL/GPL texts were checked against upstream. Local
  comment and model changes are identified in [assets.json](../notices/assets.json).
- **Solver:** the old packages had a summary notice and a generic source pointer,
  but omitted required runtime license texts and exact runtime source packages.
  New collection retains complete GPL/LGPL and exception texts, package copyright,
  Cygwin/Newlib notices, embedded COLAMD attribution and exact corresponding sources
  with distribution patches/recipes. Every `bin/` and `lib/` file is assigned to a
  reviewed component with a version, hash, notice, source and build evidence.
- **libquadmath:** split from the GCC-exception category. Its LGPL terms and actual
  upstream copyright are retained separately. Dynamically loaded runtimes remain
  replaceable ordinary files.
- **Y12:** the archived MBDyn README does not establish a redistribution grant.
  New builds force `--without-y12`, reconfigure old build caches and check the actual
  generated configuration. Existing binaries are not retroactively cleared.
- **Packaging:** both packagers include the full notice tree. Public solver
  packaging requires a matching source directory and produces a hashed
  `*-solver-sources.tar.gz` companion. Checks cover every archive file, including
  the macOS executable outside Resources, and reject missing/tampered notices,
  incomplete sources, unlisted files and unsafe archive entries.
- **Private Python/OCP path:** corrected the description of the lock's
  `sourceArtifacts` field. Embedded-Python ZIPs and wheels are acquisition binaries,
  not corresponding source. This optional test bundle is outside standard public
  releases and remains `redistributionStatus: not-established`.

## Exact published solver dependencies

| Platform | Components and matching source |
| --- | --- |
| Linux | BLAS/LAPACK: Ubuntu `lapack 3.10.0-2ubuntu1`; gfortran/quadmath: `gcc-12 12.3.0-1ubuntu1~22.04.3`. All four shipped libraries match official Ubuntu `.deb` executable `.text` hashes and GNU build IDs; relocation edits change whole-file hashes. Retained `.dsc`, original tarballs, Debian patches and package copyright. |
| macOS | Homebrew GCC 16.2.0; exact source tarball, formula and GCC patch, with immutable homebrew-core revision and hashes. The runtime set contains libgcc_s, libgfortran, libquadmath and libstdc++. |
| Windows | Cygwin 3.6.12-1; GCC 14.4.0-1; libiconv 1.19-2; gettext 0.22.5-1. Exact Cygwin source packages include their upstream archives, patches and cygport recipes; checksums were verified against the official package index. |

Future builds collect the **actual installed** package versions rather than
assuming this table will remain current. Unknown dependencies or unavailable
matching sources stop packaging. Source archives are release artifacts rather
than large Git blobs; retain the companion beside each binary download. Build
instructions are in [notices/solver/REBUILD.txt](../notices/solver/REBUILD.txt).

## Remaining limits

The original published v1.2.1 archives are historical evidence and do not acquire
these repairs simply because the source repository changed. Corrected candidate
packages and their source companions must be distributed together; the original
asset hashes above remain useful for identifying the affected packages.

The exact objc2 upstream license warning says its SDK-derived binding terms are
unclear. That warning is retained for the affected macOS crates. Apple's current
[Xcode agreement](https://www.apple.com/legal/sla/docs/xcode.pdf) distinguishes
macOS application distribution from other SDK uses; this audit does not decide
copyright in generated bindings or establish legal clearance. This is an upstream
rights uncertainty, not evidence of a proven license violation or a missing
license file that can be repaired by inventing a notice.

The historical MBDyn binaries may include Y12. Netlib's
[FAQ](https://www.netlib.org/misc/faq.html) does not supply an explicit Y12 grant;
[its archive](https://www.netlib.org/y12m/) and the embedded README leave that
question unresolved. New builds exclude it. No additional source/code permission
is inferred for optional Python/OCP native libraries.

## Validation

Local notice checks and focused integrity tests pass. Fresh three-platform source
collection, package reconstruction and clean-runner verification are in progress.
No P4 engineering-example implementation is included in this change.
