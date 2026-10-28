"""Real runs through the shared catalog route; saves compact reproducibility evidence."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import source_catalog


def main():
    reports = []
    for entry in source_catalog.catalog():
        if not entry.get("enabled"):
            continue
        result, status = source_catalog.run(entry["id"])
        assert status == 200 and result["ok"], {key: value for key, value in result.items() if key != "samples"}
        assert result["exitCode"] == 0 and result["metrics"]["maxNodeDisplacement"] > 1e-6
        report = {key: result[key] for key in ("runId", "exitCode", "deckSha256", "solver", "metrics", "elapsedSeconds")}
        report.update(id=entry["id"], sourceFiles=entry["files"], normalTermination=True)
        reports.append(report)
        print(json.dumps(report), flush=True)
    evidence = {"verifiedAtUtc": datetime.now(timezone.utc).isoformat(), "passed": True,
                "parserSha256": hashlib.sha256(Path(source_catalog.__file__).read_bytes()).hexdigest(),
                "scope": "Curated catalog run route: exact pinned source hashes, exit0, normal termination, finite complete native structural-node trajectories and requested final time. No independent mechanism accuracy or industrial qualification claim.",
                "runs": reports}
    (source_catalog.ROOT / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
