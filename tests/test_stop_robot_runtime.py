"""Unified owner runtime shutdown with fake HTTP, Robot state and clock; no real process."""

from contextlib import nullcontext
from pathlib import Path
import io
import json
import sqlite3
import tempfile
import threading
from types import SimpleNamespace
from decimal import Decimal
import subprocess
import unittest
from unittest import mock

from terminal.application.robot_control import RobotControlRejected
import tools.legacy_runtime_process as legacy
from tools.legacy_runtime_process import LegacyOwnerUnproven, ProcessInfo, select_legacy_chain
import tools.stop_robot_runtime as shutdown
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.runtime.paper_http_server import PaperHttpHandler, RobotProtectionCoverageManager
from terminal.domain.models import TradingAccountId
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
        self.backend_health = {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "database_identity": IDENTITY, "process_instance_id": "fake-paper-process",
            "build_sha": "legacy-build",
        }
        self.telegram_health = {"component": "telegram_monitoring", "status": "ready",
                                "database_identity": IDENTITY}
        self.scanner_mode = "SCANNER_RUNNING"
        self.protection = {
            "ok": True, "healthy": True, "covered_symbols": [], "coverage_roles": {},
            "armed_symbols": [], "unhealthy_symbols": {},
        }
        self.retire_reply = (409, {"ok": False, "error": "durable_protection_required"})
        self.legacy_paper_blocker = "legacy durable evidence not configured"
        self.legacy_evidence_checks = 0
        self.shutdown_replies = {}
        self.reconcile_reply = (200, {"ok": True, "success": True})
        self.reconcile_state = PAUSED
        self.post_scanner_mode = "SCANNER_STOPPED"
        self.box_upgrade_proof = shutdown.SafeStopError("legacy Box upgrade evidence not configured")
        self.box_upgrade_guard_error = None
        self.box_upgrade_checks = 0
        self.box_upgrade_guards = 0
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
        if url == BACKEND + "/api/scanner/status":
            return 200, {"ok": True, "mode": self.scanner_mode}
        if url == TELEGRAM + "/health":
            if not self.telegram_alive:
                raise shutdown.Unreachable("refused")
            return 200, dict(self.telegram_health)
        raise AssertionError(f"unexpected GET {url}")

    def post(self, url, payload, timeout):
        if url == BACKEND + "/api/robot/reconcile":
            self.calls.append("robot:reconcile")
            assert payload == {}
            assert timeout == shutdown.MUTATION_TIMEOUT_S
            # Even a lost response may follow a committed recovery transition.
            self.robot = self.reconcile_state
            if isinstance(self.reconcile_reply, Exception):
                raise self.reconcile_reply
            return self.reconcile_reply
        if url == BACKEND + "/api/scanner/stop":
            self.calls.append("scanner:stop")
            self.scanner_mode = self.post_scanner_mode
            return 200, {"ok": True, "mode": "SCANNER_STOPPED"}
        if url == BACKEND + "/api/runtime/retire-entry-coverage":
            self.calls.append("protection:retire-entry-arms")
            self._check_identity(payload)
            return self.retire_reply
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

    def probe_listener(self, host, port):
        assert host == "127.0.0.1"
        if port == 8765:
            return (700,) if self.backend_alive else ()
        if port == 8766:
            return (701,) if self.telegram_alive else ()
        raise AssertionError(f"unexpected listener probe {host}:{port}")

    legacy_chains = None

    def resolve_legacy(self, kind, host, port, root):
        self.calls.append(f"resolve:{kind}:{host}:{port}")
        chains = self.legacy_chains or {}
        if kind not in chains:
            raise LegacyOwnerUnproven("no proven owner")
        return chains[kind]

    def terminate_legacy(self, pids):
        self.calls.append(f"terminate:{list(pids)}")
        chains = self.legacy_chains or {}
        if tuple(pids) == chains.get("telegram"):
            self.telegram_alive = False
        if tuple(pids) == chains.get("backend"):
            self.backend_alive = False

    def prove_legacy_paper_quiescence(self):
        self.legacy_evidence_checks += 1
        if self.legacy_paper_blocker is not None:
            raise shutdown.SafeStopError(self.legacy_paper_blocker)

    def prove_box_upgrade(self, covered=()):
        self.box_upgrade_checks += 1
        self.box_upgrade_covered = tuple(covered)
        if isinstance(self.box_upgrade_proof, Exception):
            raise self.box_upgrade_proof
        return self.box_upgrade_proof

    def box_upgrade_guard(self, proof):
        assert proof == self.box_upgrade_proof
        self.box_upgrade_guards += 1
        if self.box_upgrade_guard_error is not None:
            raise self.box_upgrade_guard_error
        return nullcontext()

    def orchestrator(self):
        return shutdown.RuntimeShutdown(
            root=ROOT, env={}, get=lambda url, timeout: self.get(url, timeout),
            post=lambda url, payload, timeout: self.post(url, payload, timeout),
            robot_state=lambda: self.robot, stop_robot_fn=self.stop_robot,
            sleep=self.sleep, monotonic=lambda: self.now,
            legacy_resolver=lambda *args: self.resolve_legacy(*args),
            listener_probe=self.probe_listener,
            legacy_terminator=self.terminate_legacy,
            legacy_paper_quiescence=self.prove_legacy_paper_quiescence,
            legacy_paper_guard=lambda: nullcontext(),
            legacy_box_upgrade_proof=self.prove_box_upgrade,
            legacy_box_upgrade_guard=self.box_upgrade_guard,
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

    def test_unreachable_health_with_live_backend_listener_is_never_absent(self):
        runtime = LegacyEntryCoverageBridgeTests.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 63, "high_watermark": 64},
        })
        original_get = runtime.get
        health_calls = 0

        def delayed_health(url, timeout):
            nonlocal health_calls
            if url == BACKEND + "/api/health":
                health_calls += 1
                if health_calls == 1:
                    raise shutdown.Unreachable("owner queue timeout")
            return original_get(url, timeout)

        runtime.get = delayed_health
        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertGreaterEqual(health_calls, 2)
        self.assertIn("resolve:backend:127.0.0.1:8765", runtime.calls)
        self.assertIn("backend:legacy-starvation-terminate", result.steps)
        self.assertFalse(runtime.backend_alive)

    def test_unreachable_health_with_unowned_live_listener_blocks_false_absence(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.legacy_chains = {}
        original_get = runtime.get

        def dead_health(url, timeout):
            if url == BACKEND + "/api/health":
                raise shutdown.Unreachable("timeout")
            return original_get(url, timeout)

        runtime.get = dead_health
        result = runtime.orchestrator().run("all")

        self.assertFalse(result.ok)
        self.assertIn("listener is alive but exact ownership cannot be proven", result.message)
        self.assertTrue(runtime.backend_alive)

    def test_robot_needing_backend_authority_keeps_runtime_alive(self):
        for robot in (("ROBOT_STOPPED", "RECONCILIATION_REQUIRED"), ("ROBOT_WEIRD", "X")):
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
        self.assertEqual(runtime.calls, ["scanner:stop", "robot:stop", "protection:retire-entry-arms"])
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_robot_running_with_absent_backend_is_blocked_without_shutdown(self):
        runtime = FakeRuntime(robot=READY, backend=False)
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertEqual(runtime.calls, [])
        self.assertTrue(runtime.telegram_alive)


class ReconciliationShutdownTests(unittest.TestCase):
    def test_reconcile_then_canonical_stop_then_protection_then_shutdown(self):
        runtime = FakeRuntime(robot=RECON)
        original_get = runtime.get

        def get(url, timeout):
            if url == BACKEND + "/api/robot/protection-health":
                self.assertEqual(runtime.robot, STOPPED)
                runtime.calls.append("protection:quiescent")
            return original_get(url, timeout)

        runtime.get = get
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.runtime_stopped)
        self.assertEqual(runtime.calls, [
            "scanner:stop", "robot:reconcile", "robot:stop", "protection:quiescent",
            "telegram:shutdown", "backend:shutdown",
        ])
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_unresolved_or_failed_reconcile_keeps_runtime_alive(self):
        for reply, state in (
            ((409, {"ok": False, "success": False}), RECON),
            ((503, {"ok": False, "error": "robot_reconcile_unavailable"}), RECON),
            ((200, {"ok": True, "success": False}), RECON),
            ((200, {"ok": True, "success": True}), RECON),
            ((200, {"ok": True, "success": True}), STOPPED),
            ((200, {"ok": True, "success": True}), None),
        ):
            with self.subTest(reply=reply, state=state):
                runtime = FakeRuntime(robot=RECON)
                runtime.reconcile_reply, runtime.reconcile_state = reply, state
                self.assert_blocked_after_one_reconcile(runtime)

    def test_ambiguous_reconcile_is_not_retried_even_if_state_became_paused(self):
        for reply in (TimeoutError("timed out"), ConnectionError("lost response"),
                      (200, None), (200, {"ok": True}),
                      (200, {"ok": False, "success": True})):
            with self.subTest(reply=reply):
                runtime = FakeRuntime(robot=RECON)
                runtime.reconcile_reply = reply
                result = self.assert_blocked_after_one_reconcile(runtime)
                self.assertIn("not retried", result.message)

    def assert_blocked_after_one_reconcile(self, runtime):
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertFalse(result.runtime_stopped)
        self.assertEqual(runtime.calls, ["scanner:stop", "robot:reconcile"])
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
        self.assertIn("runtime kept alive", result.message)
        return result

    def test_recovered_robot_still_requires_normal_stop_and_protection_gates(self):
        for gate in ("stop", "protection"):
            with self.subTest(gate=gate):
                runtime = FakeRuntime(robot=RECON)
                if gate == "stop":
                    runtime.stop_robot = mock.Mock(side_effect=RobotControlRejected("open position"))
                else:
                    runtime.protection["covered_symbols"] = ["BTCUSDT"]
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls.count("robot:reconcile"), 1)
                self.assertFalse(any(c.startswith(("resolve", "terminate")) for c in runtime.calls))
                self.assertNotIn("telegram:shutdown", runtime.calls)
                self.assertNotIn("backend:shutdown", runtime.calls)
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)


class ShutdownArmFixture:
    """Real manager + HTTP handler + orchestrator; fake owner/hub, no runtime threads/network."""
    path = "/api/runtime/retire-entry-coverage"

    def __init__(self, robot=STOPPED):
        self.runtime = FakeRuntime(robot=robot)
        self.durable = {}
        self.store = mock.Mock()
        self.store.load_active_robot_candidate_states.return_value = ()
        self.store.load_active_paper_limits.return_value = ()
        self.store.load_open_position_projections.return_value = ()
        self.monitor = RobotBreakoutMonitor(
            lambda: self.store, TradingAccountId("paper"),
            get_closed_candle=lambda symbol: None, action_executor=mock.Mock(),
            tick_size_provider=lambda symbol: Decimal("0.01"), clock_ms=lambda: 1,
        )
        self.owner = SimpleNamespace(
            store=self.store, _robot_breakout_monitor=self.monitor,
            live_limit_acceptance_diagnostics=lambda: {"database_identity": IDENTITY},
            robot_runtime_state=lambda: SimpleNamespace(
                mode=self.runtime.robot[0], recovery_status=self.runtime.robot[1]),
            scanner_status=lambda: SimpleNamespace(mode="SCANNER_STOPPED"),
            robot_protection_coverage_symbols=lambda: tuple(self.durable),
            robot_protection_coverage_roles=lambda: dict(self.durable),
        )
        self.owner.robot_shutdown_idle_guard = lambda: PaperRuntime.robot_shutdown_idle_guard(self.owner)
        self.serialized = SimpleNamespace(call=lambda operation: operation(self.owner))
        self.hub = mock.Mock()
        self.hub.subscribe.side_effect = lambda symbol: mock.Mock(symbol=symbol)
        self.manager = RobotProtectionCoverageManager(self.hub, self.serialized)
        self.manager.arm_entry_coverage("AKEUSDT")
        self.manager.arm_entry_coverage("BLASTUSDT")
        original_get, original_post = self.runtime.get, self.runtime.post

        def get(url, timeout):
            if url == BACKEND + "/api/robot/protection-health":
                return 200, json.loads(json.dumps(self.manager.health()))
            return original_get(url, timeout)

        def post(url, payload, timeout):
            if url == BACKEND + self.path:
                self.runtime.calls.append("protection:retire-entry-arms")
                return self.request(payload)
            return original_post(url, payload, timeout)

        self.runtime.get, self.runtime.post = get, post

    def request(self, payload=None):
        payload = {"database_identity": IDENTITY} if payload is None else payload
        handler = object.__new__(PaperHttpHandler)
        handler.path = self.path
        handler.server = SimpleNamespace(robot_protection_coverage=self.manager)
        raw = json.dumps(payload).encode()
        handler.headers = {"Content-Length": str(len(raw))}
        handler.rfile = io.BytesIO(raw)
        replies = []
        handler._json_response = lambda status, body: replies.append((status, json.loads(json.dumps(body))))
        handler.do_POST()
        return replies[0]


class ShutdownArmRetirementTests(unittest.TestCase):
    def test_orphan_arms_retire_after_stop_and_full_shutdown_completes(self):
        for state in (STOPPED, READY, PAUSED, RECON):
            with self.subTest(state=state):
                f = ShutdownArmFixture(state)
                result = f.runtime.orchestrator().run("all")
                self.assertTrue(result.ok, result.message)
                expected = ["scanner:stop"]
                if state == RECON:
                    expected.append("robot:reconcile")
                if state != STOPPED:
                    expected.append("robot:stop")
                expected += ["protection:retire-entry-arms", "telegram:shutdown", "backend:shutdown"]
                self.assertEqual(f.runtime.calls, expected)
                self.assertEqual(f.manager.health()["armed_symbols"], ())
                self.assertEqual(f.manager.health()["covered_symbols"], ())
                self.assertEqual(f.hub.discard.call_count, 2)
                for call in f.hub.discard.call_args_list:
                    call.args[0].remove_update_listener.assert_called_once_with("robot-protection")
                    call.args[0].remove_disconnect_listener.assert_called_once_with("robot-protection")
                self.assertFalse(f.runtime.backend_alive or f.runtime.telegram_alive)
                # Clean repeat is idempotent and never invents a second recovery.
                self.assertEqual(f.request()[0], 200)
                self.assertEqual(f.hub.discard.call_count, 2)

    def test_durable_roles_block_retirement_without_losing_coverage(self):
        for role in ("EXPOSURE", "OBLIGATION", "ENTRY_PENDING"):
            with self.subTest(role=role):
                f = ShutdownArmFixture()
                f.durable["AKEUSDT"] = role
                before = f.manager.health()
                result = f.runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(f.manager.health(), before)
                f.hub.discard.assert_not_called()
                self.assertEqual(f.runtime.calls, ["scanner:stop", "protection:retire-entry-arms"])
                self.assertTrue(f.runtime.backend_alive and f.runtime.telegram_alive)

    def test_not_stopped_or_wrong_identity_rejected_before_arm_mutation(self):
        for state in (READY, PAUSED, RECON, ("ROBOT_STOPPED", "RECONCILIATION_REQUIRED")):
            with self.subTest(state=state):
                f = ShutdownArmFixture(state)
                self.assertEqual(f.request()[0], 409)
                self.assertEqual(len(f.manager.health()["armed_symbols"]), 2)
                f.hub.discard.assert_not_called()
        for payload, status in (({}, 400), ({"database_identity": "0" * 64}, 409),
                                ({"database_identity": IDENTITY, "force": True}, 400)):
            with self.subTest(payload=payload):
                f = ShutdownArmFixture()
                self.assertEqual(f.request(payload)[0], status)
                self.assertEqual(len(f.manager.health()["armed_symbols"]), 2)
                f.hub.discard.assert_not_called()

    def test_uncertain_entry_ownership_working_orders_or_unlinked_fill_block(self):
        for evidence in ("candidate", "order", "position", "unreadable"):
            with self.subTest(evidence=evidence):
                f = ShutdownArmFixture()
                if evidence == "candidate":
                    f.store.load_active_robot_candidate_states.return_value = (object(),)
                elif evidence == "order":
                    f.store.load_active_paper_limits.return_value = (object(),)
                elif evidence == "position":
                    f.store.load_open_position_projections.return_value = (
                        SimpleNamespace(position_key=SimpleNamespace(symbol=SimpleNamespace(value="AKEUSDT"))),)
                else:
                    f.store.load_active_paper_limits.side_effect = RuntimeError("unreadable")
                self.assertIn(f.request()[0], (409, 503))
                self.assertEqual(len(f.manager.health()["armed_symbols"]), 2)
                f.hub.discard.assert_not_called()

    def test_inflight_monitor_tick_blocks_retirement_without_wait_or_mutation(self):
        f = ShutdownArmFixture()
        entered, release = threading.Event(), threading.Event()
        def tick():
            entered.set()
            release.wait(5)
            return ()
        f.monitor._tick = tick
        thread = threading.Thread(target=f.monitor.tick)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(f.request()[0], 503)
            self.assertEqual(len(f.manager.health()["armed_symbols"]), 2)
            f.hub.discard.assert_not_called()
        finally:
            release.set()
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_timed_out_owner_callback_cannot_retire_arms_later(self):
        f = ShutdownArmFixture()
        pending = []
        calls = 0
        def call(operation):
            nonlocal calls
            calls += 1
            if calls == 2:
                pending.append(operation)
                raise TimeoutError("owner reply timed out")
            return operation(f.owner)
        f.serialized.call = call
        self.assertEqual(f.request()[0], 503)
        self.assertEqual(len(pending), 1)
        pending[0](f.owner)  # queued work finishes after the HTTP guard has exited
        self.assertEqual(len(f.manager.health()["armed_symbols"]), 2)
        f.hub.discard.assert_not_called()

    def test_strict_resync_failure_is_not_reported_as_quiescent(self):
        for failure in ("read", "discard"):
            with self.subTest(failure=failure):
                f = ShutdownArmFixture()
                if failure == "read":
                    reads = 0
                    def symbols():
                        nonlocal reads
                        reads += 1
                        if reads > 1:
                            raise RuntimeError("resync unavailable")
                        return ()
                    f.owner.robot_protection_coverage_symbols = symbols
                else:
                    f.hub.discard.side_effect = RuntimeError("unsubscribe unavailable")
                result = f.runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(f.runtime.calls, ["scanner:stop", "protection:retire-entry-arms"])
                self.assertTrue(f.manager.health()["covered_symbols"])
                self.assertTrue(f.runtime.backend_alive and f.runtime.telegram_alive)

    def test_ambiguous_transport_missing_endpoint_or_invalid_health_fails_closed_once(self):
        for reply in (TimeoutError("lost response"), (404, None), (503, {"ok": False}),
                      (200, {"ok": True}), (200, {"ok": True, "protection": {
                          "healthy": True, "covered_symbols": [], "armed_symbols": ["AKEUSDT"],
                          "unhealthy_symbols": {}}})):
            with self.subTest(reply=reply):
                f = ShutdownArmFixture()
                def request(payload):
                    if isinstance(reply, Exception):
                        raise reply
                    return reply
                f.request = request
                result = f.runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(f.runtime.calls, ["scanner:stop", "protection:retire-entry-arms"])
                self.assertTrue(f.runtime.backend_alive and f.runtime.telegram_alive)
                f.hub.discard.assert_not_called()



class LegacyEntryCoverageBridgeTests(unittest.TestCase):
    @staticmethod
    def stale_arm_runtime(status=404):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.retire_reply = (status, None)
        runtime.legacy_paper_blocker = None
        runtime.protection.update({
            "covered_symbols": ["AKEUSDT", "BLASTUSDT"],
            "armed_symbols": ["AKEUSDT", "BLASTUSDT"],
            "coverage_roles": {"AKEUSDT": "ENTRY_PENDING", "BLASTUSDT": "ENTRY_PENDING"},
        })
        runtime.legacy_chains = {"backend": (130, 120, 110, 105)}
        return runtime

    def test_old_backend_without_retire_endpoint_stops_once_after_full_proof(self):
        for status in (404, 501):
            with self.subTest(status=status):
                runtime = self.stale_arm_runtime(status)
                result = runtime.orchestrator().run("all")
                self.assertTrue(result.ok, result.message)
                self.assertTrue(result.runtime_stopped)
                self.assertEqual(result.steps, (
                    "scanner:stop", "protection:legacy-entry-proof",
                    "telegram:shutdown", "backend:legacy-terminate",
                ))
                self.assertEqual(runtime.calls, [
                    "scanner:stop", "protection:retire-entry-arms",
                    "resolve:backend:127.0.0.1:8765", "telegram:shutdown",
                    "resolve:backend:127.0.0.1:8765",
                    "terminate:[130, 120, 110, 105]",
                ])
                self.assertEqual(runtime.legacy_evidence_checks, 1)
                self.assertFalse(runtime.backend_alive or runtime.telegram_alive)
                self.assertNotIn("backend:shutdown", runtime.calls)

    def test_durable_live_ownership_blocks_legacy_termination(self):
        for blocker in (
            "legacy PAPER shutdown blocked by OPEN Robot candidates",
            "legacy PAPER shutdown blocked by open Robot trades",
            "legacy PAPER shutdown blocked by working PAPER limits",
            "legacy PAPER shutdown blocked by open PAPER exposure",
            "legacy PAPER shutdown blocked by unresolved protection obligations",
        ):
            with self.subTest(blocker=blocker):
                runtime = self.stale_arm_runtime()
                runtime.legacy_paper_blocker = blocker
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertIn(blocker, result.message)
                self.assertEqual(
                    runtime.calls, ["scanner:stop", "protection:retire-entry-arms"],
                )
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
                self.assertFalse(any(c.startswith(("resolve", "terminate")) for c in runtime.calls))

    def test_ingress_overflow_on_only_stale_temporary_arms_can_shutdown_legacy_backend(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
        })

        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.runtime_stopped)
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)
        self.assertIn("backend:legacy-terminate", result.steps)

    def test_saturated_legacy_owner_queue_bypasses_scanner_call_after_full_durable_proof(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {
                "capacity": 64,
                "current_pending": 63,
                "high_watermark": 64,
            },
        })

        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.runtime_stopped)
        self.assertEqual(result.steps, (
            "runtime:legacy-starvation-proof",
            "telegram:shutdown",
            "backend:legacy-starvation-terminate",
        ))
        self.assertNotIn("scanner:stop", runtime.calls)
        self.assertEqual(runtime.legacy_evidence_checks, 1)
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_starvation_trigger_may_recover_before_final_termination(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {
                "capacity": 64,
                "current_pending": 63,
                "high_watermark": 64,
            },
        })
        original_post = runtime.post

        def post(url, payload, timeout):
            reply = original_post(url, payload, timeout)
            if url == TELEGRAM + "/shutdown" and reply[0] == 200:
                runtime.protection.update({
                    "healthy": True,
                    "unhealthy_symbols": {},
                    "ingress": {
                        "capacity": 64,
                        "current_pending": 0,
                        "high_watermark": 64,
                    },
                })
            return reply

        runtime.post = post
        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.runtime_stopped)
        self.assertEqual(result.steps, (
            "runtime:legacy-starvation-proof",
            "telegram:shutdown",
            "backend:legacy-starvation-terminate",
        ))
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_starvation_path_still_blocks_if_temporary_coverage_shape_changes(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {
                "capacity": 64,
                "current_pending": 63,
                "high_watermark": 64,
            },
        })
        original_post = runtime.post

        def post(url, payload, timeout):
            reply = original_post(url, payload, timeout)
            if url == TELEGRAM + "/shutdown" and reply[0] == 200:
                runtime.protection.update({
                    "healthy": True,
                    "unhealthy_symbols": {},
                    "coverage_roles": {
                        "AKEUSDT": "ENTRY_PENDING",
                        "BLASTUSDT": "POSITION",
                    },
                })
            return reply

        runtime.post = post
        result = runtime.orchestrator().run("all")

        self.assertFalse(result.ok)
        self.assertIn("not stale temporary ENTRY_PENDING coverage", result.message)
        self.assertTrue(runtime.backend_alive)
        self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

    def test_starvation_path_retries_transient_legacy_health_reproof(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 63, "high_watermark": 64},
        })
        original_get = runtime.get
        health_calls = 0

        def flaky_get(url, timeout):
            nonlocal health_calls
            if url == BACKEND + "/api/health":
                health_calls += 1
                if health_calls == 2:
                    raise shutdown.Unreachable("owner queue timeout")
            return original_get(url, timeout)

        runtime.get = flaky_get
        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertGreaterEqual(health_calls, 3)
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_starvation_path_retries_503_owner_unavailable_health_reproof(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 63, "high_watermark": 64},
        })
        original_get = runtime.get
        health_calls = 0

        def flaky_get(url, timeout):
            nonlocal health_calls
            if url == BACKEND + "/api/health":
                health_calls += 1
                if health_calls == 2:
                    return 503, {"ok": False, "error": "paper_runtime_unavailable"}
            return original_get(url, timeout)

        runtime.get = flaky_get
        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertGreaterEqual(health_calls, 3)
        self.assertFalse(runtime.backend_alive or runtime.telegram_alive)

    def test_legacy_health_reproof_timeout_stays_fail_closed(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 64, "high_watermark": 64},
        })
        original_get = runtime.get
        health_calls = 0

        def unavailable_after_initial_probe(url, timeout):
            nonlocal health_calls
            if url == BACKEND + "/api/health":
                health_calls += 1
                if health_calls >= 2:
                    raise shutdown.Unreachable("owner queue timeout")
            return original_get(url, timeout)

        runtime.get = unavailable_after_initial_probe
        result = runtime.orchestrator().run("all")

        self.assertFalse(result.ok)
        self.assertIn("identity re-proof timed out", result.message)
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
        self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

    def test_legacy_health_identity_mismatch_is_not_retried(self):
        runtime = self.stale_arm_runtime()
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 64, "high_watermark": 64},
        })
        original_get = runtime.get
        health_calls = 0

        def changed_identity(url, timeout):
            nonlocal health_calls
            if url == BACKEND + "/api/health":
                health_calls += 1
                if health_calls == 2:
                    changed = dict(runtime.backend_health)
                    changed["database_identity"] = "other-db"
                    return 200, changed
            return original_get(url, timeout)

        runtime.get = changed_identity
        result = runtime.orchestrator().run("all")

        self.assertFalse(result.ok)
        self.assertIn("identity changed", result.message)
        self.assertEqual(health_calls, 2)
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
        self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

    def test_starvation_bypass_requires_robot_already_stopped(self):
        runtime = self.stale_arm_runtime()
        runtime.robot = READY
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 64, "high_watermark": 64},
        })

        result = runtime.orchestrator().run("all")

        self.assertTrue(result.ok, result.message)
        self.assertIn("scanner:stop", runtime.calls)
        self.assertIn("robot:stop", runtime.calls)
        self.assertNotIn("runtime:legacy-starvation-proof", result.steps)

    def test_starvation_bypass_requires_proven_capacity_saturation(self):
        for ingress in (
            None,
            {"capacity": 64, "current_pending": 63, "high_watermark": 63},
            {"capacity": 0, "current_pending": 0, "high_watermark": 64},
        ):
            with self.subTest(ingress=ingress):
                runtime = self.stale_arm_runtime()
                runtime.protection.update({
                    "healthy": False,
                    "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
                })
                if ingress is not None:
                    runtime.protection["ingress"] = ingress

                result = runtime.orchestrator().run("all")

                self.assertTrue(result.ok, result.message)
                self.assertIn("scanner:stop", runtime.calls)
                self.assertNotIn("runtime:legacy-starvation-proof", result.steps)

    def test_starvation_bypass_still_rejects_durable_robot_work(self):
        runtime = self.stale_arm_runtime()
        runtime.legacy_paper_blocker = "legacy PAPER shutdown blocked by working PAPER limits"
        runtime.protection.update({
            "healthy": False,
            "unhealthy_symbols": {"AKEUSDT": "ingress_overflow"},
            "ingress": {"capacity": 64, "current_pending": 64, "high_watermark": 64},
        })

        result = runtime.orchestrator().run("all")

        self.assertFalse(result.ok)
        self.assertIn("working PAPER limits", result.message)
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
        self.assertFalse(any(c.startswith("terminate") for c in runtime.calls))

    def test_only_exact_temporary_entry_shape_is_eligible_for_legacy_bridge(self):
        cases = (
            {"armed_symbols": ["AKEUSDT"]},
            {"coverage_roles": {"AKEUSDT": "EXPOSURE", "BLASTUSDT": "ENTRY_PENDING"}},
            {"unhealthy_symbols": {"AKEUSDT": "subscribe_failed"}, "healthy": False},
            {"unhealthy_symbols": {"OTHERUSDT": "ingress_overflow"}, "healthy": False},
            {"unhealthy_symbols": {"AKEUSDT": "ingress_overflow"}, "healthy": True},
            {"unhealthy_symbols": {}, "healthy": False},
        )
        for override in cases:
            with self.subTest(override=override):
                runtime = self.stale_arm_runtime()
                runtime.protection.update(override)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)
                self.assertFalse(any(c.startswith(("resolve", "terminate")) for c in runtime.calls))


class LegacyPaperQuiescenceTests(unittest.TestCase):
    @staticmethod
    def make_db(path: Path, blocker: str | None = None) -> None:
        connection = sqlite3.connect(path)
        try:
            connection.executescript(
                """
                CREATE TABLE robot_candidates (
                    trading_account_id TEXT NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE robot_trades (
                    trading_account_id TEXT NOT NULL, symbol TEXT NOT NULL, exit_time_ms INTEGER
                );
                CREATE TABLE paper_limit_orders (
                    trading_account_id TEXT NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE position_projections (
                    trading_account_id TEXT NOT NULL, category TEXT NOT NULL,
                    symbol TEXT NOT NULL, position_idx INTEGER NOT NULL,
                    side TEXT NOT NULL, quantity TEXT NOT NULL
                );
                CREATE TABLE paper_protection_obligations (
                    trading_account_id TEXT NOT NULL, status TEXT NOT NULL
                );
                """
            )
            if blocker == "approved_candidate":
                connection.execute(
                    "INSERT INTO robot_candidates VALUES ('paper', 'ROBOTUSDT', 'APPROVED')"
                )
            elif blocker == "open_candidate":
                connection.execute(
                    "INSERT INTO robot_candidates VALUES ('paper', 'ROBOTUSDT', 'OPEN')"
                )
            elif blocker == "trade":
                connection.execute(
                    "INSERT INTO robot_trades VALUES ('paper', 'ROBOTUSDT', NULL)"
                )
            elif blocker == "limit":
                connection.execute(
                    "INSERT INTO paper_limit_orders VALUES ('paper', 'LIMITUSDT', 'open')"
                )
            elif blocker == "manual_exposure":
                connection.execute(
                    "INSERT INTO position_projections VALUES "
                    "('paper', 'linear', 'MANUALUSDT', 0, 'Long', '1')"
                )
            elif blocker == "approved_exposure":
                connection.execute(
                    "INSERT INTO robot_candidates VALUES ('paper', 'ROBOTUSDT', 'APPROVED')"
                )
                connection.execute(
                    "INSERT INTO position_projections VALUES "
                    "('paper', 'linear', 'ROBOTUSDT', 0, 'Long', '1')"
                )
            elif blocker == "obligation":
                connection.execute(
                    "INSERT INTO paper_protection_obligations VALUES ('paper', 'LATCHED')"
                )
            connection.commit()
        finally:
            connection.close()

    def test_read_only_durable_proof_accepts_inert_approved_and_manual_exposure(self):
        with tempfile.TemporaryDirectory() as directory:
            for state in ("approved_candidate", "manual_exposure"):
                with self.subTest(state=state):
                    path = Path(directory) / f"{state}.sqlite3"
                    self.make_db(path, state)
                    shutdown.prove_legacy_paper_quiescence(path)

    def test_read_only_durable_proof_rejects_live_or_ambiguous_robot_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            clean = Path(directory) / "clean.sqlite3"
            self.make_db(clean)
            shutdown.prove_legacy_paper_quiescence(clean)
            for blocker, phrase in (
                ("open_candidate", "OPEN Robot candidates: ROBOTUSDT"),
                ("trade", "open Robot trades: ROBOTUSDT"),
                ("limit", "working PAPER limits"),
                ("approved_exposure", "pending Robot exposure: ROBOTUSDT"),
                ("obligation", "unresolved protection obligations"),
            ):
                with self.subTest(blocker=blocker):
                    path = Path(directory) / f"{blocker}.sqlite3"
                    self.make_db(path, blocker)
                    with self.assertRaisesRegex(shutdown.SafeStopError, phrase):
                        shutdown.prove_legacy_paper_quiescence(path)


    def test_final_guard_blocks_competing_writes_without_editing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guard.sqlite3"
            self.make_db(path)
            with shutdown.hold_legacy_paper_quiescence(path):
                competitor = sqlite3.connect(path, timeout=0.0)
                try:
                    with self.assertRaises(sqlite3.OperationalError):
                        competitor.execute(
                            "INSERT INTO robot_candidates VALUES ('paper', 'RACEUSDT', 'APPROVED')"
                        )
                finally:
                    competitor.close()
            verify = sqlite3.connect(path)
            try:
                self.assertEqual(
                    verify.execute("SELECT COUNT(*) FROM robot_candidates").fetchone()[0], 0,
                )
            finally:
                verify.close()


    def test_final_guard_uses_bounded_writer_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guard.sqlite3"
            self.make_db(path)
            real_connect = sqlite3.connect
            with mock.patch.object(
                shutdown.sqlite3, "connect", wraps=real_connect,
            ) as connect:
                with shutdown.hold_legacy_paper_quiescence(path):
                    pass

            self.assertEqual(
                connect.call_args.kwargs["timeout"],
                shutdown.LEGACY_WRITER_BARRIER_TIMEOUT_S,
            )
            self.assertGreater(shutdown.LEGACY_WRITER_BARRIER_TIMEOUT_S, 0)
            self.assertLessEqual(shutdown.LEGACY_WRITER_BARRIER_TIMEOUT_S, 5.0)


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

    def test_unprovable_legacy_owner_fails_closed_without_terminate(self):
        for status in (404, 501):
            with self.subTest(status=status):
                runtime = FakeRuntime(robot=STOPPED)
                runtime.shutdown_replies["telegram"] = (status, None)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertIn("nothing was terminated", result.message)
                self.assertNotIn("close its window", result.message)
                self.assertFalse(any(c.startswith("terminate") for c in runtime.calls))
                self.assertNotIn("backend:shutdown", runtime.calls)
                self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

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
                          "_exit(", "stop-process"):
            self.assertNotIn(forbidden, source)
        fallback = Path(legacy.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("/im", '"/t"', "os.kill", "psutil", "stop-process", "killall", "pkill",
                          "_exit(", "get-process", "win32_process\"", "shell=true"):
            self.assertNotIn(forbidden, fallback)
        self.assertEqual(fallback.count("taskkill"), 1)  # only the exact /PID call

    def test_exact_pid_termination_uses_one_pid_per_call_without_tree_or_name(self):
        with mock.patch.object(legacy.subprocess, "run") as run:
            legacy.terminate_exact_pids((4321, 1234))
        self.assertEqual(
            [c.args[0] for c in run.call_args_list],
            [["taskkill", "/PID", "4321", "/F"], ["taskkill", "/PID", "1234", "/F"]],
        )
        for c in run.call_args_list:
            self.assertNotIn("shell", c.kwargs)


def _p(pid, ppid, name, command_line, executable="", created=None):
    return ProcessInfo(pid, ppid, name, command_line, executable, created if created is not None else pid)


VENV_PY = str(ROOT / "venv" / "Scripts" / "python.exe")
BASE_PY = r"C:\Users\owner\AppData\Local\Programs\Python\Python312\python.exe"
BAT = str(ROOT / "start_paper_backend.bat")
TG = str(ROOT / "telegram_monitoring.py")


def _backend_cmd_k_shape():
    # P0.5 bootstrap: cmd.exe /k start_paper_backend.bat -> venv redirector -> base Python.
    return {
        10: _p(10, 1, "cmd.exe", f"cmd.exe /k {BAT}"),
        20: _p(20, 10, "python.exe", f'"{VENV_PY}" -m terminal.runtime.paper_http_server', VENV_PY),
        30: _p(30, 20, "python.exe", f'"{BASE_PY}" -m terminal.runtime.paper_http_server', BASE_PY),
    }


def _backend_powershell_shape():
    # Pre-P0.5 launcher: powershell -NoExit -> cmd /c bat -> venv redirector -> base Python.
    processes = _backend_cmd_k_shape()
    processes[5] = _p(5, 1, "powershell.exe",
                      f"powershell.exe -NoExit -Command \"Set-Location '{ROOT}\\'; & '{BAT}'\"")
    processes[10] = _p(10, 5, "cmd.exe", f'C:\\WINDOWS\\system32\\cmd.exe /c ""{BAT}""')
    return processes


def _backend_runtime_intent_shape():
    # Current tools.runtime_intent: CREATE_NEW_CONSOLE + cmd.exe /c start_paper_backend.bat.
    return {
        10: _p(10, 1, "cmd.exe", f'cmd.exe /c "{BAT}"'),
        20: _p(20, 10, "python.exe", f'"{VENV_PY}" -m terminal.runtime.paper_http_server', VENV_PY),
        30: _p(30, 20, "python.exe", f'"{BASE_PY}" -m terminal.runtime.paper_http_server', BASE_PY),
    }


def _telegram_cmd_k_shape():
    return {
        10: _p(10, 1, "cmd.exe", f"cmd.exe /k {VENV_PY} {TG}"),
        20: _p(20, 10, "python.exe", f'"{VENV_PY}" {TG}', VENV_PY),
        30: _p(30, 20, "python.exe", f'"{BASE_PY}" {TG}', BASE_PY),
    }


def _telegram_powershell_shape():
    processes = _telegram_cmd_k_shape()
    processes[10] = _p(10, 1, "powershell.exe",
                       f"powershell.exe -NoExit -Command \"Set-Location '{ROOT}\\'; & '{VENV_PY}' '{TG}'\"")
    return processes


def _telegram_runtime_intent_shape():
    # Current tools.runtime_intent: CREATE_NEW_CONSOLE + cmd.exe /c venv-python telegram_monitoring.py.
    return {
        10: _p(10, 1, "cmd.exe", f'cmd.exe /c "{VENV_PY}" "{TG}"'),
        20: _p(20, 10, "python.exe", f'"{VENV_PY}" "{TG}"', VENV_PY),
        30: _p(30, 20, "python.exe", f'"{BASE_PY}" "{TG}"', BASE_PY),
    }


class LegacyOwnershipProofTests(unittest.TestCase):
    def test_listener_probe_distinguishes_empty_and_live_exact_port(self):
        with mock.patch.object(legacy.os, "name", "nt"), \
                mock.patch.object(legacy, "_query_listener_chain", return_value=([], {})):
            self.assertEqual(legacy.probe_listener_pids("127.0.0.1", 8765), ())
        with mock.patch.object(legacy.os, "name", "nt"), \
                mock.patch.object(legacy, "_query_listener_chain", return_value=([700, 700], {})):
            self.assertEqual(legacy.probe_listener_pids("127.0.0.1", 8765), (700,))

    def test_current_legacy_console_shapes_prove_exact_chains(self):
        self.assertEqual(select_legacy_chain("backend", [30], _backend_cmd_k_shape(), ROOT), (30, 20, 10))
        self.assertEqual(
            select_legacy_chain("backend", [30], _backend_powershell_shape(), ROOT), (30, 20, 10, 5),
        )
        self.assertEqual(
            select_legacy_chain("backend", [30], _backend_runtime_intent_shape(), ROOT), (30, 20, 10),
        )
        self.assertEqual(select_legacy_chain("telegram", [30], _telegram_cmd_k_shape(), ROOT), (30, 20, 10))
        self.assertEqual(
            select_legacy_chain("telegram", [30], _telegram_powershell_shape(), ROOT), (30, 20, 10),
        )
        self.assertEqual(
            select_legacy_chain("telegram", [30], _telegram_runtime_intent_shape(), ROOT), (30, 20, 10),
        )

    def test_wrong_command_line_is_unproven(self):
        cases = []
        backend = _backend_cmd_k_shape()
        backend[30] = _p(30, 20, "python.exe", f'"{BASE_PY}" -m some.other.module', BASE_PY)
        cases.append(("backend", backend))
        telegram = _telegram_cmd_k_shape()
        telegram[30] = _p(30, 20, "python.exe", f'"{BASE_PY}" {ROOT / "main.py"}', BASE_PY)
        cases.append(("telegram", telegram))
        no_k = _backend_cmd_k_shape()
        no_k[10] = _p(10, 1, "cmd.exe", f"cmd.exe /s {BAT}")
        cases.append(("backend", no_k))
        wrong_cmd_c_backend = _backend_runtime_intent_shape()
        wrong_cmd_c_backend[10] = _p(10, 1, "cmd.exe", f"cmd.exe /c {ROOT / 'other_backend.bat'}")
        cases.append(("backend", wrong_cmd_c_backend))
        wrong_cmd_c_telegram = _telegram_runtime_intent_shape()
        wrong_cmd_c_telegram[10] = _p(10, 1, "cmd.exe", f"cmd.exe /c {TG}")
        cases.append(("telegram", wrong_cmd_c_telegram))
        not_noexit = _telegram_powershell_shape()
        not_noexit[10] = _p(10, 1, "powershell.exe", f"powershell.exe -Command \"& '{VENV_PY}' '{TG}'\"")
        cases.append(("telegram", not_noexit))
        foreign_parent = _backend_cmd_k_shape()
        foreign_parent[10] = _p(10, 1, "explorer.exe", BAT)
        cases.append(("backend", foreign_parent))
        for kind, processes in cases:
            with self.subTest(kind=kind, owner=processes[10].command_line):
                with self.assertRaises(LegacyOwnerUnproven):
                    select_legacy_chain(kind, [30], processes, ROOT)

    def test_wrong_project_root_is_unproven(self):
        other = Path(str(ROOT) + "-runtime-intent")
        for kind, shape in (("backend", _backend_cmd_k_shape), ("telegram", _telegram_cmd_k_shape)):
            with self.subTest(kind=kind):
                with self.assertRaises(LegacyOwnerUnproven):
                    select_legacy_chain(kind, [30], shape(), other)

    def test_ambiguous_listener_or_reused_ancestor_pid_is_unproven(self):
        for listeners in ([], [30, 31]):
            with self.subTest(listeners=listeners):
                with self.assertRaises(LegacyOwnerUnproven):
                    select_legacy_chain("backend", listeners, _backend_cmd_k_shape(), ROOT)
        reused = _backend_cmd_k_shape()
        reused[10] = _p(10, 1, "cmd.exe", f"cmd.exe /k {BAT}", created=999)
        with self.assertRaises(LegacyOwnerUnproven):
            select_legacy_chain("backend", [30], reused, ROOT)

    def test_resolver_is_unavailable_off_windows_or_off_localhost(self):
        with mock.patch.object(legacy.os, "name", "posix"), \
                mock.patch.object(legacy.subprocess, "run") as run:
            with self.assertRaises(LegacyOwnerUnproven):
                legacy.resolve_legacy_chain("backend", "127.0.0.1", 8765, ROOT)
        run.assert_not_called()
        with mock.patch.object(legacy.os, "name", "nt"), \
                mock.patch.object(legacy.subprocess, "run") as run:
            with self.assertRaises(LegacyOwnerUnproven):
                legacy.resolve_legacy_chain("backend", "0.0.0.0", 8765, ROOT)
        run.assert_not_called()


class LegacyFallbackOrchestrationTests(unittest.TestCase):
    def test_legacy_telegram_then_backend_exact_chains_are_terminated_in_order(self):
        for telegram_status, backend_status in ((501, 404), (501, 501)):
            with self.subTest(telegram=telegram_status, backend=backend_status):
                runtime = FakeRuntime(robot=READY)
                runtime.shutdown_replies = {"telegram": (telegram_status, None),
                                            "backend": (backend_status, {"ok": False})}
                runtime.legacy_chains = {"telegram": (30, 20, 10), "backend": (130, 120, 110, 105)}
                result = runtime.orchestrator().run("all")
                self.assertTrue(result.ok, result.message)
                self.assertEqual(runtime.calls, [
                    "scanner:stop", "robot:stop",
                    "telegram:shutdown", "resolve:telegram:127.0.0.1:8766", "terminate:[30, 20, 10]",
                    "backend:shutdown", "resolve:backend:127.0.0.1:8765", "terminate:[130, 120, 110, 105]",
                ])
                self.assertEqual(result.steps[-2:], ("telegram:legacy-terminate", "backend:legacy-terminate"))
                self.assertFalse(runtime.telegram_alive or runtime.backend_alive)

    def test_legacy_telegram_with_graceful_backend(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.shutdown_replies = {"telegram": (501, None)}
        runtime.legacy_chains = {"telegram": (30, 20, 10)}
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(runtime.calls[-2:], ["terminate:[30, 20, 10]", "backend:shutdown"])

    def test_non_legacy_refusals_never_reach_the_fallback(self):
        for reply in ((409, {"ok": False, "error": "database_identity_mismatch"}),
                      (500, None), (400, {"ok": False}), TimeoutError("timed out")):
            with self.subTest(reply=reply):
                runtime = FakeRuntime(robot=STOPPED)
                runtime.legacy_chains = {"telegram": (30, 20, 10), "backend": (130, 120, 110)}
                original = runtime.post

                def post(url, payload, timeout, reply=reply, original=original):
                    if url == TELEGRAM + "/shutdown":
                        runtime.calls.append("telegram:shutdown")
                        if isinstance(reply, Exception):
                            raise reply
                        return reply
                    return original(url, payload, timeout)

                runtime.post = post
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertFalse(any(c.startswith(("resolve", "terminate")) for c in runtime.calls))
                self.assertTrue(runtime.telegram_alive and runtime.backend_alive)

    def test_identity_mismatch_never_reaches_resolver_or_terminator(self):
        for target in ("backend", "telegram"):
            with self.subTest(target=target):
                runtime = FakeRuntime(robot=STOPPED)
                runtime.legacy_chains = {"telegram": (30,), "backend": (130,)}
                runtime.shutdown_replies = {"telegram": (404, None), "backend": (404, None)}
                getattr(runtime, f"{target}_health")["database_identity"] = "0" * 64
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls, [])

    def test_graceful_endpoints_are_preferred_and_never_invoke_fallback(self):
        runtime = FakeRuntime(robot=READY)
        runtime.legacy_chains = {"telegram": (30,), "backend": (130,)}
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok)
        self.assertFalse(any(c.startswith(("resolve", "terminate")) for c in runtime.calls))
        self.assertEqual(result.steps[-2:], ("telegram:shutdown", "backend:shutdown"))

    def test_legacy_process_that_survives_termination_is_reported(self):
        runtime = FakeRuntime(robot=STOPPED)
        runtime.shutdown_replies = {"telegram": (501, None)}
        runtime.legacy_chains = {"telegram": (30, 20, 10)}
        runtime.terminate_legacy = lambda pids: runtime.calls.append(f"terminate:{list(pids)}")
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("did not exit", result.message)
        self.assertNotIn("backend:shutdown", runtime.calls)


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
        stream = io.StringIO()
        with mock.patch.object(shutdown.RuntimeShutdown, "run", return_value=blocked), \
                mock.patch("sys.stdout", stream):
            self.assertEqual(shutdown.main([]), 1)
        output = stream.getvalue()
        self.assertIn("[STOP] starting scope=all", output)
        self.assertIn("STOP BLOCKED: Robot is busy", output)
        self.assertIn("steps=", output)
        self.assertEqual(shutdown.owner_text(blocked), "⛔ Остановка не выполнена: Robot is busy")

    def test_unexpected_cli_crash_is_printed_and_nonzero(self):
        stream = io.StringIO()
        with mock.patch.object(shutdown.RuntimeShutdown, "run", side_effect=RuntimeError("boom")), \
                mock.patch("sys.stdout", stream):
            self.assertEqual(shutdown.main([]), 2)
        output = stream.getvalue()
        self.assertIn("[STOP CRASH] RuntimeError: boom", output)
        self.assertIn("Traceback", output)

    def test_desktop_wrapper_runs_full_scope_module(self):
        launcher = (ROOT / "stop_robot_runtime.bat").read_text()
        self.assertIn('"%~dp0venv\\Scripts\\python.exe" -m tools.stop_robot_runtime', launcher)


# --- Legacy pre-v26 backend: pristine Box upgrade shutdown ------------------------------

PRISTINE_SYMBOLS = ("AVNTUSDT", "NEARUSDT")
LEGACY_REASON_PREFIX = "reconcile_robot could not prove pending Robot entry safety: "


def _box_snapshot(symbol, a_time_ms=1000):
    from tests.test_box_plan_persistence import snapshot

    data = snapshot()
    data["identity"]["symbol"] = symbol
    data["identity"]["a_time_ms"] = a_time_ms
    return data


class LegacyBoxUpgradeDb:
    """A real SQLiteStore DB in the AVNT/NEAR deadlock shape, rewound to schema v25.

    Pristine APPROVED / BOX_ENTRY_READY Box candidates that failed ownership on the
    pre-v26 backend, Robot ROBOT_RUNNING / RECONCILIATION_REQUIRED naming them.
    """

    def __init__(self, path: Path):
        from terminal.persistence.sqlite_store import SQLiteStore

        self.path = path
        self.account = TradingAccountId("paper")
        self.store = SQLiteStore.open(path)
        self.robot_ids = {}
        for symbol in PRISTINE_SYMBOLS:
            source, _ = self.store.save_box_plan_only(
                snapshot=_box_snapshot(symbol), created_at_ms=3001,
            )
            candidate, _ = self.store.handoff_box_plan_to_robot(
                source.candidate_id, symbol=source.symbol,
                expected_snapshot_sha256=source.snapshot_sha256, approved_at_ms=3002,
            )
            self.robot_ids[symbol] = candidate.candidate_id
            self.set_execution(symbol, {
                "last_execution_error": shutdown.LEGACY_BOX_PRISTINE_ERROR,
                "last_attempt_at_ms": 3500, "attempt_count": 4,
            })
        self.store.initialize_scanner_runtime_state(self.account, updated_at_ms=1)
        self.set_robot("ROBOT_RUNNING", "RECONCILIATION_REQUIRED", self.reason())

    def reason(self, ids=None):
        return LEGACY_REASON_PREFIX + ",".join(sorted(ids or self.robot_ids.values()))

    def set_execution(self, symbol, execution):
        candidate = self.store.get_robot_candidate(self.robot_ids[symbol])
        state = {**candidate.robot_state, "execution": execution}
        with self.store._transaction():
            self.store._connection.execute(
                "UPDATE robot_candidates SET robot_state_json=? WHERE candidate_id=?",
                (json.dumps(state), candidate.candidate_id),
            )

    def set_robot(self, mode, recovery_status, reason):
        state = (self.store.get_robot_runtime_state(self.account)
                 or self.store.initialize_robot_runtime_state(self.account, updated_at_ms=1))
        self.store.update_robot_runtime_state(
            self.account, mode=mode, recovery_status=recovery_status, reason=reason,
            expected_version=state.version, updated_at_ms=state.updated_at_ms + 1,
        )

    def finish(self, schema_version=25):
        self.store.close()
        connection = sqlite3.connect(self.path)
        try:
            connection.execute(f"PRAGMA user_version = {schema_version}")
        finally:
            connection.close()


class LegacyBoxUpgradeProofTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.count = 0

    def db(self):
        self.count += 1
        db = LegacyBoxUpgradeDb(self.directory / f"paper-{self.count}.sqlite3")
        self.addCleanup(lambda: db.store._connection is None or db.store.close())
        return db

    def assert_blocked(self, db, phrase, **finish):
        db.finish(**finish)
        with self.assertRaisesRegex(shutdown.SafeStopError, phrase):
            shutdown.prove_legacy_box_upgrade(db.path)

    def test_pristine_avnt_near_deadlock_is_proven_upgrade_safe(self):
        db = self.db()
        db.finish()
        proof = shutdown.prove_legacy_box_upgrade(db.path)
        self.assertEqual(proof.candidate_ids, tuple(sorted(db.robot_ids.values())))
        self.assertEqual(proof.symbols, PRISTINE_SYMBOLS)
        self.assertEqual(proof.schema_version, 25)
        with shutdown.hold_legacy_box_upgrade(db.path, proof):
            pass

    def test_current_schema_backend_is_not_legacy(self):
        from terminal.persistence.schema import SCHEMA_VERSION

        self.assert_blocked(self.db(), "not a legacy pre-v26", schema_version=SCHEMA_VERSION)

    def test_any_execution_blocks(self):
        from terminal.domain.models import (
            Category, Execution, ExecutionDedupKey, ExecutionId, OrderId, OrderSide, Price,
            Quantity, Symbol,
        )

        db = self.db()
        with db.store._transaction():
            db.store._insert_execution(Execution(
                ExecutionDedupKey(db.account, Category.LINEAR, ExecutionId("x1")), OrderId("o1"),
                Symbol("AVNTUSDT"), OrderSide.BUY, Price(Decimal("1")), Quantity(Decimal("1")),
                Decimal("0"), 10,
            ))
        self.assert_blocked(db, "AVNTUSDT.*executions")

    def test_any_position_projection_blocks_even_flat(self):
        from terminal.domain.models import (
            Category, Notional, PositionKey, PositionSide, Price, Quantity, Symbol,
        )
        from terminal.persistence.sqlite_store import PositionProjectionUpdate

        for side, quantity, sync in ((PositionSide.FLAT, "0", "synced"),
                                     (PositionSide.LONG, "1", "reconciliation_required")):
            with self.subTest(side=side):
                db = self.db()
                key = PositionKey(db.account, Category.LINEAR, Symbol("NEARUSDT"), 0)
                qty = Decimal(quantity)
                with db.store._transaction():
                    db.store._write_projection(PositionProjectionUpdate(
                        key, side, Quantity(qty), Price(Decimal("1")) if qty else None,
                        Decimal(0), Decimal(0), Notional(qty), sync, None, 10,
                    ))
                self.assert_blocked(db, "NEARUSDT.*position projection|pending Robot exposure")

    def test_active_limit_or_box_ownership_blocks(self):
        from terminal.domain.models import OrderId, OrderSide, Symbol

        db = self.db()
        db.store.create_paper_limit(
            client_action_id="m", request_fingerprint="m-fp", order_id=OrderId("m-1"),
            order_link_id="m-link", trading_account_id=db.account, symbol=Symbol("AVNTUSDT"),
            side=OrderSide.BUY, price=Decimal("1"), quantity=Decimal("1"), created_at_ms=10,
        )
        self.assert_blocked(db, "working PAPER limits|AVNTUSDT.*PAPER limit")

        db = self.db()
        source = db.store.get_robot_candidate(db.robot_ids["NEARUSDT"]).robot_state["source_box_candidate_id"]
        # Current code can attest a pristine baseline; that is Box ownership evidence.
        self.assertTrue(db.store.begin_box_attempt_ownership(source))
        self.assert_blocked(db, "NEARUSDT.*Box ownership")

    def test_unresolved_command_or_protection_blocks(self):
        db = self.db()
        with db.store._transaction():
            db.store._connection.execute(
                """INSERT INTO trading_commands (
                       command_id, order_link_id, trading_account_id, category, symbol,
                       position_idx, command_kind, side, requested_notional, normalized_price,
                       normalized_quantity, origin, controller, current_state, version,
                       exchange_order_id, created_at_ms, updated_at_ms)
                   VALUES ('c1', 'l1', 'paper', 'linear', 'AVNTUSDT', 0, 'create_market', 'Buy',
                           '1', NULL, '1', 'terminal_manual', 'manual', 'submitting', 1, NULL, 1, 1)""",
            )
        self.assert_blocked(db, "AVNTUSDT.*unresolved trading command")

        db = self.db()
        with db.store._transaction():
            db.store._connection.execute(
                """INSERT INTO protection_projections VALUES
                   ('paper', 'linear', 'NEARUSDT', 0, 'confirmed_active', NULL, '1', NULL, NULL, 1, 1, 1)""",
            )
        self.assert_blocked(db, "NEARUSDT.*protection projection")

    def test_open_robot_trade_blocks(self):
        from tests.test_box_plan_persistence import trade_args

        db = self.db()
        db.store.create_robot_candidate(
            candidate_id="wedge", trading_account_id=db.account,
            symbol=__import__("terminal.domain.models", fromlist=["Symbol"]).Symbol("BTCUSDT"),
            status="APPROVED", signal_snapshot={"pattern": "Falling Wedge"},
            approved_at_ms=1, updated_at_ms=1,
        )
        db.store.create_robot_trade(**trade_args("wedge"))
        self.assert_blocked(db, "OPEN Robot candidates|open Robot trades")

    def test_inert_approved_candidates_elsewhere_match_the_real_pc_shape(self):
        # Real owner PC: AVNT/NEAR blockers plus several inert APPROVED wedge
        # candidates on other symbols with no order, fill or exposure.
        from terminal.domain.models import Symbol

        db = self.db()
        for index, symbol in enumerate(("CCUSDT", "BEATUSDT", "PONSUSDT")):
            db.store.create_robot_candidate(
                candidate_id=f"wedge-{index}", trading_account_id=db.account, symbol=Symbol(symbol),
                status="APPROVED", signal_snapshot={"pattern": "Falling Wedge", "n": index},
                approved_at_ms=1, updated_at_ms=1,
            )
        db.finish()
        proof = shutdown.prove_legacy_box_upgrade(db.path)
        self.assertEqual(proof.symbols, PRISTINE_SYMBOLS)

    def test_extra_or_different_active_candidate_owner_blocks(self):
        from terminal.domain.models import Symbol

        db = self.db()
        db.store.create_robot_candidate(
            candidate_id="same-symbol-owner", trading_account_id=db.account, symbol=Symbol("AVNTUSDT"),
            status="APPROVED", signal_snapshot={"pattern": "Falling Wedge"},
            approved_at_ms=1, updated_at_ms=1,
        )
        self.assert_blocked(db, "AVNTUSDT: another active Robot candidate owns the symbol")

        db = self.db()
        db.set_robot("ROBOT_RUNNING", "RECONCILIATION_REQUIRED",
                     LEGACY_REASON_PREFIX + "box-robot-unknown")
        self.assert_blocked(db, "box-robot-unknown is not an APPROVED Box Robot candidate")

        db = self.db()
        unsorted_ids = sorted(db.robot_ids.values(), reverse=True)
        db.set_robot("ROBOT_RUNNING", "RECONCILIATION_REQUIRED",
                     LEGACY_REASON_PREFIX + ",".join(unsorted_ids))
        self.assert_blocked(db, "blocker names are malformed")

    def test_non_pristine_failure_shape_blocks(self):
        for execution, phrase in (
            ({"last_execution_error": "some other failure", "attempt_count": 1}, "not the legacy pristine"),
            ({"last_execution_error": shutdown.LEGACY_BOX_PRISTINE_ERROR, "limit_order_ids": ["x"]},
             "unexpected execution evidence"),
            ({"last_execution_error": shutdown.LEGACY_BOX_PRISTINE_ERROR, "box_ownership_ready": True},
             "unexpected execution evidence"),
        ):
            with self.subTest(execution=execution):
                db = self.db()
                db.set_execution("AVNTUSDT", execution)
                self.assert_blocked(db, phrase)

    def test_robot_or_scanner_state_mismatch_blocks(self):
        db = self.db()
        db.set_robot("ROBOT_RUNNING", "RECONCILIATION_REQUIRED", "some other reconcile failure")
        self.assert_blocked(db, "pending-entry reconciliation blocker")

        db = self.db()
        db.set_robot("ROBOT_RUNNING", "READY", None)
        self.assert_blocked(db, "RECONCILIATION_REQUIRED")

        db = self.db()
        state = db.store.get_scanner_runtime_state(db.account)
        db.store.update_scanner_runtime_state(
            db.account, mode="SCANNER_RUNNING", expected_version=state.version, updated_at_ms=5,
        )
        self.assert_blocked(db, "Scanner is not durably STOPPED")

    def test_guard_rejects_changed_evidence_and_blocks_writers(self):
        db = self.db()
        db.finish()
        proof = shutdown.prove_legacy_box_upgrade(db.path)
        changed = shutdown.LegacyBoxUpgradeProof(
            proof.schema_version, proof.robot_version + 1, proof.candidate_ids, proof.symbols,
        )
        with self.assertRaisesRegex(shutdown.SafeStopError, "changed"):
            with shutdown.hold_legacy_box_upgrade(db.path, changed):
                pass
        with shutdown.hold_legacy_box_upgrade(db.path, proof):
            competitor = sqlite3.connect(db.path, timeout=0.0)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    competitor.execute("UPDATE scanner_runtime_state SET reason='race'")
            finally:
                competitor.close()


CLOSED_ARM = "LONGXIAUSDT"


def add_closed_flat_trade(db, symbol=CLOSED_ARM, *, exit_fill=True, exit_qty="4251",
                          obligation_status="RESOLVED", close_candidate=True):
    """LONGXIA shape: filled entry LIMIT, protection STOP exit, synced FLAT, CLOSED trade."""
    from tests.test_box_plan_persistence import trade_args
    from terminal.domain.models import (
        Category, Execution, ExecutionDedupKey, ExecutionId, Notional, OrderId, OrderSide,
        PositionKey, PositionSide, Price, Quantity, Symbol,
    )
    from terminal.persistence.sqlite_store import PositionProjectionUpdate

    store, account, sym = db.store, db.account, Symbol(symbol)
    key = PositionKey(account, Category.LINEAR, sym, 0)
    candidate_id, trade_id = f"wedge-{symbol}", f"robot-trade-wedge-{symbol}"
    store.create_robot_candidate(
        candidate_id=candidate_id, trading_account_id=account, symbol=sym, status="APPROVED",
        signal_snapshot={"pattern": "Falling Wedge", "symbol": symbol},
        approved_at_ms=1, updated_at_ms=1,
    )
    store.create_paper_limit(
        client_action_id=f"entry-{symbol}", request_fingerprint=f"entry-fp-{symbol}",
        order_id=OrderId(f"limit-{symbol}"), order_link_id=f"link-{symbol}",
        trading_account_id=account, symbol=sym, side=OrderSide.BUY,
        price=Decimal("0.0588"), quantity=Decimal("4251"), created_at_ms=1000,
    )
    store.apply_paper_limit_execution_once(
        OrderId(f"limit-{symbol}"),
        Execution(ExecutionDedupKey(account, Category.LINEAR, ExecutionId(f"entry-exec-{symbol}")),
                  OrderId(f"limit-{symbol}"), sym, OrderSide.BUY, Price(Decimal("0.0585")),
                  Quantity(Decimal("4251")), Decimal("0.1"), 1100),
        PositionProjectionUpdate(key, PositionSide.LONG, Quantity(Decimal("4251")),
                                 Price(Decimal("0.0585")), Decimal(0), Decimal("0.1"),
                                 Notional(Decimal("248.6835")), "synced", None, 1100),
        updated_at_ms=1100,
    )
    args = {**trade_args(candidate_id), "trade_id": trade_id, "symbol": sym,
            "average_entry": Decimal("0.0585"), "stop_price": Decimal("0.0584"),
            "take_price": Decimal("0.06"), "entry_quantity": Decimal("4251"),
            "entry_position_version": 1, "entry_time_ms": 1200, "created_at_ms": 1200}
    store.create_robot_trade(**args)
    if exit_fill:
        store.apply_execution_once(
            Execution(ExecutionDedupKey(account, Category.LINEAR, ExecutionId(f"exit-exec-{symbol}")),
                      OrderId(f"exit-order-{symbol}"), sym, OrderSide.SELL, Price(Decimal("0.0584")),
                      Quantity(Decimal(exit_qty)), Decimal("0.1"), 2000),
            PositionProjectionUpdate(
                key, PositionSide.FLAT if Decimal(exit_qty) == 4251 else PositionSide.LONG,
                Quantity(Decimal("4251") - Decimal(exit_qty)),
                None if Decimal(exit_qty) == 4251 else Price(Decimal("0.0585")),
                Decimal("-0.4"), Decimal("0.2"), Notional(Decimal(0)), "synced", 1, 2000),
        )
    with store._transaction():
        store._connection.execute(
            """INSERT INTO paper_protection_obligations (
                   obligation_id, trade_id, trading_account_id, symbol, protection_version,
                   winning_leg, trigger_price, observed_exit_price, observed_quantity,
                   market_event_id, source_received_at_ms, latched_at_ms, order_id, exec_id,
                   status, version, updated_at_ms)
               VALUES (?, ?, 'paper', ?, 1, 'STOP', '0.0584', '0.0584', '4251', 'evt', 1990, 1995,
                       ?, ?, ?, 2, 2000)""",
            (f"obligation-{symbol}", trade_id, symbol, f"exit-order-{symbol}",
             f"exit-exec-{symbol}", obligation_status),
        )
        store._connection.execute(
            """UPDATE robot_trades SET exit_time_ms=2000, exit_price='0.0584', exit_reason='STOP',
                   realized_pnl_usdt='-0.4', realized_pnl_pct='-0.1', fees_costs_usdt='0.2',
                   version=version+1, updated_at_ms=2000
               WHERE trade_id=?""",
            (trade_id,),
        )
        if close_candidate:
            store._connection.execute(
                "UPDATE robot_candidates SET status='CLOSED' WHERE candidate_id=?", (candidate_id,),
            )
    return candidate_id, trade_id


class LegacyClosedTradeEntryArmProofTests(unittest.TestCase):
    """Class B stale arm: a fully CLOSED + synced FLAT Robot trade (LONGXIA shape)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.count = 0

    def db(self, **closed):
        self.count += 1
        db = LegacyBoxUpgradeDb(self.directory / f"closed-{self.count}.sqlite3")
        self.addCleanup(lambda: db.store._connection is None or db.store.close())
        if closed is not None:
            add_closed_flat_trade(db, **closed)
        return db

    def prove(self, db, covered=("AVNTUSDT", CLOSED_ARM)):
        db.finish()
        return shutdown.prove_legacy_box_upgrade(db.path, covered)

    def assert_blocked(self, db, phrase, covered=("AVNTUSDT", CLOSED_ARM)):
        with self.assertRaisesRegex(shutdown.SafeStopError, phrase):
            self.prove(db, covered)

    def test_longxia_closed_flat_arm_is_accepted_only_as_class_b(self):
        db = self.db()
        proof = self.prove(db)
        self.assertEqual(proof.symbols, PRISTINE_SYMBOLS)
        self.assertEqual(proof.closed_arm_symbols, (CLOSED_ARM,))
        with shutdown.hold_legacy_box_upgrade(db.path, proof):
            pass
        # A pristine blocker symbol is never re-classified as a closed-trade arm.
        self.assertEqual(self.prove(self.db(), ("AVNTUSDT", "NEARUSDT")).closed_arm_symbols, ())

    def test_arm_symbol_without_completed_robot_trade_blocks(self):
        self.assert_blocked(self.db(), "XRPUSDT: stale entry arm has no position projection",
                            covered=(CLOSED_ARM, "XRPUSDT"))

    def test_non_flat_unsynced_or_missing_position_blocks(self):
        from terminal.domain.models import Category, Notional, PositionKey, PositionSide, Quantity, Symbol
        from terminal.persistence.sqlite_store import PositionProjectionUpdate

        self.assert_blocked(self.db(exit_qty="4000"), "pending Robot exposure|not synced FLAT|journal")
        db = self.db()
        key = PositionKey(db.account, Category.LINEAR, Symbol(CLOSED_ARM), 0)
        current = db.store.get_position_projection(key)
        with db.store._transaction():
            db.store._write_projection(PositionProjectionUpdate(
                key, PositionSide.FLAT, Quantity(Decimal(0)), None, Decimal(0), Decimal(0),
                Notional(Decimal(0)), "reconciliation_required", current.version, 2100,
            ))
        self.assert_blocked(db, f"{CLOSED_ARM}: position is not synced FLAT")
        self.assert_blocked(self.db(exit_fill=False), f"{CLOSED_ARM}:.*(not synced FLAT|journal)")

    def test_open_trade_active_candidate_limit_command_or_obligation_blocks(self):
        from terminal.domain.models import OrderId, OrderSide, Symbol

        db = self.db()  # missing exit_time: the schema makes that an OPEN trade
        with db.store._transaction():
            db.store._connection.execute(
                """UPDATE robot_trades SET exit_time_ms=NULL, exit_price=NULL, exit_reason=NULL,
                       realized_pnl_usdt=NULL, realized_pnl_pct=NULL WHERE symbol=?""",
                (CLOSED_ARM,))
        self.assert_blocked(db, "open Robot trades|OPEN Robot")

        self.assert_blocked(self.db(close_candidate=False), "OPEN Robot candidates: LONGXIAUSDT")
        db = self.db(close_candidate=False)  # APPROVED on a flat symbol passes global quiescence
        with db.store._transaction():
            db.store._connection.execute(
                "UPDATE robot_candidates SET status='APPROVED' WHERE symbol=? AND status='OPEN'",
                (CLOSED_ARM,))
        self.assert_blocked(db, f"{CLOSED_ARM}: closed-trade entry arm blocked by an active Robot candidate")

        db = self.db()
        db.store.create_paper_limit(
            client_action_id="w", request_fingerprint="w-fp", order_id=OrderId("w-1"),
            order_link_id="w-link", trading_account_id=db.account, symbol=Symbol(CLOSED_ARM),
            side=OrderSide.BUY, price=Decimal("0.05"), quantity=Decimal("1"), created_at_ms=3000,
        )
        self.assert_blocked(db, "working PAPER limits")

        db = self.db()
        with db.store._transaction():
            db.store._connection.execute(
                """INSERT INTO trading_commands (
                       command_id, order_link_id, trading_account_id, category, symbol,
                       position_idx, command_kind, side, requested_notional, normalized_price,
                       normalized_quantity, origin, controller, current_state, version,
                       exchange_order_id, created_at_ms, updated_at_ms)
                   VALUES ('c1', 'l1', 'paper', 'linear', ?, 0, 'create_market', 'Buy', '1',
                           NULL, '1', 'terminal_manual', 'manual', 'unknown', 1, NULL, 1, 1)""",
                (CLOSED_ARM,),
            )
        self.assert_blocked(db, f"{CLOSED_ARM}:.*unresolved trading command")

        for status in ("TRIGGERED", "DISPATCHING"):
            self.assert_blocked(self.db(obligation_status=status), "unresolved protection obligations")

    def test_missing_or_ambiguous_exit_evidence_blocks(self):
        for sql, phrase in (
            ("UPDATE paper_protection_obligations SET exec_id='missing-exec' WHERE symbol=?",
             "exit execution is not proven"),
            ("UPDATE robot_trades SET exit_price='0.0599' WHERE symbol=?", "exit execution is not proven"),
            ("UPDATE robot_candidates SET status='EXPIRED' WHERE symbol=? AND status='CLOSED'",
             "completed Robot trade"),
            ("UPDATE robot_trades SET exit_time_ms=1999 WHERE symbol=?", "exit execution is not proven"),
            ("DELETE FROM paper_protection_obligations WHERE symbol=?", "protection exit history"),
        ):
            with self.subTest(sql=sql):
                db = self.db()
                with db.store._transaction():
                    db.store._connection.execute(sql, (CLOSED_ARM,))
                self.assert_blocked(db, phrase)

    def test_guard_rejects_changed_closed_arm_evidence(self):
        for sql, phrase in (
            ("UPDATE position_projections SET sync_state='reconciliation_required' WHERE symbol=?",
             f"{CLOSED_ARM}: position is not synced FLAT"),
            ("UPDATE robot_runtime_state SET version=version+1 WHERE ? IS NOT NULL", "changed"),
        ):
            with self.subTest(sql=sql):
                db = self.db()
                proof = self.prove(db)
                self.assertEqual(proof.closed_arm_symbols, (CLOSED_ARM,))
                connection = sqlite3.connect(db.path)
                try:
                    connection.execute(sql, (CLOSED_ARM,))
                    connection.commit()
                finally:
                    connection.close()
                with self.assertRaisesRegex(shutdown.SafeStopError, phrase):
                    with shutdown.hold_legacy_box_upgrade(db.path, proof):
                        pass


class LegacyBoxUpgradeShutdownTests(unittest.TestCase):
    IDS = ("box-robot-avnt", "box-robot-near")

    def runtime(self):
        runtime = FakeRuntime(robot=RECON)
        runtime.reconcile_reply = (409, {
            "ok": False, "success": False, "mode": "ROBOT_RUNNING",
            "recovery_status": "RECONCILIATION_REQUIRED",
            "unresolved_candidate_ids": list(self.IDS),
        })
        runtime.reconcile_state = RECON
        runtime.legacy_chains = {"backend": (130, 120, 110, 105)}
        runtime.box_upgrade_proof = shutdown.LegacyBoxUpgradeProof(25, 7, self.IDS, PRISTINE_SYMBOLS)
        return runtime

    def test_red_reproducer_without_proof_still_blocks_after_one_reconcile(self):
        runtime = self.runtime()
        runtime.box_upgrade_proof = shutdown.SafeStopError("AVNTUSDT has executions")
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("runtime kept alive", result.message)
        self.assertIn("legacy Box upgrade shutdown not proven: AVNTUSDT has executions", result.message)
        self.assertEqual(runtime.calls, ["scanner:stop", "robot:reconcile"])
        self.assertTrue(runtime.backend_alive and runtime.telegram_alive)

    def test_proven_pristine_deadlock_terminates_exact_legacy_backend_once(self):
        runtime = self.runtime()
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertTrue(result.runtime_stopped)
        self.assertEqual(result.steps, (
            "scanner:stop", "runtime:legacy-box-upgrade-proof",
            "telegram:shutdown", "backend:legacy-box-upgrade-terminate",
        ))
        self.assertEqual(runtime.calls, [
            "scanner:stop", "robot:reconcile", "resolve:backend:127.0.0.1:8765",
            "telegram:shutdown", "resolve:backend:127.0.0.1:8765",
            "terminate:[130, 120, 110, 105]",
        ])
        # Durable Robot state is never edited; the upgraded backend reconciles it.
        self.assertEqual(runtime.robot, RECON)
        self.assertNotIn("robot:stop", runtime.calls)
        self.assertNotIn("backend:shutdown", runtime.calls)
        self.assertEqual(runtime.box_upgrade_guards, 1)

    def test_stale_entry_arms_on_named_symbols_are_allowed_others_block(self):
        runtime = self.runtime()
        runtime.protection.update({
            "covered_symbols": ["AVNTUSDT"], "armed_symbols": ["AVNTUSDT"],
            "coverage_roles": {"AVNTUSDT": "ENTRY_PENDING"},
        })
        self.assertTrue(runtime.orchestrator().run("all").ok)

        for covered, roles in ((["BTCUSDT"], {"BTCUSDT": "ENTRY_PENDING"}),
                               (["AVNTUSDT"], {"AVNTUSDT": "POSITION"})):
            with self.subTest(covered=covered, roles=roles):
                runtime = self.runtime()
                runtime.protection.update({
                    "covered_symbols": covered, "armed_symbols": covered, "coverage_roles": roles,
                })
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertNotIn("terminate:[130, 120, 110, 105]", runtime.calls)
                self.assertTrue(runtime.backend_alive)

    def test_identity_chain_response_or_scanner_changes_block_without_termination(self):
        def instance_changes(runtime):
            original = runtime.get
            seen = {"n": 0}

            def get(url, timeout):
                status, body = original(url, timeout)
                if url == BACKEND + "/api/health":
                    seen["n"] += 1
                    if seen["n"] > 2:
                        body = {**body, "process_instance_id": "restarted"}
                return status, body
            runtime.get = get

        def chain_changes(runtime):
            original = runtime.resolve_legacy
            seen = {"n": 0}

            def resolve(kind, host, port, root):
                seen["n"] += 1
                chain = original(kind, host, port, root)
                return chain if seen["n"] == 1 else (999,)
            runtime.resolve_legacy = resolve

        def response_ids_differ(runtime):
            runtime.reconcile_reply[1]["unresolved_candidate_ids"] = ["box-robot-avnt"]

        def response_ids_missing(runtime):
            del runtime.reconcile_reply[1]["unresolved_candidate_ids"]

        def scanner_running(runtime):
            runtime.post_scanner_mode = "SCANNER_RUNNING"

        def database_identity_changes(runtime):
            original = runtime.post

            def post(url, payload, timeout):
                reply = original(url, payload, timeout)
                if url == BACKEND + "/api/robot/reconcile":
                    runtime.backend_health["database_identity"] = "other-db"
                return reply
            runtime.post = post

        def guard_rejects(runtime):
            runtime.box_upgrade_guard_error = shutdown.SafeStopError("legacy Box upgrade evidence changed")

        for mutate in (instance_changes, chain_changes, response_ids_differ, response_ids_missing,
                       scanner_running, database_identity_changes, guard_rejects):
            with self.subTest(case=mutate.__name__):
                runtime = self.runtime()
                mutate(runtime)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok, result.message)
                self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))
                self.assertTrue(runtime.backend_alive)
                self.assertEqual(runtime.robot, RECON)

    def longxia_runtime(self, role="ENTRY_PENDING"):
        # Exact owner-PC protection-health snapshot after the LONGXIA STOP close.
        runtime = self.runtime()
        runtime.protection.update({
            "healthy": True, "covered_symbols": [CLOSED_ARM], "armed_symbols": [CLOSED_ARM],
            "coverage_roles": {CLOSED_ARM: role}, "unhealthy_symbols": {},
        })
        runtime.box_upgrade_proof = shutdown.LegacyBoxUpgradeProof(
            25, 7, self.IDS, PRISTINE_SYMBOLS, (CLOSED_ARM,),
        )
        return runtime

    def test_red_longxia_arm_blocked_without_closed_trade_proof(self):
        runtime = self.longxia_runtime()
        runtime.box_upgrade_proof = shutdown.LegacyBoxUpgradeProof(25, 7, self.IDS, PRISTINE_SYMBOLS)
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("legacy protection covers symbols outside the upgrade proof", result.message)
        self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

    def test_longxia_closed_flat_arm_terminates_exact_legacy_backend_once(self):
        runtime = self.longxia_runtime()
        result = runtime.orchestrator().run("all")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(runtime.box_upgrade_covered, (CLOSED_ARM,))
        self.assertEqual(result.steps, (
            "scanner:stop", "runtime:legacy-box-upgrade-proof",
            "telegram:shutdown", "backend:legacy-box-upgrade-terminate",
        ))
        self.assertEqual([c for c in runtime.calls if c.startswith("terminate:")],
                         ["terminate:[130, 120, 110, 105]"])
        self.assertEqual(runtime.robot, RECON)

    def test_stop_take_role_or_new_covered_symbol_blocks(self):
        for role in ("STOP", "TAKE", "POSITION"):
            with self.subTest(role=role):
                runtime = self.longxia_runtime(role)
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

        runtime = self.longxia_runtime()
        original = runtime.get
        reads = {"n": 0}

        def get(url, timeout):
            status, body = original(url, timeout)
            if url == BACKEND + "/api/robot/protection-health":
                reads["n"] += 1
                if reads["n"] > 1:
                    body = {**body, "covered_symbols": [CLOSED_ARM, "XRPUSDT"],
                            "armed_symbols": [CLOSED_ARM, "XRPUSDT"],
                            "coverage_roles": {CLOSED_ARM: "ENTRY_PENDING", "XRPUSDT": "ENTRY_PENDING"}}
            return status, body
        runtime.get = get
        result = runtime.orchestrator().run("all")
        self.assertFalse(result.ok)
        self.assertIn("outside the upgrade proof", result.message)
        self.assertFalse(any(call.startswith("terminate:") for call in runtime.calls))

    # --- final Scanner STOPPED re-proof race (owner run after #410) -------------------

    def scanner_race_runtime(self, script, *, telegram=True, from_call=3):
        """LONGXIA + AVNT/NEAR runtime whose Nth+ /api/scanner/status reads follow
        ``script`` (exceptions are raised, tuples returned, then normal replies).

        Call 3 is the final re-proof inside the second _resolve_box_upgrade_chain,
        after Telegram shutdown -- where the owner run failed.
        """
        runtime = self.longxia_runtime()
        runtime.telegram_alive = telegram
        original = runtime.get
        state = {"calls": 0, "script": list(script)}

        def get(url, timeout):
            if url == BACKEND + "/api/scanner/status":
                state["calls"] += 1
                if state["calls"] >= from_call and state["script"]:
                    item = state["script"].pop(0)
                    if callable(item):
                        state["script"].insert(0, item)
                        item = item()
                    if isinstance(item, Exception):
                        raise item
                    return item
            return original(url, timeout)
        runtime.get = get
        runtime.scanner_reads = state
        return runtime

    def assert_terminated_once(self, runtime, result, *, telegram=True):
        self.assertTrue(result.ok, result.message)
        expected = ["scanner:stop", "runtime:legacy-box-upgrade-proof"]
        if telegram:
            expected.append("telegram:shutdown")
        expected.append("backend:legacy-box-upgrade-terminate")
        self.assertEqual(list(result.steps), expected)
        self.assertEqual([c for c in runtime.calls if c.startswith("terminate:")],
                         ["terminate:[130, 120, 110, 105]"])
        self.assertEqual(runtime.robot, RECON)

    def assert_blocked_alive(self, runtime, result, phrase):
        self.assertFalse(result.ok)
        self.assertIn(phrase, result.message)
        self.assertFalse(any(c.startswith("terminate:") for c in runtime.calls))
        self.assertTrue(runtime.backend_alive)
        self.assertEqual(runtime.robot, RECON)

    def test_final_scanner_reproof_survives_one_transient_unreachable(self):
        # RED on #410 main: the single GET failed -> "Scanner state is unavailable".
        runtime = self.scanner_race_runtime([shutdown.Unreachable("owner queue busy")])
        self.assert_terminated_once(runtime, runtime.orchestrator().run("all"))
        self.assertEqual(runtime.scanner_reads["calls"], 4)

    def test_final_scanner_reproof_survives_serialized_owner_unavailable(self):
        runtime = self.scanner_race_runtime(
            [(503, {"ok": False, "error": "scanner_control_unavailable"})] * 2)
        self.assert_terminated_once(runtime, runtime.orchestrator().run("all"))

    def test_owner_pc_shape_with_telegram_already_absent(self):
        runtime = self.scanner_race_runtime([shutdown.Unreachable("busy")], telegram=False)
        self.assert_terminated_once(runtime, runtime.orchestrator().run("all"), telegram=False)
        self.assertNotIn("telegram:shutdown", runtime.calls)

    def test_retry_ending_in_running_paused_or_malformed_blocks_immediately(self):
        for final, phrase in (
            ((200, {"ok": True, "mode": "SCANNER_RUNNING"}), "Scanner is not proven STOPPED"),
            ((200, {"ok": True, "mode": "SCANNER_PAUSED"}), "Scanner is not proven STOPPED"),
            ((200, {"ok": True}), "Scanner is not proven STOPPED"),
            ((200, None), "Scanner is not proven STOPPED"),
            ((200, {"ok": False, "mode": "SCANNER_STOPPED"}), "Scanner is not proven STOPPED"),
            ((503, {"ok": False, "error": "other"}), "Scanner is not proven STOPPED"),
            ((500, {"ok": False}), "Scanner is not proven STOPPED"),
        ):
            with self.subTest(final=final):
                runtime = self.scanner_race_runtime([shutdown.Unreachable("busy"), final])
                self.assert_blocked_alive(runtime, runtime.orchestrator().run("all"), phrase)
                self.assertEqual(runtime.scanner_reads["calls"], 4)  # no retry after a definite state

    def test_repeated_unreachable_through_deadline_blocks(self):
        runtime = self.scanner_race_runtime([lambda: shutdown.Unreachable("down")])
        result = runtime.orchestrator().run("all")
        self.assert_blocked_alive(runtime, result, "Scanner STOPPED re-proof timed out")
        self.assertGreaterEqual(runtime.now, shutdown.LEGACY_HEALTH_REPROOF_WAIT_S)

    def test_identity_or_chain_change_after_scanner_retry_blocks(self):
        def after_retry(runtime, mutate):
            original = runtime.get

            def get(url, timeout):
                if url == BACKEND + "/api/health" and runtime.scanner_reads["calls"] >= 4:
                    status, body = original(url, timeout)
                    return status, mutate(dict(body))
                return original(url, timeout)
            runtime.get = get

        for label, mutate, phrase in (
            ("instance", lambda b: {**b, "process_instance_id": "restarted"}, "identity changed"),
            ("database", lambda b: {**b, "database_identity": "other-db"}, "identity changed"),
        ):
            with self.subTest(case=label):
                runtime = self.scanner_race_runtime([shutdown.Unreachable("busy")])
                after_retry(runtime, mutate)
                self.assert_blocked_alive(runtime, runtime.orchestrator().run("all"), phrase)

        runtime = self.scanner_race_runtime([shutdown.Unreachable("busy")])
        original = runtime.resolve_legacy

        def resolve(kind, host, port, root):
            chain = original(kind, host, port, root)
            return (999,) if runtime.scanner_reads["calls"] >= 4 else chain
        runtime.resolve_legacy = resolve
        self.assert_blocked_alive(runtime, runtime.orchestrator().run("all"), "process chain changed")

    def test_ambiguous_or_non_definitive_reconcile_never_enters_upgrade_path(self):
        for reply in ((503, {"ok": False, "error": "robot_reconcile_unavailable"}),
                      (200, {"ok": True, "success": False}), TimeoutError("lost")):
            with self.subTest(reply=reply):
                runtime = self.runtime()
                runtime.reconcile_reply = reply
                result = runtime.orchestrator().run("all")
                self.assertFalse(result.ok)
                self.assertEqual(runtime.calls, ["scanner:stop", "robot:reconcile"])
                self.assertEqual(runtime.box_upgrade_checks, 0)


if __name__ == "__main__":
    unittest.main()
