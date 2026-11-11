"""One Scanner/Robot timeline, original confirmed Ikigai geometry only."""
import unittest
from decimal import Decimal as D
from unittest.mock import patch

from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from research.simulator_v2.session import VirtualReplaySession


def m1(index):
    return Candle(start_ms=index * 60_000, interval_ms=60_000,
                  open=D("100"), high=D("101"), low=D("99"),
                  close=D("100"), volume=D("1"))


class IkigaiIsolationTests(unittest.TestCase):
    def test_closed_m5_and_original_detector_only(self):
        session = VirtualReplaySession(
            simulation_run_id="ikigai", symbol="BTCUSDT",
            initial_balance=D("1000"),
            ikigai_scanner_config=IkigaiScannerConfig(window_bars=50, timeframes=("5m",)),
        )
        for i in range(159):
            session.step(m1(i))
        self.assertEqual(session.ikigai_scanner.observations, ())
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None) as original:
            session.step(m1(159))
            self.assertEqual(original.call_count, 1)
            df = original.call_args.args[0]
            self.assertEqual(len(df), 32)
            self.assertEqual(df.iloc[-1]["close"], 100.)
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.events, ())
        self.assertEqual(session.ikigai_scanner.observations, ())

    def test_m1_and_m5_use_same_detector_at_distinct_closes(self):
        session = VirtualReplaySession(
            simulation_run_id="both_tfs", symbol="BTCUSDT",
            initial_balance=D("1000"),
            ikigai_scanner_config=IkigaiScannerConfig(window_bars=50),
        )
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None) as detect:
            for i in range(160):
                session.step(m1(i))
            # M1: first evaluation on its 32nd closed minute; M5: first
            # evaluation on the 32nd closed 5m, at the 160th minute.
            self.assertEqual(detect.call_count, (160 - 31) + 1)
            self.assertEqual([len(c.args[0]) for c in detect.call_args_list[-2:]],
                             [50, 32])
            self.assertEqual(session.ikigai_scanner.observations, ())
            self.assertEqual(session.exchange.events, ())

    def test_rejects_invalid_lookback(self):
        for value in (0, 5001, True):
            with self.assertRaises(ValueError):
                IkigaiScannerConfig(value)


if __name__ == "__main__":
    unittest.main()
