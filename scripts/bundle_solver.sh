#!/usr/bin/env bash
# Copy a built MBDyn executable and every non-system library it loads into a relocatable folder.
# Usage: scripts/bundle_solver.sh path/to/mbdyn OUTPUT_DIR
set -euo pipefail
binary="$1"; out="$2"
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
rm -rf "$out"; mkdir -p "$out/bin" "$out/lib"
exe=""; case "$(uname -s)" in CYGWIN*) exe=".exe" ;; esac
cp "$binary" "$out/bin/mbdyn$exe"; chmod 755 "$out/bin/mbdyn$exe"
strip -S "$out/bin/mbdyn$exe" 2>/dev/null || true
case "$(uname -s)" in
  CYGWIN*)
    # Windows loads DLLs from the executable's folder first, so the Cygwin runtime and the GCC
    # libraries go beside mbdyn.exe; Windows system DLLs stay where they are.
    ldd "$out/bin/mbdyn.exe" | awk '$3 ~ /^\/usr\// {print $3}' | while read -r dll; do cp -L "$dll" "$out/bin/"; chmod 755 "$out/bin/$(basename "$dll")"; done
    if ldd "$out/bin/mbdyn.exe" | grep -i 'not found'; then echo "Bundled solver has unresolved DLLs." >&2; exit 1; fi
    if ldd "$out/bin/mbdyn.exe" | awk '$3 ~ /^\/usr\// {print}' | grep .; then
      echo "Bundled solver still loads the DLLs above from the Cygwin installation." >&2; exit 1
    fi
    # Record the Cygwin packages the DLLs come from, for their licences and sources.
    cygcheck -c cygwin libgfortran5 libgcc1 libstdc++6 libquadmath0 2>/dev/null | tail -n +3 > "$out/CYGWIN-PACKAGES.txt" || true
    ;;
  Linux)
    # glibc and the C++/GCC support libraries are present on every Linux system; everything else
    # (Fortran runtime, LAPACK/BLAS or any other library the build machine provided) is bundled.
    system='^(linux-vdso|ld-linux|libc|libm|libmvec|libpthread|libdl|librt|libstdc\+\+|libgcc_s)\.'
    ldd "$binary" | awk '/=> \// {print $1, $3}' | while read -r name path; do
      if ! grep -Eq "$system" <<<"$name"; then cp -L "$path" "$out/lib/$name"; chmod 644 "$out/lib/$name"; fi
    done
    patchelf --set-rpath '$ORIGIN/../lib' "$out/bin/mbdyn"
    # A RUNPATH is not inherited, so each bundled library finds its own dependencies beside it.
    for lib in "$out"/lib/*; do [ -e "$lib" ] && patchelf --set-rpath '$ORIGIN' "$lib"; done
    if ldd "$out/bin/mbdyn" | grep -E 'not found'; then echo "Bundled solver has unresolved libraries." >&2; exit 1; fi
    lib_dir="$(cd "$out/lib" && pwd -P)"
    if ldd "$out/bin/mbdyn" | awk '/=> \// {print $1, $3}' | while read -r name path; do
         grep -Eq "$system" <<<"$name" || [ "$(dirname "$(readlink -f "$path")")" = "$lib_dir" ] || echo "$name $path"
       done | grep .; then
      echo "Bundled solver still loads the libraries above from the build machine." >&2; exit 1
    fi
    ;;
  Darwin)
    # Copy every library outside the operating system, whether referenced by an absolute Homebrew
    # path or through @rpath (as the GCC runtime does), point each reference at the bundled copy,
    # then ad-hoc sign. dyld would otherwise look for them in the build machine's Homebrew.
    gcc_lib="$(brew --prefix gcc 2>/dev/null || true)/lib/gcc/current"
    resolve() { # image reference -> absolute path of the referenced library, if it is not a system one
      local image="$1" reference="$2" name dir
      case "$reference" in
        /usr/lib/*|/System/*|@loader_path/*|@executable_path/*) return ;;
        @rpath/*)
          name="${reference#@rpath/}"
          for dir in $(otool -l "$image" | awk '/cmd LC_RPATH/ {found=1} found && $1 == "path" {print $2; found=0}') "$gcc_lib"; do
            dir="${dir/@loader_path/$(dirname "$image")}"
            if [ -f "$dir/$name" ]; then echo "$dir/$name"; return; fi
          done
          echo "Cannot resolve $reference for $image" >&2; return 1 ;;
        *) echo "$reference" ;;
      esac
    }
    copy_deps() {
      local image="$1" reference source name target
      otool -L "$image" | awk 'NR>1 {print $1}' | while read -r reference; do
        source="$(resolve "$image" "$reference")"
        [ -n "$source" ] || continue
        name="$(basename "$source")"
        if [ ! -f "$out/lib/$name" ]; then cp -L "$source" "$out/lib/$name"; chmod 644 "$out/lib/$name"; copy_deps "$out/lib/$name"; fi
        if [ "$image" = "$out/bin/mbdyn" ]; then target="@loader_path/../lib/$name"; else target="@loader_path/$name"; fi
        # A library's first entry is its own install name, which -change leaves alone.
        [ "$reference" = "$target" ] || install_name_tool -change "$reference" "$target" "$image" 2>/dev/null || true
      done
    }
    copy_deps "$out/bin/mbdyn"
    for lib in "$out"/lib/*.dylib; do
      [ -e "$lib" ] || continue
      install_name_tool -id "@loader_path/$(basename "$lib")" "$lib"
      codesign --force --sign - "$lib"
    done
    codesign --force --sign - "$out/bin/mbdyn"
    # Every remaining reference must be a system library or a bundled copy.
    if otool -L "$out/bin/mbdyn" "$out"/lib/*.dylib 2>/dev/null | grep -E '^[[:space:]]+(/opt/|/usr/local/|@rpath/)'; then
      echo "Bundled solver still references the libraries above on the build machine." >&2; exit 1
    fi
    ;;
esac
cp "$root/backend/MBDyn-GPL-2.0.txt" "$out/COPYING"
bundled="$(cd "$out/lib" && ls | tr '\n' ' ')$(cd "$out/bin" && ls | grep -i '\.dll$' | tr '\n' ' ' || true)"
cat > "$out/SOURCE.txt" <<NOTE
This folder contains an unmodified build of MBDyn 1.7.3, licensed GPL-2.0-only (see COPYING).
Corresponding source: https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz
SHA-256 3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d. The same archive is attached to each Kinemeld release.
Built with: backend/build_solver.sh from the Kinemeld repository.
Runtime libraries copied from the build machine into lib/: ${bundled:-none}.
They are the GCC runtime (GPL-3.0 with the GCC Runtime Library Exception), on Windows the
Cygwin runtime (LGPL-3.0; packages in CYGWIN-PACKAGES.txt, sources at https://cygwin.com) and,
when the build machine provided them, LAPACK and BLAS (BSD-3-Clause); see THIRD_PARTY_NOTICES.md.
NOTE
echo "Bundled libraries: ${bundled:-none}"
"$out/bin/mbdyn$exe" -v 2>&1 | head -3 || true
