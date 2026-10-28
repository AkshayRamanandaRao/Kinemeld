#!/usr/bin/env bash
# Build the official pinned source locally; install no system packages here.
set -euo pipefail
base="$(cd -- "$(dirname -- "$0")" && pwd)"
for tool in gcc g++ gfortran make python3 tar; do
    command -v "$tool" >/dev/null || { echo "Missing build prerequisite: $tool" >&2; exit 1; }
done
mkdir -p "$base/vendor" "$base/evidence"
archive="$base/vendor/mbdyn-1.7.3.tar.gz"
if [ ! -f "$archive" ]; then
    python3 -c 'import sys, urllib.request; urllib.request.urlretrieve("https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz",sys.argv[1])' "$archive"
fi
printf '%s  %s\n' '3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d' "$archive" | sha256sum -c -
if [ ! -d "$base/vendor/mbdyn-1.7.3" ]; then
    tar -xzf "$archive" -C "$base/vendor"
fi
cd "$base/vendor/mbdyn-1.7.3"
if [ ! -f Makefile ]; then
    CXX='g++ -std=c++11' FFLAGS='-O2 -fallow-argument-mismatch' ./configure --disable-runtime-loading > "$base/evidence/configure.log" 2>&1
fi
make -j4 > "$base/evidence/build.log" 2>&1
./mbdyn/mbdyn -v
