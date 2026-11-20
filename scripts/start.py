#!/usr/bin/env python3
"""A single local process serves the API, worker, and built React application."""

import argparse
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="Ctrl+Tea Lecture Studio")
parser.add_argument("--port", type=int, default=8765)
parser.add_argument("--dev", action="store_true")
parser.add_argument("--open-browser", action="store_true")
args = parser.parse_args()
os.chdir(root)
sys.path.insert(0, str(root / "backend"))
from ctrltea.runtime import find_binary, tool_environment
try:
    for tool in ("pandoc", "tesseract", "libreoffice"):
        find_binary(tool)
    os.environ.update(tool_environment())
except ValueError as error:
    sys.exit(str(error))
if not (root / "frontend/dist/index.html").exists():
    sys.exit("Build the frontend first: cd frontend && npm ci && npm run build")
os.environ["PYTHONPATH"] = str(root / "backend") + os.pathsep + os.environ.get("PYTHONPATH", "")
command = [
    sys.executable,
    "-m",
    "uvicorn",
    "ctrltea.api:app",
    "--host",
    "127.0.0.1",
    "--port",
    str(args.port),
]
if args.dev:
    command.append("--reload")
browser_url = os.environ.get('CTRLTEA_PUBLIC_ORIGIN', f'http://127.0.0.1:{args.port}').rstrip('/')
def open_when_ready():
    url = browser_url
    for _ in range(80):
        try:
            with urllib.request.urlopen(url+"/api/health", timeout=.5) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            pass
        time.sleep(.25)
if args.open_browser:
    threading.Thread(target=open_when_ready,daemon=True).start()
print(f"Ctrl+Tea: {browser_url}", flush=True)
raise SystemExit(subprocess.call(command))
