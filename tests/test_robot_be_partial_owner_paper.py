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


if __name__ == "__main__":
    unittest.main()
