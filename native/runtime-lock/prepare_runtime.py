"""Prepare a test-only private CPython runtime from an explicitly pinned offline artifact set.

Preparation does not establish redistribution rights or verify native binary provenance.
The destination must be new; no system Python, PATH or installed packages are changed.
"""
import argparse
import base64
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

from draft_manifest import draft
from verify_runtime import files_under, no_links, read_json, safe_name, sha256

MAX_ARCHIVE_FILES = 10000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
EXPECTED_PIP = "26.0.1"


def artifacts_for(artifacts, lock):
    """Verify the exact declared sources before extracting or executing anything."""
    root = Path(artifacts)
    if not root.is_absolute(): raise ValueError("Artifact directory must be absolute.")
    no_links(root)
    if not root.is_dir(): raise ValueError("Artifact directory does not exist.")
    if lock.get("format") != "mbdyn-python-wheel-lock/1" or not isinstance(lock.get("packages"), dict): raise ValueError("Runtime lock is invalid.")
    python = lock.get("pythonArtifact")
    if not isinstance(python, dict) or set(python) != {"filename", "sha256", "source", "sbom"}: raise ValueError("Python artifact lock is invalid.")
    files = [python] + list(lock["packages"].values())
    paths = []
    names = set()
    for entry in files:
        name, expected = entry.get("filename"), entry.get("sha256")
        safe_name(name)
        if "/" in name or name.casefold() in names: raise ValueError("Artifact names must be unique simple filenames.")
        names.add(name.casefold())
        path = root / name
        try: no_links(path)
        except FileNotFoundError: raise ValueError(f"Missing locked artifact: {name}") from None
        if not path.is_file() or sha256(path) != expected: raise ValueError(f"Locked artifact hash mismatch: {name}")
        paths.append(path)
    return paths[0], paths[1:]


def extract_python(archive, destination):
    """Extract bounded, nonlinked entries without following archive paths outside destination."""
    seen = set(); total = 0
    with zipfile.ZipFile(archive) as source:
        items = source.infolist()
        if len(items) > MAX_ARCHIVE_FILES: raise ValueError("Python archive has too many entries.")
        for item in items:
            raw = item.filename.rstrip("/")
            if not raw: continue
            safe_name(raw)
            key = raw.casefold()
            if key in seen: raise ValueError(f"Duplicate Python archive path: {raw}")
            seen.add(key)
            if stat.S_ISLNK(item.external_attr >> 16): raise ValueError("Python archive contains a symbolic link.")
            if item.flag_bits & 1: raise ValueError("Encrypted Python archive entries are unsupported.")
            total += item.file_size
            if total > MAX_ARCHIVE_BYTES: raise ValueError("Python archive exceeds the extraction limit.")
            target = destination.joinpath(*raw.split("/"))
            if item.is_dir(): target.mkdir(parents=True, exist_ok=True); continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with source.open(item) as inp, target.open("xb") as out: shutil.copyfileobj(inp, out, length=1024 * 1024)
    for name in ("python.exe", "python312.dll", "python312.zip", "python312._pth"):
        if not (destination / name).is_file(): raise ValueError(f"Embedded Python archive is missing {name}.")
    (destination / "python312._pth").write_text("python312.zip\n.\nLib/site-packages\n../../backend\n", encoding="utf8")


def install_wheels(wheels, target):
    """Install only the preverified wheels into a new target using an isolated host pip."""
    if sys.platform != "win32" or sys.version_info[:3] != (3, 12, 10) or sys.maxsize <= 2**32:
        raise ValueError("Runtime preparation requires Windows x64 CPython 3.12.10 as the isolated build host.")
    version = subprocess.run([sys.executable, "-I", "-m", "pip", "--version"], capture_output=True, text=True, timeout=30, check=False)
    if version.returncode or not version.stdout.startswith(f"pip {EXPECTED_PIP} "):
        raise ValueError(f"Runtime preparation requires existing pip {EXPECTED_PIP}; no system installation will be performed.")
    command = [sys.executable, "-I", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-cache-dir", "--no-compile", "--disable-pip-version-check", "--target", str(target), *map(str, wheels)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=900, check=False)
    if result.returncode: raise ValueError("Offline wheel staging failed: " + (result.stderr or result.stdout)[-4000:])
    for entry in target.glob("*.pth"):
        raise ValueError(f"Unreviewed top-level .pth file generated: {entry.name}")
    # Generated CLI wrappers are unrelated to the app and can embed the builder's path.
    for name in ("bin", "Scripts"):
        scripts = target / name
        if scripts.exists():
            no_links(scripts)
            if not scripts.is_dir() or scripts.resolve().parent != target.resolve(): raise ValueError("Unexpected generated scripts path.")
            files_under(scripts.resolve())
            shutil.rmtree(scripts)
    sanitize_installer_metadata(target)


def sanitize_installer_metadata(target):
    """Remove machine-specific pip metadata and references to removed entrypoints."""
    for directory in target.glob('*.dist-info'):
        no_links(directory)
        if not directory.is_dir(): raise ValueError('Invalid installed distribution metadata.')
        direct=directory/'direct_url.json'; record=directory/'RECORD'
        if not direct.exists(): continue
        no_links(direct); no_links(record)
        if not direct.is_file() or not record.is_file(): raise ValueError('Installed distribution metadata is incomplete.')
        with record.open(encoding='utf8',newline='') as stream: rows=list(csv.reader(stream))
        expected=f'{directory.name}/direct_url.json'
        if any(len(row)!=3 for row in rows) or sum(row[0]==expected for row in rows)!=1:
            raise ValueError('Installed distribution RECORD has invalid direct URL metadata.')
        retained=[]
        for row in rows:
            path=row[0].replace('\\','/')
            if path==expected or path.startswith(('../../bin/','../../Scripts/')):continue
            if path.startswith('../../share/'):
                path=path[6:];safe_name(path);installed=target.joinpath(*path.split('/'))
                for part in [installed,*installed.parents]:
                    if part==target:break
                    no_links(part)
                if not installed.is_file():raise ValueError('Relocated wheel data is not a regular file.')
                digest='sha256='+base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest()).decode().rstrip('=')
                if row[1]!=digest or row[2]!=str(installed.stat().st_size):raise ValueError('Relocated wheel data does not match its RECORD.')
                row[0]=path
            safe_name(path)
            retained.append(row)
        direct.unlink()
        with record.open('w',encoding='utf8',newline='') as stream:csv.writer(stream,lineterminator='\n').writerows(retained)


def prepare(artifacts, destination, lock, installer=install_wheels):
    """Build a new draft runtime, or remove the temporary staging folder on failure."""
    archive, wheels = artifacts_for(artifacts, lock)
    output = Path(destination)
    if not output.is_absolute() or not output.name: raise ValueError("Runtime destination must be an absolute new directory.")
    safe_name(output.name)
    parent = output.parent.resolve(strict=True)
    if not parent.is_dir(): raise ValueError("The destination parent must exist.")
    output = parent / output.name
    if output.exists() or output.is_symlink(): raise ValueError("Runtime destination already exists; choose a new path.")
    temporary = Path(tempfile.mkdtemp(prefix=".mbdyn-runtime-", dir=parent))
    try:
        extract_python(archive, temporary)
        site = temporary / "Lib" / "site-packages"; site.mkdir(parents=True)
        installer(wheels, site)
        # Detect any persistent artifact change while the builder was working.
        artifacts_for(artifacts, lock)
        manifest = draft(temporary, archive, lock)
        (temporary / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf8")
        temporary.rename(output)
        return {"runtime": str(output), "python": str(output / "python.exe"), "artifacts": len(wheels) + 1,
                "noticeReview": "required", "redistributionStatus": "not-established"}
    finally:
        if temporary.exists():
            if temporary.parent.resolve() != parent or not temporary.name.startswith(".mbdyn-runtime-") or temporary.is_symlink(): raise RuntimeError("Refusing unexpected temporary cleanup target.")
            files_under(temporary.resolve())
            shutil.rmtree(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True); parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.artifacts, args.destination, read_json(Path(__file__).with_name("windows-cp312.json")))
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Cannot prepare private runtime: {exc}\n")


if __name__ == "__main__": main()
