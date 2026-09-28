"""Desktop launcher contract; never execute the prototype launcher itself.

The tracked .bat files are thin intent wrappers. Bootstrap, identity and Robot/
Scanner routing are owned by tools.runtime_intent and POST /api/runtime/intent
(covered by test_runtime_intent_bootstrap / test_runtime_intent_backend).
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start_robot_runtime.bat"
SCANNER_LAUNCHER = ROOT / "start_scanner.bat"


def _commands(path):
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.strip().lower().startswith("rem ")]


class RuntimeLauncherTests(unittest.TestCase):
    def test_default_robot_launcher_routes_all_intent(self):
        commands = _commands(LAUNCHER)
        self.assertIn('set "BYBITSCANNER_RUNTIME_INTENT=%~1"', commands)
        self.assertIn(
            'if "%BYBITSCANNER_RUNTIME_INTENT%"=="" set "BYBITSCANNER_RUNTIME_INTENT=ALL"',
            commands,
        )
        invoke = '"%~dp0venv\\Scripts\\python.exe" -m tools.runtime_intent "%BYBITSCANNER_RUNTIME_INTENT%"'
        self.assertEqual(commands[-2:], [invoke, "exit /b %errorlevel%"])

    def test_launcher_keeps_local_env_and_venv_preconditions_before_bootstrap(self):
        commands = _commands(LAUNCHER)
        self.assertEqual(commands[:3], ["@echo off", "setlocal", 'cd /d "%~dp0"'])
        load = commands.index(
            'if exist "%~dp0start_runtime.local.bat" call "%~dp0start_runtime.local.bat"'
        )
        self.assertEqual(commands[load + 1], "if errorlevel 1 (")
        self.assertEqual(commands[load + 3], "exit /b 1")
        venv = commands.index('if not exist "%~dp0venv\\Scripts\\python.exe" (')
        self.assertEqual(commands[venv + 2], "exit /b 1")
        bootstrap = next(i for i, line in enumerate(commands) if "tools.runtime_intent" in line)
        self.assertTrue(load < venv < bootstrap)

    def test_scanner_shortcut_routes_scanner_intent_not_all(self):
        self.assertEqual(_commands(SCANNER_LAUNCHER), [
            "@echo off",
            'call "%~dp0start_robot_runtime.bat" SCANNER',
            "exit /b %errorlevel%",
        ])

    def test_launchers_contain_no_runtime_state_machine(self):
        for path in (LAUNCHER, SCANNER_LAUNCHER):
            text = path.read_text().lower()
            with self.subTest(path=path.name):
                for forbidden in (
                    "/api/", "powershell", "invoke-", "robot_admission_ready",
                    "protection", "paper_live_safe", "scanner_acceptance_ready",
                    "hashlib", "database_identity", "telegram_monitoring.py",
                    "start_paper_backend.bat", "goto", "timeout /t",
                ):
                    self.assertNotIn(forbidden, text)
                self.assertNotRegex(text, r"\bmain(?:\.py)?\b")
                self.assertFalse(any(
                    line.lower().startswith("start ") for line in _commands(path)
                ))


class OwnerShortcutProvisioningTests(unittest.TestCase):
    def test_shortcut_sync_is_ascii_only_for_windows_powershell_51(self):
        raw = (ROOT / "tools" / "sync_owner_shortcuts.ps1").read_bytes()
        raw.decode("ascii")

    def test_shortcut_sync_targets_only_tracked_canonical_launchers(self):
        import base64

        script = (ROOT / "tools" / "sync_owner_shortcuts.ps1").read_text(encoding="ascii")
        start_name = base64.b64decode(
            "0JfQsNC/0YPRgdC6INGA0L7QsdC+0YLQsC5sbms="
        ).decode("utf-8")
        stop_name = base64.b64decode(
            "0J7RgdGC0LDQvdC+0LLQuNGC0Ywg0YDQvtCx0L7RgtCwLmxuaw=="
        ).decode("utf-8")

        self.assertEqual(start_name, "Запуск робота.lnk")
        self.assertEqual(stop_name, "Остановить робота.lnk")
        self.assertIn("$targets.Add('start_scanner.lnk', 'start_scanner.bat')", script)
        self.assertIn("'start_robot_runtime.bat'", script)
        self.assertIn("'stop_robot_runtime.bat'", script)
        self.assertNotIn("'start_robot.bat'", script)
        self.assertNotIn("'stop_robot.bat'", script)
        self.assertIn("'OWNER SHORTCUTS = CANONICAL'", script)


class StopRuntimeLauncherTests(unittest.TestCase):
    def test_safe_stop_runs_as_repo_module(self):
        launcher = (ROOT / "stop_robot_runtime.bat").read_text()
        self.assertIn('cd /d "%~dp0"', launcher)
        self.assertIn(
            '"%~dp0venv\\Scripts\\python.exe" -m tools.stop_robot_runtime',
            launcher,
        )
        self.assertNotIn(
            '"%~dp0venv\\Scripts\\python.exe" "%~dp0tools\\stop_robot_runtime.py"',
            launcher,
        )


if __name__ == "__main__":
    unittest.main()
