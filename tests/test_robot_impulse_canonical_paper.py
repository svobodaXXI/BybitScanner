"""Opt-in IMPULSE_FLOW: immutable Scanner evidence -> canonical PAPER Robot path.

All market data and order/fill effects here are in-memory stubs. This does
not assert the current publicTrade observer provides source-complete evidence.
"""
from __future__ import annotations

from decimal import Decimal
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import robot_impulse
import robot_protection
from pattern_robot_integration import is_robot_executable_signal
from terminal.application.robot_admission import scanner_candidate_admission_error
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.api.models import CommandResultStatus
from terminal.domain.models import OrderSide


def snapshot(direction="LONG", *, proven=True):
    long = direction == "LONG"
    return {
        "pattern": "IMPULSE_FLOW",
        "symbol": "BTCUSDT",
        "timeframe": "1",
        "robot_handoff_ready": True,
        "impulse": {
            "direction": direction,
            "known_at_ms": 1_800_000,
            "closed_price": "100",
            "structural_extreme": "99" if long else "101",
        },
        "impulse_source": {
            "kind": "GAP_FREE_AUTHENTICATED_TRADE_TAPE",
            "source_complete": proven,
            "receipt_cutoff_proven": True,
            "transport_generation_proven": True,
            "decision_ms": 1_800_000,
        },
    }


class ImpulseCanonicalPolicyTests(unittest.TestCase):
    def test_default_off_rejects_scanner_and_admission(self):
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "0"}):
            self.assertFalse(robot_impulse.paper_enabled())
            self.assertFalse(is_robot_executable_signal(snapshot(), timeframe="1"))
            self.assertEqual(
                scanner_candidate_admission_error({
                    "status": "AVAILABLE", "symbol": "BTCUSDT",
                    "timeframe": "1", "signal_snapshot": snapshot(),
                }),
                "Impulse PAPER Robot is disabled",
            )

    def test_current_observational_tape_cannot_become_executable(self):
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            unproven = snapshot(proven=False)
            self.assertFalse(is_robot_executable_signal(unproven, timeframe="1"))
            self.assertEqual(
                scanner_candidate_admission_error({
                    "status": "AVAILABLE", "symbol": "BTCUSDT",
                    "timeframe": "1", "signal_snapshot": unproven,
                }),
                "Impulse tape and causal M1 source are unproven",
            )
            unproven["impulse_source"]["source_complete"] = True
            unproven["impulse_source"]["kind"] = "BYBIT_PUBLICTRADE_OBSERVATION"
            self.assertFalse(is_robot_executable_signal(unproven, timeframe="1"))
            unproven["impulse_source"]["kind"] = "GAP_FREE_AUTHENTICATED_TRADE_TAPE"
            unproven["impulse_source"]["receipt_cutoff_proven"] = False
            self.assertFalse(is_robot_executable_signal(unproven, timeframe="1"))

    def test_valid_proven_candidate_has_one_canonical_paper_limit(self):
        item = snapshot()
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertTrue(is_robot_executable_signal(item, timeframe="1"))
            self.assertIsNone(scanner_candidate_admission_error({
                "status": "AVAILABLE", "symbol": "BTCUSDT",
                "timeframe": "1", "signal_snapshot": item,
            }))
        state = robot_impulse.initialize_state({
            "status": "APPROVED", "signal_snapshot": item,
        })
        self.assertEqual(state["phase"], robot_impulse.ENTRY_PHASE)
        first = robot_impulse.frozen_entry_request(
            "impulse-1", item, tick_size=Decimal("0.1"),
        )
        second = robot_impulse.frozen_entry_request(
            "impulse-1", item, tick_size=Decimal("0.1"),
        )
        self.assertEqual(first, second)
        self.assertEqual(first.symbol, "BTCUSDT")
        self.assertIs(first.side, OrderSide.BUY)
        self.assertEqual(first.limit_price, Decimal("100"))
        self.assertEqual(first.volume.amount, Decimal("1"))

    def test_long_and_short_protect_actual_fill_with_three_r(self):
        for direction, stop_side in (("LONG", -1), ("SHORT", 1)):
            with self.subTest(direction=direction):
                item = snapshot(direction)
                plan = robot_impulse.protection_after_fill(
                    "impulse-test", item, average_entry=Decimal("100"),
                    tick_size=Decimal("0.1"),
                )
                if stop_side < 0:
                    self.assertLess(plan.stop_price, Decimal("100"))
                    self.assertGreater(plan.take_price, Decimal("100"))
                else:
                    self.assertGreater(plan.stop_price, Decimal("100"))
                    self.assertLess(plan.take_price, Decimal("100"))
                self.assertGreaterEqual(
                    abs(plan.take_price - Decimal("100"))
                    / abs(plan.stop_price - Decimal("100")),
                    Decimal("3"),
                )
                self.assertEqual(plan.stop_request.symbol, "BTCUSDT")
                self.assertEqual(plan.take_request.symbol, "BTCUSDT")

    def test_unproven_or_noncausal_signal_is_rejected(self):
        for defect in ("missing_source", "future", "opposite_extreme", "bad_price"):
            item = snapshot()
            if defect == "missing_source":
                item.pop("impulse_source")
            elif defect == "future":
                item["impulse"]["known_at_ms"] = 1_800_001
            elif defect == "opposite_extreme":
                item["impulse"]["structural_extreme"] = "101"
            else:
                item["impulse"]["closed_price"] = "NaN"
            with self.subTest(defect=defect):
                with self.assertRaises(robot_impulse.ImpulseRobotError):
                    robot_impulse.frozen_terms(item)

    def test_existing_robot_monitor_submits_once_under_all_gates(self):
        item = snapshot()
        monitor = object.__new__(RobotBreakoutMonitor)
        record = SimpleNamespace(
            candidate_id="impulse-1",
            symbol=SimpleNamespace(value="BTCUSDT"),
            signal_snapshot=item,
            robot_state=robot_impulse.initialize_state({
                "status": "APPROVED", "signal_snapshot": item,
            }),
        )
        monitor._now_ms = Mock(return_value=1_800_050)
        monitor._get_closed_candle = Mock(return_value={
            "time_ms": 1_740_000, "close": Decimal("100"),
        })
        monitor._read_admission_gate = Mock(return_value=(True, False))
        monitor._active_other_owner_candidate_ids = Mock(return_value=())
        monitor._pre_entry_block_reason = Mock(return_value=None)
        monitor._arm_entry_coverage = Mock(return_value=True)
        monitor._tick_size_provider = Mock(return_value=Decimal("0.1"))
        monitor._persist_execution = Mock()
        monitor._action_executor = Mock()
        monitor._action_executor.create_limit.return_value = SimpleNamespace(
            order_id="paper-impulse-1",
        )
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertTrue(monitor._advance_impulse(record))
        monitor._action_executor.create_limit.assert_called_once()
        self.assertEqual(
            monitor._persist_execution.call_args.args[1]["limit_order_id"],
            "paper-impulse-1",
        )

    def test_monitor_requires_matching_closed_candle_and_default_off(self):
        item = snapshot()
        monitor = object.__new__(RobotBreakoutMonitor)
        record = SimpleNamespace(
            candidate_id="impulse-2",
            symbol=SimpleNamespace(value="BTCUSDT"),
            signal_snapshot=item,
            robot_state=robot_impulse.initialize_state({
                "status": "APPROVED", "signal_snapshot": item,
            }),
        )
        monitor._action_executor = Mock()
        monitor._now_ms = Mock(return_value=1_800_040)
        monitor._get_closed_candle = Mock(return_value={
            "time_ms": 1_740_000, "close": Decimal("101"),
        })
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "0"}):
            self.assertFalse(monitor._advance_impulse(record))
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertFalse(monitor._advance_impulse(record))
        monitor._action_executor.create_limit.assert_not_called()


class ImpulseDurablePaperCycleTests(unittest.TestCase):
    """Actual SQLite + owner-style fake LIMIT fills; no trading on VPS."""

    def setUp(self):
        from pathlib import Path
        import tempfile
        from terminal.persistence.sqlite_store import SQLiteStore
        from terminal.domain.models import TradingAccountId, Symbol
        from tests.test_robot_breakout_monitor import (
            _Clock, _ScriptedCandleFeed, _FakeActionExecutor,
        )

        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "paper.db"
        self.account = TradingAccountId("paper")
        self.symbol = Symbol("TESTUSDT")
        self.store = SQLiteStore.open(self.path)
        self.store.initialize_robot_runtime_state(self.account, updated_at_ms=1)
        self.store.update_robot_runtime_state(
            self.account, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=1, updated_at_ms=1,
        )
        self.clock = _Clock(1_800_040)
        self.feed = _ScriptedCandleFeed()
        self.executor = _FakeActionExecutor(self.store, self.account, self.clock)
        self.monitor = RobotBreakoutMonitor(
            lambda: SQLiteStore.open(self.path), self.account,
            get_closed_candle=self.feed,
            action_executor=self.executor,
            tick_size_provider=lambda symbol: Decimal("0.1"),
            clock_ms=self.clock,
            arm_entry_coverage=lambda symbol: True,
            release_entry_coverage=lambda symbol: None,
        )

    def tearDown(self):
        self.monitor.close()
        self.store.close()
        self.folder.cleanup()

    def _candidate(self):
        from terminal.domain.models import Symbol

        item = snapshot()
        item["symbol"] = self.symbol.value
        record, created = self.store.create_robot_candidate(
            candidate_id="impulse-e2e", trading_account_id=self.account,
            symbol=self.symbol, status="APPROVED",
            signal_snapshot=item, approved_at_ms=1_800_030,
            updated_at_ms=1_800_030,
        )
        self.assertTrue(created)
        state = robot_impulse.initialize_state({
            "status": "APPROVED", "signal_snapshot": item,
        })
        return self.store.save_robot_candidate_state(
            record.candidate_id, status="APPROVED", robot_state=state,
            expected_revision=record.state_revision, updated_at_ms=1_800_032,
        )

    def test_exact_limit_fill_creates_protected_trade_no_second_entry(self):
        from terminal.domain.models import OrderSide, Category, PositionKey

        candidate = self._candidate()
        self.feed.push(self.symbol.value, {
            "time_ms": 1_740_000, "close": Decimal("100"),
            "high": Decimal("100.1"), "low": Decimal("99.5"),
        })
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertEqual(self.monitor.tick(), (candidate.candidate_id,))
            pending = self.store.get_robot_candidate(candidate.candidate_id)
            order_id = pending.robot_state["execution"]["limit_order_id"]
            self.assertEqual(self.store.get_paper_limit(order_id, self.account).status, "open")
            self.assertEqual(len(self.executor.limit_calls), 1)

            self.executor.fill_resting_limit(
                order_id, self.symbol.value, OrderSide.BUY,
                Decimal("1"), Decimal("100"),
            )
            self.assertEqual(self.monitor.tick(), (candidate.candidate_id,))

            opened = self.store.get_robot_trade("robot-trade-" + candidate.candidate_id)
            self.assertIsNotNone(opened)
            self.assertEqual(opened.pattern, robot_impulse.PATTERN)
            self.assertEqual(opened.entry_path, "LIMIT")
            self.assertEqual(opened.entry_quantity, Decimal("1"))
            self.assertEqual(opened.average_entry, Decimal("100"))
            self.assertEqual(opened.stop_price, Decimal("98.9"))
            self.assertEqual(opened.take_price, Decimal("103.3"))
            projection = self.store.get_protection_projection(
                PositionKey(self.account, Category.LINEAR, self.symbol, 0),
            )
            self.assertEqual(projection.stop_loss, Decimal("98.9"))
            self.assertEqual(projection.take_profit, Decimal("103.3"))
            self.assertEqual(len(self.executor.limit_calls), 1)
            self.assertEqual(
                [label for label, _request in self.executor.protection_calls],
                ["create_stop", "create_take"],
            )
            self.assertEqual(self.monitor.tick(), ())
            self.assertEqual(len(self.executor.limit_calls), 1)

    def test_unmatched_closed_candle_cannot_place_limit(self):
        candidate = self._candidate()
        self.feed.push(self.symbol.value, {
            "time_ms": 1_740_000, "close": Decimal("100.1"),
            "high": Decimal("100.1"), "low": Decimal("99.5"),
        })
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertEqual(self.monitor.tick(), ())
        self.assertEqual(self.executor.limit_calls, [])
        self.assertIsNone(self.store.get_robot_trade("robot-trade-" + candidate.candidate_id))

    def test_expired_impulse_never_submits_order(self):
        candidate = self._candidate()
        self.clock.value = 1_800_000 + robot_impulse.MAX_SIGNAL_AGE_MS + 1
        with patch.dict(os.environ, {robot_impulse.PAPER_OPT_IN: "1"}):
            self.assertEqual(self.monitor.tick(), (candidate.candidate_id,))
        record = self.store.get_robot_candidate(candidate.candidate_id)
        self.assertEqual(record.status, "INVALIDATED")
        self.assertEqual(self.executor.limit_calls, [])


if __name__ == "__main__":
    unittest.main()
