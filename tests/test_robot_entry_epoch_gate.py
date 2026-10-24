"""#608 residual risks: a stale or unowned Robot ENTRY LIMIT never fills without fresh admission.

READY alone is not proof that a resting ENTRY is still wanted: a restart, start from
STOPPED or resume opens a new admission epoch, and an ENTRY placed before it fills only
after the monitor has re-evaluated it in that epoch. An ENTRY whose origin is Robot but
which no live candidate owns (lost link, terminal candidate, failed cancel) never fills.
Exit LIMITs and STOP/TAKE are untouched. Temporary SQLite only.
"""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal.application.robot_control import resume_robot_in_store
from terminal.api.models import CommandResultStatus
from terminal.domain.models import (
    OrderId, OrderSide, Symbol, TradingAccountId,
)
from tests.test_box_first_fill_frozen_stop import HimsOwnerThreadFillTests, _p1_book
from tests.test_robot_entry_admission_fence import _book
from tests.test_terminal_paper_runtime import _runtime, _set_admission

ACCOUNT = TradingAccountId("paper")


def _now():
    return int(time.time() * 1000)


class BoxEpochGateTests(HimsOwnerThreadFillTests):
    """Reuses the HIMS Box grid fixture: four resting ENTRY LIMITs, P1 at 28.25."""

    test_partial_p1_fill_is_protected_with_the_frozen_stop_and_recorded = None
    test_the_first_fill_record_is_not_overwritten_by_a_later_pass = None

    def _event(self, index):
        book = _p1_book()
        self.runtime.process_robot_market_event(
            "HIMSUSDT", book, event_id=f"HIMSUSDT:{index}", received_at_ms=book.received_at_ms,
        )

    def _fills(self):
        return self.runtime.store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))

    def _monitor_pass(self):
        runtime = self.runtime
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        runtime._streamed_book = lambda symbol: _p1_book()
        runtime._robot_breakout_monitor.tick()

    def _assert_filled_once_confirmed(self, first_event):
        self._event(first_event)
        self.assertEqual(self._fills(), ())
        self._monitor_pass()
        self._event(first_event + 1)
        self.assertEqual([(f.price.value, f.quantity.value) for f in self._fills()],
                         [(D("28.25"), D("1.17"))])

    def test_restart_recovery_into_ready_does_not_fill_stale_entries_until_confirmed(self):
        time.sleep(0.02)
        self.runtime._robot_recovery.recover()  # what a power-cycle restart does from READY
        state = self.runtime.store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual((state.mode, state.recovery_status), ("ROBOT_RUNNING", "READY"))
        self._assert_filled_once_confirmed(1)

    def test_start_from_stopped_does_not_fill_stale_entries_until_confirmed(self):
        _set_admission(self.runtime, mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        time.sleep(0.02)
        self.runtime._robot_recovery.start()
        state = self.runtime.store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual((state.mode, state.recovery_status), ("ROBOT_RUNNING", "READY"))
        self._assert_filled_once_confirmed(1)

    def test_resume_from_paused_does_not_fill_stale_entries_until_confirmed(self):
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")
        time.sleep(0.02)
        resume_robot_in_store(self.runtime.store, clock_ms=_now)
        self._assert_filled_once_confirmed(1)

    def test_confirmation_does_not_outlive_the_epoch(self):
        self._monitor_pass()  # confirmed in the epoch the fixture opened
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")
        time.sleep(0.02)
        resume_robot_in_store(self.runtime.store, clock_ms=_now)  # new epoch, new version
        self._event(1)
        self.assertEqual(self._fills(), ())

    def test_entries_placed_in_the_current_epoch_fill_without_waiting_for_a_tick(self):
        # The fixture opened READY before it created the grid: the normal new-entry path.
        self._event(1)
        self.assertEqual([(f.price.value, f.quantity.value) for f in self._fills()],
                         [(D("28.25"), D("1.17"))])

    def test_a_confirmed_entry_never_reopens_a_closed_position(self):
        self._event(1)  # P1 fills in the open epoch
        self._monitor_pass()
        # Position closes through the frozen STOP, then the market returns to the grid.
        stop = _book("HIMSUSDT", "27.96", "27.97", quantity="50", sequence=2)
        self.runtime.process_robot_market_event(
            "HIMSUSDT", stop, event_id="HIMSUSDT:2", received_at_ms=stop.received_at_ms,
        )
        buys = [f for f in self._fills() if f.side is OrderSide.BUY]
        self._event(3)
        self.assertEqual([f for f in self._fills() if f.side is OrderSide.BUY], buys)


class WedgeOwnershipGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = _runtime(Path(self.tmp.name) / "paper.sqlite3")
        self.addCleanup(self.runtime.close)
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        time.sleep(0.02)

    def _limit(self, order_id, action_id):
        self.runtime.store.create_paper_limit(
            client_action_id=action_id, request_fingerprint=f"fp-{order_id}",
            order_id=OrderId(order_id), order_link_id=f"link-{order_id}",
            trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"), side=OrderSide.BUY,
            price=D("64000"), quantity=D("1"), created_at_ms=_now(),
        )

    def _candidate(self, *, status="APPROVED", limit_order_id=None):
        store = self.runtime.store
        store.create_robot_candidate(
            candidate_id="candidate-btc", trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"),
            status="APPROVED", signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
            approved_at_ms=1000, updated_at_ms=1000,
        )
        execution = {} if limit_order_id is None else {"limit_order_id": limit_order_id}
        store.save_robot_candidate_state(
            "candidate-btc", status=status,
            robot_state={"phase": "RETEST_DETECTED", "execution": execution},
            expected_revision=0, updated_at_ms=1001,
        )

    def _match(self):
        return self.runtime._match_limits_only(
            Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
        )

    def _status(self, order_id):
        return self.runtime.store.get_paper_limit(order_id, ACCOUNT).status

    def test_entry_without_a_saved_candidate_link_never_fills(self):
        self._limit("wedge-unlinked", "robot-retest-limit-abc")
        self._candidate(limit_order_id=None)  # crash between submit and link
        self.assertEqual(self._match(), 0)
        self.assertEqual(self._status("wedge-unlinked"), "open")

    def test_entry_of_a_terminal_candidate_never_fills(self):
        self._limit("wedge-orphan", "robot-retest-limit-def")
        self._candidate(status="INVALIDATED", limit_order_id="wedge-orphan")
        self.assertEqual(self._match(), 0)
        self.assertEqual(self._status("wedge-orphan"), "open")

    def test_manual_limit_next_to_an_orphan_still_fills(self):
        self._limit("wedge-orphan", "robot-retest-limit-def")
        self._limit("manual-1", "ui-manual-limit-1")
        self._candidate(status="INVALIDATED", limit_order_id="wedge-orphan")
        self.assertEqual(self._match(), 1)
        self.assertEqual((self._status("wedge-orphan"), self._status("manual-1")),
                         ("open", "filled"))

    def test_entry_stamped_in_the_future_is_not_taken_for_a_current_epoch_order(self):
        self.runtime.store.create_paper_limit(
            client_action_id="robot-retest-limit-future", request_fingerprint="fp-future",
            order_id=OrderId("wedge-future"), order_link_id="link-future",
            trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"), side=OrderSide.BUY,
            price=D("64000"), quantity=D("1"), created_at_ms=_now() + 3_600_000,
        )
        self._candidate(limit_order_id="wedge-future")
        self.assertEqual(self._match(), 0)
        self.assertEqual(self._status("wedge-future"), "open")

    def test_owned_entry_placed_in_the_epoch_still_fills(self):
        self._limit("wedge-live", "robot-retest-limit-ghi")
        self._candidate(limit_order_id="wedge-live")
        self.assertEqual(self._match(), 1)
        self.assertEqual(self._status("wedge-live"), "filled")

    def test_synchronize_cancels_unlinked_and_orphaned_entries_but_not_manual_limits(self):
        self._limit("wedge-unlinked", "robot-retest-limit-abc")
        self._limit("manual-1", "ui-manual-limit-1")
        self._candidate(limit_order_id=None)
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")

        response = self.runtime.robot_synchronize_pending_entries()

        self.assertEqual(response.unresolved_candidate_ids, ())
        self.assertEqual((self._status("wedge-unlinked"), self._status("manual-1")),
                         ("cancelled", "open"))

    def test_failed_orphan_cancel_is_reported_unresolved_and_reconcile_fails_closed(self):
        self._limit("wedge-orphan", "robot-retest-limit-def")
        self._candidate(status="INVALIDATED", limit_order_id="wedge-orphan")
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")

        failed = type("R", (), {"status": CommandResultStatus.UNAVAILABLE})()
        with patch.object(self.runtime, "_robot_cancel_limit", lambda request: failed):
            result = self.runtime.robot_reconcile()

        self.assertFalse(result.success)
        self.assertEqual(result.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(self._status("wedge-orphan"), "open")
        self.assertEqual(self._match(), 0)

    def test_reconcile_retires_the_orphan_and_does_not_hang(self):
        self._limit("wedge-orphan", "robot-retest-limit-def")
        self._candidate(status="INVALIDATED", limit_order_id="wedge-orphan")
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")

        result = self.runtime.robot_reconcile()

        self.assertTrue(result.success, result.reason)
        self.assertEqual(result.recovery_status, "PAUSED")
        self.assertEqual(self._status("wedge-orphan"), "cancelled")


if __name__ == "__main__":
    unittest.main()
