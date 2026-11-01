"""Real-systemd probe of the PAPER contour START chain with dummy backend/Telegram (CI runner, root).

The repository's own three units are installed under isolated bbs-start-probe names with only these substitutions:
the venv interpreter -> this runner's Python, /opt/BybitScanner -> this checkout, the backend's and
the worker's programs -> small loopback HTTP stand-ins, the env file -> a probe env file, User= -> root,
and the backend's prepare-only ExecStartPre gate (it needs a provisioned host) is dropped.
ExecStop is a dummy cleanup command; shutdown semantics are proved separately. Everything
else -- Requires/After ordering, the Telegram `runtime_intent --wait-backend` readiness gate and the
start unit's real `python -m tools.runtime_intent ALL` -- is the repository's code.

Scenarios:
  S1 `systemctl start bybitscanner-paper-start.service` with a slow-starting backend
     -> backend first; Telegram only after the backend proved its identity; exactly one
        POST /api/runtime/intent {"intent": "ALL"} after both are READY; start unit Result=success
  S2 the backend refuses the intent (409 blocked_by ROBOT_RECONCILIATION_FAILED)
     -> the start unit fails and its journal names the blocker
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import textwrap
import time

REPO = Path(__file__).resolve().parents[1]
WORK = Path("/run/bbs-start")
PY = sys.executable
BACKEND_PORT, TELEGRAM_PORT = 18765, 18766
SOURCE_UNITS = ("bybitscanner-paper-backend.service", "bybitscanner-telegram.service", "bybitscanner-paper-start.service")
UNITS = tuple(name.replace("bybitscanner-", "bbs-start-probe-") for name in SOURCE_UNITS)
sys.path.insert(0, str(REPO))
from tools.runtime_intent import expected_database_identity  # noqa: E402

ENV = {
    "PYTHONPATH": str(REPO),
    "BYBITSCANNER_PAPER_DB": str(WORK / "paper_runtime.sqlite3"),
    "BYBITSCANNER_PAPER_BACKEND_URL": f"http://127.0.0.1:{BACKEND_PORT}",
    "BYBITSCANNER_TELEGRAM_MONITORING_PORT": str(TELEGRAM_PORT),
    "LIVE_MARKET_MUTATIONS_ENABLED": "false",
    "BYBITSCANNER_VPS_PAPER_AUTO_ON_START": "1",
    "BYBITSCANNER_AUTOPILOT_OWNER_TOKEN": "probe-dedicated-owner-token-not-production-12345",
}
IDENTITY = expected_database_identity(REPO, ENV)
SCENARIO_START = 0


def sh(*argv: str, check: bool = True) -> subprocess.CompletedProcess:
    out = subprocess.run(list(argv), capture_output=True, text=True, timeout=100)
    if check and out.returncode != 0:
        raise SystemExit(f"{argv} failed: {out.stdout}{out.stderr}")
    return out


def show(unit: str) -> dict[str, str]:
    out = sh("systemctl", "show", unit, "-p", "ActiveState,SubState,Result", check=False).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def journal(unit: str) -> list[str]:
    return sh("journalctl", "-u", unit, "--no-pager", "-o", "cat", "--since", f"@{SCENARIO_START}", check=False).stdout.strip().splitlines()[-8:]


SERVER = textwrap.dedent('''
    import json, os, sys, time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    kind, port, identity, events, delay, reply = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], float(sys.argv[5]), sys.argv[6]

    def log(event, **extra):
        with open(events, "a") as handle:
            handle.write(json.dumps({"t": time.time(), "kind": kind, "event": event, **extra}) + "\\n")

    if reply == "mismatch":
        identity = "wrong-database"
    autopilot = "OFF"
    log("process_started")
    time.sleep(delay)                                   # a backend needs time before it listens

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _json(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if kind == "backend" and self.path == "/api/health":
                log("health_probe")
                return self._json(200, {"ok": True, "component": "paper_backend", "mode": "paper",
                                        "database_identity": identity,
                                        "paper_live_safe": True, "robot_admission_ready": True,
                                        "scanner_acceptance_ready": True})
            if kind == "backend" and self.path == "/api/scanner/status":
                return self._json(200, {"ok": True, "mode": "SCANNER_RUNNING"})
            if kind == "backend" and self.path == "/api/robot/protection-health":
                return self._json(200, {"ok": True, "healthy": True})
            if kind == "backend" and self.path == "/api/robot/autopilot":
                return self._json(200, {"ok": True, "mode": autopilot,
                                        "trading_account_id": {"value": "paper"}})
            if kind == "telegram" and self.path == "/health":
                return self._json(200, {"component": "telegram_monitoring", "status": "ready",
                                        "database_identity": identity})
            self._json(404, {"ok": False})

        def do_POST(self):
            global autopilot
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if kind == "backend" and self.path == "/api/runtime/intent":
                log("intent", body=body)
                if reply == "blocked":
                    return self._json(409, {"ok": False, "intent": body.get("intent"), "changed": [],
                                            "final": {"robot": "RECONCILIATION_REQUIRED"},
                                            "blocked_by": ["ROBOT_RECONCILIATION_FAILED"]})
                return self._json(200, {"ok": True, "intent": body.get("intent"),
                                        "changed": ["robot:resume", "scanner:start"],
                                        "final": {"robot": "READY", "protection": "HEALTHY", "scanner": "RUNNING"},
                                        "blocked_by": []})
            if kind == "backend" and self.path == "/api/robot/autopilot":
                if self.headers.get("X-BybitScanner-Autopilot-Owner-Token") != "probe-dedicated-owner-token-not-production-12345":
                    return self._json(403, {"ok": False})
                if body != {"mode": "PAPER_AUTO", "confirm_paper_auto": True}:
                    return self._json(409, {"ok": False})
                autopilot = "PAPER_AUTO"
                log("paper_auto", mode=autopilot)
                return self._json(200, {"ok": True, "mode": autopilot})
            self._json(404, {"ok": False})

    log("listening")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
''')


def render(unit: str, text: str, reply: str) -> str:
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#"):
            continue
        if unit.startswith("bybitscanner-paper-backend") and line.startswith("ExecStartPre="):
            continue                                       # prepare-only gate needs a provisioned host
        if line.startswith("ExecStop="):
            line = "ExecStop=/bin/true"  # dummy cleanup; stop semantics have their own probe
        if line.startswith("TimeoutStopSec="):
            line = "TimeoutStopSec=3"
        if line.startswith(("User=", "Group=", "StateDirectory", "EnvironmentFile=")):
            continue
        if line.startswith("ExecStart=") and ("paper_http_server" in line or "tools.vps_release_identity exec-backend" in line):
            line = f"ExecStart={PY} {WORK}/server.py backend {BACKEND_PORT} {IDENTITY} {WORK}/events.jsonl 3 {reply}"
        elif line.startswith("ExecStart=") and "telegram_monitoring.py" in line:
            line = f"ExecStart={PY} {WORK}/server.py telegram {TELEGRAM_PORT} {IDENTITY} {WORK}/events.jsonl 0 ok"
        line = line.replace("/opt/BybitScanner/venv/bin/python", PY).replace("/opt/BybitScanner", str(REPO))
        out.append(line)
        if line == "[Service]":
            out += [f"EnvironmentFile={WORK}/probe.env"]
    rendered = "\n".join(out) + "\n"
    for source, target in zip(SOURCE_UNITS, UNITS):
        rendered = rendered.replace(source, target)
    return rendered


def install(reply: str) -> None:
    for source, unit in zip(SOURCE_UNITS, UNITS):
        text = (REPO / "deploy/systemd" / source).read_text(encoding="utf-8")
        Path(f"/etc/systemd/system/{unit}").write_text(render(source, text, reply), encoding="utf-8")
    sh("systemctl", "daemon-reload")


def events() -> list[dict]:
    path = WORK / "events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def stop_all() -> None:
    # Probe cleanup only: the backend unit refuses manual stop by design, so end the dummies directly.
    for unit in reversed(UNITS):
        sh("systemctl", "kill", "--signal=SIGKILL", unit, check=False)
    time.sleep(1)
    for unit in UNITS:
        sh("systemctl", "reset-failed", unit, check=False)


def scenario(reply: str) -> dict[str, object]:
    global SCENARIO_START
    SCENARIO_START = int(time.time())
    (WORK / "events.jsonl").unlink(missing_ok=True)
    install(reply)
    started = time.time()
    start = sh("systemctl", "start", "bbs-start-probe-paper-start.service", check=False)
    log = events()
    first = {}
    for item in log:
        first.setdefault(f"{item['kind']}:{item['event']}", item["t"])
    intents = [item["body"] for item in log if item["event"] == "intent"]
    result = {"start_rc": start.returncode, "seconds": round(time.time() - started, 1),
              "units": {unit: show(unit) for unit in UNITS}, "intents": intents,
              "order": sorted(first, key=first.get),
              "telegram_after_backend_listening": first.get("telegram:process_started", 0)
              >= first.get("backend:listening", float("inf")),
              "intent_after_both": bool(intents) and first.get("backend:intent", 0)
              >= max(first.get("backend:listening", 0), first.get("telegram:listening", 0)),
              "start_journal": journal("bbs-start-probe-paper-start.service")}
    stop_all()
    return result


def main() -> int:
    if sys.platform != "linux" or os.geteuid() != 0 or os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("Refusing: disposable GitHub Actions Linux runner as root required")
    if Path("/proc/1/comm").read_text().strip() != "systemd":
        raise SystemExit("Refusing: PID 1 must be systemd")
    for unit in (*SOURCE_UNITS, *UNITS):
        loaded = sh("systemctl", "show", unit, "-p", "LoadState", "--value", check=False).stdout.strip()
        if loaded != "not-found":
            raise SystemExit(f"Refusing existing unit: {unit} ({loaded})")
    for port in (BACKEND_PORT, TELEGRAM_PORT):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))
    WORK.mkdir(parents=True, exist_ok=False)
    (WORK / "server.py").write_text(SERVER, encoding="utf-8")
    (WORK / "probe.env").write_text("".join(f"{k}={v}\n" for k, v in ENV.items()), encoding="utf-8")
    try:
        s1 = scenario("ok")
        s2 = scenario("blocked")
        s3 = scenario("mismatch")
    finally:
        stop_all()
    print(json.dumps({"S1_start_chain": s1, "S2_intent_blocked": s2, "S3_wrong_identity": s3}, indent=2))
    start_unit = "bbs-start-probe-paper-start.service"
    checks = {
        "S3: wrong DB blocks dependent units and sends no intent": s3["start_rc"] != 0
            and s3["intents"] == [] and "telegram:process_started" not in s3["order"],
        "S1: start unit succeeded": s1["start_rc"] == 0 and s1["units"][start_unit].get("Result") == "success",
        "S1: Telegram started only after the backend proved its identity": s1["telegram_after_backend_listening"],
        "S1: exactly one intent ALL": s1["intents"] == [{"intent": "ALL"}],
        "S1: owner-authorized PAPER_AUTO confirmed": "backend:paper_auto" in s1["order"],
        "S1: intent sent after backend and Telegram were READY": s1["intent_after_both"],
        "S1: backend and Telegram stay active after the oneshot": all(
            s1["units"][u].get("ActiveState") == "active" for u in UNITS[:2]),
        "S1: journal shows READY": any(line.startswith("READY: intent=ALL") for line in s1["start_journal"]),
        "S2: blocked intent fails the start unit": s2["start_rc"] != 0
                                                    and s2["units"][start_unit].get("Result") != "success",
        "S2: journal names the blocker": any("ROBOT_RECONCILIATION_FAILED" in line for line in s2["start_journal"]),
        "S2: still exactly one intent (never retried)": s2["intents"] == [{"intent": "ALL"}],
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
