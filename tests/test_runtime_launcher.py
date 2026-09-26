"""Static ownership check; never execute the prototype launcher."""

from pathlib import Path
import re
import unittest


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
        self.assertEqual(launcher.count("Invoke-RestMethod"), 1)
        self.assertEqual(launcher.count("/api/scanner/start"), 1)
        request = next(line for line in commands if "Invoke-RestMethod" in line)
        self.assertTrue(request.startswith("powershell.exe -NoProfile -Command"))
        self.assertIn("$backendUrl = $env:BYBITSCANNER_PAPER_BACKEND_URL", request)
        self.assertIn("if (-not $backendUrl) { $backendUrl = 'http://127.0.0.1:8765' }", request)
        self.assertIn("-Method Post", request)
        self.assertIn("-Uri ($backendUrl.TrimEnd('/') + '/api/scanner/start')", request)
        self.assertIn("-Body '{}'", request)
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


if __name__ == "__main__":
    unittest.main()
