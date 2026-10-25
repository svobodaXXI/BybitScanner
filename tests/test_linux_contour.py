"""Offline Linux contour regressions; no runtime, remote network or real PAPER DB."""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tools import runtime_intent as intent, vps_check
from tests.test_vps_check import FakeHost, which

ROOT = Path(__file__).resolve().parents[1]


class ReadinessTests(unittest.TestCase):
    def bootstrap(self, get):
        return intent.RuntimeIntentBootstrap(
            root=ROOT, env={}, get=get, sleep=lambda _: None,
            monotonic=iter(range(1000)).__next__, out=lambda _: None,
            systemd_managed=True,
            post=lambda *a: self.fail("readiness sent an intent"),
            spawn=lambda *a: self.fail("systemd bootstrap spawned"))

    def response(self, identity=None):
        return intent.HttpResponse(200, json.dumps({
            "ok": True, "component": "paper_backend", "mode": "paper",
            "database_identity": identity or intent.expected_database_identity(ROOT, {})
        }).encode())

    def test_waits_until_identity_is_ready_without_spawning_or_posting(self):
        replies = iter([intent.Unreachable(), self.response()])
        def get(*args):
            response = next(replies)
            if isinstance(response, Exception):
                raise response
            return response
        self.assertEqual(self.bootstrap(get).wait_backend(), intent.EXIT_OK)

    def test_wrong_identity_fails_immediately_without_post(self):
        self.assertEqual(self.bootstrap(lambda *a: self.response("wrong")).wait_backend(), 1)

    def test_absent_backend_times_out_without_spawn_or_post(self):
        def absent(*args):
            raise intent.Unreachable()
        self.assertEqual(self.bootstrap(absent).wait_backend(), 1)

    def test_linux_execute_never_spawns_when_backend_absent(self):
        def absent(*args):
            raise intent.Unreachable()
        result = self.bootstrap(absent).execute("ALL")
        self.assertEqual(result.outcome, intent.OUTCOME_FAILED)


class EnvironmentTests(unittest.TestCase):
    def test_prestart_allows_owner_mirror_but_still_refuses_live(self):
        env = {"BYBITSCANNER_MIRROR_STANDALONE_ROBOT": "1",
               "LIVE_MARKET_MUTATIONS_ENABLED": "true"}
        checks = vps_check.check_safety_env(env, "test", enforce_off_switches=False)
        self.assertFalse(next(c.ok for c in checks if c.name.endswith("LIVE_MARKET_MUTATIONS_ENABLED")))
        self.assertTrue(next(c.ok for c in checks if c.name.endswith("BYBITSCANNER_MIRROR_STANDALONE_ROBOT")))

    def test_systemd_single_line_multiple_environment_files_cannot_hide_live(self):
        host = FakeHost()
        owner = vps_check.OWNER_ENV_FILE
        host.files[owner] = "LIVE_MARKET_MUTATIONS_ENABLED=true"
        host.show["bybitscanner-paper-backend.service"]["EnvironmentFiles"] += (
            f" {owner.as_posix()} (ignore_errors=yes)")
        with mock.patch.object(Path, "exists", return_value=True):
            checks = vps_check.check_installed_units(ROOT, run=host.run, which=which, read=host.read)
        self.assertTrue(any(not c.ok and c.name.endswith("LIVE_MARKET_MUTATIONS_ENABLED") for c in checks))


class SignalTests(unittest.TestCase):
    def test_clean_python_process_has_standard_signal_and_project_package(self):
        code = (
            "import signal, subprocess, asyncio, multiprocessing.resource_tracker; "
            "assert signal.SIGINT; assert signal.SIGTERM; "
            "assert signal.Signals(signal.SIGTERM).name == 'SIGTERM'; "
            "assert callable(signal.getsignal); assert callable(signal.signal); "
            "assert hasattr(signal, '__path__'); "
            "assert signal.SIGTERM in signal.valid_signals()"
        )
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=ROOT,
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
