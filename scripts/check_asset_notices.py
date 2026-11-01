"""Check the pinned shipped frontend/CAD/model assets and their retained notices."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HASH = re.compile(r"[0-9a-f]{64}")


def checked_path(root, name):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or any(ord(c) < 32 for c in name):
        raise ValueError(f"Unsafe asset path: {name!r}")
    parts = PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or any(part in (".", "..") for part in name.split("/")) or "" in name.split("/"):
        raise ValueError(f"Unsafe asset path: {name!r}")
    path = root
    for part in parts:
        path /= part
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError(f"Linked asset paths are not allowed: {name}")
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Asset is not a regular file within the package: {name}")
    return path


def checked_hash(root, entry):
    path = checked_path(root, entry["path"])
    expected = entry["sha256"]
    if isinstance(expected, str):
        hashes = [expected]
    elif isinstance(expected, dict) and set(expected) == {"lf", "crlf"}:
        hashes = list(expected.values())
    else:
        raise ValueError(f"Invalid asset hash declaration: {entry['path']}")
    if not all(isinstance(value, str) and HASH.fullmatch(value) for value in hashes):
        raise ValueError(f"Invalid SHA-256: {entry['path']}")
    data = path.read_bytes()
    if not data or hashlib.sha256(data).hexdigest() not in hashes:
        raise ValueError(f"Asset/notice hash mismatch: {entry['path']}")
    if isinstance(expected, dict):
        lf = data.replace(b"\r\n", b"\n")
        if b"\r" in lf or hashlib.sha256(lf).hexdigest() != expected["lf"] or hashlib.sha256(lf.replace(b"\n", b"\r\n")).hexdigest() != expected["crlf"]:
            raise ValueError(f"Asset line-ending hashes disagree: {entry['path']}")
    return entry["path"]


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def verify(root):
    """Verify package bytes offline; upstream source review is pinned in the manifest."""
    root = Path(root).resolve(strict=True)
    manifest_path = checked_path(root, "notices/assets.json")
    if manifest_path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Asset notice manifest is too large.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)
    if not isinstance(manifest, dict) or manifest.get("format") != "kinemeld-asset-notices/1" or not isinstance(manifest.get("components"), list) or not 1 <= len(manifest["components"]) <= 32:
        raise ValueError("Unsupported asset notice manifest.")
    identifiers, files, notices = set(), set(), set()
    for component in manifest["components"]:
        if not isinstance(component, dict):
            raise ValueError("Asset components must be objects.")
        identifier = component.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError("Asset component IDs must be unique and nonempty.")
        identifiers.add(identifier)
        if component.get("license") not in ("MIT", "OFL-1.1", "GPL-2.0-only") or not isinstance(component.get("version"), str) or not component["version"]:
            raise ValueError(f"Missing reviewed license/version: {identifier}")
        sources = component.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"Source artifacts are missing: {identifier}")
        for source in sources:
            if not isinstance(source, dict) or not isinstance(source.get("url"), str) or not isinstance(source.get("sha256"), str):
                raise ValueError(f"Invalid source artifact metadata: {identifier}")
            url = urlparse(source.get("url", ""))
            if url.scheme != "https" or not url.netloc or url.username or url.password or not HASH.fullmatch(source.get("sha256", "")):
                raise ValueError(f"Invalid source artifact URL/digest: {identifier}")
        for group, seen in (("files", files), ("notices", notices)):
            entries = component.get(group)
            if not isinstance(entries, list) or not entries or len(entries) > 512:
                raise ValueError(f"Missing or oversized {group}: {identifier}")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"Invalid {group} entry: {identifier}")
                index = entry.get("source")
                if type(index) is not int or not 0 <= index < len(sources) or not isinstance(entry.get("sourcePath"), str) or not entry["sourcePath"] or not isinstance(entry.get("upstreamSha256"), str) or not HASH.fullmatch(entry["upstreamSha256"]):
                    raise ValueError(f"Source identity is missing: {identifier}")
                name = checked_hash(root, entry)
                shipped_hashes = entry["sha256"].values() if isinstance(entry["sha256"], dict) else [entry["sha256"]]
                if entry["upstreamSha256"] not in shipped_hashes and not isinstance(entry.get("modifications"), str):
                    raise ValueError(f"Unexplained upstream source difference: {name}")
                if group == "files" and name in files:
                    raise ValueError(f"Asset declared more than once: {name}")
                seen.add(name)
    # Extra assets in these curated locations need a license/source review before shipping.
    actual = {path.relative_to(root).as_posix() for folder, suffixes in (
        ("frontend/vendor", {".js", ".txt"}),
        ("frontend/fonts", {".ttf", ".otf", ".woff", ".woff2", ".txt"}),
        ("examples", {".step", ".stp"}),
        ("examples/open-source", {".mbd", ".elm", ".nod", ".ref"}),
    ) for path in (root / folder).rglob("*") if path.is_file() and path.suffix.lower() in suffixes}
    declared = files | notices
    if actual - declared:
        raise ValueError(f"Assets lack pinned notices/source identity: {sorted(actual - declared)}")
    return {"ok": True, "components": len(identifiers), "files": len(files), "notices": len(notices),
            "scope": "Pinned asset and retained-notice identity; excludes separately bundled native/runtime dependencies."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.root), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Asset notice verification failed: {error}\n")


if __name__ == "__main__":
    main()
