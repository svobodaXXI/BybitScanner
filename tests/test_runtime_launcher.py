"""Desktop launcher contract; never execute the prototype launcher itself.

The tracked .bat files are thin intent wrappers. Bootstrap, identity and Robot/
Scanner routing are owned by tools.runtime_intent and POST /api/runtime/intent
(covered by test_runtime_intent_bootstrap / test_runtime_intent_backend).
"""

from pathlib import Path
import unittest
from unittest import mock

from tools import runtime_intent

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
        self.assertEqual(commands[load + 3], "pause")
        self.assertEqual(commands[load + 4], "exit /b 1")
        venv = commands.index('if not exist "%~dp0venv\\Scripts\\python.exe" (')
        self.assertEqual(commands[venv + 2], "pause")
        self.assertEqual(commands[venv + 3], "exit /b 1")
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



class DesktopStartupNoticeTests(unittest.TestCase):
    def _result(self, outcome, changed=(), blocked_by=()):
        return runtime_intent.BootstrapResult(
            "ALL", outcome, f"{outcome}: intent=ALL", tuple(changed),
            {"robot": "READY", "scanner": "STOPPED", "protection": "UNHEALTHY"},
            tuple(blocked_by),
        )

    def test_blocked_notice_shows_cause_and_partial_runtime_transitions(self):
        result = self._result(
            runtime_intent.OUTCOME_BLOCKED,
            changed=("robot:start",), blocked_by=("ROBOT_PROTECTION_UNHEALTHY",),
        )
        notice = runtime_intent.startup_issue_notice(result)
        self.assertIn("ROBOT_PROTECTION_UNHEALTHY", notice)
        self.assertIn("Защита Robot", notice)
        self.assertIn("robot:start", notice)
        self.assertIn("scanner=STOPPED", notice)
        self.assertIn("частично изменить состояние", notice)

    def test_unknown_outcome_warns_not_to_retry_automatically(self):
        notice = runtime_intent.startup_issue_notice(
            self._result(runtime_intent.OUTCOME_ERROR)
        )
        self.assertIn("Исход команды неизвестен", notice)
        self.assertIn("Не повторяйте запуск вслепую", notice)

    def test_desktop_run_shows_one_dialog_only_on_failure_without_retry(self):
        for outcome in (
            runtime_intent.OUTCOME_READY,
            runtime_intent.OUTCOME_BLOCKED,
            runtime_intent.OUTCOME_FAILED,
            runtime_intent.OUTCOME_ERROR,
        ):
            with self.subTest(outcome=outcome):
                result = self._result(outcome)
                with mock.patch.object(runtime_intent.RuntimeIntentBootstrap, "execute",
                                       return_value=result) as execute:
                    with mock.patch.object(runtime_intent, "show_startup_issue_dialog",
                                           return_value=True) as dialog:
                        lines = []
                        bootstrap = runtime_intent.RuntimeIntentBootstrap(out=lines.append)
                        self.assertEqual(
                            bootstrap.run("ALL", desktop_notice=True), result.exit_code,
                        )
                        execute.assert_called_once_with("ALL")
                        self.assertEqual(
                            dialog.call_count, 0 if outcome == runtime_intent.OUTCOME_READY else 1,
                        )

    def test_programmatic_run_does_not_open_any_dialog(self):
        result = self._result(runtime_intent.OUTCOME_BLOCKED)
        with mock.patch.object(runtime_intent.RuntimeIntentBootstrap, "execute",
                               return_value=result):
            with mock.patch.object(runtime_intent, "show_startup_issue_dialog") as dialog:
                self.assertEqual(
                    runtime_intent.RuntimeIntentBootstrap(out=lambda _: None).run("ALL"),
                    runtime_intent.EXIT_BLOCKED,
                )
                dialog.assert_not_called()

    def test_native_dialog_uses_topmost_flag(self):
        result = self._result(
            runtime_intent.OUTCOME_BLOCKED, blocked_by=("ROBOT_PROTECTION_UNHEALTHY",),
        )
        with mock.patch.object(runtime_intent.os, "name", "nt"):
            with mock.patch("ctypes.windll", create=True) as windll:
                windll.user32.MessageBoxW.return_value = 1
                self.assertTrue(runtime_intent.show_startup_issue_dialog(result))
                windll.user32.MessageBoxW.assert_called_once()
                args = windll.user32.MessageBoxW.call_args.args
                self.assertIn("ROBOT_PROTECTION_UNHEALTHY", args[1])
                self.assertTrue(args[3] & 0x40000)

    def test_dialog_failure_does_not_change_exit_code(self):
        result = self._result(runtime_intent.OUTCOME_BLOCKED)
        with mock.patch.object(runtime_intent, "show_startup_issue_dialog",
                               return_value=False):
            bootstrap = runtime_intent.RuntimeIntentBootstrap(out=lambda _: None)
            with mock.patch.object(bootstrap, "execute", return_value=result):
                self.assertEqual(
                    bootstrap.run("ALL", desktop_notice=True), runtime_intent.EXIT_BLOCKED,
                )


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
