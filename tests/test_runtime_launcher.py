"""Launcher ownership checks; never execute the prototype launcher itself.

The Scanner routing PowerShell command runs only against a local stub backend.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import threading
import unittest

LAUNCHER = Path(__file__).resolve().parents[1] / "start_robot_runtime.bat"


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
        # An already READY worker is reused and skips the second start.
        self.assertEqual(lines[worker - 2:worker],
                         ["call :wait_telegram_ready 1", "if not errorlevel 1 goto telegram_ready"])
        # A newly started worker must prove READY within a bound or the launcher exits nonzero.
        self.assertEqual(lines[worker + 1:worker + 3],
                         ["call :wait_telegram_ready 60", "if errorlevel 1 ("])
        self.assertIn("exit /b 1", lines[worker + 4])
        self.assertEqual(lines[scanner - 1], ":telegram_ready")
        self.assertEqual(lines.count(":telegram_ready"), 1)
        self.assertEqual(sum("goto telegram_ready" in line for line in lines), 1)
        probe = lines[lines.index(":wait_telegram_ready") + 2]
        self.assertIn("$env:BYBITSCANNER_TELEGRAM_MONITORING_PORT", probe)
        self.assertIn("$port = '8766'", probe)
        self.assertIn("'http://127.0.0.1:' + $port + '/health'", probe)
        # An unrelated HTTP 200 fails closed: component identity and status are both required.
        self.assertIn("$h = $r.Content | ConvertFrom-Json;", probe)
        self.assertIn("if ($r.StatusCode -eq 200 -and $h.component -eq 'telegram_monitoring' "
                      "-and $h.status -eq 'ready') { exit 0 }", probe)
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


if __name__ == "__main__":
    unittest.main()
