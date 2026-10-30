"""Assemble a Kinemeld desktop release archive for Linux, macOS or Windows.

The archive contains the native desktop host, the Python service, the web interface,
examples, documentation and notices. A prebuilt MBDyn solver directory (bin/ and lib/)
may be bundled; Python 3.10+ and the optional STEP runtime are installed separately.

    python scripts/package_release.py --platform linux --binary native/target/release/mbdyn-studio-desktop \
        --version 0.9.0 [--solver build/solver] [--out dist]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ["backend", "frontend", "examples", "docs", "LICENSE", "THIRD_PARTY_NOTICES.md", "README.md", "start.py", "requirements.txt"]
SKIP_PARTS = {"__pycache__", "evidence", "demos", "node_modules"}
SKIP_FILES = {"solver.json", "agent.json"}


def wanted(path):
    relative = path.relative_to(ROOT)
    if any(part in SKIP_PARTS for part in relative.parts) or path.name in SKIP_FILES:
        return False
    if relative.parts[0] == "backend" and ("vendor" in relative.parts or path.name.startswith("test_") or path.suffix == ".sh"):
        return False
    return path.suffix not in {".pyc", ".log", ".zip", ".stl"}


def copy_resources(target):
    for name in RESOURCES:
        source = ROOT / name
        if source.is_file():
            target.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / name)
            continue
        for path in sorted(source.rglob("*")):
            if path.is_file() and wanted(path):
                destination = target / path.relative_to(ROOT)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)


def executable(path):
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write(path, text, mode_exec=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\r\n" if path.suffix == ".cmd" else "\n")
    if mode_exec:
        executable(path)


def layout(platform, binary, version, solver, stage):
    name = f"Kinemeld-{version}"
    if platform == "macos":
        bundle = stage / "Kinemeld.app" / "Contents"
        app = bundle / "Resources" / "app"
        copy_resources(app)
        (bundle / "MacOS").mkdir(parents=True)
        shutil.copy2(binary, bundle / "MacOS" / "kinemeld")
        executable(bundle / "MacOS" / "kinemeld")
        write(bundle / "Info.plist", f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Kinemeld</string>
<key>CFBundleDisplayName</key><string>Kinemeld</string>
<key>CFBundleIdentifier</key><string>io.github.akshayramanandarao.kinemeld</string>
<key>CFBundleVersion</key><string>{version}</string>
<key>CFBundleShortVersionString</key><string>{version}</string>
<key>CFBundleExecutable</key><string>kinemeld</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSMinimumSystemVersion</key><string>11.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
""")
        write(stage / "README-macOS.txt", "Move Kinemeld.app to Applications. The app is not notarized: on first launch, Control-click it and choose Open.\n"
              "Kinemeld needs Python 3.10+ (python3 on PATH, or set MBDYN_STUDIO_PYTHON). STEP import needs: python3 -m pip install -r Kinemeld.app/Contents/Resources/app/requirements.txt\n")
        return app, stage
    root = stage / name
    copy_resources(root)
    if platform == "windows":
        shutil.copy2(binary, root / "Kinemeld.exe")
        write(root / "Start Kinemeld.cmd", '@echo off\r\nstart "" "%~dp0Kinemeld.exe"\r\n')
        write(root / "Start Kinemeld in browser.cmd", '@echo off\r\ncd /d "%~dp0"\r\npython start.py\r\n')
    else:
        shutil.copy2(binary, root / "kinemeld")
        executable(root / "kinemeld")
        write(root / "start-browser.sh", '#!/bin/sh\ncd "$(dirname "$0")" && exec python3 start.py "$@"\n', True)
        write(root / "kinemeld.desktop", "[Desktop Entry]\nType=Application\nName=Kinemeld\nComment=Multibody dynamics workbench for MBDyn\n"
              "Exec=sh -c 'cd \"$(dirname \"%k\")\" && ./kinemeld'\nTerminal=false\nCategories=Science;Engineering;\n")
    return root, stage


def bundle_solver(solver, app):
    if not solver:
        return False
    target = app / "solver"
    shutil.copytree(solver, target)
    for path in (target / "bin").iterdir():
        executable(path)
    return True


def manifest(app, version, platform, solver):
    files = {}
    for path in sorted(app.rglob("*")):
        if path.is_file():
            files[path.relative_to(app).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    (app / "package-manifest.json").write_text(json.dumps({"application": "Kinemeld", "version": version, "platform": platform,
                                                           "bundledSolver": solver, "files": files}, indent=1) + "\n", encoding="utf-8")


def archive(stage, out, stem, platform):
    out.mkdir(parents=True, exist_ok=True)
    if platform == "linux":
        path = out / f"{stem}.tar.gz"
        with tarfile.open(path, "w:gz") as tar:
            for item in sorted(stage.iterdir()):
                tar.add(item, arcname=item.name)
        return path
    path = out / f"{stem}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(stage.rglob("*")):
            info = zipfile.ZipInfo.from_file(file, file.relative_to(stage).as_posix())
            if file.is_dir():
                continue
            info.compress_type = zipfile.ZIP_DEFLATED
            with file.open("rb") as handle:
                bundle.writestr(info, handle.read())
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--platform", choices=["linux", "macos", "windows"], required=True)
    parser.add_argument("--arch", default="x86_64")
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--solver", type=Path)
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    stage = args.out / f"stage-{args.platform}-{args.arch}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    app, top = layout(args.platform, args.binary, args.version, args.solver, stage)
    bundled = bundle_solver(args.solver, app)
    manifest(app, args.version, args.platform, bundled)
    path = archive(top, args.out, f"Kinemeld-{args.version}-{args.platform}-{args.arch}", args.platform)
    shutil.rmtree(stage)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (path.parent / (path.name + ".sha256")).write_text(f"{digest}  {path.name}\n", encoding="utf-8")
    print(f"{path} ({path.stat().st_size / 1e6:.1f} MB, solver {'bundled' if bundled else 'not bundled'})")


if __name__ == "__main__":
    os.umask(0o022)
    main()
