"""Start the local workbench, or reuse this app's existing loopback server."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


def health(url):
    try:
        with urllib.request.urlopen(url + "/api/health", timeout=1) as response:
            return json.load(response).get("application") == "mbdyn-studio"
    except (OSError, ValueError, urllib.error.URLError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port from 1024 to 65535.")
    url = f"http://127.0.0.1:{args.port}"
    if health(url):
        print(f"Kinemeld is already running: {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    root = Path(__file__).resolve().parent
    process = subprocess.Popen([sys.executable, str(root / "backend/server.py"),
                                "--port", str(args.port)], cwd=root)
    try:
        for _ in range(30):
            if process.poll() is not None:
                print("The server could not start. Check whether another app uses this port.", file=sys.stderr)
                return process.returncode or 1
            if health(url):
                print(f"Kinemeld is ready: {url}\nKeep this window open. Press Ctrl+C to stop.")
                if not args.no_browser:
                    webbrowser.open(url)
                return process.wait()
            time.sleep(.1)
        print("The local server did not become ready.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
