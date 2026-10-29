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
if [ ! -d "$base/vendor/mbdyn-1.7.3" ]; then
    tar -xzf "$archive" -C "$base/vendor"
fi
cd "$base/vendor/mbdyn-1.7.3"
if [ ! -f Makefile ]; then
    CC="$CC" CXX="$CXX -std=c++11" F77="$FC" FC="$FC" FFLAGS='-O2 -fallow-argument-mismatch' ./configure --disable-runtime-loading > "$base/evidence/configure.log" 2>&1 || { tail -40 "$base/evidence/configure.log" >&2; exit 1; }
fi
make -j"${MBDYN_JOBS:-4}" > "$base/evidence/build.log" 2>&1 || { tail -60 "$base/evidence/build.log" >&2; exit 1; }
./mbdyn/mbdyn -v
