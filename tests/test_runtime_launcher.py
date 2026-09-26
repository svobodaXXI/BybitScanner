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


if __name__ == "__main__":
    unittest.main()
