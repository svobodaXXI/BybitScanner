"""Packaged standalone viewer smoke test for Windows/Linux CI.

Uses only loopback HTTP and bundled static assets; no public Bybit requests.
Does not touch trading accounts or local PAPER files.
"""
from __future__ import annotations

from pathlib import Path
from queue import Queue, Empty
import re
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
assert (ROOT / "START_LOCAL.cmd").is_file(), "Windows launcher missing"
assert (ROOT / "dist" / "replay.html").is_file(), "Standalone build missing"

proc = subprocess.Popen(
    [sys.executable, "-B", str(ROOT / "server.py")],
    cwd=ROOT,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)
lines: Queue[str] = Queue()


def collect_lines() -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        lines.put(line)


reader = Thread(target=collect_lines, daemon=True)
reader.start()
try:
    try:
        first = lines.get(timeout=15)
    except Empty as exc:
        raise RuntimeError("Local viewer did not start within 15 seconds") from exc
    found = re.search(r"http://127\.0\.0\.1:\d+/replay\.html", first)
    if not found:
        raise RuntimeError("Unexpected local viewer startup message: " + first)
    url = found.group(0)
    with urlopen(url, timeout=5) as response:
        html = response.read().decode("utf-8")
        assert response.status == 200
    assert 'id="replay-root"' in html, "Viewer root absent"
    script = re.search(r'<script[^>]+src="(/assets/[^"]+\.js)"', html)
    assert script is not None, "Built viewer JS was not included"
    host = url.removesuffix("/replay.html")
    with urlopen(host + script.group(1), timeout=5) as response:
        script_bytes = response.read()
        assert response.status == 200 and len(script_bytes) > 1000
    try:
        urlopen(host + "/api/robot/status", timeout=5)
        raise AssertionError("Trading API route should not be exposed")
    except HTTPError as error:
        assert error.code == 404, f"Unexpected protected endpoint code: {error.code}"
    try:
        urlopen(Request(host + "/local-replay/history", data=b"{}", method="POST"), timeout=5)
        raise AssertionError("Trading HTTP mutation should not be allowed")
    except HTTPError as error:
        assert error.code == 405, f"Unexpected POST status: {error.code}"
    print("WINDOWS_LOCAL_REPLAY_SMOKE_OK (loopback, HTML, JS, forbidden routes)")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
