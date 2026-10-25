"""Issue #627: Linux-safe canonical shutdown. Fake HTTP / process only; nothing is started or killed."""

from contextlib import nullcontext
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import tools.legacy_runtime_process as legacy
import tools.stop_robot_runtime as shutdown
from tools import vps_check
from tools.runtime_intent import expected_database_identity

ROOT = Path(__file__).resolve().parents[1]
BACKEND = "http://127.0.0.1:8765"
TELEGRAM = "http://127.0.0.1:8766"
IDENTITY = expected_database_identity(ROOT, {})
STOPPED = ("ROBOT_STOPPED", "ROBOT_STOPPED")
READY = ("ROBOT_RUNNING", "READY")

PROC_NET_TCP = """  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:223D 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000        0 11111 1 0000000000000000 100 0 0 10 0
   1: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 22222 1 0000000000000000 100 0 0 10 0
   2: 0100007F:C350 0100007F:223D 01 00000000:00000000 00:00000000 00000000  1000        0 33333 1 0000000000000000 100 0 0 10 0
"""


class FakeHost:
    """The two PAPER endpoints as a Linux host exposes them; records every call."""

    def __init__(self, *, robot=READY, backend=True, telegram=True, health_up=True):
        self.robot, self.backend, self.telegram, self.health_up = robot, backend, telegram, health_up
        self.calls, self.shutdown_status = [], {}
        self.terminated = []

    def get(self, url, timeout):
        if url == BACKEND + "/api/health":
            if not self.backend or not self.health_up:
                raise shutdown.Unreachable("down")
            return 200, {"ok": True, "component": "paper_backend", "mode": "paper", "database_identity": IDENTITY}
        if url == TELEGRAM + "/health":
            if not self.telegram:
                raise shutdown.Unreachable("down")
            return 200, {"component": "telegram_monitoring", "database_identity": IDENTITY}
        if url == BACKEND + "/api/robot/protection-health":
            return 200, {"healthy": True, "covered_symbols": [], "unhealthy_symbols": {}, "armed_symbols": []}
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, payload, timeout):
        self.calls.append(url.replace(BACKEND, "").replace(TELEGRAM, "tg"))
        if url.endswith("/api/scanner/stop"):
            return 200, {"ok": True}
        if url.endswith("/shutdown"):
            status = self.shutdown_status.get("telegram" if url.startswith(TELEGRAM) else "backend", 200)
            if status == 200:
                if url.startswith(TELEGRAM):
                    self.telegram = False
                else:
                    self.backend = False
            return status, {"ok": status == 200}
        raise AssertionError(f"unexpected POST {url}")

    def stop_robot(self):
        self.calls.append("robot:stop")
        self.robot = STOPPED

    def orchestrator(self, *, listener=lambda host, port: (legacy.LISTENER_PID_UNRESOLVED,),
                     resolver=None):
        return shutdown.RuntimeShutdown(
            root=ROOT, env={}, get=self.get, post=self.post, robot_state=lambda: self.robot,
            stop_robot_fn=self.stop_robot, sleep=lambda s: None, monotonic=iter(range(0, 10_000)).__next__,
            listener_probe=listener, legacy_resolver=resolver or legacy.resolve_legacy_chain,
            legacy_terminator=self.terminated.extend, legacy_supported=False,
            legacy_paper_quiescence=lambda: self.calls.append("QUIESCENCE_PROOF"),
            legacy_paper_guard=lambda: (self.calls.append("SQLITE_BARRIER"), nullcontext())[1],
        )


class LinuxShutdownTests(unittest.TestCase):
    def test_graceful_path_is_unchanged_and_ordered(self):
        host = FakeHost()
        result = host.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(host.calls, ["/api/scanner/stop", "robot:stop", "tg/shutdown", "/api/runtime/shutdown"])
        self.assertEqual(host.terminated, [])

    def test_missing_shutdown_endpoint_fails_closed_without_termination(self):
        for which in ("backend", "telegram"):
            with self.subTest(which=which):
                host = FakeHost()
                host.shutdown_status[which] = 404
                result = host.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertIn("unavailable on this platform", result.message)
                self.assertEqual(host.terminated, [])
                self.assertNotIn("SQLITE_BARRIER", host.calls)

    def test_unreachable_health_with_a_live_listener_keeps_the_runtime_alive(self):
        host = FakeHost(health_up=False)
        result = host.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("runtime kept alive", result.message)
        self.assertEqual(host.calls, [])                       # no mutation of any kind
        self.assertEqual(host.terminated, [])

    def test_absent_backend_with_robot_still_running_is_blocked_not_cleaned_up(self):
        host = FakeHost(backend=False, telegram=False)
        result = host.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertEqual(host.calls, [])

    def test_open_exposure_blocks_backend_shutdown_even_if_stop_robot_succeeded(self):
        host = FakeHost()
        host.get_original = host.get

        def covered(url, timeout):
            if url.endswith("/api/robot/protection-health"):
                return 200, {"healthy": True, "covered_symbols": ["BLUAIUSDT"], "unhealthy_symbols": {},
                             "armed_symbols": []}
            return host.get_original(url, timeout)

        host.get = covered
        result = host.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("coverage", result.message)
        self.assertNotIn("/api/runtime/shutdown", host.calls)
        self.assertEqual(host.terminated, [])

    def test_legacy_starvation_bypass_and_sqlite_barrier_are_never_used_on_linux(self):
        host = FakeHost(robot=STOPPED)
        with mock.patch.object(shutdown.RuntimeShutdown, "_legacy_owner_queue_starved",
                               side_effect=AssertionError("starvation path consulted")):
            result = host.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertNotIn("SQLITE_BARRIER", host.calls)


class LinuxProcessHelperTests(unittest.TestCase):
    def test_forced_termination_and_ownership_resolution_refuse_off_windows(self):
        with mock.patch.object(legacy.os, "name", "posix"), \
                mock.patch.object(legacy.subprocess, "run", side_effect=AssertionError("process command run")):
            with self.assertRaises(legacy.LegacyOwnerUnproven):
                legacy.terminate_exact_pids([123])
            with self.assertRaises(legacy.LegacyOwnerUnproven):
                legacy.resolve_legacy_chain(legacy.BACKEND, "127.0.0.1", 8765, ROOT)
        self.assertFalse(legacy.legacy_fallback_supported() and legacy.os.name != "nt")

    def test_linux_listener_probe_is_a_read_only_proc_net_tcp_parse(self):
        self.assertTrue(legacy.linux_listening(8765, [PROC_NET_TCP]))                 # 0x223D, LISTEN
        self.assertFalse(legacy.linux_listening(8766, [PROC_NET_TCP]))                # absent
        self.assertFalse(legacy.linux_listening(50000, [PROC_NET_TCP]))               # only ESTABLISHED
        with mock.patch.object(legacy.os, "name", "posix"), \
                mock.patch.object(legacy, "_read_linux_tables", return_value=[PROC_NET_TCP]), \
                mock.patch.object(legacy.subprocess, "run", side_effect=AssertionError("spawned")):
            self.assertEqual(legacy.probe_listener_pids("127.0.0.1", 8765), (legacy.LISTENER_PID_UNRESOLVED,))
            self.assertEqual(legacy.probe_listener_pids("127.0.0.1", 8766), ())
            with self.assertRaises(legacy.LegacyOwnerUnproven):
                legacy.probe_listener_pids("0.0.0.0", 8765)

    def test_unreadable_listener_state_fails_closed(self):
        with mock.patch.object(legacy.os, "name", "posix"), \
                mock.patch.object(legacy, "_read_linux_tables", side_effect=legacy.LegacyOwnerUnproven("x")):
            with self.assertRaises(legacy.LegacyOwnerUnproven):
                legacy.probe_listener_pids("127.0.0.1", 8765)

    def test_detached_helper_uses_its_own_session_on_linux_and_windows_flags_stay(self):
        with mock.patch.object(shutdown.os, "name", "posix"), \
                mock.patch.object(shutdown.subprocess, "Popen") as popen:
            shutdown.launch_detached("all", notify_chat="7", root=ROOT)
        kwargs = popen.call_args.kwargs
        self.assertIs(kwargs["start_new_session"], True)
        self.assertNotIn("creationflags", kwargs)
        self.assertEqual(popen.call_args.args[0][-5:-2], ["-m", "tools.stop_robot_runtime", "all"])
        with mock.patch.object(shutdown.os, "name", "nt"), \
                mock.patch.object(shutdown.subprocess, "Popen") as popen:
            shutdown.launch_detached("scanner", root=ROOT)
        self.assertIn("creationflags", popen.call_args.kwargs)
        self.assertNotIn("start_new_session", popen.call_args.kwargs)

    def test_env_file_supplies_the_unit_environment_to_an_operator_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "paper.env"
            env_file.write_text("# c\nBYBITSCANNER_PAPER_DB=/var/lib/bybitscanner/paper_runtime.sqlite3\n",
                                encoding="utf-8")
            env = shutdown._environment(env_file)
        self.assertEqual(env["BYBITSCANNER_PAPER_DB"], "/var/lib/bybitscanner/paper_runtime.sqlite3")
        self.assertNotEqual(expected_database_identity(ROOT, env), expected_database_identity(ROOT, {}))


class SystemdIntegrationTests(unittest.TestCase):
    def unit(self, name):
        return (ROOT / vps_check.UNIT_DIR / name).read_text(encoding="utf-8")

    def test_backend_stop_is_the_canonical_safe_stop_and_a_blocked_stop_leaves_the_backend_alive(self):
        service = vps_check._unit_sections(self.unit("bybitscanner-paper-backend.service"))["Service"]
        self.assertIn("-m tools.stop_robot_runtime all", service["ExecStop"])
        self.assertTrue(service["ExecStop"].startswith("/opt/BybitScanner/venv/bin/python "))
        self.assertEqual(service["KillSignal"], "SIGCONT")             # harmless: not SIGINT/SIGTERM
        self.assertEqual(service["SendSIGKILL"], "no")
        self.assertEqual(service["Restart"], "no")
        self.assertGreaterEqual(int(service["TimeoutStopSec"]), 120)   # longer than the tool's own waits
        sections = vps_check._unit_sections(self.unit("bybitscanner-paper-backend.service"))
        self.assertNotIn("Install", sections)
        self.assertEqual(sections["Unit"]["RefuseManualStop"], "yes")   # no manual stop job can untrack it

    def test_telegram_worker_does_not_reap_the_detached_stop_helper(self):
        sections = vps_check._unit_sections(self.unit("bybitscanner-telegram.service"))
        self.assertEqual(sections["Service"]["KillMode"], "process")
        self.assertNotIn("ExecStop", sections["Service"])
        self.assertNotIn("Install", sections)
        self.assertEqual(sections["Unit"]["Requires"], "bybitscanner-paper-backend.service")

    def test_repository_units_satisfy_the_validator_contract(self):
        self.assertTrue(all(c.ok for c in vps_check.check_repo_units(ROOT)))

    def test_validator_rejects_units_that_would_bypass_the_safe_stop(self):
        backend = self.unit("bybitscanner-paper-backend.service")
        entry = "-m terminal.runtime.paper_http_server"
        cases = {
            "ExecStop is not the canonical": backend.replace("ExecStop=", "#ExecStop="),
            "KillSignal=SIGINT": backend.replace("KillSignal=SIGCONT", "KillSignal=SIGINT"),
            "SendSIGKILL is not disabled": backend.replace("SendSIGKILL=no", "SendSIGKILL=yes"),
            "KillMode=none": backend.replace("Restart=no", "Restart=no\nKillMode=none"),
            "RefuseManualStop is not yes": backend.replace("RefuseManualStop=yes\n", ""),
        }
        for expected, text in cases.items():
            with self.subTest(expected):
                problems = vps_check.unit_problems(text, entry, check_interpreter=False)
                self.assertTrue(any(expected in p for p in problems), problems)
        telegram = self.unit("bybitscanner-telegram.service").replace("KillMode=process", "")
        self.assertTrue(any("KillMode is not process" in p for p in
                            vps_check.unit_problems(telegram, "telegram_monitoring.py", check_interpreter=False)))

    def test_no_plain_signal_stop_is_documented_for_normal_operation(self):
        runbook = (ROOT / "DOCUMENTS/VPS_DEPLOYMENT_RUNBOOK.md").read_text(encoding="utf-8").split(
            "## Previous VPS", 1)[0]
        self.assertIn("RefuseManualStop=yes", runbook)
        self.assertIn("-m tools.stop_robot_runtime all --env-file /etc/bybitscanner/paper.env", runbook)
        self.assertIn("Never answer a blocked stop with `kill`", runbook)
        self.assertIn("not an absolute guarantee", runbook)


if __name__ == "__main__":
    unittest.main()
