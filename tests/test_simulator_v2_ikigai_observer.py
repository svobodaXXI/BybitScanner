"""One Scanner/Robot timeline, original confirmed Ikigai geometry only."""
import unittest
from decimal import Decimal as D
from unittest.mock import patch

from research.historical_market_replay import Candle
from research.simulator_v2.ikigai_observer import IkigaiScannerConfig
from geometry.ikigai_box import IkigaiBoxFormation
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

    def test_both_original_box_timeframes_publish_only_confirmed_scanner_facts(self):
        formation = IkigaiBoxFormation(
            direction="LONG", impulse_start_index=1, impulse_end_index=2,
            box_start_index=3, box_end_index=7, second_start_index=8,
            as_of_index=9, anchor_start_index=1, anchor_end_index=2,
            anchor_start_price=112.9, anchor_end_price=100.,
            box_low=100., box_high=108., second_extreme=91.,
            fibonacci_1_0=100., fibonacci_1_618=92.,
            fibonacci_2_618=79.05,
        )
        session = VirtualReplaySession(
            simulation_run_id="native_box_facts", symbol="BTCUSDT",
            initial_balance=D("1000"),
            ikigai_scanner_config=IkigaiScannerConfig(window_bars=50),
        )
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None):
            for i in range(159):
                session.step(m1(i))
        old_events = session.events
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=formation) as detect:
            session.step(m1(159))
            self.assertEqual(detect.call_count, 2)
        new = session.events[len(old_events):]
        facts = [e for e in new if e.kind == "IKIGAI_BOX_DETECTED"]
        self.assertEqual(len(facts), 2)
        self.assertEqual([dict(e.details)["timeframe"] for e in facts], ["1m", "5m"])
        self.assertEqual(len({e.entity_id for e in facts}), 2)
        self.assertEqual({e.virtual_time_ms for e in facts}, {160 * 60_000})
        self.assertEqual({e.source for e in facts}, {"SCANNER"})
        self.assertTrue(all(dict(e.details)["status"] ==
                            "DETECTOR_ONLY_NO_ROBOT_ADMISSION" for e in facts))
        self.assertEqual(len(session.ikigai_scanner.observations), 2)
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.events, ())
        self.assertEqual(session.account.snapshot(
            as_of_ms=160 * 60_000, mark_price=m1(159).close,
        ).balance, D("1000"))

    def test_detector_error_does_not_commit_phantom_box_and_retry_same_minute(self):
        session = VirtualReplaySession(
            simulation_run_id="box_failure", symbol="BTCUSDT",
            initial_balance=D("1000"),
            ikigai_scanner_config=IkigaiScannerConfig(window_bars=50, timeframes=("1m",)),
        )
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None):
            for i in range(31):
                session.step(m1(i))
        old_events, old_clock = session.events, session.virtual_time_ms
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   side_effect=RuntimeError("original detector unavailable")):
            with self.assertRaisesRegex(RuntimeError, "original detector unavailable"):
                session.step(m1(31))
        self.assertEqual(session.events, old_events)
        self.assertEqual(session.virtual_time_ms, old_clock)
        self.assertEqual(session.ikigai_scanner.observations, ())
        with patch("research.simulator_v2.ikigai_observer.detect_ikigai_box",
                   return_value=None):
            session.step(m1(31))
        self.assertEqual(session.ikigai_scanner.observations, ())
        self.assertEqual(session.account.fills, ())

    def test_rejects_invalid_lookback(self):
        for value in (0, 5001, True):
            with self.assertRaises(ValueError):
                IkigaiScannerConfig(value)


if __name__ == "__main__":
    unittest.main()
