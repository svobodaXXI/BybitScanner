"""SAFE STOP 2026-10-14: synchronize-pending-entries ends pre-entry Wedge ideas.

Four APPROVED Wedge candidates (WAITING_BREAKOUT / WAITING_RETEST / RETEST_DETECTED)
without order, fill or exposure kept ``robot_entry_ownership_unresolved`` and blocked
stop_robot. Under ROBOT_STOPPED they are now terminalized -- but only from durable
PAPER evidence: a missing ``limit_order_id`` alone is not proof, because an entry
whose caller timed out may still have been executed by the owner (AAVEUSDT).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from terminal.domain.models import OrderId, OrderSide, Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_robot_breakout_monitor_admission_catchup import SYMBOL, _snapshot
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument

ACCOUNT = TradingAccountId("paper")
PHASES = ("WAITING_BREAKOUT", "WAITING_RETEST", "RETEST_DETECTED")


class _Execution:
    def __init__(self, at_ms):
        self.exchange_timestamp_ms = at_ms


class StoppedPreEntryWedgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target in ("latest_scanner_closed_candle", "load_scanner_catchup_closed_candles"):
            patcher = patch(f"terminal.runtime.paper_runtime.{target}",
                            side_effect=RuntimeError("no kline in this test"))
            patcher.start()
            self.addCleanup(patcher.stop)
        primary = _instrument()
        self.runtime = PaperRuntime(
            Path(self.tmp.name) / "paper.sqlite3", book_provider=StaticBookProvider(),
            instrument_snapshot=primary,
            instrument_provider=lambda symbol: replace(primary, symbol=symbol),
        )
        self.addCleanup(self.runtime.close)
        self.store = self.runtime.store
        self.apex = 130

    def candidate(self, candidate_id, phase, *, execution=None):
        record, _ = self.store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=ACCOUNT, symbol=Symbol(SYMBOL),
            status="APPROVED", signal_snapshot=self.next_snapshot(), approved_at_ms=1_000,
            updated_at_ms=1_000,
        )
        state = {"phase": phase, "direction": "LONG", "geometry_cursor": 101,
                 "breakout_index": None if phase == "WAITING_BREAKOUT" else 101,
                 "retest_index": 102 if phase == "RETEST_DETECTED" else None,
                 "execution": dict(execution or {})}
        self.store.save_robot_candidate_state(
            candidate_id, status="APPROVED", robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=1_100,
        )

    def next_snapshot(self):
        self.apex += 1  # one admitted snapshot identity per candidate
        return _snapshot(apex_index=self.apex)

    def sync(self):
        return self.runtime.robot_synchronize_pending_entries()

    def status(self, candidate_id):
        return self.store.get_robot_candidate(candidate_id).status

    def test_each_pre_entry_phase_is_terminalized_without_side_effects(self):
        self.assertEqual(self.store.get_robot_runtime_state(ACCOUNT).mode, "ROBOT_STOPPED")
        for phase in PHASES:
            with self.subTest(phase=phase):
                self.candidate(f"w-{phase}", phase)
                response = self.sync()
                self.assertEqual(self.status(f"w-{phase}"), "INVALIDATED")
                self.assertIn(f"w-{phase}", response.terminalized_candidate_ids)
                self.assertEqual(response.unresolved_candidate_ids, ())
                record = self.store.get_robot_candidate(f"w-{phase}")
                self.assertEqual(record.robot_state["phase"], phase)
                self.assertIn("stopped_without_entry_reason", record.robot_state["execution"])
        self.assertEqual(self.store.load_open_position_projections(ACCOUNT), ())
        self.assertEqual(len(self.store.load_executions()), 0)

    def test_late_owner_entry_without_recorded_order_id_keeps_the_candidate(self):
        # The candidate recorded only a timeout; the owner still created the LIMIT.
        self.candidate("late", "RETEST_DETECTED",
                       execution={"last_execution_error": "PAPER runtime operation timed out"})
        self.store.create_paper_limit(
            client_action_id="robot-retest-limit-late", request_fingerprint="fp",
            order_id=OrderId("paper-limit-late"), order_link_id="late-link",
            trading_account_id=ACCOUNT, symbol=Symbol(SYMBOL), side=OrderSide.BUY,
            price=Decimal("90"), quantity=Decimal("1"), created_at_ms=1_200,
        )
        self.sync()
        self.assertEqual(self.status("late"), "APPROVED")
        self.assertEqual(len(self.store.load_active_paper_limits(ACCOUNT, Symbol(SYMBOL))), 1)

    def test_any_fill_since_approval_or_unfinished_command_keeps_the_candidate(self):
        self.candidate("filled", "WAITING_RETEST")
        with patch.object(self.store, "load_executions_for_symbol",
                          return_value=(_Execution(1_500),)):
            self.sync()
        self.assertEqual(self.status("filled"), "APPROVED")

        class _Command:
            trading_account_id = ACCOUNT
            symbol = Symbol(SYMBOL)

        with patch.object(self.store, "load_unfinished_commands", return_value=(_Command(),)):
            self.sync()
        self.assertEqual(self.status("filled"), "APPROVED")
        # An old fill from before approval is not this idea's.
        with patch.object(self.store, "load_executions_for_symbol",
                          return_value=(_Execution(999),)):
            self.sync()
        self.assertEqual(self.status("filled"), "INVALIDATED")

    def test_running_robot_never_terminalizes_through_this_rule(self):
        self.candidate("paused", "WAITING_BREAKOUT")
        stopped = self.store.get_robot_runtime_state(ACCOUNT)
        self.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="PAUSED", reason=None,
            expected_version=stopped.version, updated_at_ms=int(time.time() * 1000),
        )
        response = self.sync()
        self.assertEqual(self.status("paused"), "APPROVED")
        self.assertEqual(response.terminalized_candidate_ids, ())


if __name__ == "__main__":
    unittest.main()
