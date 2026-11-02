"""Isolated real Studio/solver fixture; no user settings or retained runs are changed."""
import json
from pathlib import Path
import sys
import tempfile
from http.server import ThreadingHTTPServer

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import app_paths
import server
import solver
from verify_rotary_control import robot_arm

binary=Path(sys.argv[1]).resolve()
if not binary.is_file():raise SystemExit('Supply an existing native MBDyn executable.')
with tempfile.TemporaryDirectory(prefix='kinemeld-servo-') as temporary:
    root=Path(temporary)
    solver.RUNS=app_paths.RUNS=app_paths.LEGACY_RUNS=root/'runs'
    server.TOUR_PREFERENCE=root/'tour.json'
    solver.configuration=lambda:dict(mode='native',executable=str(binary))
    class Handler(server.Handler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/fixture/active-controller':
                directories=sorted(solver.RUNS.glob('*'),key=lambda path:path.stat().st_mtime,reverse=True)
                for directory in directories:
                    trace=directory/'controller-trace.jsonl'
                    if trace.exists() and not (directory/'summary.json').exists():
                        self.respond({'runId':directory.name,'bytes':trace.stat().st_size});return
                self.respond({'runId':None,'bytes':0});return
            super().do_GET()
    service=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    print(json.dumps({'port':service.server_port,'model':robot_arm()}),flush=True)
    try:service.serve_forever()
    finally:service.server_close()
