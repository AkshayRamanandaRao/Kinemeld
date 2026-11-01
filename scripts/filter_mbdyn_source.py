"""Remove the eleven unused Y12 Fortran files from the pinned upstream archive.

Every retained tar header and file payload is copied byte-for-byte. The resulting
uncompressed tar is deterministic across gzip/zlib implementations and platforms.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

UPSTREAM_URL = "https://raw.githubusercontent.com/mmorandi/MBDyn-web/main/userfiles/downloads/mbdyn-1.7.3.tar.gz"
UPSTREAM_SHA = "3cf05cd1cb14c1af3d987aac119b6ecf0d835bc1aee06bc4cf7cc5a245c1f36d"
FILTERED_SHA = "1fd09e766c30485423d57e0379b5248e095aeec59bcec59a3f4b518e19f0fcc3"
SOURCE_VERSION = "1.7.3-kinemeld-no-y12"
REMOVED = {f"mbdyn-1.7.3/libraries/liby12/{name}.f" for name in (
    "y12mae", "y12maf", "y12mbe", "y12mbf", "y12mce", "y12mcf", "y12mde", "y12mdf", "y12mfe", "y12mge", "y12mhe")}


def transform(upstream, destination, manifest):
    original = upstream.read_bytes()
    if hashlib.sha256(original).hexdigest() != UPSTREAM_SHA:
        raise ValueError("MBDyn upstream archive digest mismatch")
    raw = gzip.decompress(original)
    output, removed = bytearray(), []
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            if member.name in REMOVED:
                removed.append({"path": member.name, "sha256": hashlib.sha256(archive.extractfile(member).read()).hexdigest()})
            else:
                end = member.offset_data + ((member.size + 511) // 512) * 512
                output.extend(raw[member.offset:end])
    if {record["path"] for record in removed} != REMOVED:
        raise ValueError("Pinned MBDyn archive does not contain the exact reviewed Y12 implementation set")
    output.extend(b"\0" * 1024)
    digest = hashlib.sha256(output).hexdigest()
    if digest != FILTERED_SHA:
        raise ValueError("Filtered MBDyn source archive digest mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)
    manifest.write_text(json.dumps({"format": "kinemeld-mbdyn-source-transform/1", "sourceVersion": SOURCE_VERSION,
        "upstreamUrl": UPSTREAM_URL, "upstreamSha256": UPSTREAM_SHA, "outputSha256": digest,
        "transformation": "Remove only the eleven unused libraries/liby12/*.f implementations; preserve all retained tar headers and payloads unchanged; append two zero tar blocks.",
        "reason": "The archived liby12 README supplies no copyright/license grant. Distributed builds use --without-y12.",
        "removed": sorted(removed, key=lambda item: item["path"])}, indent=2) + "\n", encoding="utf-8")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(transform(args.upstream, args.destination, args.manifest))
