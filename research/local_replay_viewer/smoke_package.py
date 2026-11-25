"""Packaged standalone viewer smoke test for Windows/Linux CI.

Uses only loopback HTTP and bundled static assets; no public Bybit requests.
Does not touch trading accounts or local PAPER files.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from queue import Queue, Empty
import re
import subprocess
import sys
from threading import Thread
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
assert (ROOT / "START_LOCAL.cmd").is_file(), "Windows launcher missing"
assert (ROOT / "dist" / "replay.html").is_file(), "Standalone build missing"
# The reviewed public HTTPS trust anchor ships with the same exact desktop
# release. Pairing must never accept an origin from a protocol link or token.
trusted = ROOT / "trusted-statistics-origin.txt"
assert trusted.is_file() and not trusted.is_symlink(), "Reviewed Statistics origin pin missing"
origin = trusted.read_text(encoding="ascii").removesuffix("\n")
url = urlsplit(origin)
assert (url.scheme == "https" and url.hostname and url.username is None
        and url.password is None and not url.path and not url.query
        and not url.fragment and origin == f"https://{url.netloc}"), "Invalid origin pin"

# Local H-017 risk module must ship in the extracted Windows archive.
from research.h017_local_risk import H017LocalRiskPolicy
policy = H017LocalRiskPolicy()
assert policy.initial_cash == 200 and policy.slot_budget == 10
assert policy.max_open_positions == 20
proposal = policy.proposal(side="LONG", expected_entry="100", target="101")
assert proposal is not None and proposal.stop == Decimal("99.3")


proc = subprocess.Popen(
    [sys.executable, "-B", str(ROOT / "server.py"), "--no-browser"],
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
    # Optional offline public research archive: absent in the lightweight
    # package, present in the single real-H1 owner acceptance bundle.
    import json
    with urlopen(host + "/local-replay/bundled", timeout=5) as response:
        bundled = ROOT / "real-h1-august.json"
        if bundled.is_file():
            assert response.status == 200
            document = json.loads(response.read())
            assert document["source"] == "SIMULATION"
            assert document["mode"] == "MARKET_ONLY"
            assert document["symbol"] == "GRASSUSDT"
            assert document["market_data_source"] == "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M"
            assert len(document["events"]) == 2016
        else:
            assert response.status == 204
            assert response.read() == b""
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


# Only on disposable Windows GitHub CI. Never change an owner's trust store.
def verify_windows_native_bridge():
    import hashlib
    import json
    import os
    import shutil
    import ssl
    import tempfile
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from unittest.mock import patch
    from urllib.error import URLError
    import launch_bridge_agent as agent

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        cert, key = root / "test.pem", root / "test.key"
        openssl = shutil.which("openssl") or str(
            Path(os.environ["ProgramFiles"]) / "Git/usr/bin/openssl.exe")
        subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=MachineTime CI isolated TLS",
                        "-addext", "subjectAltName=IP:127.0.0.1",
                        "-addext", "extendedKeyUsage=serverAuth"],
                       check=True, capture_output=True, timeout=20)
        fingerprint = hashlib.sha1(
            ssl.PEM_cert_to_DER_cert(cert.read_text(encoding="ascii"))).hexdigest()
        token, code = "A" * 64, "C" * 24
        seen = []
        bridge = "/api/diary/simulator-bridge/"
        episode = "te_" + "a" * 24
        request_id = "b" * 32

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, data):
                raw = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_POST(self):
                route = urlsplit(self.path).path
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append(route)
                if route == bridge + "pair-claim":
                    assert self.headers["X-BybitScanner-Local-Pair-Claim"] == "v1"
                    assert body == {"device_id": "owner-pc", "code": code}
                    self.reply(200, {"ok": True, "device_id": "owner-pc", "token": token})
                elif route == bridge + "ack":
                    assert self.headers["X-BybitScanner-Simulator-Device-Token"] == token
                    assert body == {"device_id": "owner-pc", "request_id": request_id, "launched": True}
                    self.reply(200, {"ok": True, "state": "LAUNCHED"})
                else:
                    self.reply(404, {})

            def do_GET(self):
                route = urlsplit(self.path).path
                seen.append(route)
                if self.headers.get("X-BybitScanner-Simulator-Device-Token") != token:
                    self.reply(403, {"ok": False, "error": "simulator_device_unauthorized"})
                elif route == bridge + "poll":
                    if self.path.endswith("viewer_running=0"):
                        self.reply(200, {"ok": True, "state": "IDLE"})
                    else:
                        self.reply(200, {"ok": True, "state": "OPEN_EPISODE",
                                         "episode_id": episode, "request_id": request_id})
                elif route == bridge + "facts":
                    self.send_response(302)
                    self.send_header("Location", self.server.origin + bridge + "poll")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self.reply(404, {})

        host = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        host.socket = context.wrap_socket(host.socket, server_side=True)
        host.origin = f"https://127.0.0.1:{host.server_address[1]}"
        thread = Thread(target=host.serve_forever, daemon=True)
        thread.start()
        certutil = str(Path(os.environ["SystemRoot"]) / "System32/certutil.exe")
        try:
            probe = Request(host.origin + bridge + "poll?device_id=owner-pc&viewer_running=0")
            try:
                agent._relay_https_opener().open(probe, 5)
                raise AssertionError("Untrusted TLS unexpectedly accepted")
            except HTTPError:
                raise AssertionError("Untrusted TLS reached HTTP handler")
            except URLError:
                assert not seen
            subprocess.run([certutil, "-user", "-f", "-addstore", "Root", str(cert)],
                           check=True, capture_output=True, timeout=20)
            try:
                agent._relay_https_opener().open(probe, 5)
                raise AssertionError("Unauthenticated poll accepted")
            except HTTPError as error:
                assert error.code == 403
            with patch.object(agent, "CONFIG_PATH", root / "launch-bridge.json"), \
                 patch.object(agent, "_trusted_statistics_origin", return_value=host.origin), \
                 patch.object(agent, "install_if_configured", return_value=True), \
                 patch.object(agent, "viewer_is_running", return_value=True):
                agent.claim_one_time_pairing_code("owner-pc", code)
                config = agent.read_config()
                assert config == {"origin": host.origin, "device_id": "owner-pc", "token": token}
                opened = []
                assert agent.poll_once(config, launch=opened.append) == "OPEN_REQUESTED"
                assert opened == [episode]
                before = len(seen)
                redirect = Request(host.origin + bridge + "facts?device_id=owner-pc&request_id=" + request_id,
                                   headers={"X-BybitScanner-Simulator-Device-Token": token})
                try:
                    agent._relay_https_opener().open(redirect, 5)
                    raise AssertionError("Redirect accepted")
                except HTTPError as error:
                    assert error.code == 302
                assert seen[before:] == [bridge + "facts"]
            assert seen == [bridge + "poll", bridge + "pair-claim", bridge + "poll",
                            bridge + "poll", bridge + "ack", bridge + "facts"]
            print("WINDOWS_NATIVE_TLS_CLAIM_PERSIST_POLL_ACK_NO_REDIRECT_OK")
        finally:
            host.shutdown()
            host.server_close()
            thread.join(timeout=5)
            subprocess.run([certutil, "-user", "-delstore", "Root", fingerprint],
                           capture_output=True, timeout=20)


import os
if os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_OS") == "Windows":
    verify_windows_native_bridge()
