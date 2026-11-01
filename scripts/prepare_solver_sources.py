"""Prepare and verify exact solver notices and corresponding-source evidence.

The reviewed inventory is tied to the build runner's package metadata, not library
filenames alone. Source archives stay beside the binary artifact for release upload.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "kinemeld-solver-compliance/1"
MBDYN_SHA = "1fd09e766c30485423d57e0379b5248e095aeec59bcec59a3f4b518e19f0fcc3"
LICENSES = {
    "mbdyn": "GPL-2.0-only",
    "gcc-runtime": "GPL-3.0-or-later WITH GCC-exception-3.1",
    "quadmath": "LGPL-2.1-or-later",
    "cygwin": "LGPL-3.0-or-later WITH Cygwin-exception",
    "libiconv": "LGPL-2.1-or-later",
    "gettext-runtime": "LGPL-2.1-or-later",
    "lapack-blas": "BSD-3-Clause",
}
NAMES = {
    "mbdyn": re.compile(r"mbdyn(?:\.exe)?$"),
    "gcc-runtime": re.compile(r"(?:lib(?:gfortran|gcc_s|stdc\+\+|gomp)[.-]|cyg(?:gfortran|gcc_s|stdc\+\+|gomp)[-_]).+", re.I),
    "quadmath": re.compile(r"(?:lib|cyg)quadmath[.-].+", re.I),
    "cygwin": re.compile(r"cygwin1\.dll$", re.I),
    "libiconv": re.compile(r"(?:cygiconv|libiconv)[.-].+", re.I),
    "gettext-runtime": re.compile(r"(?:cygintl|libintl)[.-].+", re.I),
    "lapack-blas": re.compile(r"lib(?:lapack|blas|openblas)[.-].+", re.I),
}
LEGAL_FILES = {
    "mbdyn": ["GPL-2.0.txt", "COLAMD-2.1.txt", "OpenLDAP-getopt.txt", "OpenLDAP-COPYRIGHT.txt", "OpenLDAP-LICENSE.txt"],
    "gcc-runtime": ["GPL-3.0.txt", "GCC-exception-3.1.txt"],
    "quadmath": ["LGPL-2.1.txt"],
    "cygwin": ["GPL-3.0.txt", "LGPL-3.0.txt", "Cygwin-exception.txt", "Cygwin-NEWLIB.txt"],
    "libiconv": ["LGPL-2.1.txt"],
    "gettext-runtime": ["LGPL-2.1.txt"],
    "lapack-blas": [],
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def child(root, name):
    relative = PurePosixPath(name)
    if not name or "\\" in name or relative.is_absolute() or any(p in ("..", ".") for p in relative.parts):
        raise ValueError(f"Unsafe artifact path: {name!r}")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Artifact escapes its root: {name!r}")
    if path.is_symlink():
        raise ValueError(f"Artifact must be a regular file, not a symbolic link: {name!r}")
    return path


def verify_license_texts(notices):
    records = json.loads((notices / "license-provenance.json").read_text(encoding="utf-8"))["licenses"]
    names = [record["file"] for record in records]
    required = {name for files in LEGAL_FILES.values() for name in files}
    if len(names) != len(set(names)) or not required <= set(names):
        raise ValueError("Solver license provenance is duplicate or incomplete.")
    for record in records:
        path = child(notices, record["file"])
        if not path.is_file() or digest(path) != record["sha256"]:
            raise ValueError(f"Solver license text differs from reviewed provenance: {record['file']}")


def checked_input(item, base):
    path = Path(item["path"])
    if not path.is_absolute():
        path = base / path
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing regular input artifact: {path}")
    expected = item.get("sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(path) != expected:
        raise ValueError(f"Input digest mismatch: {path}")
    return path


def put(source, root, name):
    target = child(root, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and digest(target) != digest(source):
        raise ValueError(f"Refusing to replace a different source artifact: {target}")
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return {"path": name, "sha256": digest(target), "bytes": target.stat().st_size}


def check_record(root, record):
    path = child(root, record["path"])
    if not path.is_file() or path.stat().st_size != record.get("bytes") or digest(path) != record.get("sha256"):
        raise ValueError(f"Missing or changed solver compliance artifact: {record['path']}")
    return path


def binaries(solver):
    result = set()
    for folder in ("bin", "lib"):
        for path in (solver / folder).rglob("*") if (solver / folder).is_dir() else []:
            if path.is_file():
                if path.is_symlink():
                    raise ValueError(f"Bundled libraries must be materialized regular files: {path}")
                result.add(path.relative_to(solver).as_posix())
    return result


def verify(solver, sources):
    manifest = json.loads((solver / "DEPENDENCIES.json").read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT or manifest.get("platform") not in ("linux", "macos", "windows"):
        raise ValueError("Unsupported solver compliance manifest.")
    covered = set()
    if not manifest.get("components"):
        raise ValueError("The solver compliance inventory is empty.")
    for component in manifest["components"]:
        family = component.get("family")
        if family not in LICENSES or component.get("license") != LICENSES[family]:
            raise ValueError(f"Unreviewed solver runtime license/family: {family}")
        if not component.get("version") or not component.get("sourceVersion"):
            raise ValueError("A component must identify its installed and source-package versions.")
        if not component.get("files") or not component.get("notices") or not component.get("sources") or not component.get("evidence"):
            raise ValueError(f"Incomplete notices, source or build-package evidence for {component.get('name')}")
        for record in component["files"]:
            name = record["path"]
            if name in covered or not NAMES[family].fullmatch(PurePosixPath(name).name):
                raise ValueError(f"Duplicate or unreviewed bundled library: {name}")
            if PurePosixPath(name).parts[0] not in ("bin", "lib"):
                raise ValueError(f"A solver binary must be in bin/ or lib/: {name}")
            covered.add(name)
            check_record(solver, record)
        for record in component["notices"]:
            path = check_record(solver, record)
            if path.stat().st_size < 40:
                raise ValueError(f"Empty or placeholder notice: {path}")
        notice_names = {PurePosixPath(record["path"]).name for record in component["notices"]}
        if not set(LEGAL_FILES[family]) <= notice_names:
            raise ValueError(f"Required complete license/exception texts absent for {component['name']}")
        if not component.get("packageNotice") or component["packageNotice"] not in [r["path"] for r in component["notices"]]:
            raise ValueError(f"The actual upstream/distribution copyright notice is absent for {component['name']}")
        for record in component["sources"]:
            check_record(sources, record)
            if urlparse(record.get("url", "")).scheme != "https" or record.get("sourceVersion") != component["sourceVersion"]:
                raise ValueError(f"Source version/HTTPS provenance missing for {component['name']}")
        if family == "mbdyn" and not any(record["sha256"] == MBDYN_SHA for record in component["sources"]):
            raise ValueError("MBDyn corresponding source is not the pinned Y12-filtered 1.7.3 archive.")
        for record in component["evidence"]:
            check_record(sources, record)
    if covered != binaries(solver):
        raise ValueError(f"Solver inventory does not cover every bundled binary: {sorted(binaries(solver) ^ covered)}")
    if not any(c["family"] == "mbdyn" for c in manifest["components"]):
        raise ValueError("MBDyn itself is missing from the solver inventory.")
    if not manifest.get("buildInputs"):
        raise ValueError("Corresponding source must retain the build/packaging scripts.")
    for record in manifest["buildInputs"]:
        check_record(sources, record)
    source_manifest = json.loads((sources / "source-manifest.json").read_text(encoding="utf-8"))
    if source_manifest != manifest:
        raise ValueError("Binary and corresponding-source manifests differ.")
    return manifest


def prepare(solver, sources, inventory):
    verify_license_texts(ROOT / "notices/solver")
    spec = json.loads(inventory.read_text(encoding="utf-8"))
    if spec.get("format") != "kinemeld-solver-input/1":
        raise ValueError("Unsupported reviewed solver-input inventory.")
    if not solver.is_dir():
        raise ValueError("The solver bundle must already exist.")
    manifest = {"format": FORMAT, "platform": spec["platform"], "components": [], "buildInputs": []}
    sources.mkdir(parents=True, exist_ok=True)
    for original in spec["components"]:
        component = {key: original[key] for key in ("name", "family", "version", "sourceVersion")}
        family = component["family"]
        if family not in LICENSES:
            raise ValueError(f"Unreviewed runtime family: {family}")
        component["license"] = LICENSES[family]
        component["files"] = []
        for name in original["files"]:
            path = child(solver, name)
            if not path.is_file():
                raise ValueError(f"Inventory names a missing bundled file: {name}")
            component["files"].append({"path": name, "sha256": digest(path), "bytes": path.stat().st_size})
        component["notices"] = []
        for name in LEGAL_FILES[family]:
            component["notices"].append(put(ROOT / "notices/solver" / name, solver, f"notices/licenses/{name}"))
        notice = checked_input(original["packageNotice"], inventory.parent)
        notice_name = f"notices/{original['name']}/{notice.name}"
        component["notices"].append(put(notice, solver, notice_name))
        component["packageNotice"] = notice_name
        component["sources"] = []
        for item in original["sources"]:
            source = checked_input(item, inventory.parent)
            record = put(source, sources, f"archives/{source.name}")
            record.update(url=item["url"], sourceVersion=item["sourceVersion"])
            if "derivation" in item:
                record["derivation"] = item["derivation"]
            component["sources"].append(record)
        component["evidence"] = []
        for item in original["evidence"]:
            path = checked_input(item, inventory.parent)
            component["evidence"].append(put(path, sources, f"metadata/{original['name']}/{path.name}"))
        manifest["components"].append(component)
    for item in spec.get("buildInputs", []):
        path = checked_input(item, inventory.parent)
        manifest["buildInputs"].append(put(path, sources, f"build/{path.name}"))
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    (solver / "DEPENDENCIES.json").write_text(text, encoding="utf-8")
    (sources / "source-manifest.json").write_text(text, encoding="utf-8")
    verify(solver, sources)
    (solver / "SOURCE.txt").write_text(
        "The exact per-file versions, copyright notices and source hashes are in DEPENDENCIES.json.\n"
        "The matching solver-sources release artifact contains every recorded archive, distribution\n"
        "metadata file and build/packaging input. Distribute it alongside this binary package.\n"
        "These checks establish artifact identity and inventory coverage, not legal advice or\n"
        "bit-for-bit reproducible builds. Runtime libraries remain replaceable in bin/ and lib/.\n",
        encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "verify"])
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--inventory", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        if not args.inventory:
            parser.error("prepare requires --inventory from the exact build/package evidence")
        result = prepare(args.solver, args.sources, args.inventory)
    else:
        result = verify(args.solver, args.sources)
    print(json.dumps({"ok": True, "platform": result["platform"], "components": len(result["components"]),
                      "files": sum(len(c["files"]) for c in result["components"])}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError) as error:
        print(f"Solver source audit failed: {error}", file=sys.stderr)
        raise SystemExit(1)
