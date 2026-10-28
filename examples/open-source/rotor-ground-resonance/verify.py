"""Run the pinned research model through the configured, bounded MBDyn process."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[2] / "backend"))
import solver


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    provenance = json.loads((ROOT / "provenance.json").read_text())
    for item in provenance["files"]:
        path = ROOT / item["path"]
        if digest(path) != item["sha256"]:
            raise ValueError(f"Original source hash mismatch: {path.name}")
    original = ROOT / "original"
    runnable = ROOT / "runnable"
    source = (original / "GR_rotor.mbd").read_bytes()
    expected = source.replace(b'\toutput results: netcdf, no text;',
        b'# Modified 2026-10-27 for MBDyn Studio: use native text output for importer compatibility.\n#\toutput results: netcdf, no text;')
    if (runnable / "GR_rotor.mbd").read_bytes() != expected:
        raise ValueError("Runnable model differs from the documented output-only adaptation")
    for name in provenance["dependencies"]:
        if (original / name).read_bytes() != (runnable / name).read_bytes():
            raise ValueError(f"Modified include: {name}")
    info = solver.status()
    if not info["available"]:
        raise RuntimeError(info["detail"])
    directory = ROOT / ".runs" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    for path in runnable.iterdir():
        if path.is_file():
            shutil.copyfile(path, directory / path.name)
    argv = solver.command(solver.configuration(), ["-f", "GR_rotor.mbd", "-o", "result"], directory, bounded=True)
    start = time.monotonic()
    result = solver.execute(argv, directory)
    result.update(verifiedAt=datetime.now(timezone.utc).isoformat(), solver=info,
                  elapsedSeconds=time.monotonic() - start, command=argv,
                  runDirectory=str(directory), sourceRevision=provenance["revision"],
                  inputSha256={path.name: digest(path) for path in runnable.iterdir() if path.is_file()},
                  expectedFinalTimeSeconds=60.0, physicalValidation="Not established; execution and finite native output only.")
    log = (directory / "solver.log").read_text(errors="replace")
    shutil.copyfile(directory / "solver.log", ROOT / "failure.log.txt")
    result.update(logTail=log[-8000:], logSha256=digest(directory / "solver.log"),
                  observedStructuralNodeIds=sorted({int(label) for label in re.findall(r"Reading Structural\((\d+)\)", log)}))
    try:
        if "error" in result:
            raise ValueError(result["error"])
        completion = re.search(r"End of simulation at time\s+(\S+)\s+after\s+(\d+)\s+steps", log)
        if not completion:
            raise ValueError("Solver did not report simulation completion")
        final_time, steps = float(completion[1]), int(completion[2])
        if not math.isfinite(final_time) or abs(final_time - 60.0) > 1e-6:
            raise ValueError(f"Requested 60 seconds but solver reported {final_time}")
        counts = Counter()
        ranges = {}
        with (directory / "result.mov").open() as stream:
            for line in stream:
                values = [float(value) for value in line.split()]
                if len(values) != 13 or not all(math.isfinite(value) for value in values):
                    raise ValueError("Malformed or non-finite native motion record")
                node = int(values[0])
                if values[0] != node:
                    raise ValueError("Non-integer native node label")
                counts[node] += 1
                bounds = ranges.setdefault(node, [[value, value] for value in values[1:4]])
                for bounds_i, value in zip(bounds, values[1:4]):
                    bounds_i[0], bounds_i[1] = min(bounds_i[0], value), max(bounds_i[1], value)
        if not counts or len(set(counts.values())) != 1:
            raise ValueError("Native structural nodes have inconsistent record counts")
        result.update(ok=True, finalTimeSeconds=final_time, steps=steps,
                      nativeNodeIds=sorted(counts), recordsPerNode=dict(counts), positionRangesM=ranges,
                      outputs={name: {"sha256":digest(directory/name),"bytes":(directory/name).stat().st_size}
                               for name in ("result.mov", "result.out", "solver.log")})
    except (OSError, ValueError) as error:
        result.update(ok=False, error=str(error))
    (ROOT / "verification.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
