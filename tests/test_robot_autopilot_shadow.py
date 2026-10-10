"""Autopilot SHADOW First Eligible (issue #446, slice A1). Temporary DBs only.

SHADOW evaluates each arrived candidate once with the existing Stage A policy and
appends to the existing audit. It must never admit, plan or trade.
"""

import tempfile
import time
import unittest
from pathlib import Path
from decimal import Decimal

import pattern_robot_integration as integration
from robot_candidate_store import create_signal_snapshot, load_candidate
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW, OUTCOME_REJECT, OUTCOME_WAIT, POLICY_VERSION, REASON_ELIGIBLE,
    REASON_CANDIDATE_INVALID, REASON_CANDIDATE_NOT_EXECUTABLE, REASON_PORTFOLIO_POLICY_UNSET,
    REASON_PROTECTION_HEALTH_UNKNOWN, REASON_PROTECTION_UNHEALTHY, REASON_ROBOT_NOT_READY,
    REASON_SYMBOL_OWNED,
)
from terminal.application.robot_autopilot_shadow import (
    SOURCE_BOX_PLAN, SOURCE_SCANNER, observe_shadow_candidate,
)
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_continuity_recovery_candidate_snapshot import _runtime
from tests.test_terminal_paper_runtime import _CONFIRMED_BOX_FORMATION, _set_admission

ACCOUNT = TradingAccountId("paper")
TRADING_TABLES = ("paper_limit_orders", "executions", "trading_commands", "robot_trades")


def _wedge(directory, candidate_id="wedge-1", symbol="ONGUSDT", timeframe="1", **extra):
    snapshot = {
        "symbol": symbol, "pattern": "Falling Wedge",
        "geometry": {"current_index": 10, "apex": {"index": 30},
                     "upper_line": {"slope": 0.1, "intercept": 10},
                     "lower_line": {"slope": -0.1, "intercept": 20}},
        **extra,
    }
    return create_signal_snapshot(snapshot, timeframe=timeframe, store_dir=directory,
                                  candidate_id=candidate_id, created_at="2026-10-10T00:00:00+00:00")


def _l_shape(directory, candidate_id="lshape-1", reward_risk=2.5, symbol="ONGUSDT"):
    return create_signal_snapshot({
        "symbol": symbol, "pattern": "L-shape", "timeframe": "5", "scanner_source_timeframe": "5",
        "robot_handoff_ready": True,
        "l_shape": {"direction": "LONG", "source_timeframe": "5", "breakout_time_ms": 1_000_000,
                    "extreme_time_ms": 900_000, "reference": 100, "target": 110, "stop": 96,
                    "stop_kind": "STRUCTURAL", "structural_stop": 96, "potential_percent": 10,
                    "reward_risk": reward_risk},
    }, timeframe="5", store_dir=directory, candidate_id=candidate_id,
        created_at="2026-10-10T00:00:00+00:00")


class _Db:
    """A temporary PAPER store with a durable Robot/Autopilot state."""

    def __init__(self, root: Path, *, autopilot="SHADOW", robot=("ROBOT_RUNNING", "READY")):
        self.candidates = root / "candidates"
        self.store = SQLiteStore.open(root / "paper.sqlite3")
        self.store.initialize_paper_account(ACCOUNT, Decimal("5000"), updated_at_ms=1)
        state = self.store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=1000)
        self.store.update_robot_runtime_state(ACCOUNT, mode=robot[0], recovery_status=robot[1],
                                              reason=None, expected_version=state.version,
                                              updated_at_ms=1001)
        ap = self.store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=1000)
        if autopilot != "OFF":
            self.store.update_robot_autopilot_state(ACCOUNT, mode=autopilot,
                                                    expected_version=ap.version, updated_at_ms=1001)

    def observe(self, ref, source=SOURCE_SCANNER, health=None, now=5000):
        return observe_shadow_candidate(
            self.store, ACCOUNT, source=source, candidate_ref=ref,
            protection_healthy=health, candidate_store_dir=self.candidates, clock_ms=lambda: now,
        )

    def decisions(self):
        return self.store.load_robot_auto_decisions(ACCOUNT)

    def footprint(self):
        c = self.store._connection
        return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (*TRADING_TABLES, "robot_candidates"))


class ShadowObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _db(self, **kwargs):
        db = _Db(self.root, **kwargs)
        self.addCleanup(lambda: db.store.close())
        return db

    def test_off_writes_nothing_and_changes_nothing(self):
        db = self._db(autopilot="OFF")
        _wedge(db.candidates)
        before = db.footprint()
        self.assertIsNone(db.observe("wedge-1", health=lambda: True))
        self.assertEqual(db.decisions(), ())
        self.assertEqual(db.footprint(), before)

    def test_shadow_records_a_decision_without_any_trading_side_effect(self):
        db = self._db()
        _wedge(db.candidates)
        before = db.footprint()

        unknown = db.observe("wedge-1")
        self.assertEqual((unknown.result.outcome, unknown.result.reason_code),
                         (OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN))
        record = unknown.decision
        self.assertEqual((record.mode, record.policy_version, record.pattern, record.symbol.value,
                          record.timeframe, record.resulting_candidate_id),
                         ("SHADOW", POLICY_VERSION, "Falling Wedge", "ONGUSDT", "1", None))
        # Nothing approved, admitted or traded; the JSON candidate stays AVAILABLE.
        self.assertEqual(db.footprint(), before)
        self.assertIsNone(db.store.get_robot_candidate("wedge-1"))
        self.assertEqual(load_candidate("wedge-1", store_dir=db.candidates)["status"], "AVAILABLE")

    def test_owner_approved_portfolio_policy_allows_empty_portfolio(self):
        db = self._db()
        _wedge(db.candidates)
        result = db.observe("wedge-1", health=lambda: True).result
        self.assertEqual((result.outcome, result.reason_code), (OUTCOME_ALLOW, REASON_ELIGIBLE))

    def test_unhealthy_or_failing_protection_source_never_counts_as_healthy(self):
        db = self._db()
        _wedge(db.candidates, "w-a")
        _wedge(db.candidates, "w-b", symbol="AAAUSDT")
        self.assertEqual(db.observe("w-a", health=lambda: False).result.reason_code,
                         REASON_PROTECTION_UNHEALTHY)

        def broken():
            raise RuntimeError("coverage manager unavailable")

        self.assertEqual(db.observe("w-b", health=broken).result.reason_code,
                         REASON_PROTECTION_HEALTH_UNKNOWN)

    def test_robot_not_ready_waits(self):
        db = self._db(robot=("ROBOT_STOPPED", "ROBOT_STOPPED"))
        _wedge(db.candidates)
        result = db.observe("wedge-1", health=lambda: True).result
        self.assertEqual((result.outcome, result.reason_code), (OUTCOME_WAIT, REASON_ROBOT_NOT_READY))

    def test_wedge_and_l_shape_keep_their_own_gates(self):
        db = self._db()
        # Wedge 5m without a proven 1m handoff/geometry is not admissible.
        _wedge(db.candidates, "w5", timeframe="5")
        # L-shape below its frozen 2:1 reward/risk is not admissible.
        _l_shape(db.candidates, "l-low", reward_risk=1.5)
        # Unsupported pattern.
        create_signal_snapshot({"symbol": "ONGUSDT", "pattern": "Triangle Compression"},
                               timeframe="1", store_dir=db.candidates, candidate_id="tri")
        for ref, outcome, reason in (
            ("w5", OUTCOME_REJECT, REASON_CANDIDATE_INVALID),
            ("l-low", OUTCOME_REJECT, REASON_CANDIDATE_INVALID),
            ("tri", OUTCOME_REJECT, REASON_CANDIDATE_INVALID),
        ):
            with self.subTest(ref=ref):
                result = db.observe(ref, health=lambda: True).result
                self.assertEqual((result.outcome, result.reason_code), (outcome, reason))
        # A valid L-shape passes its own gate and reaches the portfolio gate.
        _l_shape(db.candidates, "l-ok", reward_risk=2.5, symbol="BBBUSDT")
        self.assertEqual(db.observe("l-ok", health=lambda: True).result.reason_code,
                         REASON_ELIGIBLE)

    def test_not_executable_snapshot_is_rejected(self):
        db = self._db()
        _wedge(db.candidates, "obs", scanner_observational_only=True)
        result = db.observe("obs", health=lambda: True).result
        self.assertIn(result.reason_code, {REASON_CANDIDATE_NOT_EXECUTABLE, REASON_CANDIDATE_INVALID})
        self.assertEqual(result.outcome, OUTCOME_REJECT)

    def test_repeated_event_is_recorded_once_and_later_symbol_signal_waits(self):
        db = self._db()
        _wedge(db.candidates, "first")
        first = db.observe("first", health=lambda: True, now=5000)
        again = db.observe("first", health=lambda: True, now=6000)
        self.assertTrue(first.created)
        self.assertFalse(again.created)
        self.assertEqual(len(db.decisions()), 1)

        # The owner manually admits a different idea on the same symbol; a later
        # arriving signal for that symbol must not compete with it.
        _wedge(db.candidates, "manual")
        from terminal.application.robot_admission import admit_robot_candidate
        db.store.close()
        admit_robot_candidate("manual", database_path=self.root / "paper.sqlite3",
                              store_dir=db.candidates, clock_ms=lambda: 7000)
        db.store = SQLiteStore.open(self.root / "paper.sqlite3")
        _wedge(db.candidates, "later")
        later = db.observe("later", health=lambda: True, now=8000)
        self.assertEqual((later.result.outcome, later.result.reason_code), (OUTCOME_WAIT, REASON_SYMBOL_OWNED))
        self.assertEqual([d.candidate_ref for d in db.decisions()], ["first", "later"])  # arrival order


class ShadowRuntimeHookTests(unittest.TestCase):
    def _runtime(self, temp, mode):
        runtime = _runtime(temp)
        runtime._robot_command_dispatcher = lambda operation: operation(runtime)
        if mode != "OFF":
            runtime.set_autopilot_mode(mode)
        return runtime

    def _footprint(self, runtime):
        c = runtime.store._connection
        return tuple(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TRADING_TABLES)

    def test_box_plan_freeze_is_observed_in_shadow_without_admission(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp, "SHADOW")
            try:
                runtime.bind_autopilot_protection_health(lambda: True)
                before = self._footprint(runtime)
                source_id = runtime._dispatch_ikigai_box_plan_preparation(
                    "BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)
                decisions = runtime.store.load_robot_auto_decisions(ACCOUNT)
                self.assertEqual([(d.candidate_ref, d.pattern, d.reason_code) for d in decisions],
                                 [(source_id, "IKIGAI_BOX", REASON_ELIGIBLE)])
                self.assertEqual(runtime.store.get_robot_candidate(source_id).status, "BOX_PLAN_ONLY")
                linked = [c for c in runtime.store.load_robot_candidates(ACCOUNT)
                          if c.status != "BOX_PLAN_ONLY"]
                self.assertEqual(linked, [])
                self.assertEqual(self._footprint(runtime), before)
                # The same Box arriving again (repeated Scanner pass) is not re-recorded.
                runtime._dispatch_ikigai_box_plan_preparation("BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)
                self.assertEqual(len(runtime.store.load_robot_auto_decisions(ACCOUNT)), 1)
            finally:
                runtime.close()

    def test_shadow_failure_never_blocks_box_freeze_or_scanner_handoff(self):
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp, "SHADOW")
            try:
                with patch("terminal.runtime.paper_runtime.observe_shadow_candidate",
                           side_effect=RuntimeError("shadow failure")):
                    source_id = runtime._dispatch_ikigai_box_plan_preparation(
                        "BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)
                self.assertEqual(runtime.store.get_robot_candidate(source_id).status, "BOX_PLAN_ONLY")
                self.assertEqual(runtime.store.load_robot_auto_decisions(ACCOUNT), ())

                # An unbound or failing owner dispatch must not break the Scanner handoff.
                runtime._robot_command_dispatcher = None
                original = integration.create_signal_snapshot
                integration.create_signal_snapshot = lambda snapshot, *, timeframe: create_signal_snapshot(
                    snapshot, timeframe=timeframe, store_dir=Path(temp) / "candidates")
                try:
                    with integration.robot_candidate_observer(
                            runtime._dispatch_autopilot_shadow_scanner_candidate):
                        handoff = integration.prepare_robot_handoff(
                            {"symbol": "ONGUSDT", "pattern": "Falling Wedge"}, timeframe="1", enabled=True)
                finally:
                    integration.create_signal_snapshot = original
                self.assertTrue(handoff.executable and handoff.candidate_id)
            finally:
                runtime.close()

    def test_box_plan_freeze_with_autopilot_off_records_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = self._runtime(temp, "OFF")
            try:
                runtime._dispatch_ikigai_box_plan_preparation("BTCUSDT", "5", _CONFIRMED_BOX_FORMATION)
                self.assertEqual(runtime.store.load_robot_auto_decisions(ACCOUNT), ())
            finally:
                runtime.close()

    def test_paper_auto_is_rejected_and_never_survives_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            runtime = self._runtime(temp, "SHADOW")
            try:
                with self.assertRaises(ValueError):
                    runtime.set_autopilot_mode("PAPER_AUTO")
                self.assertEqual(runtime.autopilot_state().mode, "SHADOW")
                # Simulate a durable PAPER_AUTO left by some other writer.
                state = runtime.store.get_robot_autopilot_state(ACCOUNT)
                runtime.store.update_robot_autopilot_state(
                    ACCOUNT, mode="PAPER_AUTO", expected_version=state.version,
                    updated_at_ms=int(time.time() * 1000) + 1)
            finally:
                runtime.close()
            restarted = _runtime(temp)
            try:
                state = restarted.autopilot_state()
                self.assertEqual((state.mode, state.reason), ("OFF", "restart_recovery"))
            finally:
                restarted.close()
            self.assertTrue(path.exists())

    def test_shadow_survives_restart_and_off_is_the_default(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                self.assertEqual(runtime.autopilot_state().mode, "OFF")
                runtime.set_autopilot_mode("SHADOW")
            finally:
                runtime.close()
            restarted = _runtime(temp)
            try:
                self.assertEqual(restarted.autopilot_state().mode, "SHADOW")
            finally:
                restarted.close()


class CandidateObserverScopeTests(unittest.TestCase):
    def test_observer_is_scoped_and_its_failure_never_breaks_the_handoff(self):
        seen = []
        with tempfile.TemporaryDirectory() as temp:
            original = integration.create_signal_snapshot
            integration.create_signal_snapshot = lambda snapshot, *, timeframe: create_signal_snapshot(
                snapshot, timeframe=timeframe, store_dir=Path(temp))
            try:
                snapshot = {"symbol": "ONGUSDT", "pattern": "Falling Wedge"}
                self.assertIsNone(integration._candidate_observer.get())
                with integration.robot_candidate_observer(seen.append):
                    result = integration.prepare_robot_handoff(snapshot, timeframe="1", enabled=True)
                self.assertEqual(seen, [result.candidate_id])
                self.assertIsNone(integration._candidate_observer.get())

                def broken(_candidate_id):
                    raise RuntimeError("observer failure")

                with integration.robot_candidate_observer(broken):
                    result = integration.prepare_robot_handoff(snapshot, timeframe="1", enabled=True)
                self.assertTrue(result.executable and result.candidate_id)
            finally:
                integration.create_signal_snapshot = original


if __name__ == "__main__":
    unittest.main()
