"""Issue #399: robot_close_all() must route on full OPEN candidate records.

Root cause: b856959 switched robot_close_all() to the lightweight
load_active_robot_candidate_states() projection (RobotCandidateStateRecord:
candidate_id/symbol/status/robot_state, no signal snapshot) while it only
needed symbol/status. 945afed then added Box routing that read
``candidate.signal_snapshot`` on those rows -- in the try block and again in
the except handler -- and passed the row to _robot_close_box_candidate(),
which needs the full record. Every OPEN candidate raised AttributeError, the
handler raised again, and operator close-all-now failed outright.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from terminal.api.models import (
    ClientActionId, CloseAllCommandRequest, CommandResult, CommandResultStatus,
    MarketCommandRequest, VolumeRequest, VolumeUnit,
)
from terminal.domain.models import (
    Category, OrderSide, PositionKey, PositionSide, Symbol, TradingAccountId,
)
from terminal.persistence.sqlite_store import RobotCandidateRecord
from tests.test_terminal_paper_runtime import _open_robot_position, _runtime, _set_admission


ACCOUNT = TradingAccountId("paper")


def _buy(runtime, symbol: str, action_id: str) -> None:
    result = runtime.api.market(MarketCommandRequest(
        ClientActionId(action_id), symbol, OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal("321")), Decimal("64250"),
        "Percent", Decimal("0.5"),
    ))
    assert result.status is CommandResultStatus.COMPLETED


def _open_box_candidate(runtime, *, symbol: str = "ETHUSDT") -> None:
    """A real OPEN Ikigai Box candidate row (trade-backed), for routing."""
    runtime.store.create_robot_candidate(
        candidate_id="candidate-box", trading_account_id=ACCOUNT, symbol=Symbol(symbol),
        status="APPROVED",
        signal_snapshot={
            "symbol": symbol, "pattern": "IKIGAI_BOX",
            "source_box_candidate_id": "box-plan-1",
        },
        approved_at_ms=1000, updated_at_ms=1000,
    )
    runtime.store.create_robot_trade(
        trade_id="trade-box", trading_account_id=ACCOUNT, candidate_id="candidate-box",
        symbol=Symbol(symbol), direction="LONG", pattern="IKIGAI_BOX", source_timeframe="5",
        signal_time_ms=10, entry_time_ms=20, entry_path="LIMIT", actual_wv=Decimal("1"),
        average_entry=Decimal("64250"), stop_price=Decimal("60000"),
        take_price=Decimal("70000"), entry_quantity=Decimal("1"),
        entry_position_version=1, created_at_ms=1001,
    )


def _position(runtime, symbol: str):
    return runtime.store.get_position_projection(
        PositionKey(ACCOUNT, Category.LINEAR, Symbol(symbol), 0)
    )


def _ready(runtime) -> None:
    _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="READY")


class RobotCloseAllTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.runtime = _runtime(Path(self._temp.name) / "paper.sqlite3")

    def tearDown(self):
        self.runtime.close()
        self._temp.cleanup()

    def close_all(self, action_id: str = "robot-close-all-1"):
        return self.runtime.robot_close_all(CloseAllCommandRequest(ClientActionId(action_id)))

    def test_lightweight_rows_lack_snapshot_and_close_all_no_longer_crashes(self):
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        light = self.runtime.store.load_active_robot_candidate_states(ACCOUNT)
        self.assertFalse(hasattr(light[0], "signal_snapshot"))

        response = self.close_all()

        self.assertEqual([item.status for item in response.results], [CommandResultStatus.COMPLETED])

    def test_open_non_box_position_closes_through_robot_full_close(self):
        _ready(self.runtime)
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        entry = self.runtime.store.load_executions()[-1]

        with patch.object(
            self.runtime, "_robot_close_box_candidate",
            side_effect=AssertionError("non-Box must not use the Box close"),
        ):
            response = self.close_all()

        self.assertEqual([item.status for item in response.results], [CommandResultStatus.COMPLETED])
        close = self.runtime.store.load_executions()[-1]
        self.assertEqual((close.side, close.quantity.value), (OrderSide.SELL, entry.quantity.value))
        position = _position(self.runtime, "BTCUSDT")
        self.assertEqual((position.side, position.quantity.value), (PositionSide.FLAT, Decimal("0")))
        state = self.runtime.store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual(state.recovery_status, "READY")

    def test_open_box_candidate_routes_through_box_close_with_full_record(self):
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        _open_box_candidate(self.runtime)
        seen = []

        def box_close(candidate):
            seen.append(candidate)
            return CommandResult("box-close", CommandResultStatus.COMPLETED, "filled", "ok")

        with patch.object(self.runtime, "_robot_close_box_candidate", side_effect=box_close):
            response = self.close_all()

        self.assertEqual(len(seen), 1)
        record = seen[0]
        self.assertIsInstance(record, RobotCandidateRecord)
        self.assertEqual(
            (record.candidate_id, record.symbol.value, record.status),
            ("candidate-box", "ETHUSDT", "OPEN"),
        )
        self.assertEqual(record.signal_snapshot["source_box_candidate_id"], "box-plan-1")
        self.assertEqual(
            [item.status for item in response.results],
            [CommandResultStatus.COMPLETED, CommandResultStatus.COMPLETED],
        )
        # The non-Box symbol still went through the canonical full close.
        self.assertEqual(_position(self.runtime, "BTCUSDT").side, PositionSide.FLAT)

    def test_one_candidate_failure_is_surfaced_and_others_still_close(self):
        _ready(self.runtime)
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        _open_box_candidate(self.runtime)

        with patch.object(
            self.runtime, "_robot_close_box_candidate", side_effect=RuntimeError("box failed"),
        ):
            response = self.close_all()

        by_status = sorted((item.status.value, item.reason_code) for item in response.results)
        self.assertEqual(
            by_status, [("completed", "completed"), ("unavailable", "box_close_failed")],
        )
        self.assertEqual(_position(self.runtime, "BTCUSDT").side, PositionSide.FLAT)
        state = self.runtime.store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual(state.recovery_status, "RECONCILIATION_REQUIRED")

    def test_non_box_failure_reports_close_failed_without_crashing(self):
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        # stable's robot_close_all calls the Robot API's full_close directly
        with patch.object(self.runtime._robot_api, "full_close", side_effect=RuntimeError("down")):
            response = self.close_all()
        self.assertEqual(
            [(item.status, item.reason_code) for item in response.results],
            [(CommandResultStatus.UNAVAILABLE, "close_failed")],
        )

    def test_repeated_close_all_does_not_double_close_or_reverse(self):
        _buy(self.runtime, "BTCUSDT", "robot-open-btc")
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        self.close_all("robot-close-all-1")
        executions = len(self.runtime.store.load_executions())

        for attempt in ("robot-close-all-1", "robot-close-all-2"):  # replay + new request
            response = self.close_all(attempt)
            self.assertEqual(
                [(item.status, item.reason_code) for item in response.results],
                [(CommandResultStatus.COMPLETED, "already_flat")],
            )
        self.assertEqual(len(self.runtime.store.load_executions()), executions)
        position = _position(self.runtime, "BTCUSDT")
        self.assertEqual((position.side, position.quantity.value), (PositionSide.FLAT, Decimal("0")))

    def test_flat_robot_position_is_a_no_op_never_a_reversal(self):
        # OPEN Robot candidate whose position is already flat (never filled here).
        _open_robot_position(self.runtime, candidate_id="candidate-btc", trade_id="trade-btc")
        response = self.close_all()
        self.assertEqual(
            [(item.status, item.reason_code) for item in response.results],
            [(CommandResultStatus.COMPLETED, "already_flat")],
        )
        self.assertEqual(self.runtime.store.load_executions(), ())
        position = _position(self.runtime, "BTCUSDT")
        self.assertTrue(position is None or position.side is PositionSide.FLAT)


if __name__ == "__main__":
    unittest.main()
