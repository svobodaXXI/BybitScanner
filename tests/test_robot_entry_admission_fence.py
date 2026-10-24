"""#608 power outage: resting Robot ENTRY LIMITs never fill while admission is closed.

After the 24.10.2026 outage the restart lands on RECONCILIATION_REQUIRED, but
four PRLUSDT Box ENTRY LIMITs stayed ``open`` below the market. Robot coverage
subscribes their symbol (ENTRY_PENDING) and the first ordered book event used to
fill them, opening new exposure from a stale plan before reconciliation. Exit
LIMITs and STOP/TAKE protection keep working. Temporary SQLite only.
"""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import time
import unittest

from terminal.domain.models import (
    Category, OrderId, OrderSide, PositionKey, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from tests.test_box_first_fill_frozen_stop import HimsOwnerThreadFillTests, _p1_book
from tests.test_terminal_paper_runtime import (
    _runtime, _seed_pending_candidate_with_resting_limit, _set_admission,
)

ACCOUNT = TradingAccountId("paper")
CLOSED = (
    ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
    ("ROBOT_RUNNING", "RECONCILING"),
    ("ROBOT_RUNNING", "PAUSED"),
)


def _book(symbol, bid, ask, quantity="5", sequence=1):
    now = int(time.time() * 1000)
    return NormalizedOrderBook(
        symbol=Symbol(symbol),
        bids=(PriceLevel(Price(D(bid)), Quantity(D(quantity))),),
        asks=(PriceLevel(Price(D(ask)), Quantity(D(quantity))),),
        health=BookHealth.READY, received_at_ms=now, available_depth=1,
        source_generation=0, source_sequence=sequence, source_update_id=sequence,
        source_event_at_ms=now, source_matching_engine_cts_ms=None,
    )


class BoxEntryFenceTests(HimsOwnerThreadFillTests):
    """Reuses the HIMS Box grid fixture (four resting ENTRY LIMITs, P1 at 28.25)."""

    test_partial_p1_fill_is_protected_with_the_frozen_stop_and_recorded = None
    test_the_first_fill_record_is_not_overwritten_by_a_later_pass = None

    def _entry_orders(self):
        store = self.runtime.store
        return [
            store.get_paper_limit(item.order_id.value, ACCOUNT)
            for item in store.load_box_order_ownership(self.source.candidate_id)
            if item.role == "ENTRY"
        ]

    def _process(self, event_id):
        book = _p1_book()
        return self.runtime.process_robot_market_event(
            "HIMSUSDT", book, event_id=event_id, received_at_ms=book.received_at_ms,
        )

    def test_closed_admission_never_fills_box_entry_limits(self):
        for index, (mode, recovery) in enumerate(CLOSED):
            with self.subTest(recovery=recovery):
                _set_admission(self.runtime, mode=mode, recovery_status=recovery)
                self._process(f"HIMSUSDT:{index + 1}")
                store = self.runtime.store
                self.assertEqual(store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT")), ())
                self.assertEqual([order.status for order in self._entry_orders()], ["open"] * 4)
                self.assertIsNone(store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol("HIMSUSDT")))
                record = store.get_robot_candidate(self.candidate.candidate_id)
                self.assertEqual(record.status, "APPROVED")

    def test_the_fence_lifts_only_with_ready_admission(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        self._process("HIMSUSDT:1")
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        self._process("HIMSUSDT:2")
        store = self.runtime.store
        fills = store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))
        self.assertEqual([(fill.price.value, fill.quantity.value) for fill in fills],
                         [(D("28.25"), D("1.17"))])
        self.assertEqual(store.get_robot_candidate(self.candidate.candidate_id).status, "OPEN")

    def test_generic_robot_match_path_is_fenced_too(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        self.runtime._streamed_book = lambda symbol: _p1_book()
        self.assertEqual(self.runtime.robot_match_symbol("HIMSUSDT"), 0)
        self.assertEqual(
            self.runtime.store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT")), ())


class WedgeEntryFenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = _runtime(Path(self.tmp.name) / "paper.sqlite3")
        self.addCleanup(self.runtime.close)
        _seed_pending_candidate_with_resting_limit(
            self.runtime, candidate_id="candidate-btc", order_id="wedge-entry-1",
        )
        # A manual (non-Robot) PAPER LIMIT on the same symbol is not Robot entry exposure.
        self.runtime.store.create_paper_limit(
            client_action_id="seed-manual", request_fingerprint="seed-fp-manual",
            order_id=OrderId("manual-limit-1"), order_link_id="seed-link-manual",
            trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"), side=OrderSide.BUY,
            price=D("64000"), quantity=D("1"), created_at_ms=1000,
        )

    def _limits(self):
        store = self.runtime.store
        return {
            order_id: store.get_paper_limit(order_id, ACCOUNT).filled_quantity
            for order_id in ("wedge-entry-1", "manual-limit-1")
        }

    def test_retest_detected_entry_limit_is_fenced_while_reconciliation_is_required(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        applied = self.runtime._match_limits_only(
            Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
        )
        self.assertEqual(applied, 1)
        self.assertEqual(self._limits(), {"wedge-entry-1": D("0"), "manual-limit-1": D("1")})

    def test_ready_admission_keeps_the_existing_fill(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        applied = self.runtime._match_limits_only(
            Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
            allowed_order_ids={"wedge-entry-1"},
        )
        self.assertEqual(applied, 1)
        self.assertEqual(self._limits()["wedge-entry-1"], D("1"))


if __name__ == "__main__":
    unittest.main()
