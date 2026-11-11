"""Native double-extremum Scanner integration on actually CLOSED local M1.

No synthetic fills, no PAPER, no own detector or duplicated Robot rule.
"""
from decimal import Decimal as D
import unittest

from research.historical_market_replay import Candle
from research.simulator_v2.frozen_level_observer import NativeFrozenLevelScanner
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
