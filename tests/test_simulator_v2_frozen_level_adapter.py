"""Native L-shape and confirmed neckline Robot policy -> virtual GTC/STOP/TAKE.

Only existing robot_l_shape strategy and virtual exchange are exercised.
No live account, PAPER mutation, duplicated strategy or synthetic Scanner signal.
"""
from decimal import Decimal as D
import unittest

import robot_l_shape
from research.historical_market_replay import Candle
from research.simulator_v2.frozen_level_adapter import (
    FrozenLevelSimulationBlocked, preview_native_frozen_level,
)
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings


START = 1_500_000_000_000  # UTC M1 and M5 aligned


def settings(**changes):
    fields = dict(
        tick_size=D("0.01"), contracts_per_working_volume=D("1"),
        quantity_step=D("0.01"), minimum_quantity=D("0.01"),
        max_notional_usdt=D("1000"), max_risk_usdt=D("20"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )
    fields.update(changes)
    return SimWedgeRiskSettings(**fields)


def candidate(pattern="L-shape"):
    terms_key = "neckline_entry" if pattern in {"Double Top", "Double Bottom"} else "l_shape"
    is_short = pattern == "Double Top"
    terms = dict(
        direction="SHORT" if is_short else "LONG", source_timeframe="1",
        breakout_time_ms=START,
        reference="100", target="90" if is_short else "110",
        stop="102" if is_short else "98",
        structural_stop="102" if is_short else "98",
        stop_kind="STRUCTURAL", potential_percent="10", reward_risk="5",
    )
    if terms_key == "neckline_entry":
        terms.update(
            neckline="100.5" if is_short else "99.5",
            confirmation=dict(
                kind="NECKLINE_BODY_CLOSE", timeframe="1",
                close_time_ms=START + 60_000, close="100",
            ),
        )
    return dict(
        status="APPROVED", candidate_id="native_test_" + pattern.replace(" ", "_"),
        symbol="BTCUSDT", timeframe="1",
        signal_snapshot=dict(
            pattern=pattern, symbol="BTCUSDT", timeframe="1",
            robot_handoff_ready=True, **{terms_key: terms},
        ),
    )


def minute(start, op, high, low, close):
    return Candle(start_ms=start, interval_ms=60_000,
                  open=D(op), high=D(high), low=D(low),
                  close=D(close), volume=D("100"))


class FrozenLevelNativeAdapterTests(unittest.TestCase):
    def test_original_lshape_retest_to_virtual_take_with_real_fees(self):
        native = candidate()
        state, event = robot_l_shape.initialize_state(native)
        self.assertEqual(event, robot_l_shape.EVENT_INITIALIZED)
        with self.assertRaises(FrozenLevelSimulationBlocked):
            preview_native_frozen_level(
                native, state, settings=settings(),
                virtual_time_ms=START + 60_000,
            )
        state, event = robot_l_shape.process_closed_candle(
            native["signal_snapshot"], state,
            dict(time_ms=START + 60_000, high=101, low=99, close=100),
        )
        self.assertEqual(event, robot_l_shape.EVENT_RETEST)
        preview = preview_native_frozen_level(
            native, state, settings=settings(),
            virtual_time_ms=START + 60_000,
        )
        self.assertEqual(preview.pattern, "L-shape")
        self.assertEqual(preview.protected.entry.limit_price, D("100.02"))
        self.assertEqual(preview.protected.entry.quantity, D("1"))
        self.assertEqual(preview.protected.stop_price, D("98"))
        self.assertEqual(preview.protected.take_price, D("110"))
        self.assertGreaterEqual(preview.native_net_reward_risk, D("2"))

        session = VirtualReplaySession(
            simulation_run_id="native_level_unit", symbol="BTCUSDT",
            initial_balance=D("1000"),
        )
        session.step(minute(START, "100", "101", "99", "100"))
        session.exchange.submit_protected_limit(
            preview.protected, submitted_at_ms=session.virtual_time_ms,
        )
        session.step(minute(START + 60_000, "100", "101", "99.5", "100.5"))
        self.assertEqual(len(session.account.fills), 1)
        self.assertEqual(session.account.fills[0].price, D("100.02"))
        session.step(minute(START + 120_000, "101", "110.5", "100", "109"))
        self.assertEqual(len(session.account.fills), 2)
        final = session.account.snapshot(as_of_ms=session.virtual_time_ms, mark_price=D("109"))
        expected_net = (D("110") - D("100.02")) - (
            D("100.02") + D("110")
        ) * D("0.0006")
        self.assertEqual(final.realized_net_pnl, expected_net)
        self.assertEqual(final.position_quantity, D(0))
        self.assertEqual([e.kind for e in session.exchange.events if e.kind.endswith("FILLED")],
                         ["FILLED", "TAKE_FILLED"])

    def test_original_double_top_and_bottom_are_ready_only_after_native_confirmation(self):
        for pattern, side in (("Double Top", "SELL"), ("Double Bottom", "BUY")):
            with self.subTest(pattern=pattern):
                native = candidate(pattern)
                state, event = robot_l_shape.initialize_state(native)
                self.assertEqual(event, "NECKLINE_CLOSE_CONFIRMATION_READY")
                with self.assertRaises(FrozenLevelSimulationBlocked):
                    preview_native_frozen_level(
                        native, state, settings=settings(),
                        virtual_time_ms=START,
                    )
                preview = preview_native_frozen_level(
                    native, state, settings=settings(),
                    virtual_time_ms=START + 60_000,
                )
                self.assertEqual(preview.pattern, pattern)
                self.assertEqual(preview.protected.entry.side, side)

    def test_missing_proof_wrong_origin_risk_and_mirror_fail_closed(self):
        native = candidate()
        state, _ = robot_l_shape.initialize_state(native)
        state, _ = robot_l_shape.process_closed_candle(
            native["signal_snapshot"], state,
            dict(time_ms=START + 60_000, high=101, low=99),
        )
        for change in (
            {"status": "AVAILABLE"},
            {"symbol": "ETHUSDT"},
            {"signal_snapshot": {**native["signal_snapshot"], "robot_handoff_ready": False}},
        ):
            with self.subTest(change=change), self.assertRaises(FrozenLevelSimulationBlocked):
                preview_native_frozen_level(
                    {**native, **change}, state, settings=settings(),
                    virtual_time_ms=START + 60_000,
                )
        with self.assertRaises(FrozenLevelSimulationBlocked):
            preview_native_frozen_level(
                native, state, settings=settings(max_risk_usdt=D("0.5")),
                virtual_time_ms=START + 60_000,
            )
        mirror = {**native, "signal_snapshot": {
            **native["signal_snapshot"], "pattern": "MIRROR",
        }}
        with self.assertRaises(FrozenLevelSimulationBlocked):
            preview_native_frozen_level(
                mirror, state, settings=settings(),
                virtual_time_ms=START + 60_000,
            )


if __name__ == "__main__":
    unittest.main()
