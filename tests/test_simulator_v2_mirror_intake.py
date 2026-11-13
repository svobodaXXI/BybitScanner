"""Native MIRROR Scanner proof -> native Robot -> one private SIMULATION LIMIT."""
from copy import deepcopy
from decimal import Decimal as D
import unittest
from unittest.mock import patch
import os

from geometry.naked_retest import initialize_state, process_closed_candle
from mirror_levels.levels import (
    LevelRegistry, SOURCE_SWING_ZONE, horizontal_level,
)
from mirror_levels.tracker import new_record, STATUS_UNTESTED
import mirror_scanner
import robot_l_shape
from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.robot_sandbox import (
    ConnectedSimulationRobot, SimulationExecutionNotConnected,
)
from research.simulator_v2.session import VirtualReplaySession
from terminal.domain.models import Symbol

FIVE = 300_000
MINUTE = 60_000
SYMBOL = "BTCUSDT"
# Verified naked DOWN at group 3; all following groups remain below 110.
GROUPS = (
    ("112", "113", "111", "112"),
    ("112", "113", "111", "112"),
    ("112", "113", "111", "112"),
    ("111", "111.5", "104", "105"),
    ("104.5", "105", "104.2", "104.6"),
    ("104.6", "105", "103.9", "104"),
    ("103.95", "105.2", "103.9", "105"),
    ("105", "105.4", "104.8", "105.2"),
)


def minute(i):
    opened, high, low, closed = map(D, GROUPS[i // 5])
    fraction = D(i % 5) / 5
    next_fraction = D(i % 5 + 1) / 5
    op = opened + (closed - opened) * fraction
    close = opened + (closed - opened) * next_fraction
    return Candle(
        start_ms=i * MINUTE, interval_ms=MINUTE, open=op, close=close,
        high=max(op, close, high if i % 5 == 2 else op),
        low=min(op, close, low if i % 5 == 2 else op),
        volume=D("1"),
    )


def terms():
    return BoxSimulationRiskTerms(
        tick_size=D("0.01"), working_quantity=D("8"),
        quantity_step=D("1"), minimum_quantity=D("1"),
        maximum_notional_usdt=D("1000"), maximum_loss_usdt=D("300"),
        entry_fee_rate=D("0.0002"), exit_fee_rate=D("0.0006"),
        adverse_stop_slippage_per_unit=D("0"),
        additional_cost_allowance_usdt=D("0"),
    )


def native_scanner_state():
    level = horizontal_level(
        symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE,
        pattern=None, side="lower", price=110,
        anchor_time_ms=0, confirmed_at_ms=2 * FIVE,
    )
    state = mirror_scanner.empty_state(SYMBOL, "5")
    registry = LevelRegistry()
    registry.add(level)
    state["registry"] = registry.to_dict()
    retest, _ = initialize_state(level.boundary)
    for index in range(2, len(GROUPS)):
        opened, high, low, close = map(float, GROUPS[index])
        retest, _ = process_closed_candle(level.boundary, retest, {
            "open_time_ms": index * FIVE,
            "close_time_ms": (index + 1) * FIVE,
            "open": opened, "high": high, "low": low, "close": close,
            "closed": True,
        })
    assert retest["phase"] == "RETEST_CAMPAIGN_ACTIVE", retest
    breakout = retest["breakout"]
    record = new_record(level)
    record.update(
        naked_retest=retest, status=STATUS_UNTESTED, candidate=True,
        lifecycle=mirror_scanner.LIFECYCLE_TRACKING, rejection=None,
    )
    state["records"][level.level_id] = record
    available_at = len(GROUPS) * FIVE
    frozen = {
        "direction": "LONG", "source_timeframe": "5",
        "breakout_time_ms": available_at - FIVE,
        "reference": "105.2", "target": "110", "stop": "103.9",
        "structural_stop": "103.9", "stop_kind": "REVERSAL_FORMATION_EXTREME",
        "potential_percent": "4.56", "reward_risk": "3",
        "level_id": level.level_id, "level_timeframe": "5",
        "level_source": level.source, "level_pattern": level.pattern,
        "level_side": level.side, "level_breakout_direction": breakout["direction"],
        "level_breakout_close_ms": breakout["close_time_ms"],
        "confirmation": {"kind": "ENGULFING", "timeframe": "5",
                         "close_time_ms": available_at},
    }
    entry_id = f"{level.level_id}@5@{available_at}"
    state["standalone_entries"] = [{
        "entry_id": entry_id, "handoff": "OFF", "terms": frozen,
    }]
    return state, entry_id


class NativeMirrorSimulatorIntakeTests(unittest.TestCase):
    def session(self, run_id):
        return VirtualReplaySession(
            simulation_run_id=run_id, symbol=SYMBOL, initial_balance=D("1000"),
        )

    def robot(self, session):
        return ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=terms(),
            mirror_working_volume_usdt=D("250"),
            mirror_risk_limit_usdt=D("300"),
        )

    def populate(self, session, robot):
        for i in range(len(GROUPS) * 5):
            session.step(minute(i))
            robot.after_committed_minute()

    def test_exact_authorized_mirror_is_submitted_once_through_native_robot(self):
        session = self.session("mirror_native_intake")
        state, entry_id = native_scanner_state()
        with self.robot(session) as robot:
            self.populate(session, robot)
            # Local SIMULATION explicit choice, not a change to the global
            # standalone Robot flag or a new Robot strategy implementation.
            with patch.dict(os.environ, {robot_l_shape.MIRROR_STANDALONE_ENV: "0"}):
                candidate_id = robot.admit_mirror(state, entry_id=entry_id)
            candidate = robot._store.get_robot_candidate(candidate_id)
            self.assertEqual(candidate.signal_snapshot["pattern"], "MIRROR")
            self.assertEqual(candidate.trading_account_id, robot.account_id)
            self.assertEqual(len(session.exchange.robot_limits), 1)
            order = session.exchange.robot_limits[0]
            self.assertEqual((order.entry.side, order.entry.limit_price,
                              order.entry.quantity, order.reduce_only),
                             ("BUY", D("105.22"), D("2"), False))
            with self.assertRaisesRegex(SimulationExecutionNotConnected, "active"):
                robot.admit_mirror(state, entry_id=entry_id)

    def _closed_m1(self, index, *, op, high, low, close):
        return Candle(
            start_ms=index * MINUTE, interval_ms=MINUTE,
            open=D(op), high=D(high), low=D(low), close=D(close),
            volume=D("1"),
        )

    def _admitted_for_trade(self, run_id):
        session = self.session(run_id)
        state, entry_id = native_scanner_state()
        robot = self.robot(session)
        self.populate(session, robot)
        candidate_id = robot.admit_mirror(state, entry_id=entry_id)
        return session, robot, state, entry_id, candidate_id

    def _filled_mirror(self, session, robot, candidate_id):
        # The confirmation closed at 40m; native LIMIT is durable only then.
        # The first venue-eligible price is the following 40-41m closed M1.
        session.step(self._closed_m1(
            40, op="105.2", high="105.4", low="105", close="105.2",
        ))
        robot.after_committed_minute()
        trade = robot._store.get_open_robot_trade_for_symbol(
            robot.account_id, Symbol(SYMBOL),
        )
        self.assertIsNotNone(trade)
        self.assertEqual((trade.pattern, trade.candidate_id, trade.direction),
                         ("MIRROR", candidate_id, "LONG"))
        self.assertEqual((trade.entry_quantity, trade.average_entry),
                         (D("2"), D("105.22")))
        self.assertIsNotNone(session.exchange.robot_stop)
        self.assertIsNotNone(session.exchange.robot_take)
        snapshot = session.account.snapshot(
            as_of_ms=session.virtual_time_ms, mark_price=D("105.2"),
        )
        self.assertEqual(snapshot.position_quantity, D("2"))
        return trade

    def _assert_mirror_closed(self, session, robot, trade, *, reason, price):
        closed = robot._store.get_robot_trade(trade.trade_id)
        self.assertEqual((closed.exit_reason, closed.exit_price), (reason, D(price)))
        self.assertIsNotNone(closed.exit_time_ms)
        expected_gross = (D(price) - D("105.22")) * D("2")
        entry_fee = D("105.22") * D("2") * D("0.0006")
        exit_fee = D(price) * D("2") * D("0.0006")
        self.assertEqual(closed.realized_pnl_usdt, expected_gross)
        self.assertEqual(closed.fees_costs_usdt, entry_fee + exit_fee)
        self.assertEqual(
            closed.realized_pnl_pct,
            (expected_gross - entry_fee - exit_fee) / (D("105.22") * D("2")) * 100,
        )
        snap = session.account.snapshot(
            as_of_ms=session.virtual_time_ms, mark_price=D(price),
        )
        self.assertEqual(snap.position_quantity, D("0"))
        self.assertEqual(snap.realized_gross_pnl, expected_gross)
        self.assertEqual(snap.fees, entry_fee + exit_fee)
        self.assertEqual(snap.realized_net_pnl, expected_gross - entry_fee - exit_fee)
        self.assertEqual(snap.applied_fills, 2)
        obligation = robot._store.get_paper_protection_obligation_for_trade(trade.trade_id)
        self.assertEqual((obligation.status, obligation.winning_leg), ("RESOLVED", reason))
        self.assertTrue(robot.can_admit)
        self.assertIsNone(session.exchange.robot_stop)
        self.assertIsNone(session.exchange.robot_take)
        self.assertEqual(session.exchange.robot_limits, ())
        self.assertEqual(robot._store.get_robot_candidate(trade.candidate_id).status, "CLOSED")

    def test_experimental_one_fill_lock_uses_attested_campaign_not_signal(self):
        session = self.session("mirror_one_fill_campaign_unit")
        state, entry_id = native_scanner_state()
        with ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=terms(),
            mirror_working_volume_usdt=D("250"),
            mirror_risk_limit_usdt=D("300"),
            mirror_auto_scan=True,
            mirror_one_filled_trade_per_campaign=True,
        ) as robot:
            self.populate(session, robot)
            # This focused intake test supplies a manually constructed Scanner
            # state. Stop the separate automatic observer before injecting it;
            # the real-market E2E independently exercises full automatic scan.
            robot._auto_mirror_scanner = None
            candidate_id = robot.admit_mirror(state, entry_id=entry_id)
            key = robot._mirror_campaign_key(
                state["standalone_entries"][0]["terms"],
            )
            self.assertNotIn(key, robot._mirror_consumed_campaigns)
            self._filled_mirror(session, robot, candidate_id)
            self.assertIn(key, robot._mirror_consumed_campaigns)
            session.step(self._closed_m1(
                41, op="105.2", high="111", low="105", close="110",
            ))
            robot.after_committed_minute()
            self.assertTrue(robot.can_admit)
            with self.assertRaisesRegex(
                SimulationExecutionNotConnected, "already has an attested",
            ):
                robot.admit_mirror(state, entry_id=entry_id)
            different = dict(state["standalone_entries"][0]["terms"])
            different["level_breakout_close_ms"] += FIVE
            self.assertNotIn(robot._mirror_campaign_key(different),
                             robot._mirror_consumed_campaigns)
            self.assertEqual(robot.mirror_experiment_suppressed, ())

    def test_research_ambiguity_excludes_every_simultaneous_signal_not_one(self):
        from unittest.mock import Mock
        for skip, expected_error in ((False, True), (True, False)):
            session = self.session("mirror_ambiguous_" + str(skip).lower())
            with ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=terms(),
                mirror_working_volume_usdt=D("250"),
                mirror_risk_limit_usdt=D("300"),
                mirror_auto_scan=True,
                mirror_research_skip_ambiguous=skip,
            ) as robot:
                robot._auto_mirror_scanner = Mock(
                    observe_committed=Mock(return_value=("level-a@1@60000", "level-b@1@60000")),
                )
                session.step(minute(0))
                if expected_error:
                    with self.assertRaisesRegex(
                        SimulationExecutionNotConnected,
                        "no proven priority",
                    ):
                        robot.after_committed_minute()
                    self.assertEqual(robot.mirror_ambiguous_research_events, ())
                else:
                    robot.after_committed_minute()
                    self.assertEqual(
                        robot.mirror_ambiguous_research_events,
                        ((MINUTE, ("level-a@1@60000", "level-b@1@60000")),),
                    )
                self.assertFalse(robot._source_candidate_ids)
                self.assertFalse(session.exchange.robot_limits)
                self.assertTrue(robot.can_admit)

    def test_experimental_gate_requires_explicit_auto_mode(self):
        session = self.session("mirror_one_fill_invalid_options")
        with self.assertRaisesRegex(ValueError, "automatic local replay"):
            ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=terms(),
                mirror_working_volume_usdt=D("250"),
                mirror_risk_limit_usdt=D("300"),
                mirror_one_filled_trade_per_campaign=True,
            )
        with self.assertRaisesRegex(TypeError, "boolean"):
            ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=terms(),
                mirror_working_volume_usdt=D("250"),
                mirror_risk_limit_usdt=D("300"), mirror_auto_scan=True,
                mirror_one_filled_trade_per_campaign="yes",
            )

    def test_native_mirror_take_closes_with_actual_fees_net_pnl_and_no_replay(self):
        session, robot, state, entry_id, candidate_id = self._admitted_for_trade("mirror_take_e2e")
        with robot:
            trade = self._filled_mirror(session, robot, candidate_id)
            session.step(self._closed_m1(
                41, op="105.2", high="111", low="105", close="110",
            ))
            robot.after_committed_minute()
            self._assert_mirror_closed(session, robot, trade, reason="TAKE", price="110")
            self.assertEqual(session.exchange.last_minute_order_events[0].kind, "TAKE_FILLED")
            session.step(self._closed_m1(
                42, op="110", high="111", low="109.5", close="110.5",
            ))
            robot.after_committed_minute()
            self.assertEqual(len(session.account.fills), 2)
            with self.assertRaisesRegex(ValueError, "exact committed close"):
                robot.admit_mirror(state, entry_id=entry_id)

    def test_native_mirror_stop_gap_closes_at_worse_open_with_actual_fees(self):
        session, robot, _state, _entry_id, candidate_id = self._admitted_for_trade("mirror_stop_e2e")
        with robot:
            trade = self._filled_mirror(session, robot, candidate_id)
            session.step(self._closed_m1(
                41, op="102", high="103", low="100", close="101",
            ))
            robot.after_committed_minute()
            self._assert_mirror_closed(session, robot, trade, reason="STOP", price="102")
            self.assertEqual(session.exchange.last_minute_order_events[0].kind, "STOP_FILLED")

    def test_native_mirror_stop_wins_ambiguous_same_candle(self):
        session, robot, _state, _entry_id, candidate_id = self._admitted_for_trade("mirror_stop_first")
        with robot:
            trade = self._filled_mirror(session, robot, candidate_id)
            stop = session.exchange.robot_stop.stop_price
            session.step(self._closed_m1(
                41, op="105.2", high="112", low="100", close="106",
            ))
            robot.after_committed_minute()
            self._assert_mirror_closed(
                session, robot, trade, reason="STOP", price=str(stop),
            )

    def test_forbidden_source_and_future_confirmation_never_create_order(self):
        session = self.session("mirror_native_rejected")
        state, entry_id = native_scanner_state()
        with self.robot(session) as robot:
            self.populate(session, robot)
            bad = deepcopy(state)
            bad["standalone_entries"][0]["terms"]["level_pattern"] = "HORN"
            with self.assertRaisesRegex(ValueError, "revoked"):
                robot.admit_mirror(bad, entry_id=entry_id)
            future = deepcopy(state)
            future["standalone_entries"][0]["terms"]["confirmation"]["close_time_ms"] += FIVE
            with self.assertRaises(ValueError):
                robot.admit_mirror(future, entry_id=entry_id)
            self.assertEqual(session.exchange.robot_limits, ())
            self.assertEqual(robot._store.load_robot_candidates(robot.account_id), ())

    def test_missing_original_closed_history_blocks_mirror_admission(self):
        state, entry_id = native_scanner_state()
        session = self.session("mirror_native_missing")
        with self.robot(session) as robot:
            session.step(minute(0))
            robot.after_committed_minute()
            with self.assertRaises(ValueError):
                robot.admit_mirror(state, entry_id=entry_id)
            self.assertEqual(session.exchange.robot_limits, ())

    def test_explicit_profile_only_and_no_duplicate_research_robot(self):
        session = self.session("mirror_native_config")
        with self.assertRaisesRegex(TypeError, "Scanner or explicit"):
            ConnectedSimulationRobot(session, tick_size=D("0.01"), terms=terms())
        with self.assertRaisesRegex(ValueError, "bounded"):
            ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=terms(),
                mirror_working_volume_usdt=D("2000"),
                mirror_risk_limit_usdt=D("300"),
            )
