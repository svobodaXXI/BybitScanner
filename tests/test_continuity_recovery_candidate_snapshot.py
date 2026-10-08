"""Continuity recovery must read the signal snapshot from the full candidate record.

``load_active_robot_candidate_states`` is a light projection without a signal
snapshot; recovery used to read ``candidate.signal_snapshot`` from it and raised
AttributeError, leaving coverage unhealthy and the pending entries uncancelled.
All databases are temporary.
"""

import tempfile
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from terminal.domain.models import OrderId, OrderSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import BoxOwnedPaperLimitSpec
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import (
    _CONFIRMED_BOX_FORMATION,
    StaticBookProvider,
    _crossing_book,
    _instrument,
    _seed_pending_candidate_with_resting_limit,
    _set_admission,
)

ACCOUNT = TradingAccountId("paper")


def _box_instrument(symbol: str):
    return replace(
        _instrument(), symbol=symbol,
        min_order_quantity=Decimal("0.0001"), quantity_step=Decimal("0.0001"),
    )


def _runtime(temp: str) -> PaperRuntime:
    runtime = PaperRuntime(
        Path(temp) / "paper.sqlite3",
        book_provider=StaticBookProvider(),
        instrument_snapshot=_instrument(),
        instrument_provider=_box_instrument,
    )
    _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status="READY")
    return runtime


def _seed_box_with_four_entry_limits(runtime: PaperRuntime) -> tuple[str, list[str]]:
    store = runtime.store
    source_id = runtime._prepare_ikigai_box_robot_plan("BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)
    source = store.get_robot_candidate(source_id)
    candidate, _ = store.handoff_box_plan_to_robot(
        source_id, symbol=source.symbol,
        expected_snapshot_sha256=source.snapshot_sha256, approved_at_ms=int(time.time() * 1000) + 10,
    )
    assert store.begin_box_attempt_ownership(source_id)
    plan = source.signal_snapshot["plan"]
    order_ids = [f"box-seed-order-{slot}" for slot in range(1, 5)]
    limits = tuple(
        BoxOwnedPaperLimitSpec(
            slot=slot,
            client_action_id=f"box-seed-action-{slot}",
            request_fingerprint=f"box-seed-fp-{slot}",
            order_id=OrderId(order_ids[slot - 1]),
            order_link_id=f"box-seed-link-{slot}",
            side=OrderSide.BUY,
            price=Decimal(plan["limit_prices"][slot - 1]),
            quantity=Decimal(plan["limit_quantities"][slot - 1]),
            created_at_ms=2100,
        )
        for slot in range(1, 5)
    )
    store.create_box_mixed_entry_ownership(
        source_id, trading_account_id=ACCOUNT, symbol=source.symbol,
        market_orders=(), limit_orders=limits,
    )
    return candidate.candidate_id, order_ids


def _book(symbol: str = "BTCUSDT"):
    # Far above every seeded BUY limit: recovery must never fill anything.
    return _crossing_book(symbol, bid="65000", ask="65001")


def _recover(runtime: PaperRuntime, symbol: str = "BTCUSDT") -> bool:
    book = _book(symbol)
    return runtime.recover_robot_protection_continuity_loss(
        symbol, book, event_id=f"{symbol}:rest-recovery:1",
        received_at_ms=book.received_at_ms, reason="websocket_disconnect:test",
    )


def _status(runtime: PaperRuntime, order_id: str) -> str:
    return runtime.store.get_paper_limit(order_id, ACCOUNT).status


def _footprint(runtime: PaperRuntime) -> tuple[int, int, int]:
    connection = runtime.store._connection
    return tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("paper_limit_orders", "executions", "robot_trades")
    )


class ContinuityRecoveryCandidateSnapshotTests(unittest.TestCase):
    def test_approved_box_with_four_entry_limits_is_cancelled_without_new_orders_or_fills(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                candidate_id, order_ids = _seed_box_with_four_entry_limits(runtime)
                assert [_status(runtime, item) for item in order_ids] == ["open"] * 4
                before = _footprint(runtime)

                assert _recover(runtime) is True

                assert [_status(runtime, item) for item in order_ids] == ["cancelled"] * 4
                assert _footprint(runtime) == before
                assert runtime.store.get_robot_candidate(candidate_id).status == "APPROVED"
            finally:
                runtime.close()


    def test_recovery_is_idempotent_for_the_box(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _candidate_id, order_ids = _seed_box_with_four_entry_limits(runtime)
                assert _recover(runtime) is True
                after_first = _footprint(runtime)

                assert _recover(runtime) is True

                assert [_status(runtime, item) for item in order_ids] == ["cancelled"] * 4
                assert _footprint(runtime) == after_first
            finally:
                runtime.close()


    def test_approved_wedge_resting_limit_is_cancelled(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _seed_pending_candidate_with_resting_limit(
                    runtime, candidate_id="candidate-wedge-recovery", order_id="wedge-order-1",
                )
                before = _footprint(runtime)

                # The return value also reflects the global reconcile of a still
                # waiting Wedge, which is outside this fix; the effect is what matters.
                _recover(runtime)

                assert _status(runtime, "wedge-order-1") == "cancelled"
                assert _footprint(runtime) == before
                _recover(runtime)
                assert _status(runtime, "wedge-order-1") == "cancelled"
                assert _footprint(runtime) == before
            finally:
                runtime.close()


    def test_candidate_on_another_symbol_is_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _seed_pending_candidate_with_resting_limit(
                    runtime, candidate_id="candidate-eth", order_id="eth-order-1", symbol="ETHUSDT",
                )
                _candidate_id, order_ids = _seed_box_with_four_entry_limits(runtime)

                _recover(runtime, "BTCUSDT")

                assert [_status(runtime, item) for item in order_ids] == ["cancelled"] * 4
                assert _status(runtime, "eth-order-1") == "open"
                assert runtime.store.get_robot_candidate("candidate-eth").status == "APPROVED"
            finally:
                runtime.close()


    def test_missing_full_record_fails_closed_and_cancels_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _candidate_id, order_ids = _seed_box_with_four_entry_limits(runtime)
                before = _footprint(runtime)
                real_get = runtime.store.get_robot_candidate

                def vanished(candidate_id):
                    record = real_get(candidate_id)
                    return None if record is not None and record.status == "APPROVED" else record

                with patch.object(runtime.store, "get_robot_candidate", side_effect=vanished):
                    assert _recover(runtime) is False

                assert [_status(runtime, item) for item in order_ids] == ["open"] * 4
                assert _footprint(runtime) == before
                state = runtime.store.get_robot_runtime_state(ACCOUNT)
                assert state.recovery_status == "RECONCILIATION_REQUIRED"
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
