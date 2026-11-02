"""Isolated actual-solver fixture for the design-search GUI checks."""
from copy import deepcopy
from http.server import ThreadingHTTPServer
from pathlib import Path
import json
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
import app_paths
import models
import server
import solver

binary = Path(sys.argv[1]).resolve()
if not binary.is_file():
    raise SystemExit("Supply a native MBDyn executable for the GUI test.")
with tempfile.TemporaryDirectory(prefix="kinemeld-design-search-") as temporary:
    runs = Path(temporary) / "runs"
    runs.mkdir()
    solver.RUNS = app_paths.RUNS = app_paths.LEGACY_RUNS = runs
    solver.configuration = lambda: {"mode": "native", "executable": str(binary)}
    server.TOUR_PREFERENCE = runs / "tour.json"
    model = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "mass-spring"))
    model["simulation"] = {"duration": .4, "step": .0025}
    app = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    print(json.dumps({"port": app.server_port, "model": model}), flush=True)
    try:
        app.serve_forever()
    finally:
        app.server_close()
