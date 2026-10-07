"""Desktop launcher contract; never execute the prototype launcher itself.

The tracked .bat files are thin intent wrappers. Bootstrap, identity and Robot/
Scanner routing are owned by tools.runtime_intent and POST /api/runtime/intent
(covered by test_runtime_intent_bootstrap / test_runtime_intent_backend).
"""

import os
import subprocess
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "start_robot_runtime.bat"
SCANNER_LAUNCHER = ROOT / "start_scanner.bat"


def _commands(path):
    return [line.strip() for line in path.read_text().splitlines()
            if line.strip() and not line.strip().lower().startswith("rem ")]


class RuntimeLauncherTests(unittest.TestCase):
    def test_default_robot_launcher_routes_robot_intent_never_implicit_all(self):
        commands = _commands(LAUNCHER)
        self.assertIn('set "BYBITSCANNER_RUNTIME_INTENT=%~1"', commands)
        self.assertIn(
            'if "%BYBITSCANNER_RUNTIME_INTENT%"=="" set "BYBITSCANNER_RUNTIME_INTENT=ROBOT"',
            commands,
        )
        self.assertFalse(any("INTENT=ALL" in line for line in commands))
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


@unittest.skipUnless(os.name == "nt", "batch launcher semantics are Windows-only")
class DesktopLaunchResolutionTests(unittest.TestCase):
    """Run the real tracked .bat files in cmd with only the bootstrap call replaced.

    The final `-m tools.runtime_intent` line is swapped for an echo of the resolved
    intent, so nothing is bootstrapped, no backend/Scanner/Robot is started, and no
    python process runs; every line before it (arguments, defaults, delegation) is real.
    """

    def _resolve(self, launcher_name, *args):
        invoke = '"%~dp0venv\\Scripts\\python.exe" -m tools.runtime_intent "%BYBITSCANNER_RUNTIME_INTENT%"'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "venv" / "Scripts").mkdir(parents=True)
            (root / "venv" / "Scripts" / "python.exe").write_bytes(b"")
            for name in ("start_robot_runtime.bat", "start_scanner.bat"):
                text = (ROOT / name).read_text()
                if name == "start_robot_runtime.bat":
                    self.assertIn(invoke, text)
                    text = text.replace(invoke, "echo RESOLVED_INTENT=%BYBITSCANNER_RUNTIME_INTENT%")
                (root / name).write_text(text)
            done = subprocess.run(
                ["cmd.exe", "/c", str(root / launcher_name), *args],
                cwd=temp, capture_output=True, text=True, timeout=30, check=False,
            )
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        return [line for line in done.stdout.splitlines() if line.startswith("RESOLVED_INTENT=")]

    def test_robot_desktop_launch_without_argument_resolves_robot(self):
        self.assertEqual(self._resolve("start_robot_runtime.bat"), ["RESOLVED_INTENT=ROBOT"])

    def test_robot_desktop_shortcut_with_explicit_robot_argument_resolves_robot(self):
        self.assertEqual(self._resolve("start_robot_runtime.bat", "ROBOT"), ["RESOLVED_INTENT=ROBOT"])

    def test_scanner_desktop_launch_resolves_scanner(self):
        self.assertEqual(self._resolve("start_scanner.bat"), ["RESOLVED_INTENT=SCANNER"])

    def test_explicit_all_remains_all(self):
        self.assertEqual(self._resolve("start_robot_runtime.bat", "ALL"), ["RESOLVED_INTENT=ALL"])


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

    def test_shortcut_sync_pins_robot_only_arguments_and_never_all(self):
        script = (ROOT / "tools" / "sync_owner_shortcuts.ps1").read_text(encoding="ascii")

        self.assertIn("$intentArguments[$robotShortcut] = 'ROBOT'", script)
        self.assertIn("$shortcut.Arguments = $expectedArguments", script)
        self.assertIn("$verify.Arguments, $expectedArguments", script)
        self.assertNotIn("'ALL'", script)
        self.assertNotIn("'SCANNER'", script)


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

    def test_safe_stop_persists_last_run_without_leaking_failed_shells(self):
        launcher = (ROOT / "stop_robot_runtime.bat").read_text()
        self.assertIn(
            'set "STOP_LOG=%TEMP%\\BybitScanner-stop-last.log"',
            launcher,
        )
        self.assertIn(
            '-m tools.stop_robot_runtime >> "%STOP_LOG%" 2>&1',
            launcher,
        )
        self.assertIn('echo [STOP BAT] EXIT_CODE=%STOP_RC%', launcher)
        self.assertIn('if not "%STOP_RC%"=="0" (', launcher)
        self.assertIn('type "%STOP_LOG%"', launcher)
        self.assertNotIn("pause", launcher.lower())


if __name__ == "__main__":
    unittest.main()
