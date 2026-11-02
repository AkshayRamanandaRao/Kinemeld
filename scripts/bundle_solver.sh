#!/usr/bin/env bash
# Copy a built MBDyn executable and every non-system library it loads into a relocatable folder.
# Usage: scripts/bundle_solver.sh path/to/mbdyn OUTPUT_DIR
set -euo pipefail
binary="$1"; out="$2"
root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
rm -rf "$out"; mkdir -p "$out/bin" "$out/lib"
: > "$out/BUILD-ORIGINS.tsv"
exe=""; case "$(uname -s)" in CYGWIN*) exe=".exe" ;; esac
cp "$binary" "$out/bin/mbdyn$exe"; chmod 755 "$out/bin/mbdyn$exe"
printf 'bin/mbdyn%s\t%s\n' "$exe" "$(cd "$(dirname "$binary")" && pwd -P)/$(basename "$binary")" >> "$out/BUILD-ORIGINS.tsv"
strip -S "$out/bin/mbdyn$exe" 2>/dev/null || true
case "$(uname -s)" in
  CYGWIN*)
    # Windows loads DLLs from the executable's folder first, so the Cygwin runtime and the GCC
    # libraries go beside mbdyn.exe; Windows system DLLs stay where they are. cygcheck reads the
    # import tables recursively (ldd under Cygwin can miss DLLs).
    cygwin_bin="$(cygpath -w /usr/bin)"
    cygcheck "$(cygpath -w "$out/bin/mbdyn.exe")" | tr -d '\r' | sed 's/^ *//' | grep -iF "$cygwin_bin\\" | sort -u | while read -r dll; do
      cp "$(cygpath -u "$dll")" "$out/bin/"
      printf 'bin/%s\t%s\n' "$(basename "$(cygpath -u "$dll")")" "$(cygpath -u "$dll")" >> "$out/BUILD-ORIGINS.tsv"
    done
    chmod 755 "$out"/bin/*.dll
    ls "$out/bin"/*.dll >/dev/null 2>&1 || { echo "cygcheck found no Cygwin DLLs for mbdyn.exe." >&2; exit 1; }
    # Starting the bundle from this Cygwin shell would mix two copies of the Cygwin runtime in
    # one process tree; check it from a native Windows shell with only Windows on PATH instead.
    # Record the Cygwin package each bundled DLL comes from, for its licence and source.
    for dll in "$out"/bin/*.dll; do
      printf '%s\t%s\n' "$(basename "$dll")" "$(cygcheck -f "/usr/bin/$(basename "$dll")" | tr -d '\r')"
    done > "$out/CYGWIN-PACKAGES.txt"
    ;;
  Linux)
    # glibc and the C++/GCC support libraries are present on every Linux system; everything else
    # (Fortran runtime, LAPACK/BLAS or any other library the build machine provided) is bundled.
    system='^(linux-vdso|ld-linux|libc|libm|libmvec|libpthread|libdl|librt|libstdc\+\+|libgcc_s)\.'
    ldd "$binary" | awk '/=> \// {print $1, $3}' | while read -r name path; do
      if ! grep -Eq "$system" <<<"$name"; then
        cp -L "$path" "$out/lib/$name"; chmod 644 "$out/lib/$name"
        printf 'lib/%s\t%s\n' "$name" "$(readlink -f "$path")" >> "$out/BUILD-ORIGINS.tsv"
      fi
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
        if [ ! -f "$out/lib/$name" ]; then
          cp -L "$source" "$out/lib/$name"; chmod 644 "$out/lib/$name"
          printf 'lib/%s\t%s\n' "$name" "$source" >> "$out/BUILD-ORIGINS.tsv"
          copy_deps "$out/lib/$name"
        fi
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
printf '%s\n' 'UNVERIFIED: run collect_solver_sources.py before distributing this solver.' > "$out/SOURCE.txt"
echo "Bundled libraries: ${bundled:-none}"
"$out/bin/mbdyn$exe" -v 2>&1 | head -3 || true
