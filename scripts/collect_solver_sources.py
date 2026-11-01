"""Collect corresponding source from the exact packages used by bundle_solver.sh.

Unknown dependencies or unavailable matching package metadata stop release packaging.
Archives include distribution patches/recipes; no source is substituted by a homepage.
"""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import urllib.request

from prepare_solver_sources import MBDYN_SHA, NAMES, ROOT, digest, prepare

MBDYN_URL = "https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz"
CYGWIN_MIRROR = "https://mirrors.kernel.org/sourceware/cygwin/"


def reference(path):
    return {"path": str(path.resolve()), "sha256": digest(path)}


def download(url, target, expected=None, algorithm="sha256"):
    if not url.startswith("https://"):
        raise ValueError(f"Source transport must be HTTPS: {url}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        temporary = target.with_name(target.name + ".part")
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
        temporary.replace(target)
    if expected:
        actual = hashlib.new(algorithm, target.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"{algorithm} mismatch for {target.name}")
    return target


def source(path, url, version):
    return {**reference(path), "url": url, "sourceVersion": version}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def source_tar(archive, work):
    """Unwrap a distribution source package, retaining its complete outer archive."""
    if archive.name.endswith(".tar.zst"):
        # Cygwin's tar needs the zstd package; macOS bsdtar handles it itself.
        names = run("tar", "-tf", str(archive)).splitlines()
        name = next((n for n in names if re.search(r"/(?:gcc|libiconv|gettext|newlib-cygwin)-[^/]+\.tar\.(?:xz|gz|bz2|lz)$", n)), None)
        if not name:
            raise ValueError(f"No upstream source archive in {archive}")
        target = work / PurePosixPath(name).name
        temporary = target.with_name(target.name + ".part")
        with temporary.open("wb") as output:
            subprocess.run(["tar", "-xOf", str(archive), name], stdout=output, check=True)
        temporary.replace(target)
        return target
    with tarfile.open(archive) as bundle:
        for member in bundle:
            if re.search(r"/(?:gcc|libiconv|gettext|newlib-cygwin)-[^/]+\.tar\.(?:xz|gz|bz2|lz)$", member.name):
                target = work / PurePosixPath(member.name).name
                target.write_bytes(bundle.extractfile(member).read())
                return target
    return archive


def leading_comments(data):
    text = data.decode("utf-8", errors="replace")
    match = re.match(r"\s*((?:(?:/\*.*?\*/|//[^\n]*\n)\s*)+)", text, re.S)
    return match.group(1) if match else ""


def copyright_notice(archive, family, work):
    """Keep upstream legal files and source copyright headers, including BSD parts."""
    inner = source_tar(archive, work)
    output = work / f"{family}-{archive.name.split('-src.')[0]}-COPYRIGHT.txt"
    # GNU gettext's official archive uses lzip, understood by GNU/bsdtar.
    if inner.name.endswith(".tar.lz"):
        uncompressed = work / inner.name.removesuffix(".lz")
        temporary = uncompressed.with_name(uncompressed.name + ".part")
        with temporary.open("wb") as handle:
            subprocess.run(["lzip", "-dc", str(inner)], stdout=handle, check=True)
        temporary.replace(uncompressed)
        inner = uncompressed
    selected = []
    paths = {
        "gcc-runtime": ("libgcc/", "libstdc++-v3/", "libgfortran/", "libgomp/"),
        "quadmath": ("libquadmath/",),
        "cygwin": ("winsup/cygwin/", "winsup/cygserver/", "newlib/"),
        "libiconv": ("lib/", "libcharset/", "srclib/"),
        "gettext-runtime": ("gettext-runtime/intl/", "gettext-runtime/gnulib-lib/"),
    }[family]
    with tarfile.open(inner, "r|*") as bundle:
        for member in bundle:
            if not member.isfile():
                continue
            relative = member.name.partition("/")[2]
            basename = PurePosixPath(relative).name
            legal = basename.startswith(("COPYING", "COPYRIGHT", "AUTHORS", "CYGWIN_LICENSE"))
            code = relative.startswith(paths) and basename.endswith((".c", ".cc", ".h", ".S"))
            if legal or code:
                data = bundle.extractfile(member).read()
                text = data.decode("utf-8", errors="replace") if legal else leading_comments(data)
                if text.strip():
                    selected.append(f"===== {member.name} =====\n{text}\n")
    if not selected:
        raise ValueError(f"No actual upstream copyright notices found in {archive}")
    output.write_text("\n".join(selected), encoding="utf-8")
    return output


def cygwin_entry(index, package, version):
    section = re.search(rf"^@ {re.escape(package)}\n(.*?)(?=^@ |\Z)", index, re.M | re.S)
    if not section:
        raise ValueError(f"Cygwin package absent from index: {package}")
    for block in re.split(r"^\[(?:prev|test)\]\s*$", section.group(1), flags=re.M):
        fields = dict(re.findall(r"^(version|source|install|srcpkg): (.+)$", block, re.M))
        if fields.get("version") == version and "source" in fields:
            return fields
    raise ValueError(f"Matching Cygwin source is unavailable: {package} {version}")


def collect_cygwin(solver, work, origins):
    index_file = download(CYGWIN_MIRROR + "x86_64/setup.xz", work / "cygwin-setup.xz")
    index = lzma.decompress(index_file.read_bytes()).decode()
    components = []
    for filename, original in origins.items():
        if filename.startswith("bin/mbdyn"):
            continue
        family = next((key for key, pattern in NAMES.items() if pattern.fullmatch(PurePosixPath(filename).name)), None)
        if family not in ("gcc-runtime", "quadmath", "cygwin", "libiconv", "gettext-runtime"):
            raise ValueError(f"Unreviewed Cygwin dependency: {filename}")
        installed = run("cygcheck", "-f", original)
        match = re.fullmatch(r"(.+)-(\d[^\s]*-\d+)", installed)
        if not match:
            raise ValueError(f"Cannot identify installed Cygwin owner: {installed}")
        package, version = match.groups()
        fields = cygwin_entry(index, package, version)
        if digest(solver / filename) != digest(Path(original)):
            raise ValueError(f"Bundled Cygwin library differs from its installed owner: {filename}")
        relative, size, checksum = fields["source"].split()
        archive = download(CYGWIN_MIRROR + relative, work / PurePosixPath(relative).name, checksum, "sha512")
        if archive.stat().st_size != int(size):
            raise ValueError(f"Cygwin source size mismatch: {relative}")
        evidence = work / f"{package}-{version}-metadata.json"
        evidence.write_text(json.dumps({"installedOwner": installed, "filename": filename,
                                       "indexUrl": CYGWIN_MIRROR + "x86_64/setup.xz", **fields}, indent=2) + "\n")
        notice = copyright_notice(archive, family, work)
        components.append({"name": package, "family": family, "version": version, "sourceVersion": version,
                           "files": [filename], "packageNotice": reference(notice),
                           "sources": [source(archive, CYGWIN_MIRROR + relative, version)],
                           "evidence": [reference(evidence), reference(index_file)]})
    return components


def collect_homebrew(solver, work, origins):
    receipt_text = run("brew", "info", "--json=v2", "gcc")
    receipt = work / "homebrew-installed-gcc.json"
    receipt.write_text(receipt_text + "\n")
    installed = json.loads(receipt_text)["formulae"][0]
    prefix = Path(run("brew", "--prefix", "gcc")).resolve()
    keg_receipt = prefix / "INSTALL_RECEIPT.json"
    keg = json.loads(keg_receipt.read_text())
    api_file = download("https://formulae.brew.sh/api/formula/gcc.json", work / "homebrew-gcc.json")
    api = json.loads(api_file.read_text())
    versions = {entry["version"] for entry in installed["installed"]}
    version = api["versions"]["stable"]
    # Do not silently use today's recipe for an older or locally modified keg.
    if versions != {version} or any(entry.get("built_as_bottle") is False for entry in installed["installed"]):
        raise ValueError("Installed Homebrew GCC does not match the official bottle source recipe")
    stable = api["urls"]["stable"]
    archive = download(stable["url"].replace("http://", "https://"), work / PurePosixPath(stable["url"]).name, stable["checksum"])
    tap_head = keg["source"]["tap_git_head"]
    if not re.fullmatch(r"[a-f0-9]{40}", tap_head):
        raise ValueError("The installed Homebrew GCC receipt has no exact tap commit")
    raw = f"https://raw.githubusercontent.com/Homebrew/homebrew-core/{tap_head}/"
    formula = download(raw + api["ruby_source_path"], work / "gcc-homebrew.rb", api["ruby_source_checksum"]["sha256"])
    installed_formula = prefix / ".brew/gcc.rb"
    if digest(installed_formula) != digest(formula):
        raise ValueError("Installed Homebrew GCC formula differs from its pinned source recipe")
    sources = [source(archive, stable["url"].replace("http://", "https://"), version), source(formula, raw + api["ruby_source_path"], version)]
    for patch in api.get("patches", []):
        url = patch.get("url") or raw + patch["file"]
        checksum = patch.get("sha256") or api["local_patch_checksums"][patch["file"]]
        path = download(url, work / PurePosixPath(url).name, checksum)
        sources.append(source(path, url, version))
    groups = {}
    for filename, original in origins.items():
        if filename.startswith("bin/mbdyn"):
            continue
        if not Path(original).resolve().is_relative_to(prefix):
            raise ValueError(f"Unreviewed non-GCC Homebrew dependency: {original}")
        family = next((key for key, pattern in NAMES.items() if pattern.fullmatch(PurePosixPath(filename).name)), None)
        if family not in ("gcc-runtime", "quadmath"):
            raise ValueError(f"Unreviewed Homebrew runtime: {filename}")
        groups.setdefault(family, []).append(filename)
    return [{"name": "homebrew-" + family, "family": family, "version": version, "sourceVersion": version,
             "files": files, "packageNotice": reference(copyright_notice(archive, family, work)), "sources": sources,
             "evidence": [reference(receipt), reference(api_file), reference(keg_receipt), reference(installed_formula)]} for family, files in groups.items()]


def collect(solver, work):
    work.mkdir(parents=True, exist_ok=True)
    origins_file = solver / "BUILD-ORIGINS.tsv"
    origins = dict(line.split("\t", 1) for line in origins_file.read_text().splitlines())
    archive = download(MBDYN_URL, work / "mbdyn-1.7.3.tar.gz", MBDYN_SHA)
    notice = work / "MBDyn-COPYRIGHT.txt"
    with tarfile.open(archive) as bundle:
        notice.write_bytes(b"MBDyn 1.7.3 original upstream notices\n\n" + b"\n\n".join(
            bundle.extractfile("mbdyn-1.7.3/" + name).read() for name in ("AUTHORS", "COPYING")))
    platform = "windows" if sys.platform.startswith("cygwin") else "macos" if sys.platform == "darwin" else "linux"
    components = [{"name": "mbdyn", "family": "mbdyn", "version": "1.7.3", "sourceVersion": "1.7.3",
                   "files": [name for name in origins if name.startswith("bin/mbdyn")],
                   "packageNotice": reference(notice), "sources": [source(archive, MBDYN_URL, "1.7.3")],
                   "evidence": [reference(origins_file), reference(ROOT / "backend/evidence/mbconfig.h")]}]
    if platform == "windows":
        components.extend(collect_cygwin(solver, work, origins))
    elif platform == "macos":
        components.extend(collect_homebrew(solver, work, origins))
    else:
        from collect_solver_linux import collect as collect_linux
        components.extend(collect_linux(solver, work, origins))
    inputs = [ROOT / name for name in ("backend/build_solver.sh", "scripts/bundle_solver.sh", ".github/workflows/release.yml",
                                      "backend/evidence/configure-arguments.txt", "backend/evidence/mbconfig.h",
                                      "scripts/collect_solver_sources.py", "scripts/collect_solver_linux.py",
                                      "scripts/prepare_solver_sources.py", "notices/solver/REBUILD.txt")]
    config = (ROOT / "backend/evidence/mbconfig.h").read_text()
    if re.search(r"^#define USE_Y12\s+1", config, re.M):
        raise ValueError("Y12 has no verified redistribution grant in the archived source; disable it")
    return {"format": "kinemeld-solver-input/1", "platform": platform,
            "components": components, "buildInputs": [reference(path) for path in inputs]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        work = args.work or args.sources.parent / "solver-source-work"
        output = args.output or work / "solver-input.json"
        inventory = collect(args.solver, work)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(inventory, indent=2) + "\n")
        prepare(args.solver, args.sources, output)
        print(f"Verified {len(inventory['components'])} solver components and matching sources.")
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Solver corresponding-source collection failed: {error}\n")
