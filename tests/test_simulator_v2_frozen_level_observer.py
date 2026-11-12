"""Native double-extremum Scanner integration on actually CLOSED local M1.

No synthetic fills, no PAPER, no own detector or duplicated Robot rule.
"""
from decimal import Decimal as D
import unittest

from research.historical_market_replay import Candle
import robot_l_shape
from research.simulator_v2.frozen_level_observer import NativeFrozenLevelScanner
from research.simulator_v2.frozen_level_adapter import preview_native_frozen_level
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from research.simulator_v2.timeline import MinuteFrame


BASE = 3_000_000  # the exact production confirmed-neckline regression fixture
DOUBLE_TOP_BARS = [
    (100, 98, 99), (104, 99, 103), (110, 102, 108),
    (105, 100, 102), (103, 95, 98), (105, 99, 103),
    (109.8, 102, 107), (106, 98, 101), (96.5, 94, 94.5),
]


def frame(index: int, h: float, lo: float, close: float) -> MinuteFrame:
    bar = Candle(
        start_ms=BASE + index * 60_000, interval_ms=60_000,
        open=D(str(close)), high=D(str(h)), low=D(str(lo)),
        close=D(str(close)), volume=D("1"),
    )
    return MinuteFrame(
        symbol="LABUSDT", simulation_run_id="real_native_detector",
        virtual_time_ms=bar.end_ms, minute=bar, latest_closed_5m=None,
        newly_closed_5m=None, latest_closed_1h=None, newly_closed_1h=None,
    )


class FrozenLevelNativeScannerTests(unittest.TestCase):
    def test_double_top_requires_last_confirmed_closed_candle_and_exact_original_snapshot(self):
        scanner = NativeFrozenLevelScanner(
            symbol="LABUSDT", simulation_run_id="real_native_detector",
            selected=frozenset({"DOUBLE_TOP"}), window_bars=50,
        )
        for idx, row in enumerate(DOUBLE_TOP_BARS[:-1]):
            self.assertEqual(scanner.observe_closed(frame(idx, *row)), ())
        self.assertEqual(scanner.observations, ())
        result = scanner.observe_closed(frame(8, *DOUBLE_TOP_BARS[-1]))
        self.assertEqual(len(result), 1)
        observation = result[0]
        self.assertEqual(observation.pattern, "Double Top")
        self.assertEqual(observation.source_timeframe, "1")
        self.assertEqual(observation.available_at_ms, BASE + 9 * 60_000)
        self.assertEqual(observation.candidate["status"], "APPROVED")
        self.assertEqual(
            observation.candidate["signal_snapshot"]["neckline_entry"]["confirmation"]["close_time_ms"],
            observation.available_at_ms,
        )
        with self.assertRaisesRegex(ValueError, "next committed"):
            scanner.observe_closed(frame(8, *DOUBLE_TOP_BARS[-1]))

    def test_real_scanner_neckline_native_robot_to_stop_first_virtual_receipts(self):
        """Real detector and Robot policy, same-minute adverse virtual STOP."""
        scanner = NativeFrozenLevelScanner(
            symbol="LABUSDT", simulation_run_id="real_native_detector",
            selected=frozenset({"DOUBLE_TOP"}), window_bars=50,
        )
        session = VirtualReplaySession(
            simulation_run_id="real_native_detector", symbol="LABUSDT",
            initial_balance=D("1000"),
        )
        for idx, row in enumerate(DOUBLE_TOP_BARS):
            source = frame(idx, *row)
            session.step(source.minute)
            observed = scanner.observe_closed(source)
        self.assertEqual(len(observed), 1)
        state, decision = robot_l_shape.initialize_state(observed[0].candidate)
        self.assertEqual(decision, "NECKLINE_CLOSE_CONFIRMATION_READY")
        settings = SimWedgeRiskSettings(
            tick_size=D("0.01"), contracts_per_working_volume=D("1"),
            quantity_step=D("0.01"), minimum_quantity=D("0.01"),
            max_notional_usdt=D("1000"), max_risk_usdt=D("20"),
            entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
        )
        protected = preview_native_frozen_level(
            observed[0].candidate, state, settings=settings,
            virtual_time_ms=session.virtual_time_ms,
        ).protected
        self.assertEqual(protected.entry.side, "SELL")
        self.assertEqual(protected.entry.limit_price, D("94.48"))
        session.exchange.submit_protected_limit(
            protected, submitted_at_ms=session.virtual_time_ms,
        )
        last = BASE + len(DOUBLE_TOP_BARS) * 60_000
        session.step(Candle(
            start_ms=last, interval_ms=60_000,
            open=D("95"), high=D("97"), low=D("93"),
            close=D("94"), volume=D("1"),
        ))
        self.assertEqual(
            [item.kind for item in session.exchange.events if item.kind.endswith("FILLED")],
            ["FILLED", "STOP_FILLED"],
        )
        self.assertEqual(len(session.account.fills), 2)
        self.assertEqual(session.account.fills[0].virtual_time_ms,
                         session.account.fills[1].virtual_time_ms)
        snapshot = session.account.snapshot(
            as_of_ms=session.virtual_time_ms, mark_price=D("94"),
        )
        self.assertEqual(snapshot.position_quantity, D(0))
        # Use the same 1.5% production Robot protection policy as live PAPER.
        native_stop = D("94.48") * D("1.015")
        self.assertEqual(protected.stop_price, native_stop)
        expected = (D("94.48") - native_stop) - (
            D("94.48") + native_stop
        ) * D("0.0006")
        self.assertEqual(snapshot.realized_net_pnl, expected)
        self.assertLess(snapshot.realized_net_pnl, 0)

    def test_wrong_pattern_selection_and_uncommitted_m5_fail_closed(self):
        scanner = NativeFrozenLevelScanner(
            symbol="LABUSDT", simulation_run_id="real_native_detector",
            selected=frozenset({"DOUBLE_BOTTOM"}), window_bars=50,
        )
        for i, row in enumerate(DOUBLE_TOP_BARS):
            self.assertEqual(scanner.observe_closed(frame(i, *row)), ())
        wrong = frame(9, 95, 92, 94)
        bad_m5 = Candle(
            start_ms=BASE + 6 * 60_000, interval_ms=300_000,
            open=D("94"), high=D("95"), low=D("92"), close=D("94"),
            volume=D("1"),
        )
        tampered = MinuteFrame(
            symbol=wrong.symbol, simulation_run_id=wrong.simulation_run_id,
            virtual_time_ms=wrong.virtual_time_ms, minute=wrong.minute,
            latest_closed_5m=bad_m5, newly_closed_5m=bad_m5,
            latest_closed_1h=None, newly_closed_1h=None,
        )
        with self.assertRaisesRegex(ValueError, "verified fully closed UTC M5"):
            scanner.observe_closed(tampered)
        other = MinuteFrame(
            symbol="OTHERUSDT", simulation_run_id=wrong.simulation_run_id,
            virtual_time_ms=wrong.virtual_time_ms, minute=wrong.minute,
            latest_closed_5m=None, newly_closed_5m=None,
            latest_closed_1h=None, newly_closed_1h=None,
        )
        with self.assertRaisesRegex(ValueError, "same run"):
            scanner.observe_closed(other)


if __name__ == "__main__":
    unittest.main()
