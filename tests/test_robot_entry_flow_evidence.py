from __future__ import annotations
from decimal import Decimal as D
from unittest import TestCase

from robot_entry_flow_evidence import FlowWindow, compare_flow_windows


def window(start, *, buy, sell, p0, p1, book_valid=False, bid=None, ask=None):
    return FlowWindow(
        start_ms=start, end_ms=start + 1000,
        start_price=D(p0), end_price=D(p1),
        buy_notional_usdt=D(buy), sell_notional_usdt=D(sell),
        book_valid=book_valid,
        bid_refill_ratio=D(bid) if bid is not None else None,
        ask_refill_ratio=D(ask) if ask is not None else None,
    )


class RobotFlowEvidenceTests(TestCase):
    def test_buy_wave_is_an_observation_not_a_trade(self):
        earlier = window(0, buy="100", sell="200", p0="100", p1="99")
        now = window(1000, buy="300", sell="100", p0="99", p1="100")
        result = compare_flow_windows(earlier, now, decision_ms=2000)
        self.assertTrue(result.buy_wave_accelerating)
        self.assertEqual(result.known_at_ms, 2000)
        self.assertIsNone(result.sell_absorption_candidate)

    def test_sell_pressure_with_fading_impact_and_real_refill(self):
        earlier = window(0, buy="10", sell="1000", p0="100", p1="99")
        now = window(1000, buy="10", sell="1500", p0="99", p1="98.95",
                     book_valid=True, bid="0.4")
        result = compare_flow_windows(earlier, now, decision_ms=2001)
        self.assertTrue(result.sell_impact_fading)
        self.assertTrue(result.bid_refill_observed)
        self.assertTrue(result.sell_absorption_candidate)

    def test_missing_l2_keeps_absorption_unknown(self):
        earlier = window(0, buy="10", sell="1000", p0="100", p1="99")
        now = window(1000, buy="10", sell="1500", p0="99", p1="98.95")
        result = compare_flow_windows(earlier, now, decision_ms=2000)
        self.assertTrue(result.sell_impact_fading)
        self.assertIsNone(result.bid_refill_observed)
        self.assertIsNone(result.sell_absorption_candidate)

    def test_short_side_is_symmetric(self):
        earlier = window(0, buy="1000", sell="10", p0="100", p1="101")
        now = window(1000, buy="1500", sell="10", p0="101", p1="101.05",
                     book_valid=True, ask="0.3")
        result = compare_flow_windows(earlier, now, decision_ms=2000)
        self.assertTrue(result.buy_impact_fading)
        self.assertTrue(result.buy_absorption_candidate)

    def test_bad_book_or_lookahead_refused(self):
        earlier = window(0, buy="0", sell="1", p0="100", p1="99")
        now = window(1000, buy="0", sell="1", p0="99", p1="98")
        with self.assertRaises(ValueError):
            compare_flow_windows(earlier, now, decision_ms=1999)
        with self.assertRaises(ValueError):
            compare_flow_windows(earlier, window(3000, buy="1", sell="1", p0="99", p1="99"), decision_ms=4000)
        with self.assertRaises(ValueError):
            window(0, buy="0", sell="1", p0="100", p1="99", bid="0.5")
        with self.assertRaises(ValueError):
            window(0, buy="-1", sell="1", p0="100", p1="99")

    def test_empty_window_is_neutral_and_not_invented(self):
        earlier = window(0, buy="0", sell="0", p0="100", p1="100")
        now = window(1000, buy="0", sell="0", p0="100", p1="100")
        result = compare_flow_windows(earlier, now, decision_ms=2000)
        self.assertIsNone(result.current_delta_fraction)
        self.assertFalse(result.buy_wave_accelerating)
        self.assertFalse(result.sell_impact_fading)
