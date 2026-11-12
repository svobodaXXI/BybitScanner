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


class PublicTakerBridgeTests(TestCase):
    def test_ws_and_historical_public_prints_have_identical_semantics(self):
        from robot_entry_flow_evidence import normalize_bybit_taker_print, aggregate_taker_prints
        ws = normalize_bybit_taker_print(
            {"s": "ICNTUSDT", "i": "a", "T": 1794049215011,
             "S": "Buy", "p": "0.2886", "v": "235"},
            layout="WS_PUBLIC_TRADE",
        )
        archive = normalize_bybit_taker_print(
            {"symbol": "ICNTUSDT", "trdMatchID": "a", "timestamp": "1794049215.011",
             "side": "Buy", "price": "0.2886", "size": "235"},
            layout="PUBLIC_TRADE_ARCHIVE",
        )
        self.assertEqual(ws, archive)
        self.assertEqual(ws.notional_usdt, D("67.8210"))
        aggregated = aggregate_taker_prints(
            (archive,), symbol="ICNTUSDT", start_ms=1794049215000,
            end_ms=1794049216000,
        )
        self.assertEqual(aggregated.buy_notional_usdt, D("67.8210"))
        self.assertEqual(aggregated.sell_notional_usdt, D("0"))

    def test_real_taker_sells_are_not_labelled_as_buys(self):
        from robot_entry_flow_evidence import normalize_bybit_taker_print, aggregate_taker_prints
        one = normalize_bybit_taker_print(
            {"s": "ICNTUSDT", "i": "one", "T": 1, "S": "Buy", "p": "1", "v": "2"},
            layout="WS_PUBLIC_TRADE",
        )
        two = normalize_bybit_taker_print(
            {"s": "ICNTUSDT", "i": "two", "T": 2, "S": "Sell", "p": "0.9", "v": "4"},
            layout="WS_PUBLIC_TRADE",
        )
        w = aggregate_taker_prints((one, two), symbol="ICNTUSDT", start_ms=0, end_ms=1000)
        self.assertEqual(w.buy_notional_usdt, D("2"))
        self.assertEqual(w.sell_notional_usdt, D("3.6"))
        self.assertLess(w.price_change_bps, D(0))

    def test_missing_side_and_empty_interval_remain_unknown(self):
        from robot_entry_flow_evidence import normalize_bybit_taker_print, aggregate_taker_prints
        with self.assertRaises(ValueError):
            normalize_bybit_taker_print(
                {"symbol": "ICNTUSDT", "trdMatchID": "a", "timestamp": "1",
                 "price": "1", "size": "2"}, layout="PUBLIC_TRADE_ARCHIVE",
            )
        self.assertIsNone(aggregate_taker_prints((), symbol="ICNTUSDT", start_ms=0, end_ms=1000))

    def test_duplicate_and_late_execution_rejected(self):
        from robot_entry_flow_evidence import TakerPrint, aggregate_taker_prints
        p = TakerPrint("ICNTUSDT", "trade", 110, "Buy", D("1"), D("1"))
        with self.assertRaises(ValueError):
            aggregate_taker_prints((p, p), symbol="ICNTUSDT", start_ms=100, end_ms=200)
        with self.assertRaises(ValueError):
            aggregate_taker_prints((p,), symbol="ICNTUSDT", start_ms=0, end_ms=100)
        with self.assertRaises(ValueError):
            aggregate_taker_prints((p,), symbol="BTCUSDT", start_ms=100, end_ms=200)

    def test_replay_builds_only_completed_windows(self):
        from robot_entry_flow_evidence import TakerPrint, aggregate_taker_prints, compare_flow_windows
        early = (
            TakerPrint("ICNTUSDT", "a", 5, "Sell", D("1"), D("200")),
            TakerPrint("ICNTUSDT", "b", 20, "Buy", D("0.99"), D("100")),
        )
        later = (
            TakerPrint("ICNTUSDT", "c", 1005, "Buy", D("1"), D("300")),
            TakerPrint("ICNTUSDT", "d", 1010, "Buy", D("1.01"), D("100")),
        )
        first = aggregate_taker_prints(early, symbol="ICNTUSDT", start_ms=0, end_ms=1000)
        second = aggregate_taker_prints(later, symbol="ICNTUSDT", start_ms=1000, end_ms=2000)
        result = compare_flow_windows(first, second, decision_ms=2000)
        self.assertTrue(result.buy_wave_accelerating)
        with self.assertRaises(ValueError):
            compare_flow_windows(first, second, decision_ms=1999)
