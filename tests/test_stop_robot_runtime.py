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
            self.scanner_mode = "SCANNER_STOPPED"
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

    def orchestrator(self):
        return shutdown.RuntimeShutdown(
            root=ROOT, env={}, get=self.get, post=self.post,
            robot_state=lambda: self.robot, stop_robot_fn=self.stop_robot,
            sleep=self.sleep, monotonic=lambda: self.now,
            legacy_resolver=self.resolve_legacy, legacy_terminator=self.terminate_legacy,
            legacy_paper_quiescence=self.prove_legacy_paper_quiescence,
            legacy_paper_guard=lambda: nullcontext(),
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

    def test_durable_candidate_limit_exposure_or_obligation_blocks_legacy_termination(self):
        for blocker in (
            "legacy PAPER shutdown blocked by active Robot candidates",
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
                    trading_account_id TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE paper_limit_orders (
                    trading_account_id TEXT NOT NULL, status TEXT NOT NULL
                );
                CREATE TABLE position_projections (
                    trading_account_id TEXT NOT NULL, category TEXT NOT NULL,
                    position_idx INTEGER NOT NULL, side TEXT NOT NULL, quantity TEXT NOT NULL
                );
                CREATE TABLE paper_protection_obligations (
                    trading_account_id TEXT NOT NULL, status TEXT NOT NULL
                );
                """
            )
            if blocker == "candidate":
                connection.execute("INSERT INTO robot_candidates VALUES ('paper', 'APPROVED')")
            elif blocker == "limit":
                connection.execute("INSERT INTO paper_limit_orders VALUES ('paper', 'open')")
            elif blocker == "exposure":
                connection.execute(
                    "INSERT INTO position_projections VALUES ('paper', 'linear', 0, 'Long', '1')"
                )
            elif blocker == "obligation":
                connection.execute(
                    "INSERT INTO paper_protection_obligations VALUES ('paper', 'LATCHED')"
                )
            connection.commit()
        finally:
            connection.close()

    def test_read_only_durable_proof_accepts_empty_state_and_rejects_each_blocker(self):
        with tempfile.TemporaryDirectory() as directory:
            clean = Path(directory) / "clean.sqlite3"
            self.make_db(clean)
            shutdown.prove_legacy_paper_quiescence(clean)
            for blocker, phrase in (
                ("candidate", "active Robot candidates"),
                ("limit", "working PAPER limits"),
                ("exposure", "open PAPER exposure"),
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
                            "INSERT INTO robot_candidates VALUES ('paper', 'APPROVED')"
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
        with mock.patch.object(shutdown.RuntimeShutdown, "run", return_value=blocked):
            self.assertEqual(shutdown.main([]), 1)
        self.assertEqual(shutdown.owner_text(blocked), "⛔ Остановка не выполнена: Robot is busy")

    def test_desktop_wrapper_runs_full_scope_module(self):
        launcher = (ROOT / "stop_robot_runtime.bat").read_text()
        self.assertIn('"%~dp0venv\\Scripts\\python.exe" -m tools.stop_robot_runtime', launcher)


if __name__ == "__main__":
    unittest.main()
