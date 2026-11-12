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
