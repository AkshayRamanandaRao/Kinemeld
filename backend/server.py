"""Local-only Kinemeld API and static frontend server (standard library)."""

import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

from models import EXAMPLES, deck, metrics, preview, validate
import solver
import source_catalog
import agent
import app_paths
import featured
import step_geometry
import step_mass
import kinematics
import primitive_step

ROOT = app_paths.RESOURCE_ROOT
VERSION = "0.3.0"
RUN_LOCK = threading.Lock()
RUN_CONTROL_LOCK = threading.Lock()
ACTIVE_RUN = None
PENDING_CANCELLATIONS = {}
FINISHED_TOKENS = {}
STEP_LOCK = threading.Lock()
KINEMATICS_LOCK = threading.Lock()
STEP_ROOT = ROOT / "examples" / "step-suspension"
TOUR_PREFERENCE = app_paths.TOUR_PREFERENCE


def _expire_run_tokens(now):
    for records in (PENDING_CANCELLATIONS, FINISHED_TOKENS):
        for token, expiry in list(records.items()):
            if expiry <= now:
                del records[token]


def request_run_cancel(token):
    """Cancel only the run identified by the caller's random request token."""
    with RUN_CONTROL_LOCK:
        now=time.monotonic();_expire_run_tokens(now)
        if ACTIVE_RUN is not None:
            if ACTIVE_RUN[0] != token:
                return {"ok":False,"error":"That run token does not own the active solver."}, 404
            ACTIVE_RUN[1].cancel()
            return {"ok":True,"state":"stopping"}, 200
        if token in FINISHED_TOKENS:
            return {"ok":False,"error":"This solver run has already finished."}, 409
        if len(PENDING_CANCELLATIONS) >= 128:
            return {"ok":False,"error":"Too many pending cancellation requests."}, 429
        PENDING_CANCELLATIONS[token]=now+30
        return {"ok":True,"state":"pending"}, 202


def begin_run_control(token):
    global ACTIVE_RUN
    control=solver.RunControl() if token else None
    with RUN_CONTROL_LOCK:
        _expire_run_tokens(time.monotonic())
        if token and token in FINISHED_TOKENS:
            raise ValueError("A run token cannot be reused.")
        if token and PENDING_CANCELLATIONS.pop(token,None) is not None:
            control.cancel()
        ACTIVE_RUN=(token,control)
    return control


def finish_run_control(token):
    global ACTIVE_RUN
    with RUN_CONTROL_LOCK:
        ACTIVE_RUN=None
        if token: FINISHED_TOKENS[token]=time.monotonic()+30


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "frontend"), **kwargs)

    def local_request(self):
        allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        if host not in allowed or (origin is not None and origin not in {"http://"+h for h in allowed}):
            self.respond({"ok": False, "error": "Only same-origin loopback requests are accepted."}, 403)
            return False
        return True

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def respond(self, value, status=200):
        content = json.dumps(value, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def send_file(self, path, attachment=False):
        if not path.is_file():
            self.respond({"ok": False, "error": "File not found."}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as source:
            self.copyfile(source, self.wfile)

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/health":
            health = {"application": "mbdyn-studio", "version": VERSION}
            if nonce := getattr(self.server, "startup_nonce", None):
                health["startupNonce"] = nonce
            self.respond(health)
        elif path == "/api/status":
            self.respond({"solver": solver.status(), "capabilities": [x["id"] for x in EXAMPLES], "localOnly": True, "projectSchemaVersion": 1})
        elif path == "/api/examples":
            self.respond({"examples": EXAMPLES})
        elif path == "/api/featured":
            self.respond({"studies": featured_catalog()})
        elif match := re.fullmatch(r"/api/featured/([a-z0-9-]{1,64})", path):
            study = next((item for item in featured_catalog() if item["id"] == match[1]), None)
            if not study:
                self.respond({"ok": False, "error": "Unknown featured study."}, 404)
                return
            self.respond(featured.project(study))
        elif path == "/api/source-examples":
            self.respond({"examples": source_catalog.catalog()})
        elif path == "/api/agent/status":
            self.respond(agent.status())
        elif path == "/api/tour-preference":
            try:
                preference_path = app_paths.existing_config(TOUR_PREFERENCE, app_paths.TOUR_PREFERENCE, app_paths.LEGACY_TOUR_PREFERENCE)
                preference = json.loads(preference_path.read_text(encoding="utf-8")) if preference_path.exists() else {"enabled": False}
                if not isinstance(preference, dict) or set(preference) != {"enabled"} or type(preference["enabled"]) is not bool:
                    raise ValueError("Invalid saved tour preference.")
                self.respond(preference)
            except (OSError, ValueError) as exc:
                self.respond({"ok": False, "error": str(exc)}, 500)
        elif path == "/api/step/suspension":
            self.respond(json.loads((STEP_ROOT / "catalog.json").read_text(encoding="utf-8")))
        elif path == "/api/step/pendulum":
            asset = ROOT / "examples" / "step-pendulum" / "pendulum.step"
            if not asset.is_file() or hashlib.sha256(asset.read_bytes()).hexdigest() != "21d27f30d5cc9459f70d7d3cc66f61a6e7c6b1a7e4f69b4fd72e2837090d96ac":
                self.respond({"ok": False, "error": "The original pendulum STEP source is missing or has changed."}, 422)
            else:
                self.send_file(asset)
        elif match := re.fullmatch(r"/api/step/suspension/([0-9]{1,2})", path):
            catalog = json.loads((STEP_ROOT / "catalog.json").read_text(encoding="utf-8"))["files"]
            index = int(match[1])
            if index >= len(catalog):
                self.respond({"ok": False, "error": "Unknown STEP part."}, 404)
                return
            item = catalog[index]
            asset = (STEP_ROOT / item["name"]).resolve()
            if asset.parent != STEP_ROOT.resolve():
                self.respond({"ok": False, "error": "Invalid catalog path."}, 422)
                return
            if not asset.is_file() or asset.stat().st_size != item["size"] or hashlib.sha256(asset.read_bytes()).hexdigest() != item["sha256"]:
                self.respond({"ok": False, "error": "The STEP part is missing or does not match the source checksum."}, 422)
                return
            self.send_file(asset)
        elif path == "/api/reference/nasa-mars-2020-wheel":
            reference = ROOT / "examples" / "reference" / "nasa-mars-2020-wheel.stl"
            if not reference.is_file() or reference.stat().st_size != 2266484:
                self.respond({"ok": False, "error": "The optional NASA reference STL is not installed. See docs/reference-geometry.md for the pinned download."}, 404)
            elif hashlib.sha256(reference.read_bytes()).hexdigest() != "6318740c1ce44b5d4deb85866dd2a2cef9195197019553c78f0c439ab737c4ad":
                self.respond({"ok": False, "error": "The NASA reference STL does not match the pinned source digest."}, 422)
            else:
                self.send_file(reference)
        elif match := re.fullmatch(r"/api/runs/([0-9a-f]{32})/(model\.mbd|solver\.log|results\.csv|project\.json|summary\.json|result\.mov|result\.out|result\.log|result\.jnt)", path):
            self.send_file(app_paths.run_directory(match[1], solver.RUNS) / match[2], attachment=True)
        elif path.startswith("/api/"):
            self.respond({"ok": False, "error": "Unknown API endpoint."}, 404)
        elif path.startswith("/docs/") or path.startswith("/examples/"):
            candidate = (ROOT / unquote(path).lstrip("/")).resolve()
            base = ROOT / path.split("/")[1]
            if not candidate.is_relative_to(base) or candidate.suffix not in (".md", ".json", ".mbd", ".txt"):
                self.respond({"ok": False, "error": "Unsupported document path."}, 404)
            else:
                self.send_file(candidate)
        else:
            super().do_GET()

    def do_POST(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path in ("/api/step/convert", "/api/step/mass"):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/step":
                self.respond({"ok": False, "error": "Use application/step for STEP imports."}, 415)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= step_geometry.MAX_STEP_BYTES:
                    raise ValueError("STEP input must be between 1 byte and 12 MiB.")
                name = unquote(self.headers.get("X-Step-Filename", "Imported.step"))
                if path == "/api/step/mass":
                    density_headers = self.headers.get_all("X-Step-Density", [])
                    part_headers = self.headers.get_all("X-Step-Part", [])
                    witness_headers = self.headers.get_all("X-Step-Witness", [])
                    if len(density_headers) != 1 or len(part_headers) != 1 or len(witness_headers) > 1:
                        raise ValueError("Supply exactly one density and STEP occurrence header.")
                    density = float(density_headers[0])
                    part_id = part_headers[0]
                    witness = step_mass.decode_witness(witness_headers[0]) if witness_headers else None
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ValueError("STEP upload ended before its declared length.")
                if not STEP_LOCK.acquire(blocking=False):
                    self.respond({"ok": False, "error": "A STEP conversion is already running."}, 409)
                    return
                try:
                    result = step_mass.calculate(data, density, part_id, witness) if path == "/api/step/mass" else step_geometry.convert_step(data, name)
                    self.respond({"ok": True, **result})
                finally:
                    STEP_LOCK.release()
            except (ValueError, OSError) as exc:
                self.respond({"ok": False, "error": str(exc)}, 422)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self.respond({"ok": False, "error": "Use application/json."}, 415)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 65536:
                self.respond({"ok": False, "error": "Supply a JSON request up to 64 KiB."}, 413)
                return
            def invalid_constant(value):
                raise ValueError(f"Non-finite JSON number: {value}")
            raw = self.rfile.read(size)
            body = agent.strict_json(raw) if path in ("/api/agent/chat", "/api/step/primitive", "/api/run/cancel", "/api/kinematics") else json.loads(raw, parse_constant=invalid_constant)
            if path == "/api/step/primitive":
                if not STEP_LOCK.acquire(blocking=False):
                    self.respond({"ok": False, "error": "Another STEP operation is already running."}, 409)
                    return
                try:
                    data = primitive_step.generate_step(body)
                finally:
                    STEP_LOCK.release()
                self.send_response(200)
                self.send_header("Content-Type", "application/step")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/api/tour-preference":
                if not isinstance(body, dict) or set(body) != {"enabled"} or type(body["enabled"]) is not bool:
                    raise ValueError("Tour preference requires exactly one boolean enabled field.")
                TOUR_PREFERENCE.parent.mkdir(parents=True, exist_ok=True)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=TOUR_PREFERENCE.parent, prefix="tour-", suffix=".tmp", delete=False) as stream:
                        temporary = stream.name
                        json.dump(body, stream)
                    os.replace(temporary, TOUR_PREFERENCE)
                finally:
                    if temporary and os.path.exists(temporary):
                        os.unlink(temporary)
                self.respond(body)
                return
            if path == "/api/agent/chat":
                if not agent.CHAT_LOCK.acquire(blocking=False):
                    self.respond({"ok": False, "code": "busy", "error": "An agent request is already in progress. Wait for it to finish."}, 409)
                    return
                try:
                    self.respond(agent.chat(body))
                except agent.AgentError as exc:
                    self.respond({"ok": False, "code": exc.code, "error": str(exc)}, exc.status)
                finally:
                    agent.CHAT_LOCK.release()
                return
            if path == "/api/kinematics":
                if not KINEMATICS_LOCK.acquire(blocking=False):
                    self.respond({"ok": False, "error": "Another kinematics calculation is in progress."}, 409)
                    return
                try:
                    try:
                        result = kinematics.solve(body)
                    except kinematics.KinematicsError as exc:
                        self.respond({"ok": False, "error": str(exc)}, 422)
                    else:
                        self.respond(result)
                finally:
                    KINEMATICS_LOCK.release()
                return
            if path == "/api/run/cancel":
                if not isinstance(body,dict) or set(body)!={"runToken"} or not isinstance(body["runToken"],str) or not re.fullmatch(r"[0-9a-f]{32}",body["runToken"]):
                    raise ValueError("Supply exactly one 32-character lowercase hexadecimal run token.")
                result,code=request_run_cancel(body["runToken"])
                self.respond(result,code)
                return
            field = "id" if path == "/api/source-run" else "model"
            allowed = {field, "runToken"} if path in ("/api/run", "/api/source-run") else {field}
            if not isinstance(body, dict) or set(body) not in ({field}, allowed):
                raise ValueError(f"Expected {field} and optional run token for solver runs.")
            token=body.get("runToken")
            if token is not None and (not isinstance(token,str) or not re.fullmatch(r"[0-9a-f]{32}",token)):
                raise ValueError("Run token must contain 32 lowercase hexadecimal characters.")
            model = body[field]
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            self.respond({"ok": False, "error": str(exc)}, 400)
            return
        except OSError as exc:
            self.respond({"ok": False, "error": str(exc)}, 500)
            return
        if path == "/api/source-run":
            if not RUN_LOCK.acquire(blocking=False):
                self.respond({"ok": False, "error": "A solver run is already in progress. Wait for it to finish."}, 409)
                return
            started=False
            try:
                control=begin_run_control(token)
                started=True
                result, code = source_catalog.run(model, control=control)
                self.respond(result, code)
            except ValueError as exc:
                self.respond({"ok":False,"error":str(exc)},409)
            finally:
                if started: finish_run_control(token)
                RUN_LOCK.release()
            return
        is_source = isinstance(model, dict) and model.get("kind") == "source-example"
        check = source_catalog.validate_model(model) if is_source else validate(model)
        if path == "/api/validate":
            self.respond(check)
            return
        if path not in ("/api/deck", "/api/preview", "/api/run"):
            self.respond({"ok": False, "error": "Unknown API endpoint."}, 404)
            return
        if not check["valid"]:
            self.respond({"ok": False, "error": "Fix the model before continuing.", **check}, 422)
            return
        if path == "/api/deck":
            self.respond(source_catalog.deck_for_model(model) if is_source else {**check, "deck": deck(model), "filename": model["kind"] + ".mbd"})
        elif is_source:
            self.respond({"ok": False, "error": "Use /api/source-run with the catalog ID for upstream studies; synthetic previews are unavailable."}, 422)
        elif path == "/api/preview":
            if model.get("kind") in ("planar-assembly", "spatial-assembly"):
                self.respond({"ok": False, "error": "Independent preview is unavailable for authored assemblies; run MBDyn to obtain results."}, 422)
                return
            samples = preview(model)
            stride = max(1, math.ceil((len(samples)-1)/2000))
            displayed = samples[::stride]
            if displayed[-1] != samples[-1]:
                displayed.append(samples[-1])
            self.respond({"ok": True, "source": "Reference preview", "model": model, "samples": displayed, "metrics": metrics(model,samples), "detail": "Independent RK4 or closed-form reference calculation; MBDyn was not run."})
        elif not RUN_LOCK.acquire(blocking=False):
            self.respond({"ok": False, "error": "A solver run is already in progress. Wait for it to finish."}, 409)
        else:
            started=False
            try:
                control=begin_run_control(token)
                started=True
                result, code = solver.run(model, control=control)
                self.respond(result, code)
            except ValueError as exc:
                self.respond({"ok":False,"error":str(exc)},409)
            finally:
                if started: finish_run_control(token)
                RUN_LOCK.release()


def featured_catalog():
    """Featured studies are saved projects shipped in examples/, listed by examples/featured.json."""
    return featured.catalog()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--startup-nonce", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a local port from 1024 to 65535.")
    if args.startup_nonce is not None and not re.fullmatch(r"[0-9a-f]{64}", args.startup_nonce):
        parser.error("The startup nonce must contain 64 lowercase hexadecimal characters.")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.startup_nonce = args.startup_nonce
    print(f"Kinemeld: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
