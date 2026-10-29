#!/usr/bin/env bash
# Copy a built MBDyn executable and the compiler runtime libraries it needs into a relocatable folder.
# Usage: scripts/bundle_solver.sh path/to/mbdyn OUTPUT_DIR
set -euo pipefail
binary="$1"; out="$2"
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
rm -rf "$out"; mkdir -p "$out/bin" "$out/lib"
cp "$binary" "$out/bin/mbdyn"; chmod 755 "$out/bin/mbdyn"
strip -S "$out/bin/mbdyn" 2>/dev/null || true
case "$(uname -s)" in
  Linux)
    # Bundle the GCC Fortran runtime; glibc and libstdc++ come from the system.
    for lib in $(ldd "$binary" | awk '/libgfortran|libquadmath/ {print $3}'); do cp -L "$lib" "$out/lib/"; done
    patchelf --set-rpath '$ORIGIN/../lib' "$out/bin/mbdyn"
    ;;
  Darwin)
    # Rewrite Homebrew GCC runtime references to the bundled copies, then ad-hoc sign.
    copy_deps() {
      # grep exits 1 when a library has no Homebrew dependencies; that is not an error here.
      otool -L "$1" | awk 'NR>1 {print $1}' | { grep -E '/(opt|usr/local)/' || true; } | while read -r dep; do
        name="$(basename "$dep")"
        if [ ! -f "$out/lib/$name" ]; then cp -L "$dep" "$out/lib/$name"; chmod 644 "$out/lib/$name"; copy_deps "$out/lib/$name"; fi
        install_name_tool -change "$dep" "@loader_path/../lib/$name" "$1" 2>/dev/null || true
        install_name_tool -change "$dep" "@loader_path/$name" "$1" 2>/dev/null || true
      done
    }
    copy_deps "$out/bin/mbdyn"
    for lib in "$out"/lib/*.dylib; do
      [ -e "$lib" ] || continue
      install_name_tool -id "@loader_path/$(basename "$lib")" "$lib"
      otool -L "$lib" | awk 'NR>1 {print $1}' | { grep -E '/(opt|usr/local)/' || true; } | while read -r dep; do
        install_name_tool -change "$dep" "@loader_path/$(basename "$dep")" "$lib"
      done
      codesign --force --sign - "$lib"
    done
    codesign --force --sign - "$out/bin/mbdyn"
    ;;
esac
cp "$root/backend/MBDyn-GPL-2.0.txt" "$out/COPYING"
cat > "$out/SOURCE.txt" <<NOTE
This folder contains an unmodified build of MBDyn 1.7.3, licensed GPL-2.0-only (see COPYING).
Corresponding source: https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz
SHA-256 3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d. The same archive is attached to each Kinemeld release.
Built with: backend/build_solver.sh from the Kinemeld repository.
NOTE
"$out/bin/mbdyn" -v 2>&1 | head -3 || true
