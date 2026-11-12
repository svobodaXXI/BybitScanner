"""Auto MIRROR: original Scanner evidence -> original Robot -> virtual TAKE.

No trading runtime, remote clients, production candidate DB or Telegram.
"""
from decimal import Decimal as D
from unittest import TestCase
from unittest.mock import patch

import mirror_scanner
from mirror_levels.levels import SOURCE_SWING_ZONE, horizontal_level
from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_plan_preview import BoxSimulationRiskTerms
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot
from research.simulator_v2.session import VirtualReplaySession
from terminal.domain.models import Symbol

MINUTE = 60_000
FIVE = 5 * MINUTE
SYMBOL = "BTCUSDT"
# The very same coarse sequence used by native standalone PAPER E2E:
# mature historical range -> strict naked DOWN -> bearish + engulfing ->
# next closed M5 confirms LONG toward the first retest of level 110.
GROUPS = (
    (("112", "113", "111", "112"),) * 34
    + (
        ("111", "111.5", "104", "105"),
        ("104.5", "105.0", "104.2", "104.6"),
        ("104.6", "104.8", "103.9", "104.0"),
        ("103.95", "105.2", "103.9", "105.0"),
        ("105.0", "105.4", "104.8", "105.2"),
        ("105.2", "105.5", "105.0", "105.3"),
    )
)


def candle(index):
    opened, high, low, closed = map(D, GROUPS[index // 5])
    i = index % 5
    op = opened + (closed - opened) * D(i) / 5
    close = opened + (closed - opened) * D(i + 1) / 5
    return Candle(
        start_ms=index * MINUTE, interval_ms=MINUTE,
        open=op, close=close,
        high=max(op, close, high if i == 2 else op),
        low=min(op, close, low if i == 2 else op),
        volume=D("1"),
    )


def explicit_terms():
    return BoxSimulationRiskTerms(
        tick_size=D("0.01"), working_quantity=D("8"),
        quantity_step=D("1"), minimum_quantity=D("1"),
        maximum_notional_usdt=D("1000"), maximum_loss_usdt=D("300"),
        entry_fee_rate=D("0.0002"), exit_fee_rate=D("0.0006"),
        adverse_stop_slippage_per_unit=D("0"),
        additional_cost_allowance_usdt=D("0"),
    )


def minute(index, *, op, high, low, close):
    return Candle(
        start_ms=index * MINUTE, interval_ms=MINUTE,
        open=D(op), high=D(high), low=D(low), close=D(close),
        volume=D("1"),
    )


class NativeMirrorAutomaticTests(TestCase):
    def new_run(self, run_id):
        session = VirtualReplaySession(
            simulation_run_id=run_id, symbol=SYMBOL, initial_balance=D("1000"),
        )
        robot = ConnectedSimulationRobot(
            session, tick_size=D("0.01"), terms=explicit_terms(),
            mirror_working_volume_usdt=D("250"),
            mirror_risk_limit_usdt=D("300"), mirror_auto_scan=True,
        )
        level = horizontal_level(
            symbol=SYMBOL, timeframe="5", source=SOURCE_SWING_ZONE,
            pattern=None, side="lower", price=110,
            anchor_time_ms=9 * FIVE, confirmed_at_ms=10 * FIVE,
        )
        def scanner_levels(_symbol, _tf, frame, **_kwargs):
            # Fixed synthetic source, discovered strictly when its own
            # originally confirmed pivot could be known, not before.
            if int(frame["time"].iloc[-2]) + FIVE < level.confirmed_at_ms:
                return []
            return [level]
        return session, robot, scanner_levels

    def test_native_five_minute_signal_auto_admits_and_reaches_factual_take(self):
        session, robot, level_source = self.new_run("mirror_auto_take")
        with robot, patch.object(mirror_scanner, "collect_levels", level_source), (
            patch.object(mirror_scanner, "CONFIRMATION_TIMEFRAMES", ("5",))
        ), patch("pattern_robot_integration.prepare_robot_handoff",
                 side_effect=AssertionError("PAPER handoff forbidden")):
            for i in range(39 * 5):
                session.step(candle(i))
                robot.after_committed_minute()
            limits = session.exchange.robot_limits
            self.assertEqual(len(limits), 1)
            self.assertEqual((limits[0].entry.side, limits[0].entry.limit_price,
                              limits[0].entry.quantity),
                             ("BUY", D("105.22"), D("2")))
            self.assertEqual(len(robot._source_candidate_ids), 1)
            candidate_id = robot._source_candidate_ids[0]
            state = mirror_scanner.load_state(SYMBOL, "5", robot._mirror_root)
            self.assertTrue(any(x["handoff"] == "PENDING"
                                for x in state["standalone_entries"]))
            session.step(candle(39 * 5))
            robot.after_committed_minute()
            open_trade = robot._store.get_open_robot_trade_for_symbol(
                robot.account_id, Symbol(SYMBOL),
            )
            self.assertIsNotNone(open_trade)
            self.assertEqual(open_trade.candidate_id, candidate_id)
            self.assertEqual(session.account.snapshot(
                as_of_ms=session.virtual_time_ms, mark_price=D("105.2"),
            ).position_quantity, D("2"))
            session.step(minute(
                39 * 5 + 1, op="105.3", high="111", low="105", close="110",
            ))
            robot.after_committed_minute()
            trade = robot._store.get_robot_trade(open_trade.trade_id)
            self.assertEqual((trade.exit_reason, trade.exit_price),
                             ("TAKE", D("110")))
            self.assertEqual(
                trade.realized_pnl_usdt - trade.fees_costs_usdt,
                session.account.snapshot(
                    as_of_ms=session.virtual_time_ms, mark_price=D("110"),
                ).realized_net_pnl,
            )
            self.assertEqual(len(session.account.fills), 2)
            self.assertTrue(robot.can_admit)

    def test_offline_auto_scan_requires_explicit_private_risk_profile(self):
        session = VirtualReplaySession(
            simulation_run_id="mirror_auto_reject", symbol=SYMBOL,
            initial_balance=D("1000"),
        )
        with self.assertRaisesRegex(ValueError, "risk profile"):
            ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=explicit_terms(),
                mirror_auto_scan=True,
            )
        with self.assertRaisesRegex(TypeError, "boolean"):
            ConnectedSimulationRobot(
                session, tick_size=D("0.01"), terms=explicit_terms(),
                mirror_working_volume_usdt=D("250"),
                mirror_risk_limit_usdt=D("300"), mirror_auto_scan="true",
            )
