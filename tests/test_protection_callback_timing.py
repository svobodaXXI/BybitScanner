"""Offline only: deterministic clocks, serialized callback and scratch SQLite."""
import json
import tempfile
import threading
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from terminal.protection_timing import capture_callback, protection_span
from terminal.runtime.paper_http_server import (
    SerializedPaperRuntime, RobotProtectionCoverageManager,
)
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.domain.models import Symbol, TradingAccountId
from tests.test_robot_protection_overflow_recovery import _Owner, _Context, _BookSnapshot, SYMBOL


class Clock:
    value = 10.0

    def __call__(self):
        return self.value

    def advance(self, ms):
        self.value += ms / 1000


def owner_queue():
    # Exercise the real queue and callback methods without starting a thread/service.
    owner = object.__new__(SerializedPaperRuntime)
    owner._thread = SimpleNamespace(is_alive=lambda: True)
    owner._requests = Mock(qsize=lambda: 0)
    owner._protection_tasks = deque()
    owner._protection_ingress_lock = threading.Lock()
    owner._protection_ingress_pending = 0
    owner._protection_ingress_capacity = 64
    owner._protection_ingress_high_watermark = 0
    owner._protection_wake_pending = False
    owner._protection_ingress_max_queue_latency_ms = 0.0
    owner._protection_ingress_max_processing_ms = 0.0
    owner._protection_ingress_recent = deque()
    owner._owner_diagnostics_disabled = False
    owner._slowest_owner_task = (0.0, "", "")
    return owner


class ProtectionCallbackTimingTests(unittest.TestCase):
    def test_slow_callback_correlates_queue_stage_nested_and_residual(self):
        owner, clock = owner_queue(), Clock()
        effects = []

        def operation(runtime):
            self.assertIs(runtime, effects)
            with protection_span("state"):
                clock.advance(100)
            with protection_span("limit"):
                clock.advance(150)
                with protection_span("sqlite_commit"):
                    clock.advance(50)
            clock.advance(25)
            effects.append("once")

        with patch("time.perf_counter", clock), patch("terminal.runtime.paper_http_server.LOGGER.warning") as log:
            owner.enqueue(operation, symbol="AKEUSDT", coverage_role="EXPOSURE", event_id="AKEUSDT:42:7")
            clock.advance(600)
            owner._run_protection_task(effects, owner._protection_tasks.popleft())
        self.assertEqual(effects, ["once"])
        self.assertEqual(owner._protection_ingress_pending, 0)
        args = log.call_args.args
        self.assertAlmostEqual(args[3], 325)
        self.assertIn("queue_latency_ms=600.0", args[-1])
        report = json.loads(args[-1].split(" protection_timing=")[1])
        self.assertEqual(report["event_id"], "AKEUSDT:42:7")
        self.assertTrue(report["accounting_valid"])
        self.assertAlmostEqual(report["stage_sum_ms"], 300)
        self.assertAlmostEqual(report["unmeasured_ms"], 25)
        self.assertAlmostEqual(report["sqlite_control_nested_ms"]["commit"], 50)
        self.assertAlmostEqual(report["stage_sum_ms"] + report["unmeasured_ms"], report["callback_elapsed_ms"])

    def test_fast_callback_is_silent_even_after_long_queue_wait(self):
        owner, clock = owner_queue(), Clock()
        with patch("time.perf_counter", clock), patch("terminal.runtime.paper_http_server.LOGGER.warning") as log:
            owner.enqueue(lambda _: clock.advance(1), event_id="fast")
            clock.advance(5000)
            owner._run_protection_task(None, owner._protection_tasks.popleft())
        log.assert_not_called()

    def test_exception_records_partial_stage_and_clears_context(self):
        owner, clock = owner_queue(), Clock()

        def fail(_):
            with protection_span("protection"):
                clock.advance(500)
                raise ValueError("original error")

        with patch("time.perf_counter", clock), patch("terminal.runtime.paper_http_server.LOGGER") as log:
            owner.enqueue(fail, event_id="failed")
            owner._run_protection_task(None, owner._protection_tasks.popleft())
            log.exception.assert_called_once_with("PAPER owner task failed")
            report = json.loads(log.warning.call_args.args[-1].split(" protection_timing=")[1])
            self.assertAlmostEqual(report["stages_ms"]["protection"], 500)
            with capture_callback() as next_trace:
                with protection_span("state"):
                    clock.advance(2)
            self.assertNotIn("protection", next_trace.elapsed)
        self.assertEqual(owner._protection_ingress_pending, 0)

    def test_diagnostic_clock_failure_does_not_hide_business_exception(self):
        with capture_callback() as trace:
            with patch("time.perf_counter", side_effect=RuntimeError("diagnostic failure")):
                with self.assertRaisesRegex(ValueError, "business failure"):
                    with protection_span("state"):
                        raise ValueError("business failure")
        self.assertFalse(trace.valid)

    def test_book_event_id_reaches_same_queued_callback(self):
        queue, runtime = owner_queue(), _Owner()
        manager = RobotProtectionCoverageManager(object(), queue)
        manager._covered[SYMBOL] = _Context(public_orderbook=_BookSnapshot())
        manager._roles[SYMBOL] = "EXPOSURE"
        event_id = f"{SYMBOL}:177600000001:10680001"
        manager._on_update(SYMBOL, event_id)
        task = queue._protection_tasks.popleft()
        self.assertEqual(task.event_id, event_id)
        queue._run_protection_task(runtime, task)
        self.assertEqual(runtime.processed[0][2], event_id)

    def test_real_market_path_preserves_order_result_and_allowed_limits(self):
        clock = Clock()
        calls = []
        candidate = SimpleNamespace(symbol=Symbol("AKEUSDT"), status="APPROVED",
                                    robot_state={"phase": "RETEST_DETECTED", "execution": {"limit_order_id": "owned"}})
        runtime = object.__new__(PaperRuntime)
        runtime._paper_account_id = TradingAccountId("paper")

        def read(*_):
            calls.append("state")
            clock.advance(20)
            return (candidate,)

        def match(symbol, book, event_id, *, allowed_order_ids):
            calls.append(("limit", event_id, allowed_order_ids))
            clock.advance(30)
            return 0

        def protect(*_, **kwargs):
            calls.append(("protection", kwargs["event_id"]))
            clock.advance(40)
            return "obligation"

        runtime.store = SimpleNamespace(load_robot_candidates_for_symbol=read)
        runtime._match_limits_only = match
        runtime.evaluate_robot_protection_crossing = protect
        book = SimpleNamespace(symbol=Symbol("AKEUSDT"))
        plain = runtime.process_robot_market_event("AKEUSDT", book, event_id="e", received_at_ms=1)
        expected_calls = calls[:]
        calls.clear()
        with patch("time.perf_counter", clock), capture_callback() as trace:
            measured = runtime.process_robot_market_event("AKEUSDT", book, event_id="e", received_at_ms=1)
        self.assertEqual(measured, plain)
        self.assertEqual(calls, expected_calls)
        for stage, expected in (("state", 20), ("limit", 30), ("fill", 0), ("protection", 40)):
            self.assertAlmostEqual(trace.elapsed[stage], expected)

    def test_real_sqlite_commit_rollback_and_durability_are_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            with SQLiteStore.open(Path(directory) / "scratch.sqlite3") as store:
                settings = store.settings()
                with capture_callback() as trace:
                    store.initialize_robot_autopilot_state(TradingAccountId("paper"), updated_at_ms=1)
                    with self.assertRaisesRegex(ValueError, "rollback"):
                        with store._transaction():
                            store._connection.execute("UPDATE robot_autopilot_state SET updated_at_ms=99")
                            raise ValueError("rollback")
                self.assertEqual(store.get_robot_autopilot_state(TradingAccountId("paper")).updated_at_ms, 1)
                self.assertEqual(store.settings(), settings)
                for name in ("sqlite_begin", "sqlite_commit", "sqlite_rollback"):
                    self.assertIn(name, trace.elapsed)
                    self.assertGreaterEqual(trace.elapsed[name], 0)

    def test_existing_partial_fill_and_stop_contract_with_timing_active(self):
        # Reuse the existing offline fill regression, with diagnostics active.
        # Its setup uses only a temporary DB and static books, no services.
        from tests.test_box_first_fill_frozen_stop import HimsOwnerThreadFillTests
        case = HimsOwnerThreadFillTests(
            "test_partial_p1_fill_is_protected_with_the_frozen_stop_and_recorded")
        try:
            case.setUp()
            with capture_callback() as trace:
                case.test_partial_p1_fill_is_protected_with_the_frozen_stop_and_recorded()
            self.assertGreater(trace.elapsed["fill"], 0)
            self.assertGreater(trace.elapsed["sqlite_commit"], 0)
        finally:
            case.doCleanups()
