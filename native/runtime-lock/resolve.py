#!/usr/bin/env python3
"""Resolve the explicitly pinned Windows CPython 3.12 wheel inventory from PyPI metadata.

This records artifact identity, not software authenticity or redistribution approval.
It downloads metadata only; package installation is a separate, explicit operation.
"""
import json
from pathlib import Path
import re
import urllib.request

# These are the versions on the qualification host, not a security certification.
PACKAGES = {
    "cadquery-ocp": ("7.9.3.1.1", "cadquery_ocp-7.9.3.1.1-cp312-cp312-win_amd64.whl"),
    "cadquery-ocp-proxy": ("7.9.3.1.1", "cadquery_ocp_proxy-7.9.3.1.1-py3-none-any.whl"),
    "vtk": ("9.6.2", "vtk-9.6.2-cp312-cp312-win_amd64.whl"),
    "matplotlib": ("3.11.0", "matplotlib-3.11.0-cp312-cp312-win_amd64.whl"),
    "numpy": ("2.4.4", "numpy-2.4.4-cp312-cp312-win_amd64.whl"),
    "contourpy": ("1.3.3", "contourpy-1.3.3-cp312-cp312-win_amd64.whl"),
    "cycler": ("0.12.1", "cycler-0.12.1-py3-none-any.whl"),
    "fonttools": ("4.63.0", "fonttools-4.63.0-cp312-cp312-win_amd64.whl"),
    "kiwisolver": ("1.5.0", "kiwisolver-1.5.0-cp312-cp312-win_amd64.whl"),
    "packaging": ("26.0", "packaging-26.0-py3-none-any.whl"),
    "pillow": ("12.2.0", "pillow-12.2.0-cp312-cp312-win_amd64.whl"),
    "pyparsing": ("3.3.2", "pyparsing-3.3.2-py3-none-any.whl"),
    "python-dateutil": ("2.9.0.post0", "python_dateutil-2.9.0.post0-py2.py3-none-any.whl"),
    "six": ("1.17.0", "six-1.17.0-py2.py3-none-any.whl"),
}


def main():
    try:
        from packaging.markers import default_environment
        from packaging.requirements import Requirement
        from packaging.utils import canonicalize_name
        from packaging.version import Version
    except ImportError as exc:
        raise SystemExit("The metadata resolver needs the existing Python 'packaging' library; it never installs packages.") from exc
    environment = default_environment()
    environment.update(python_version="3.12", python_full_version="3.12.10", sys_platform="win32", os_name="nt", platform_system="Windows", platform_machine="AMD64", implementation_name="cpython", platform_python_implementation="CPython", extra="")
    metadata = {}
    for name, (version, filename) in sorted(PACKAGES.items()):
        url=f"https://pypi.org/pypi/{name}/{version}/json"
        with urllib.request.urlopen(url, timeout=30) as response:
            if response.geturl() != url:
                raise ValueError(f"Unexpected metadata redirect for {name}")
            entry=json.load(response)
        if entry["info"]["version"] != version:
            raise ValueError(f"Unexpected version for {name}")
        matches=[item for item in entry["urls"] if item["filename"]==filename and item["packagetype"]=="bdist_wheel"]
        if len(matches)!=1 or not re.fullmatch(r"[0-9a-f]{64}", matches[0]["digests"]["sha256"]):
            raise ValueError(f"Missing or ambiguous target wheel for {name}: {filename}")
        wheel=matches[0]
        if wheel.get("yanked"):
            raise ValueError(f"Pinned wheel for {name} has been yanked")
        metadata[name]={"version":version,"filename":filename,"sha256":wheel["digests"]["sha256"],"source":url,"url":wheel["url"],"requires":entry["info"].get("requires_dist") or []}
    # Verify every active runtime dependency of the explicit closure for the target environment.
    for name, data in metadata.items():
        for text in data["requires"]:
            requirement=Requirement(text)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            dep=canonicalize_name(requirement.name)
            if dep not in metadata or not requirement.specifier.contains(Version(metadata[dep]["version"]), prereleases=True):
                raise ValueError(f"Incomplete Windows CPython 3.12 runtime closure: {name} requires {text}")
    target=Path(__file__).resolve().parent
    python_artifact={"filename":"python-3.12.10-embed-amd64.zip","sha256":"4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3","source":"https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip","sbom":"https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip.spdx.json"}
    lock={"format":"mbdyn-python-wheel-lock/1","target":"CPython 3.12, Windows x86-64","pythonVersionTested":"3.12.10","licenseReview":"not completed","pythonArtifact":python_artifact,"packages":metadata}
    (target/"windows-cp312.json").write_text(json.dumps(lock,indent=2,sort_keys=True)+"\n",encoding="utf8")
    lines=["# Windows x86-64 / CPython 3.12 only; see windows-cp312.json.","# Artifact hashes do not establish authenticity, license clearance or security.","--only-binary=:all:"]
    lines += [f"{name}=={value['version']} --hash=sha256:{value['sha256']}" for name,value in metadata.items()]
    (target/"requirements-windows-cp312.txt").write_text("\n".join(lines)+"\n",encoding="utf8")
    print(f"Locked {len(metadata)} exact wheel artifacts; runtime and native-binary license audit remains open.")

if __name__ == "__main__":
    main()
