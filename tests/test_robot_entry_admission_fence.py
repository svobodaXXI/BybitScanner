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

from terminal.application.robot_control import resume_robot_in_store
from terminal.domain.models import (
    Category, OrderId, OrderSide, PositionKey, PositionSide, Price, Quantity, Symbol,
    TradingAccountId,
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

    def test_the_fence_lifts_only_with_ready_admission_and_a_monitor_confirmation(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        self._process("HIMSUSDT:1")
        time.sleep(0.02)
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        self._process("HIMSUSDT:2")  # READY alone does not vouch for an ENTRY from before it
        store = self.runtime.store
        self.assertEqual(store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT")), ())
        self.runtime._robot_command_dispatcher = lambda operation: operation(self.runtime)
        self.runtime._streamed_book = lambda symbol: _p1_book()
        self.runtime._robot_breakout_monitor.tick()
        self._process("HIMSUSDT:3")
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


class BoxRecoveryResumeTests(BoxEntryFenceTests):
    """Invariants after the fence: reconciliation retires stale ENTRYs, protection keeps working."""

    test_closed_admission_never_fills_box_entry_limits = None
    test_the_fence_lifts_only_with_ready_admission_and_a_monitor_confirmation = None
    test_generic_robot_match_path_is_fenced_too = None

    def _book(self, bid, ask, quantity="5", sequence=2):
        return _book("HIMSUSDT", bid, ask, quantity=quantity, sequence=sequence)

    def _run(self, book, event_id):
        return self.runtime.process_robot_market_event(
            "HIMSUSDT", book, event_id=event_id, received_at_ms=book.received_at_ms,
        )

    def test_reconcile_retires_stale_entries_and_resume_never_fills_them(self):
        store = self.runtime.store
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        self._process("HIMSUSDT:1")
        self.assertEqual(store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT")), ())

        result = self.runtime.robot_reconcile()

        self.assertTrue(result.success, result.reason)
        self.assertEqual(result.recovery_status, "PAUSED")
        self.assertEqual([order.status for order in self._entry_orders()], ["cancelled"] * 4)
        resume_robot_in_store(store, clock_ms=lambda: int(time.time() * 1000))
        state = store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual((state.mode, state.recovery_status), ("ROBOT_RUNNING", "READY"))

        self._process("HIMSUSDT:2")

        self.assertEqual(store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT")), ())
        self.assertIsNone(store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol("HIMSUSDT")))

    def test_closed_admission_blocks_remaining_entries_but_never_the_take_exit(self):
        store = self.runtime.store
        key, take, remaining = self._open_position_with_take_and_remaining_entries()

        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        # Market dips through P2..P4: new exposure from the stale grid must not open.
        self._run(self._book("28.05", "28.06", quantity="50", sequence=2), "HIMSUSDT:2")
        self.assertEqual(store.get_position_projection(key).quantity.value, D("2.21"))
        self.assertEqual(
            [store.get_paper_limit(order_id, ACCOUNT).status for order_id in remaining],
            ["open"] * len(remaining),
        )

        # TAKE at 28.64 reduces exposure and stays executable while admission is closed.
        self._run(self._book("28.64", "28.65", sequence=3), "HIMSUSDT:3")
        self.assertEqual(store.get_paper_limit(take.order_id.value, ACCOUNT).status, "filled")
        self.assertEqual(store.get_position_projection(key).side, PositionSide.FLAT)

    def test_closed_admission_never_blocks_the_protective_stop(self):
        store = self.runtime.store
        key, _take, remaining = self._open_position_with_take_and_remaining_entries()

        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        # Through the frozen STOP 27.98: protection closes the position; no stale ENTRY re-opens it.
        self._run(self._book("27.96", "27.97", quantity="50", sequence=2), "HIMSUSDT:2")

        self.assertEqual(store.get_position_projection(key).side, PositionSide.FLAT)
        buys = [fill for fill in store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))
                if fill.side is OrderSide.BUY]
        self.assertEqual([(fill.price.value, fill.quantity.value) for fill in buys],
                         [(D("28.25"), D("2.21"))])
        # The realized setup retires the untouched grid; none of it filled.
        self.assertEqual(
            [store.get_paper_limit(order_id, ACCOUNT).status for order_id in remaining],
            ["cancelled"] * len(remaining),
        )

    def _open_position_with_take_and_remaining_entries(self):
        store = self.runtime.store
        # The fixture opened READY before it placed the grid: its ENTRYs are in this epoch.
        self._run(_p1_book(quantity="2.21"), "HIMSUSDT:1")  # P1 fills 2.21 @ 28.25, TAKE EXIT armed
        key = PositionKey(ACCOUNT, Category.LINEAR, Symbol("HIMSUSDT"), 0)
        self.assertEqual(store.get_position_projection(key).quantity.value, D("2.21"))
        ownership = store.load_box_order_ownership(self.source.candidate_id)
        take = next(item for item in ownership if item.role == "EXIT" and item.slot == 1)
        remaining = [
            item.order_id.value for item in ownership
            if item.role == "ENTRY"
            and store.get_paper_limit(item.order_id.value, ACCOUNT).status == "open"
        ]
        self.assertEqual(len(remaining), 3)
        return key, take, remaining


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

    def _limits_status(self):
        store = self.runtime.store
        return {
            order_id: store.get_paper_limit(order_id, ACCOUNT).status
            for order_id in ("wedge-entry-1", "manual-limit-1")
        }

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

    def test_stopped_robot_never_fills_a_stale_entry_limit(self):
        for recovery in ("ROBOT_STOPPED", "RECONCILIATION_REQUIRED"):
            with self.subTest(recovery=recovery):
                _set_admission(self.runtime, mode="ROBOT_STOPPED", recovery_status=recovery)
                self.runtime._match_limits_only(
                    Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
                )
                self.assertEqual(self._limits()["wedge-entry-1"], D("0"))

    def test_pause_sync_then_resume_never_fills_the_cancelled_entry(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")
        self.runtime.robot_synchronize_pending_entries()
        self.assertEqual(self._limits_status()["wedge-entry-1"], "cancelled")
        resume_robot_in_store(self.runtime.store, clock_ms=lambda: int(time.time() * 1000))

        applied = self.runtime._match_limits_only(
            Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
        )

        self.assertEqual(applied, 1)  # only the manual limit
        self.assertEqual(self._limits(), {"wedge-entry-1": D("0"), "manual-limit-1": D("1")})

    def test_ready_admission_fills_the_entry_once_the_monitor_confirmed_it(self):
        store = self.runtime.store

        def match():
            return self.runtime._match_limits_only(
                Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
                allowed_order_ids={"wedge-entry-1"},
            )

        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        self.assertEqual(match(), 0)  # seeded before this READY epoch: not yet re-evaluated
        self.assertEqual(self._limits()["wedge-entry-1"], D("0"))

        # What RobotBreakoutMonitor._confirm_entry_admission persists after its checks.
        version = store.get_robot_runtime_state(ACCOUNT).version
        record = store.get_robot_candidate("candidate-btc")
        state = dict(record.robot_state)
        state["execution"] = {**state["execution"], "entry_admission_version": version}
        store.save_robot_candidate_state(
            "candidate-btc", status="APPROVED", robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=int(time.time() * 1000),
        )
        self.assertEqual(match(), 1)
        self.assertEqual(self._limits()["wedge-entry-1"], D("1"))


if __name__ == "__main__":
    unittest.main()
