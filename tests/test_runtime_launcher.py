"""Launcher ownership checks; never execute the prototype launcher itself.

The Scanner routing PowerShell command runs only against a local stub backend.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / "start_robot_runtime.bat"
IDENTITY_CODE_PREFIX = 'set "BYBITSCANNER_PAPER_DB_IDENTITY_CODE='


def _identity_code():
    """The launcher's single expected PAPER DB identity definition."""
    lines = [line.strip() for line in LAUNCHER.read_text().splitlines()]
    (line,) = [line for line in lines if line.startswith(IDENTITY_CODE_PREFIX)]
    return line[len(IDENTITY_CODE_PREFIX):-1]


class RuntimeLauncherTests(unittest.TestCase):
    def test_scanner_start_has_one_backend_owner(self):
        launcher = (Path(__file__).resolve().parents[1] / "start_robot_runtime.bat").read_text()
        commands = [line.strip() for line in launcher.splitlines()
                    if line.strip() and not line.lstrip().lower().startswith("rem ")]
        self.assertNotRegex(launcher.lower(), r"\bmain(?:\.py)?\b")
        starts = [line for line in commands if re.match(r"start\s", line, re.I)]
        self.assertEqual(len(starts), 2)
        self.assertIn("start_paper_backend.bat", starts[0])
        self.assertIn("telegram_monitoring.py", starts[1])
        self.assertEqual(launcher.count("/api/scanner/start"), 1)
        self.assertEqual(sum("Invoke-RestMethod" in line for line in commands), 1)
        request = next(line for line in commands if "Invoke-RestMethod" in line)
        self.assertTrue(request.startswith("powershell.exe -NoProfile -Command"))
        self.assertIn("$backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL", request)
        self.assertIn("if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }", request)
        self.assertIn("$base = $backendUrl.TrimEnd('/')", request)
        self.assertIn("$ErrorActionPreference = 'Stop'", request)
        self.assertEqual(commands[commands.index(request) + 1], "if errorlevel 1 exit /b 1")


    def test_scanner_start_is_gated_on_telegram_readiness(self):
        launcher = (Path(__file__).resolve().parents[1] / "start_robot_runtime.bat").read_text()
        lines = [line.strip() for line in launcher.splitlines() if line.strip()]
        worker = next(i for i, line in enumerate(lines) if "telegram_monitoring.py" in line)
        scanner = next(i for i, line in enumerate(lines) if "/api/scanner/start" in line)
        # An already READY worker is reused and skips the second start; a READY worker
        # for another PAPER DB stops the launcher before anything else starts.
        self.assertEqual(lines[worker - 6:worker - 4],
                         ["call :wait_telegram_ready 1", "if errorlevel 2 ("])
        self.assertEqual(lines[worker - 3:worker], ["exit /b 1", ")",
                                                    "if not errorlevel 1 goto telegram_ready"])
        # A newly started worker must prove READY within a bound or the launcher exits nonzero.
        self.assertEqual(lines[worker + 1:worker + 3],
                         ["call :wait_telegram_ready 60", "if errorlevel 1 ("])
        self.assertIn("exit /b 1", lines[worker + 4])
        # Telegram READY leads to the Robot/protection barrier, then Scanner routing.
        self.assertEqual(lines[scanner - 7], ":telegram_ready")
        self.assertTrue(lines[scanner - 6].startswith("rem "))
        self.assertEqual(lines[scanner - 5:scanner - 3],
                         ["call :probe_paper_backend 0 robot", "if errorlevel 1 ("])
        self.assertEqual(lines[scanner - 2:scanner], ["exit /b 1", ")"])
        self.assertEqual(lines.count(":telegram_ready"), 1)
        self.assertEqual(sum("goto telegram_ready" in line for line in lines), 1)
        probe = lines[lines.index(":wait_telegram_ready") + 2]
        self.assertIn("$env:BYBITSCANNER_TELEGRAM_MONITORING_PORT", probe)
        self.assertIn("$port = '8766'", probe)
        self.assertIn("'http://127.0.0.1:' + $port + '/health'", probe)
        # An unrelated HTTP 200 fails closed: component identity and status are both required.
        self.assertIn("$h = $r.Content | ConvertFrom-Json }", probe)
        self.assertIn("$r.StatusCode -eq 200 -and $h.component -eq 'telegram_monitoring' "
                      "-and $h.status -eq 'ready') { if ($h.database_identity -is [string] "
                      "-and $h.database_identity -ceq $expected) { exit 0 }", probe)
        self.assertEqual(probe.count("exit 0"), 1)
        self.assertTrue(probe.endswith('exit 1"'))
        self.assertGreater(lines.index(":wait_telegram_ready"), lines.index("exit /b 0"))



class _StubBackend(BaseHTTPRequestHandler):
    status_code = 200
    status_body = b""
    posts: list

    def do_GET(self):  # noqa: N802
        self.send_response(self.status_code if self.path == "/api/scanner/status" else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.status_body)

    def do_POST(self):  # noqa: N802
        self.posts.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format, *args):  # noqa: A002
        pass


@unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell launcher routing")
class LauncherScannerRoutingTests(unittest.TestCase):
    """Run only the launcher's Scanner routing command against a stub backend."""

    def _route(self, status_body, status_code=200):
        lines = [line.strip() for line in LAUNCHER.read_text().splitlines()]
        request = next(line for line in lines if "/api/scanner/status" in line)
        prefix = 'powershell.exe -NoProfile -Command "'
        self.assertTrue(request.startswith(prefix) and request.endswith('"'))
        self.assertEqual(lines[lines.index(request) + 1], "if errorlevel 1 exit /b 1")
        if not isinstance(status_body, bytes):
            status_body = json.dumps(status_body).encode()
        handler = type("Handler", (_StubBackend,), {
            "status_code": status_code, "status_body": status_body, "posts": [],
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            env = dict(os.environ, BYBITSCANNER_PAPER_BACKEND_URL=(
                f"http://127.0.0.1:{server.server_address[1]}/"))
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", request[len(prefix):-1]],
                env=env, capture_output=True, text=True, timeout=60,
            )
        finally:
            server.shutdown()
            server.server_close()
        return result.returncode, handler.posts

    def test_stopped_starts_scanner(self):
        self.assertEqual(self._route({"ok": True, "mode": "SCANNER_STOPPED"}),
                         (0, ["/api/scanner/start"]))

    def test_paused_resumes_scanner(self):
        self.assertEqual(self._route({"ok": True, "mode": "SCANNER_PAUSED"}),
                         (0, ["/api/scanner/resume"]))

    def test_running_is_success_without_mutation(self):
        self.assertEqual(self._route({"ok": True, "mode": "SCANNER_RUNNING"}), (0, []))

    def test_unknown_missing_or_unavailable_state_fails_closed(self):
        for body, code in (({"ok": True, "mode": "SCANNER_BROKEN"}, 200),
                           ({"ok": True, "mode": "scanner_stopped"}, 200),
                           ({"ok": True}, 200),
                           ({"ok": False, "mode": "SCANNER_STOPPED"}, 200),
                           (b"not json", 200),
                           ({"ok": False, "error": "scanner_control_unavailable"}, 503)):
            with self.subTest(body=body, code=code):
                returncode, posts = self._route(body, code)
                self.assertNotEqual(returncode, 0)
                self.assertEqual(posts, [])



class LauncherBackendReuseTests(unittest.TestCase):
    """Backend spawn is decided only by the canonical /api/health identity probe."""

    def _lines(self):
        return [line.strip() for line in LAUNCHER.read_text().splitlines() if line.strip()]

    def test_probe_result_decides_spawn_before_any_scanner_mutation(self):
        lines = self._lines()
        spawn = [i for i, line in enumerate(lines) if "start_paper_backend.bat" in line]
        self.assertEqual(len(spawn), 1)
        spawn = spawn[0]
        probe_call = lines.index("call :probe_paper_backend 0")
        # 2 = something answered without matching identity: exit before any spawn.
        self.assertEqual(lines[probe_call + 1], "if errorlevel 2 (")
        self.assertEqual(lines[probe_call + 3], "exit /b 1")
        # 0 = matching canonical backend: skip the only backend spawn.
        self.assertEqual(lines[probe_call + 5], "if not errorlevel 1 goto paper_backend_ready")
        self.assertEqual(sum("goto paper_backend_ready" in line for line in lines), 1)
        self.assertEqual(lines.count(":paper_backend_ready"), 1)
        ready = lines.index(":paper_backend_ready")
        self.assertTrue(probe_call < spawn < ready)
        # 1 = unreachable: fall through to exactly one spawn.
        self.assertEqual(lines[probe_call + 6], lines[spawn])
        scanner = next(i for i, line in enumerate(lines) if "/api/scanner/" in line)
        telegram = next(i for i, line in enumerate(lines) if "telegram_monitoring.py" in line)
        self.assertTrue(ready < telegram < scanner)

    def test_only_a_spawned_backend_waits_and_unproven_readiness_stops_startup(self):
        lines = self._lines()
        spawn = next(i for i, line in enumerate(lines) if "start_paper_backend.bat" in line)
        ready = lines.index(":paper_backend_ready")
        telegram = next(i for i, line in enumerate(lines) if "telegram_monitoring.py" in line)
        # The fixed backend sleep is replaced by the bounded readiness wait.
        self.assertNotIn("timeout /t", LAUNCHER.read_text().lower())
        wait = lines.index("call :probe_paper_backend 60")
        self.assertTrue(lines[spawn + 1].startswith("rem "))
        self.assertEqual(wait, spawn + 2)
        self.assertEqual(lines[wait + 1], "if errorlevel 1 (")
        self.assertEqual(lines[wait + 3], "exit /b 1")
        self.assertEqual(lines[wait + 4:wait + 6], [")", ":paper_backend_ready"])
        # The reuse path jumps past both the spawn and the post-spawn wait.
        reuse = lines.index("if not errorlevel 1 goto paper_backend_ready")
        self.assertTrue(reuse < spawn < wait < ready < telegram)
        self.assertEqual(sum(line.startswith("call :probe_paper_backend") for line in lines), 3)
        label = lines.index(":probe_paper_backend")
        self.assertEqual(lines[label + 1], 'set "BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS=%~1"')


@unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell launcher probe")
class LauncherBackendProbeTests(unittest.TestCase):
    """Run only the launcher's backend health probe against a stub or closed port."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db_path = Path(temp.name) / "paper.sqlite3"
        from terminal.persistence.sqlite_store import SQLiteStore

        store = SQLiteStore.open(self.db_path)
        try:
            self.identity = store.database_identity  # the backend's own definition
        finally:
            store.close()

    def _probe(self, backend_url, wait_seconds=0, require=""):
        lines = [line.strip() for line in LAUNCHER.read_text().splitlines()]
        command = lines[lines.index(":probe_paper_backend") + 3]
        prefix = 'powershell.exe -NoProfile -Command "'
        self.assertTrue(command.startswith(prefix) and command.endswith('"'))
        env = dict(os.environ, BYBITSCANNER_PAPER_BACKEND_URL=backend_url,
                   BYBITSCANNER_PAPER_DB=str(self.db_path), BYBITSCANNER_PYTHON=sys.executable,
                   BYBITSCANNER_PAPER_BACKEND_WAIT_SECONDS=str(wait_seconds),
                   BYBITSCANNER_PAPER_BACKEND_REQUIRE=require,
                   BYBITSCANNER_PAPER_DB_IDENTITY_CODE=_identity_code())
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command[len(prefix):-1]],
            env=env, capture_output=True, text=True, timeout=60,
        )
        return result.returncode

    @staticmethod
    def _handler(body, code=200):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        return type("Handler", (_StubBackend,), {
            "status_code": code, "status_body": body, "posts": [], "do_GET": _health_get,
        })

    @staticmethod
    def _free_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return probe.getsockname()[1]

    def _probe_stub(self, body, code=200, wait_seconds=0):
        handler = self._handler(body, code)
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            returncode = self._probe(f"http://127.0.0.1:{server.server_address[1]}",
                                     wait_seconds)
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(handler.posts, [])  # the probe never mutates the backend
        return returncode

    def _health(self, **overrides):
        return {"ok": True, "component": "paper_backend", "mode": "paper",
                "database_identity": self.identity, "process_instance_id": "i",
                "build_sha": "", **overrides}

    def test_matching_canonical_backend_is_reused(self):
        self.assertEqual(self._probe_stub(self._health()), 0)

    def test_unreachable_backend_is_spawned(self):
        self.assertEqual(self._probe(f"http://127.0.0.1:{self._free_port()}"), 1)

    def test_spawned_backend_that_becomes_ready_is_accepted(self):
        port = self._free_port()
        handler = self._handler(self._health())
        servers = []

        def start_backend_late():
            # Nothing listens at first, then the early-bound backend appears.
            server = ThreadingHTTPServer(("127.0.0.1", port), handler)
            servers.append(server)
            server.serve_forever()

        timer = threading.Timer(2.0, start_backend_late)
        timer.start()
        try:
            self.assertEqual(self._probe(f"http://127.0.0.1:{port}", wait_seconds=30), 0)
        finally:
            timer.join(timeout=5)
            for server in servers:
                server.shutdown()
                server.server_close()

    def test_spawned_backend_that_never_becomes_ready_times_out_nonzero(self):
        self.assertEqual(self._probe(f"http://127.0.0.1:{self._free_port()}", wait_seconds=3), 1)
        # An early-bound backend that accepts but never serves is also retried, then times out.
        with socket.socket() as bound:
            bound.bind(("127.0.0.1", 0))
            bound.listen(8)
            port = bound.getsockname()[1]
            self.assertEqual(self._probe(f"http://127.0.0.1:{port}", wait_seconds=3), 1)

    def test_wrong_identity_during_wait_fails_closed(self):
        for body, code in ((self._health(database_identity="0" * 64), 200),
                           (self._health(component="telegram_monitoring"), 200),
                           (b"not json", 200)):
            with self.subTest(body=body, code=code):
                self.assertEqual(self._probe_stub(body, code, wait_seconds=30), 2)

    def test_non_matching_answer_fails_closed_without_spawn(self):
        for body, code in ((self._health(component="telegram_monitoring"), 200),
                           (self._health(database_identity="0" * 64), 200),
                           (self._health(database_identity=self.identity.upper()), 200),
                           (self._health(mode="live"), 200),
                           (self._health(ok="true"), 200),
                           ({"ok": True, "mode": "paper"}, 200),
                           (b"not json", 200),
                           ({"ok": False, "error": "paper_runtime_unavailable"}, 503)):
            with self.subTest(body=body, code=code):
                self.assertEqual(self._probe_stub(body, code), 2)


def _health_get(self):
    self.send_response(self.status_code if self.path == "/api/health" else 404)
    self.send_header("Content-Type", "application/json")
    self.end_headers()
    self.wfile.write(self.status_body)



@unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell launcher probe")
class LauncherRobotBarrierTests(unittest.TestCase):
    """Run the launcher's Robot/protection barrier against a stub backend."""

    setUp = LauncherBackendProbeTests.setUp
    _probe = LauncherBackendProbeTests._probe
    _health = LauncherBackendProbeTests._health
    _free_port = staticmethod(LauncherBackendProbeTests._free_port)

    def _ready_health(self, **overrides):
        return self._health(**{"robot_admission_ready": True, "paper_live_safe": True,
                               "scanner_acceptance_ready": True, **overrides})

    def _barrier(self, health, protection, protection_code=200):
        routes = {"/api/health": (200, health), "/api/robot/protection-health":
                  (protection_code, protection)}
        self.requested = []

        def do_get(handler):
            self.requested.append(handler.path)
            code, body = routes.get(handler.path, (404, {"ok": False}))
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            handler.send_response(code)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(raw)

        handler = type("Handler", (_StubBackend,), {"posts": [], "do_GET": do_get})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            returncode = self._probe(f"http://127.0.0.1:{server.server_address[1]}",
                                     require="robot")
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(handler.posts, [])  # never any Scanner or Robot mutation
        return returncode

    def _protection(self, **overrides):
        return {"ok": True, "healthy": True, "covered_symbols": [], "coverage_roles": {},
                "unhealthy_symbols": {}, "ingress": {}, **overrides}

    def test_admission_and_protection_ready_lets_scanner_routing_proceed(self):
        self.assertEqual(
            self._barrier(self._ready_health(), self._protection()), 0)
        self.assertEqual(self.requested, ["/api/health", "/api/robot/protection-health"])

    def test_robot_admission_not_ready_fails_before_scanner_mutation(self):
        for admission in (False, "true", None):
            with self.subTest(admission=admission):
                health = self._ready_health(robot_admission_ready=admission)
                self.assertEqual(self._barrier(health, self._protection()), 2)
        missing = self._ready_health()
        del missing["robot_admission_ready"]
        self.assertEqual(self._barrier(missing, self._protection()), 2)

    def test_unhealthy_protection_fails_before_scanner_mutation(self):
        ready = self._ready_health()
        for protection in (self._protection(healthy=False),
                           self._protection(unhealthy_symbols={"BTCUSDT": "subscribe_failed"}),
                           self._protection(healthy="true")):
            with self.subTest(protection=protection):
                self.assertEqual(self._barrier(ready, protection), 2)

    def test_malformed_or_unavailable_barrier_responses_fail_closed(self):
        ready = self._ready_health()
        without_symbols = self._protection()
        del without_symbols["unhealthy_symbols"]
        for protection, code in ((without_symbols, 200),
                                 (self._protection(unhealthy_symbols=None), 200),
                                 (self._protection(unhealthy_symbols=[]), 200),
                                 (self._protection(ok=False), 200),
                                 (b"not json", 200),
                                 ({"ok": False, "error": "robot_protection_health_unavailable"}, 503)):
            with self.subTest(protection=protection, code=code):
                self.assertEqual(self._barrier(ready, protection, code), 2)
        self.assertEqual(self._barrier(
            self._ready_health(database_identity="0" * 64),
            self._protection()), 2)
        self.assertNotEqual(
            self._probe(f"http://127.0.0.1:{self._free_port()}", require="robot"), 0)

    def test_unproven_paper_safety_or_scanner_config_fails_before_protection(self):
        for field in ("paper_live_safe", "scanner_acceptance_ready"):
            for value in (False, None, "true", 1, "missing"):
                with self.subTest(field=field, value=value):
                    health = self._ready_health(**{field: value})
                    if value == "missing":
                        del health[field]
                    self.assertEqual(self._barrier(health, self._protection()), 2)
                    # Neither protection health nor Scanner status is read after the failure.
                    self.assertEqual(self.requested, ["/api/health"])



class LauncherIdentityDefinitionTests(unittest.TestCase):
    def test_backend_and_telegram_share_one_identity_definition(self):
        text = LAUNCHER.read_text()
        self.assertEqual(text.count(IDENTITY_CODE_PREFIX), 1)
        self.assertEqual(text.count("hashlib.sha256"), 1)
        self.assertEqual(text.count("-c $env:BYBITSCANNER_PAPER_DB_IDENTITY_CODE"), 2)


@unittest.skipUnless(shutil.which("powershell.exe"), "Windows PowerShell launcher probe")
class LauncherTelegramIdentityTests(unittest.TestCase):
    """Run only the launcher's Telegram READY wait against a stub worker."""

    setUp = LauncherBackendProbeTests.setUp
    _free_port = staticmethod(LauncherBackendProbeTests._free_port)

    def _wait(self, port, wait_seconds):
        lines = [line.strip() for line in LAUNCHER.read_text().splitlines()]
        command = lines[lines.index(":wait_telegram_ready") + 2]
        prefix = 'powershell.exe -NoProfile -Command "'
        self.assertTrue(command.startswith(prefix) and command.endswith('"'))
        env = dict(os.environ, BYBITSCANNER_TELEGRAM_MONITORING_PORT=str(port),
                   BYBITSCANNER_TELEGRAM_WAIT_SECONDS=str(wait_seconds),
                   BYBITSCANNER_PAPER_DB=str(self.db_path), BYBITSCANNER_PYTHON=sys.executable,
                   BYBITSCANNER_PAPER_DB_IDENTITY_CODE=_identity_code())
        started = time.monotonic()
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command[len(prefix):-1]],
            env=env, capture_output=True, text=True, timeout=90,
        )
        return result.returncode, time.monotonic() - started

    def _wait_stub(self, body, code=200, wait_seconds=30):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()

        def do_get(handler):
            handler.send_response(code if handler.path == "/health" else 404)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(raw)

        handler = type("Handler", (_StubBackend,), {"posts": [], "do_GET": do_get})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            return self._wait(server.server_address[1], wait_seconds)
        finally:
            server.shutdown()
            server.server_close()

    def _ready(self, **overrides):
        return {"component": "telegram_monitoring", "status": "ready",
                "database_identity": self.identity, **overrides}

    def test_matching_ready_identity_proceeds(self):
        self.assertEqual(self._wait_stub(self._ready())[0], 0)

    def test_ready_with_wrong_or_missing_identity_fails_closed_immediately(self):
        missing = self._ready()
        del missing["database_identity"]
        for body in (self._ready(database_identity="0" * 64),
                     self._ready(database_identity=self.identity.upper()),
                     self._ready(database_identity=None),
                     self._ready(database_identity=123),
                     missing):
            with self.subTest(body=body):
                returncode, elapsed = self._wait_stub(body, wait_seconds=30)
                self.assertEqual(returncode, 2)
                self.assertLess(elapsed, 20)  # not treated as merely not ready

    def test_not_ready_or_unavailable_keeps_bounded_wait(self):
        not_ready = {"component": "telegram_monitoring", "status": "not_ready",
                     "database_identity": self.identity}
        for returncode, elapsed in (self._wait_stub(not_ready, code=503, wait_seconds=3),
                                    self._wait(self._free_port(), wait_seconds=3)):
            self.assertEqual(returncode, 1)
            self.assertGreaterEqual(elapsed, 3)


if __name__ == "__main__":
    unittest.main()
