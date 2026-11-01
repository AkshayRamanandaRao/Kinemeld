#!/usr/bin/env bash
# Build the official pinned source locally; install no system packages here.
set -euo pipefail
base="$(cd -- "$(dirname -- "$0")" && pwd)"
CC="${CC:-gcc}"; CXX="${CXX:-g++}"; FC="${FC:-gfortran}"
for tool in "$CC" "$CXX" "$FC" make python3 tar; do
    command -v "$tool" >/dev/null || { echo "Missing build prerequisite: $tool" >&2; exit 1; }
done
mkdir -p "$base/vendor" "$base/evidence"
archive="$base/vendor/mbdyn-1.7.3.tar.gz"
if [ ! -f "$archive" ]; then
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve("https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz",sys.argv[1])' "$archive"
fi
python3 -c 'import hashlib, sys; d = hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest(); sys.exit(0 if d == sys.argv[2] else "MBDyn archive digest mismatch")' "$archive" 3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d
filtered="$base/vendor/mbdyn-1.7.3-kinemeld-no-y12.tar"
python3 "$base/../scripts/filter_mbdyn_source.py" "$archive" "$filtered" --manifest "$base/evidence/mbdyn-source-transform.json"
# Build only from the verified archive, never a stale or locally edited tree.
vendor_dir="$(cd -- "$base/vendor" && pwd -P)"
source_dir="$vendor_dir/mbdyn-1.7.3"
[ ! -L "$source_dir" ] || { echo 'Refusing to replace a linked source directory.' >&2; exit 1; }
[ "$(dirname "$source_dir")" = "$vendor_dir" ] || exit 1
rm -rf -- "$source_dir"
tar -xf "$filtered" -C "$vendor_dir"
cd "$base/vendor/mbdyn-1.7.3"
# An older configured source tree may still include Y12. Its archived README
# contains no redistribution grant, so reconfigure it before producing a bundle.
if [ ! -f Makefile ] || ! grep -q '^/\* #undef USE_Y12 \*/' include/mbconfig.h 2>/dev/null; then
    # MBDYN_CONFIGURE_FLAGS adds platform options, e.g. --disable-shared on Windows (Cygwin),
    # where libtool would otherwise build DLLs and leave a wrapper in place of mbdyn.exe.
    # shellcheck disable=SC2086
    CC="$CC" CXX="$CXX -std=c++11" F77="$FC" FC="$FC" FFLAGS='-O2 -fallow-argument-mismatch' ./configure --disable-runtime-loading ${MBDYN_CONFIGURE_FLAGS:-} --without-y12 > "$base/evidence/configure.log" 2>&1 || { tail -40 "$base/evidence/configure.log" >&2; exit 1; }
fi
grep -q '^/\* #undef USE_Y12 \*/' include/mbconfig.h || { echo 'Y12 must remain disabled in distributed builds.' >&2; exit 1; }
./config.status --config > "$base/evidence/configure-arguments.txt"
cp include/mbconfig.h "$base/evidence/mbconfig.h"
make -j"${MBDYN_JOBS:-4}" > "$base/evidence/build.log" 2>&1 || { tail -60 "$base/evidence/build.log" >&2; exit 1; }
./mbdyn/mbdyn -v
