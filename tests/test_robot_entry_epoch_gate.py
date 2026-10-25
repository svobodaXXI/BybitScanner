"""#608 residual risks: a stale or unowned Robot ENTRY LIMIT never fills without fresh admission.

READY alone is not proof that a resting ENTRY is still wanted. The admission epoch is
robot_runtime_state.version (monotonic, never reused): a restart, start from STOPPED or
resume opens a new one, and an ENTRY from an earlier or unknown epoch fills only after the
monitor re-evaluated it in the current one. Robot ENTRY origin is recorded in SQLite with
the LIMIT (robot_entry_orders), not inferred from ids or wall-clock time. An ENTRY no live
candidate owns never fills. Exit LIMITs, STOP/TAKE and manual LIMITs are untouched.
Temporary SQLite only.
"""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal.application.robot_control import resume_robot_in_store
from terminal.api.models import (
    ClientActionId, CommandResultStatus, LimitCommandRequest, VolumeRequest, VolumeUnit,
)
from terminal.domain.models import (
    OrderId, OrderSide, Symbol, TradingAccountId,
)
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_box_first_fill_frozen_stop import (
    HimsOwnerThreadFillTests, _hims_instrument, _p1_book,
)
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument
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

    def test_restart_with_the_clock_set_back_fails_closed_then_needs_confirmation(self):
        path = Path(self.tmp.name) / "paper.sqlite3"
        before = self.runtime.store.get_robot_runtime_state(ACCOUNT)
        self.runtime.close()

        def reopen():
            return PaperRuntime(
                path, book_provider=StaticBookProvider(), instrument_snapshot=_instrument(),
                instrument_provider=_hims_instrument,
            )

        # Power loss resets the clock one hour back: the epoch cannot advance and
        # the runtime refuses to start rather than reuse the old READY.
        with patch("time.time", return_value=before.updated_at_ms / 1000 - 3600):
            with self.assertRaises(Exception):
                reopen()
        unchanged = SQLiteStore.open(path)
        try:
            self.assertEqual(unchanged.get_robot_runtime_state(ACCOUNT), before)
        finally:
            unchanged.close()

        # Clock corrected: restart opens a new epoch; the old grid waits for the monitor.
        self.runtime = reopen()
        self.addCleanup(self.runtime.close)
        self.assertGreater(self.runtime.store.get_robot_runtime_state(ACCOUNT).version,
                           before.version)
        self._assert_filled_once_confirmed(1)

    def test_clock_jump_forward_does_not_age_or_refresh_an_entry(self):
        later = time.time() + 30 * 24 * 3600
        with patch("time.time", return_value=later):
            self._event(1)  # same epoch, clock jumped a month ahead: still a current ENTRY
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
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.runtime = _runtime(self.path)
        self.addCleanup(lambda: self.runtime.close())
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")

    def _limit(self, order_id, action_id, *, robot=True, created_at_ms=None):
        self.runtime.store.create_paper_limit(
            client_action_id=action_id, request_fingerprint=f"fp-{order_id}",
            order_id=OrderId(order_id), order_link_id=f"link-{order_id}",
            trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"), side=OrderSide.BUY,
            price=D("64000"), quantity=D("1"),
            created_at_ms=_now() if created_at_ms is None else created_at_ms,
            robot_entry=robot,
        )

    def _candidate(self, *, status="APPROVED", limit_order_id=None, candidate_id="candidate-btc"):
        store = self.runtime.store
        store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=ACCOUNT, symbol=Symbol("BTCUSDT"),
            status="APPROVED", signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge",
                                                "id": candidate_id},
            approved_at_ms=1000, updated_at_ms=1000,
        )
        execution = {} if limit_order_id is None else {"limit_order_id": limit_order_id}
        store.save_robot_candidate_state(
            candidate_id, status=status,
            robot_state={"phase": "RETEST_DETECTED", "execution": execution},
            expected_revision=0, updated_at_ms=1001,
        )

    def _confirm(self, version, candidate_id="candidate-btc"):
        # What RobotBreakoutMonitor._confirm_entry_admission persists after its checks.
        store = self.runtime.store
        record = store.get_robot_candidate(candidate_id)
        state = dict(record.robot_state)
        state["execution"] = {**state["execution"], "entry_admission_version": version}
        store.save_robot_candidate_state(
            candidate_id, status=record.status, robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=_now(),
        )

    def _version(self):
        return self.runtime.store.get_robot_runtime_state(ACCOUNT).version

    def _match(self):
        return self.runtime._match_limits_only(
            Symbol("BTCUSDT"), _book("BTCUSDT", "63990", "63995"), "BTCUSDT:1",
        )

    def _status(self, order_id):
        return self.runtime.store.get_paper_limit(order_id, ACCOUNT).status

    def _new_epoch(self):
        # A fresh READY epoch (pause + resume). Restart recovery of this minimal
        # Wedge lands RECONCILIATION_REQUIRED (no closed-candle evidence); restart
        # into READY is covered by BoxEpochGateTests.
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="PAUSED")
        resume_robot_in_store(self.runtime.store, clock_ms=_now)

    # --- origin --------------------------------------------------------------------

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

    def test_origin_does_not_depend_on_the_action_id_prefix(self):
        # A future Robot writer with an id nobody has listed is still a Robot ENTRY.
        result = self.runtime._robot_create_limit(LimitCommandRequest(
            ClientActionId("robot-some-new-entry-kind-1"), "BTCUSDT", OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, D("64000")), D("64000"), D("64000"),
        ))
        self.assertIs(result.status, CommandResultStatus.COMPLETED)
        entries = self.runtime.store.load_active_robot_entry_orders(ACCOUNT)
        self.assertEqual(entries[result.order_id][1], self._version())
        self.assertEqual(self._match(), 0)  # no owning candidate yet
        self._candidate(limit_order_id=result.order_id)
        self.assertEqual(self._match(), 1)  # owned and created in this epoch

    def test_manual_limits_stay_manual_whatever_their_id(self):
        self._limit("wedge-orphan", "robot-retest-limit-def")
        self._limit("manual-1", "robot-retest-limit-looks-like-robot", robot=False)
        self._candidate(status="INVALIDATED", limit_order_id="wedge-orphan")
        self.assertEqual(self._match(), 1)
        self.assertEqual((self._status("wedge-orphan"), self._status("manual-1")),
                         ("open", "filled"))

    def test_legacy_limits_are_classified_once_from_evidence_and_need_confirmation(self):
        self._limit("legacy-prefixed", "robot-retest-limit-old", robot=False)
        self._limit("legacy-linked", "6f9c1d1e-uuid-like", robot=False)
        self._limit("manual-old", "8a1b2c3d-uuid-like", robot=False)
        self._candidate(limit_order_id="legacy-linked")
        self.runtime.store._connection.execute("DROP TABLE robot_entry_orders")  # pre-#608 DB
        self.runtime.close()

        self.runtime = _runtime(self.path)
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        entries = self.runtime.store.load_active_robot_entry_orders(ACCOUNT)
        self.assertEqual({order_id: epoch for order_id, (_s, epoch) in entries.items()},
                         {"legacy-prefixed": None, "legacy-linked": None})
        self.assertEqual(self._match(), 1)  # only the manual LIMIT
        self.assertEqual(
            (self._status("legacy-prefixed"), self._status("legacy-linked"),
             self._status("manual-old")),
            ("open", "open", "filled"),
        )
        self._confirm(self._version())  # the monitor re-evaluated the linked one now
        self.assertEqual(self._match(), 1)
        self.assertEqual(self._status("legacy-linked"), "filled")

    # --- epoch -----------------------------------------------------------------------

    def test_owned_entry_created_in_the_epoch_fills_without_waiting(self):
        self._limit("wedge-live", "robot-retest-limit-ghi")
        self._candidate(limit_order_id="wedge-live")
        self.assertEqual(self._match(), 1)
        self.assertEqual(self._status("wedge-live"), "filled")

    def test_old_entry_waits_after_every_new_epoch_until_confirmed_in_it(self):
        self._limit("wedge-live", "robot-retest-limit-ghi")
        self._candidate(limit_order_id="wedge-live")
        for _ in range(2):  # repeated READY
            self._new_epoch()
            self.assertEqual(self._match(), 0)
        self._confirm(self._version() - 2)  # confirmed in the previous READY epoch
        self.assertEqual(self._match(), 0)  # a confirmation from an older epoch does not count
        self._confirm(self._version())
        self.assertEqual(self._match(), 1)

    def test_wall_clock_times_never_decide_the_epoch(self):
        hour = 3_600_000
        self._limit("wedge-future", "robot-retest-limit-f", created_at_ms=_now() + 24 * hour)
        self._candidate(limit_order_id="wedge-future")
        self._new_epoch()
        self.assertEqual(self._match(), 0)  # stamped a day ahead, still an old epoch
        self.assertEqual(self._status("wedge-future"), "open")

        self._limit("wedge-past", "robot-retest-limit-p", created_at_ms=1000)
        self._candidate(limit_order_id="wedge-past", candidate_id="candidate-p")
        self.assertEqual(self._match(), 1)  # stamped in 1970, yet created in this epoch
        self.assertEqual((self._status("wedge-past"), self._status("wedge-future")),
                         ("filled", "open"))

    def _robot_entry(self, action_id):
        result = self.runtime._robot_create_limit(LimitCommandRequest(
            ClientActionId(action_id), "BTCUSDT", OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, D("64000")), D("64000"), D("64000"),
        ))
        self.assertIs(result.status, CommandResultStatus.COMPLETED)
        return result.order_id

    def test_clock_set_back_then_catching_up_never_revives_an_old_entry(self):
        # Created while the clock ran a day ahead; the clock is then corrected,
        # a new READY epoch opens, and later the clock passes the ENTRY's stamp.
        day = 24 * 3600
        with patch("time.time", return_value=time.time() + day):
            order_id = self._robot_entry("robot-retest-limit-clock")
        self._candidate(limit_order_id=order_id)
        self._new_epoch()
        with patch("time.time", return_value=time.time() + 2 * day):
            self.assertEqual(self._match(), 0)
        self.assertEqual(self._status(order_id), "open")

    def test_orphan_with_an_unlisted_action_id_never_fills(self):
        order_id = self._robot_entry("robot-some-new-entry-kind-2")
        self._candidate(status="INVALIDATED", limit_order_id=order_id)
        self.assertEqual(self._match(), 0)
        self.assertEqual(self._status(order_id), "open")

    # --- retirement ----------------------------------------------------------------

    def test_synchronize_cancels_unlinked_and_orphaned_entries_but_not_manual_limits(self):
        self._limit("wedge-unlinked", "robot-retest-limit-abc")
        self._limit("manual-1", "ui-manual-limit-1", robot=False)
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
