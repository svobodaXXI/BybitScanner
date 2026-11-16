"""Proof of the new internal once-only Wedge PAPER reduction through the real owner.

No automatic producer calls this method. It is not authorization to run a
Wedge/BE strategy on VPS. All executions are local in-memory market evidence.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest

from terminal.api.models import CommandResultStatus
from terminal.domain.models import (
    Category, OrderId, PositionKey, Symbol, TradingAccountId,
)
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import (
    _runtime, _crossing_book, _open_robot_position_with_confirmed_protection,
    _set_admission,
)


class RobotBePartialOwnerPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "be.sqlite3"
        self.runtime = _runtime(self.db)
        self.addCleanup(self.runtime.close)
        self.account = TradingAccountId("paper")
        self.symbol = Symbol("BTCUSDT")
        self.candidate_id = "wedge-be-owner"
        self.trade_id = "robot-trade-wedge-be-owner"
        now_ms = int(time.time() * 1000)
        self.minute = (now_ms // 60000 - 2) * 60000
        # Entry fill is a past, immutable source-time execution; the later
        # closed M1 bar is available before the current fresh execution book.
        self.runtime._limit_executor.clock_ms = lambda: self.minute + 30000
        _open_robot_position_with_confirmed_protection(
            self.runtime, symbol=self.symbol.value,
            entry_price=Decimal("64250.5"), stop_price=Decimal("64000"),
            take_price=Decimal("65300"), trade_id=self.trade_id,
            candidate_id=self.candidate_id,
        )
        candidate = self.runtime.store.get_robot_candidate(self.candidate_id)
        fills = self.runtime.store.load_executions_for_symbol(self.account, self.symbol)
        self.assertEqual(len(fills), 1)
        execution = {"limit_order_id": fills[0].order_id.value}
        self.runtime.store.save_robot_candidate_state(
            self.candidate_id, status="OPEN",
            robot_state={"phase": "OPEN", "direction": "LONG", "execution": execution},
            expected_revision=candidate.state_revision,
            updated_at_ms=int(time.time() * 1000),
        )
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        self.key = PositionKey(self.account, Category.LINEAR, self.symbol, 0)
        self.initial = self.runtime.store.get_position_projection(self.key).quantity.value
        self.book = _crossing_book(self.symbol.value, bid="64800", ask="64800.5")

    def run_partial(self, **overrides):
        kwargs = dict(
            candle_open_ms=self.minute + 60000,
            candle_end_ms=self.minute + 120000,
            candle_high=Decimal("64800"), candle_low=Decimal("64600"),
            book=self.book,
        )
        kwargs.update(overrides)
        return self.runtime._robot_wedge_be_partial_once(self.candidate_id, **kwargs)

    def test_exact_reduce_only_partial_preserves_stop_take_and_trade(self):
        initial = len(self.runtime.store.load_executions())
        result = self.run_partial()
        self.assertEqual(result.status, CommandResultStatus.COMPLETED)
        after = self.runtime.store.get_position_projection(self.key)
        instrument = self.runtime._instrument_provider(self.symbol.value)
        partial = (
            self.initial * Decimal("0.25") / instrument.quantity_step
        ).to_integral_value(rounding="ROUND_FLOOR") * instrument.quantity_step
        self.assertEqual(after.quantity.value, self.initial - partial)
        self.assertEqual(len(self.runtime.store.load_executions()), initial + 1)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertEqual(protection.stop_loss, Decimal("64000"))
        self.assertEqual(protection.take_profit, Decimal("65300"))
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        record = self.runtime.store.get_robot_candidate(self.candidate_id)
        intent = record.robot_state["execution"]["wedge_be_partial_intent"]
        self.assertTrue(intent["reduce_only_required"])
        self.assertEqual(intent["partial_quantity"], str(partial))
        # The same candidate can never dispatch a second partial, even if a
        # caller replays a different quote/source event.
        second = self.run_partial()
        self.assertEqual(second.status, CommandResultStatus.UNKNOWN)
        self.assertEqual(len(self.runtime.store.load_executions()), initial + 1)

    def test_unconfirmed_m1_or_protection_collision_does_not_latch_or_execute(self):
        before = len(self.runtime.store.load_executions())
        result = self.run_partial(candle_high=Decimal("64700"))
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        record = self.runtime.store.get_robot_candidate(self.candidate_id)
        self.assertNotIn("wedge_be_partial_intent", record.robot_state["execution"])
        result = self.run_partial(candle_high=Decimal("65400"))
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(len(self.runtime.store.load_executions()), before)

    def test_invalid_future_m1_rejected_before_any_intent(self):
        before = len(self.runtime.store.load_executions())
        with self.assertRaises(Exception):
            self.run_partial(
                candle_open_ms=self.minute + 120000,
                candle_end_ms=self.minute + 180000,
            )
        self.assertEqual(len(self.runtime.store.load_executions()), before)
        self.assertNotIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )


    def test_verified_partial_tightens_stop_once_using_actual_execution_fees(self):
        initial_executions = len(self.runtime.store.load_executions())
        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        book_after_fill = _crossing_book(
            self.symbol.value, bid="64800", ask="64800.5",
        )
        response = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id, book=book_after_fill,
            worst_case_slippage_ticks=2,
        )
        self.assertEqual(response.status, CommandResultStatus.COMPLETED)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertGreater(protection.stop_loss, Decimal("64000"))
        self.assertLess(protection.stop_loss, Decimal("64800"))
        self.assertEqual(protection.take_profit, Decimal("65300"))
        self.assertIsNone(self.runtime.store.get_robot_trade(self.trade_id).exit_time_ms)
        persisted = self.runtime.store.get_robot_candidate(self.candidate_id)
        stop_intent = persisted.robot_state["execution"]["wedge_be_stop_intent"]
        self.assertEqual(str(protection.stop_loss), stop_intent["stop_price"])
        # Reconciliation is a durable projection read, not another STOP
        # command and absolutely not another partial market execution.
        repeated = self.runtime._robot_wedge_be_reconcile_partial(
            self.candidate_id,
            book=_crossing_book(self.symbol.value, bid="64801", ask="64801.5"),
            worst_case_slippage_ticks=2,
        )
        self.assertEqual(repeated.status, CommandResultStatus.COMPLETED)
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            protection.stop_loss,
        )
        self.assertEqual(
            len(self.runtime.store.load_executions()), initial_executions + 1,
        )

    def test_unknown_stop_result_does_not_replay_amendment(self):
        from unittest.mock import patch

        self.assertEqual(self.run_partial().status, CommandResultStatus.COMPLETED)
        from terminal.api.models import PaperStopMutationResult
        fake_unknown = PaperStopMutationResult(
            "fake-be-stop", CommandResultStatus.UNKNOWN, "unknown",
        )
        with patch.object(self.runtime, "_robot_amend_stop", return_value=fake_unknown) as amend:
            result = self.runtime._robot_wedge_be_reconcile_partial(
                self.candidate_id,
                book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
                worst_case_slippage_ticks=2,
            )
            self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
            self.assertEqual(amend.call_count, 1)
            result = self.runtime._robot_wedge_be_reconcile_partial(
                self.candidate_id,
                book=_crossing_book(self.symbol.value, bid="64800", ask="64800.5"),
                worst_case_slippage_ticks=2,
            )
            self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
            self.assertEqual(amend.call_count, 1)
        protection = self.runtime.store.get_protection_projection(self.key)
        self.assertEqual(protection.stop_loss, Decimal("64000"))
        self.assertEqual(protection.take_profit, Decimal("65300"))

    def _enable_auto(self):
        self.runtime._wedge_be_auto_paper_enabled = True
        monitor = self.runtime._robot_breakout_monitor
        monitor._wedge_be_auto_paper_enabled = True
        monitor._get_closed_candle = lambda symbol: {
            "time_ms": self.minute + 60000,
            "high": 64800, "low": 64600, "close": 64800,
        } if symbol == self.symbol.value else None
        return monitor

    def test_wedge_auto_default_off_prevents_any_market_or_stop_command(self):
        from unittest.mock import patch

        monitor = self.runtime._robot_breakout_monitor
        original = len(self.runtime.store.load_executions())
        with patch.object(monitor, "_get_closed_candle", side_effect=AssertionError("auto disabled")):
            self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(self.runtime.store.load_executions()), original)
        self.assertNotIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )

    def test_automatic_closed_m1_then_next_tick_reconciles_stop_once(self):
        from unittest.mock import patch

        monitor = self._enable_auto()
        initial_executions = len(self.runtime.store.load_executions())
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            self.assertEqual(len(self.runtime.store.load_executions()), initial_executions + 1)
            after_partial = self.runtime.store.get_protection_projection(self.key)
            self.assertEqual(after_partial.stop_loss, Decimal("64000"))
            self.assertEqual(monitor.tick(), (self.candidate_id,))
            protected = self.runtime.store.get_protection_projection(self.key)
            self.assertGreater(protected.stop_loss, Decimal("64000"))
            self.assertEqual(protected.take_profit, Decimal("65300"))
            self.assertEqual(monitor.tick(), (self.candidate_id,))
        self.assertEqual(len(self.runtime.store.load_executions()), initial_executions + 1)
        self.assertEqual(
            self.runtime.store.get_protection_projection(self.key).stop_loss,
            protected.stop_loss,
        )

    def test_auto_rejects_unclosed_or_stale_m1_without_dispatch(self):
        from unittest.mock import patch

        monitor = self._enable_auto()
        initial_executions = len(self.runtime.store.load_executions())
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")):
            monitor._get_closed_candle = lambda _: {
                "time_ms": self.minute + 120000, "high": 64800,
                "low": 64600, "close": 64800,
            }
            self.assertEqual(monitor.tick(), ())
            monitor._get_closed_candle = lambda _: {
                "time_ms": self.minute - 300000, "high": 64800,
                "low": 64600, "close": 64800,
            }
            self.assertEqual(monitor.tick(), ())
        self.assertEqual(len(self.runtime.store.load_executions()), initial_executions)

    def test_auto_recovery_never_resubmits_unknown_partial(self):
        from unittest.mock import patch
        from terminal.api.models import CommandResult

        monitor = self._enable_auto()
        original = len(self.runtime.store.load_executions())
        unknown = CommandResult(
            "unknown-be", CommandResultStatus.UNKNOWN, "unknown", "owner outcome unknown",
            None, True,
        )
        with patch.object(self.runtime, "_streamed_book", side_effect=lambda symbol:
                          _crossing_book(self.symbol.value, bid="64800", ask="64800.5")), \\
             patch.object(self.runtime._robot_api, "full_close", return_value=unknown) as send:
            self.assertEqual(monitor.tick(), ())
            self.assertEqual(send.call_count, 1)
            self.assertEqual(monitor.tick(), ())
            self.assertEqual(send.call_count, 1)
        self.assertEqual(len(self.runtime.store.load_executions()), original)
        self.assertIn(
            "wedge_be_partial_intent",
            self.runtime.store.get_robot_candidate(self.candidate_id).robot_state["execution"],
        )


if __name__ == "__main__":
    unittest.main()
