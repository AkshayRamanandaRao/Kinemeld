"""Owned local-model fixture and isolated run store for assistant workflow GUI tests."""
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
import tempfile
import threading

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
import agent
import app_paths
import models
import server
import solver

binary = Path(sys.argv[1]).resolve()
if not binary.is_file():
    raise SystemExit("Supply a verified native MBDyn executable for the owned GUI test.")
storage = tempfile.TemporaryDirectory(prefix="kinemeld-agent-workflows-")
runs = Path(storage.name) / "runs"
runs.mkdir()
solver.RUNS = app_paths.RUNS = app_paths.LEGACY_RUNS = runs
solver.configuration = lambda: {"mode": "native", "executable": str(binary)}
server.TOUR_PREFERENCE = runs / "tour.json"

model = deepcopy(next(item["model"] for item in models.EXAMPLES if item["id"] == "spatial-revolute"))
model["simulation"] = {"duration": .2, "step": .005}
joint = model["joints"][0]
model["frames"] = [dict(id="datum"+side.upper(), name="Picked datum "+side.upper(), body=joint[side],
                        translation=deepcopy(joint["anchor"+side.upper()]), rotation=dict(rx=0., ry=0., rz=0.)) for side in ("a", "b")]
links = [dict(joint=joint["id"], side=side, frame="datum"+side.upper(),
              axis=max(joint["axis"+side.upper()], key=lambda key: joint["axis"+side.upper()][key])) for side in ("a", "b")]


class LocalModel(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value):
        data = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply({"models": [{"name": "fixture:tools", "size": 2000000}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/show":
            return self.reply({"capabilities": ["tools"]})
        if body["messages"][-1]["role"] == "tool":
            calls = []
        else:
            text = next(item["content"] for item in reversed(body["messages"]) if item["role"] == "user")
            if text.startswith("Study"):
                calls = [("set_parameter_study", {"input": "bodies/arm/mass", "values": [.5, 1., 2.]})]
                if text.startswith("StudyWrongRun"):
                    calls.append(("request_run", {}))
                elif "then run the study" in text:
                    calls.append(("request_study_run", {}))
            elif text.startswith("FrameLinks"):
                calls = [("link_joint_frames", {"links": links})]
            elif text.startswith("Rename"):
                calls = [("set_model_name", {"name": "Reviewed robot joint"})]
            else:
                calls = [("current_result_summary", {})]
        self.reply({"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": "Review the recorded tool evidence and any proposed workflow before applying.",
                   "tool_calls": [{"function": {"name": name, "arguments": args}} for name, args in calls]}})


provider = ThreadingHTTPServer(("127.0.0.1", 0), LocalModel)
threading.Thread(target=provider.serve_forever, daemon=True).start()
agent.configuration = lambda: f"http://127.0.0.1:{provider.server_port}"
agent.time_budget = lambda: 15
app = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
print(json.dumps({"port": app.server_port, "model": model}), flush=True)
try:
    app.serve_forever()
finally:
    app.server_close()
    provider.shutdown()
    provider.server_close()
    storage.cleanup()
