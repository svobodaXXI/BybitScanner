"""Unified owner runtime shutdown with fake HTTP, Robot state and clock; no real process."""

from pathlib import Path
import subprocess
import unittest
from unittest import mock

from terminal.application.robot_control import RobotControlRejected
import tools.stop_robot_runtime as shutdown
from tools.runtime_intent import expected_database_identity

ROOT = Path(__file__).resolve().parents[1]
BACKEND = "http://127.0.0.1:8765"
TELEGRAM = "http://127.0.0.1:8766"
IDENTITY = expected_database_identity(ROOT, {})

STOPPED = ("ROBOT_STOPPED", "ROBOT_STOPPED")
READY = ("ROBOT_RUNNING", "READY")
PAUSED = ("ROBOT_RUNNING", "PAUSED")
RECON = ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")


class FakeRuntime:
    def __init__(self, *, robot=READY, backend=True, telegram=True):
        self.robot = robot
        self.backend_alive = backend
        self.telegram_alive = telegram
        self.backend_health = {"ok": True, "component": "paper_backend", "mode": "paper",
                               "database_identity": IDENTITY}
        self.telegram_health = {"component": "telegram_monitoring", "status": "ready",
                                "database_identity": IDENTITY}
        self.protection = {"ok": True, "healthy": True, "covered_symbols": [],
                           "unhealthy_symbols": {}}
        self.shutdown_replies = {}
        self.exit_after_polls = {"telegram": 1, "backend": 1}
        self.calls = []
        self.now = 0.0

    def get(self, url, timeout):
        if url == BACKEND + "/api/health":
            if not self.backend_alive:
                raise shutdown.Unreachable("refused")
            return 200, dict(self.backend_health)
        if url == BACKEND + "/api/robot/protection-health":
            return 200, dict(self.protection)
        if url == TELEGRAM + "/health":
            if not self.telegram_alive:
                raise shutdown.Unreachable("refused")
            return 200, dict(self.telegram_health)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, payload, timeout):
        if url == BACKEND + "/api/scanner/stop":
            self.calls.append("scanner:stop")
            return 200, {"ok": True, "mode": "SCANNER_STOPPED"}
        if url == TELEGRAM + "/shutdown":
            self.calls.append("telegram:shutdown")
            self._check_identity(payload)
            reply = self.shutdown_replies.get("telegram", (200, {"ok": True}))
            if reply[0] == 200:
                self.telegram_alive = False
            return reply
        if url == BACKEND + "/api/runtime/shutdown":
            self.calls.append("backend:shutdown")
            self._check_identity(payload)
            reply = self.shutdown_replies.get("backend", (200, {"ok": True}))
            if reply[0] == 200:
                self.backend_alive = False
            return reply
        raise AssertionError(f"unexpected POST {url}")

    @staticmethod
    def _check_identity(payload):
        assert payload == {"database_identity": IDENTITY}, payload

    def stop_robot(self):
        self.calls.append("robot:stop")
        if self.robot not in (READY, PAUSED):
            raise RobotControlRejected("stop_robot is illegal")
        self.robot = STOPPED

    def sleep(self, seconds):
        self.now += seconds

    def orchestrator(self):
        return shutdown.RuntimeShutdown(
            root=ROOT, env={}, get=self.get, post=self.post,
            robot_state=lambda: self.robot, stop_robot_fn=self.stop_robot,
            sleep=self.sleep, monotonic=lambda: self.now,
        )


class FullShutdownTests(unittest.TestCase):
    def test_full_stop_orders_scanner_robot_telegram_backend(self):
        for robot in (READY, PAUSED):
            with self.subTest(robot=robot):
                runtime = FakeRuntime(robot=robot)
                result = runtime.orchestrator().run("all")
                self.assertTrue(result.ok, result.message)
                self.assertTrue(result.runtime_stopped)
                self.assertEqual(runtime.calls, [
                    "scanner:stop", "robot:stop", "telegram:shutdown", "backend:shutdown",
                ])
                self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_already_stopped_robot_is_not_stopped_again(self):
        runtime = FakeRuntime(robot=STOPPED)
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok)
        self.assertEqual(runtime.calls, ["scanner:stop", "telegram:shutdown", "backend:shutdown"])

    def test_absent_processes_with_stopped_robot_are_idempotent_success(self):
        for robot in (STOPPED, None):
            with self.subTest(robot=robot):
                runtime = FakeRuntime(robot=robot, backend=False, telegram=False)
                result = runtime.orchestrator().run("all")
                self.assertTrue(result.ok)
                self.assertEqual(runtime.calls, [])

    def test_absent_backend_with_live_telegram_shuts_telegram_only(self):
        runtime = FakeRuntime(robot=STOPPED, backend=False)
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok)
        self.assertEqual(runtime.calls, ["telegram:shutdown"])

    def test_robot_needing_backend_authority_keeps_runtime_alive(self):
        for robot in (RECON, ("ROBOT_STOPPED", "RECONCILIATION_REQUIRED"), ("ROBOT_WEIRD", "X")):
            with self.subTest(robot=robot):
                runtime = FakeRuntime(robot=robot)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls, ["scanner:stop"])
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_rejected_robot_stop_keeps_runtime_alive(self):
        runtime = FakeRuntime(robot=READY)
        runtime.stop_robot = mock.Mock(side_effect=RobotControlRejected("open Robot position"))
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("open Robot position", result.message)
        self.assertEqual(runtime.calls, ["scanner:stop"])
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_active_protection_coverage_keeps_runtime_alive(self):
        runtime = FakeRuntime(robot=READY)
        runtime.protection["covered_symbols"] = ["BTCUSDT"]
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertEqual(runtime.calls, ["scanner:stop", "robot:stop"])
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_robot_running_with_absent_backend_is_blocked_without_shutdown(self):
        runtime = FakeRuntime(robot=READY, backend=False)
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertEqual(runtime.calls, [])
        self.assertTrue(runtime.telegram_alive)


class OwnershipTests(unittest.TestCase):
    def test_wrong_backend_identity_blocks_every_mutation_and_shutdown(self):
        for override in ({"database_identity": "0" * 64}, {"component": "telegram_monitoring"},
                         {"mode": "live"}, {"ok": False}):
            with self.subTest(override=override):
                runtime = FakeRuntime(robot=STOPPED)
                runtime.backend_health.update(override)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls, [])

    def test_wrong_telegram_identity_blocks_every_mutation_and_shutdown(self):
        for override in ({"database_identity": "0" * 64}, {"database_identity": None},
                         {"component": "something_else"}):
            with self.subTest(override=override):
                runtime = FakeRuntime(robot=READY)
                runtime.telegram_health.update(override)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls, [])
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_legacy_worker_without_shutdown_endpoint_fails_closed_before_backend(self):
        for status in (404, 501):
            with self.subTest(status=status):
                runtime = FakeRuntime(robot=STOPPED)
                runtime.shutdown_replies["telegram"] = (status, None)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertIn("legacy", result.message)
                self.assertNotIn("backend:shutdown", runtime.calls)
                self.assertTrue(runtime.backend_alive)

    def test_refused_backend_shutdown_is_not_retried(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.shutdown_replies["backend"] = (409, {"ok": False, "error": "runtime_still_required"})
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertEqual(runtime.calls.count("backend:shutdown"), 1)

    def test_waits_boundedly_for_health_to_disappear(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.shutdown_replies["telegram"] = (200, {"ok": True})
        original = runtime.post

        def post(url, payload, timeout):
            reply = original(url, payload, timeout)
            if url == TELEGRAM + "/shutdown":
                runtime.telegram_alive = True  # accepted but never exits
            return reply

        runtime.post = post
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("did not exit", result.message)
        self.assertGreaterEqual(runtime.now, shutdown.EXIT_WAIT_S)
        self.assertNotIn("backend:shutdown", runtime.calls)

    def test_no_broad_process_kill_exists(self):
        source = Path(shutdown.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("taskkill", "os.kill", "psutil", "terminate(", ".kill(", "netstat",
                          "_exit("):
            self.assertNotIn(forbidden, source)


class ScannerScopeTests(unittest.TestCase):
    def test_scanner_stop_with_stopped_robot_shuts_telegram_then_backend(self):
        runtime = FakeRuntime(robot=STOPPED)
        result = runtime.orchestrator().run("scanner")
        self.assertTrue(result.ok)
        self.assertTrue(result.runtime_stopped)
        self.assertEqual(runtime.calls, ["scanner:stop", "telegram:shutdown", "backend:shutdown"])

    def test_scanner_stop_keeps_runtime_for_a_live_robot_and_never_stops_it(self):
        for robot in (READY, PAUSED, RECON):
            with self.subTest(robot=robot):
                runtime = FakeRuntime(robot=robot)
                result = runtime.orchestrator().run("scanner")
                self.assertTrue(result.ok)
                self.assertFalse(result.runtime_stopped)
                self.assertEqual(runtime.calls, ["scanner:stop"])
                self.assertEqual(runtime.robot, robot)
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_scanner_stop_keeps_runtime_while_protection_coverage_is_active(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.protection["covered_symbols"] = ["BTCUSDT"]
        result = runtime.orchestrator().run("scanner")
        self.assertTrue(result.ok)
        self.assertFalse(result.runtime_stopped)
        self.assertEqual(runtime.calls, ["scanner:stop"])


class HandoffAndCliTests(unittest.TestCase):
    def test_detached_helper_has_no_persistent_window(self):
        with mock.patch("tools.stop_robot_runtime.subprocess.Popen") as popen:
            shutdown.launch_detached("all", notify_chat=42, root=ROOT)
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1:], ["-m", "tools.stop_robot_runtime", "all", "--notify-chat", "42"])
        self.assertEqual(kwargs["cwd"], str(ROOT))
        self.assertNotIn("shell", kwargs)
        flags = kwargs["creationflags"]
        self.assertEqual(flags & getattr(subprocess, "CREATE_NEW_CONSOLE", 0), 0)
        self.assertEqual(
            flags,
            getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        for stream in ("stdin", "stdout", "stderr"):
            self.assertIs(kwargs[stream], subprocess.DEVNULL)
        with self.assertRaises(ValueError):
            shutdown.launch_detached("robot", root=ROOT)

    def test_main_defaults_to_full_scope_and_notifies_result(self):
        result = shutdown.ShutdownResult("all", True, "Runtime STOPPED.", runtime_stopped=True)
        with mock.patch.object(shutdown.RuntimeShutdown, "run", return_value=result) as run, \
                mock.patch.object(shutdown, "_notify") as notify:
            self.assertEqual(shutdown.main([]), 0)
            self.assertEqual(shutdown.main(["scanner", "--notify-chat", "42"]), 0)
        self.assertEqual([c.args[0] for c in run.call_args_list], ["all", "scanner"])
        notify.assert_called_once_with("42", "✅ Остановлено: сканер, робот, Telegram и backend.")

    def test_blocked_result_is_nonzero_with_owner_blocker_text(self):
        blocked = shutdown.ShutdownResult("all", False, "STOP BLOCKED: Robot is busy")
        with mock.patch.object(shutdown.RuntimeShutdown, "run", return_value=blocked):
            self.assertEqual(shutdown.main([]), 1)
        self.assertEqual(shutdown.owner_text(blocked), "⛔ Остановка не выполнена: Robot is busy")

    def test_desktop_wrapper_runs_full_scope_module(self):
        launcher = (ROOT / "stop_robot_runtime.bat").read_text()
        self.assertIn('"%~dp0venv\\Scripts\\python.exe" -m tools.stop_robot_runtime', launcher)


if __name__ == "__main__":
    unittest.main()
