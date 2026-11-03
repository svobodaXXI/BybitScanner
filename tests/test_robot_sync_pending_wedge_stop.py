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

    def test_frozen_canonical_reconciliation_retires_only_never_filled(self):
        self.candidate("frozen", "WAITING_RETEST")
        stopped = self.store.get_robot_runtime_state(ACCOUNT)
        self.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILING", reason=None,
            expected_version=stopped.version, updated_at_ms=int(time.time() * 1000),
        )
        scanner = self.store.get_scanner_runtime_state(ACCOUNT)
        autopilot = self.store.get_robot_autopilot_state(ACCOUNT)
        self.assertEqual(scanner.mode, "SCANNER_STOPPED")
        self.assertEqual(autopilot.mode, "OFF")
        response = self.sync()
        self.assertEqual(self.status("frozen"), "INVALIDATED")
        self.assertIn("frozen", response.terminalized_candidate_ids)
        self.assertIn(
            "FROZEN_RECONCILING",
            self.store.get_robot_candidate("frozen")
            .robot_state["execution"]["stopped_without_entry_reason"],
        )

    def test_reconciliation_rejects_unfrozen_scanner_or_autopilot(self):
        self.candidate("unfrozen", "WAITING_BREAKOUT")
        stopped = self.store.get_robot_runtime_state(ACCOUNT)
        self.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILING", reason=None,
            expected_version=stopped.version, updated_at_ms=int(time.time() * 1000),
        )
        scanner = self.store.get_scanner_runtime_state(ACCOUNT)
        self.store.update_scanner_runtime_state(
            ACCOUNT, mode="SCANNER_RUNNING",
            expected_version=scanner.version, updated_at_ms=int(time.time() * 1000),
        )
        self.sync()
        self.assertEqual(self.status("unfrozen"), "APPROVED")
        scanner = self.store.get_scanner_runtime_state(ACCOUNT)
        self.store.update_scanner_runtime_state(
            ACCOUNT, mode="SCANNER_STOPPED",
            expected_version=scanner.version, updated_at_ms=int(time.time() * 1000),
        )
        autopilot = self.store.get_robot_autopilot_state(ACCOUNT)
        self.store.update_robot_autopilot_state(
            ACCOUNT, mode="PAPER_AUTO",
            expected_version=autopilot.version, updated_at_ms=int(time.time() * 1000),
        )
        self.sync()
        self.assertEqual(self.status("unfrozen"), "APPROVED")

    def test_frozen_reconciliation_preserves_any_post_approval_fill(self):
        self.candidate("filled-frozen", "RETEST_DETECTED")
        stopped = self.store.get_robot_runtime_state(ACCOUNT)
        self.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILING", reason=None,
            expected_version=stopped.version, updated_at_ms=int(time.time() * 1000),
        )
        with patch.object(self.store, "load_executions_for_symbol",
                          return_value=(_Execution(1_500),)):
            self.sync()
        self.assertEqual(self.status("filled-frozen"), "APPROVED")

    def frozen_incident_idea(self, cid="frozen-nonwedge", *, symbol="BNCUSDT",
                            approved_at_ms=1_000):
        record, _ = self.store.create_robot_candidate(
            candidate_id=cid, trading_account_id=ACCOUNT, symbol=Symbol(symbol),
            status="APPROVED",
            signal_snapshot={"symbol": symbol, "pattern": "MIRROR",
                             "case": cid},
            approved_at_ms=approved_at_ms, updated_at_ms=approved_at_ms,
        )
        return record

    def frozen_reconcile_state(self):
        stopped = self.store.get_robot_runtime_state(ACCOUNT)
        self.store.update_robot_runtime_state(
            ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILING",
            reason=None, expected_version=stopped.version,
            updated_at_ms=int(time.time() * 1000),
        )

    def test_incident_only_untraded_nonwedge_retires_under_frozen_reconcile(self):
        self.frozen_reconcile_state()
        idea = self.frozen_incident_idea()
        self.assertTrue(self.runtime._terminalize_frozen_incident_never_traded(idea))
        self.assertEqual(self.status(idea.candidate_id), "INVALIDATED")
        execution = self.store.get_robot_candidate(idea.candidate_id).robot_state["execution"]
        self.assertIn("FROZEN_20261103", execution["stopped_without_entry_reason"])

    def test_incident_nonwedge_refuses_other_symbol_future_idea_or_unfrozen(self):
        self.frozen_reconcile_state()
        other = self.frozen_incident_idea("other", symbol="OTHERUSDT")
        future = self.frozen_incident_idea(
            "future", symbol="HEMIUSDT", approved_at_ms=1_793_703_600_001,
        )
        assert not self.runtime._terminalize_frozen_incident_never_traded(other)
        assert not self.runtime._terminalize_frozen_incident_never_traded(future)
        valid = self.frozen_incident_idea("unfrozen", symbol="INUSDT")
        scanner = self.store.get_scanner_runtime_state(ACCOUNT)
        self.store.update_scanner_runtime_state(
            ACCOUNT, mode="SCANNER_RUNNING", expected_version=scanner.version,
            updated_at_ms=int(time.time() * 1000),
        )
        assert not self.runtime._terminalize_frozen_incident_never_traded(valid)
        self.assertEqual(self.status("unfrozen"), "APPROVED")

    def test_incident_nonwedge_refuses_fill_order_and_competing_owner(self):
        self.frozen_reconcile_state()
        idea = self.frozen_incident_idea("filled-candidate", symbol="RUNEUSDT")
        # Immutable execution history later than approval must block.
        with patch.object(self.store, "prove_approved_candidate_never_traded", return_value=False):
            assert not self.runtime._terminalize_frozen_incident_never_traded(idea)
        self.assertEqual(self.status("filled-candidate"), "APPROVED")
        self.store.create_paper_limit(
            client_action_id="pending-limit-for-frozen", request_fingerprint="fp",
            order_id=OrderId("paper-limit-frozen"), order_link_id="frozen-link",
            trading_account_id=ACCOUNT, symbol=Symbol("RUNEUSDT"), side=OrderSide.BUY,
            price=Decimal("90"), quantity=Decimal("1"), created_at_ms=1_200,
        )
        self.assertFalse(self.store.prove_approved_candidate_never_traded(idea))
        assert not self.runtime._terminalize_frozen_incident_never_traded(idea)
        self.assertEqual(self.status("filled-candidate"), "APPROVED")

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
