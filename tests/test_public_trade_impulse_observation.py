"""Exact publicTrade observation gates; no trading candidates or order side effects."""
import unittest
from decimal import Decimal

from terminal.market_data.impulse_observation import PublicTradeObservation


def frame(*prints, symbol="BTCUSDT"):
    return {"topic": "publicTrade." + symbol, "data": list(prints)}


def trade(identity="id1", timestamp=1000, side="Buy", price="100", qty="2", symbol="BTCUSDT"):
    return {"i": identity, "T": timestamp, "S": side, "p": price, "v": qty, "s": symbol}


class PublicTradeObservationTests(unittest.TestCase):
    def test_actual_taker_side_and_notional_read_only(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade(), trade("id2", 1001, "Sell", "99", "3"))))
        s = o.snapshot()
        self.assertEqual([x.side for x in s["prints"]], ["Buy", "Sell"])
        self.assertEqual([x.notional for x in s["prints"]], [Decimal("200"), Decimal("297")])
        self.assertEqual(s["continuity"], "UNPROVEN")
        self.assertFalse(s["order_authority"])
        self.assertTrue(s["gap_or_truncation"])

    def test_exact_duplicates_are_not_double_counted(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade())))
        self.assertTrue(o.observe(frame(trade())))
        self.assertEqual(o.snapshot()["observed_prints"], 1)

    def test_conflicting_duplicate_and_backward_timestamp_are_atomic_rejections(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade())))
        self.assertFalse(o.observe(frame(trade("id2", 1001), trade("id1", 1002, qty="3"))))
        self.assertFalse(o.observe(frame(trade("older", 999))))
        self.assertEqual([p.trade_id for p in o.snapshot()["prints"]], ["id1"])
        self.assertEqual(o.snapshot()["invalid_frames"], 2)

    def test_bad_symbol_side_identity_and_numeric_values_are_rejected(self):
        bad = [
            trade(symbol="ETHUSDT"), trade(side="UNKNOWN"), trade(identity=""),
            trade(price="NaN"), trade(qty="0"), trade(timestamp=-1),
        ]
        o = PublicTradeObservation("BTCUSDT")
        for item in bad:
            self.assertFalse(o.observe(frame(item)))
        self.assertFalse(o.observe(frame(trade(), symbol="ETHUSDT")))
        self.assertFalse(o.observe({"topic": "publicTrade.BTCUSDT", "data": "wrong"}))
        self.assertEqual(o.snapshot()["observed_prints"], 0)

    def test_disconnect_discards_pre_gap_prints_and_requires_new_generation(self):
        o = PublicTradeObservation("BTCUSDT")
        o.observe(frame(trade()))
        o.mark_gap()
        self.assertEqual(o.snapshot()["generation"], 1)
        self.assertEqual(o.snapshot()["observed_prints"], 0)
        self.assertEqual(o.snapshot()["continuity"], "UNPROVEN")
        self.assertTrue(o.observe(frame(trade("after", 2000))))
        self.assertEqual([p.trade_id for p in o.snapshot()["prints"]], ["after"])

    def test_bounded_overflow_never_claims_unbroken_completeness(self):
        o = PublicTradeObservation("BTCUSDT")
        for i in range(PublicTradeObservation.LIMIT + 1):
            self.assertTrue(o.observe(frame(trade(f"id{i}", 1000 + i))))
        s = o.snapshot()
        self.assertEqual(s["observed_prints"], PublicTradeObservation.LIMIT)
        self.assertEqual(s["prints"][0].trade_id, "id1")
        self.assertTrue(s["gap_or_truncation"])
        self.assertEqual(s["continuity"], "UNPROVEN")

    def test_existing_hub_dispatch_observes_only_applied_real_trade_topic(self):
        from terminal.market_data.hub import MarketDataHub, SymbolContext

        class Registry:
            def get(self, symbol):
                return type("Instrument", (), {"symbol": symbol.upper(), "tick_size": Decimal("0.01")})()

        class Book:
            depth = 50
            def apply_message(self, message): return "APPLIED"
            def set_update_consumer(self, consumer): pass
            def mark_disconnected(self): pass
            def close(self): pass

        class Trades:
            def apply_message(self, message): return "APPLIED"
            def close(self): pass

        def create(symbol, tick):
            return SymbolContext(symbol, Book(), Trades(), {})

        hub = MarketDataHub(Registry(), create, connection_factory=lambda *args, **kwargs: None)
        context = hub.subscribe("BTCUSDT")
        hub._dispatch(frame(trade()))
        self.assertEqual(context.impulse_observation.snapshot()["observed_prints"], 1)
        context.impulse_observation.mark_gap()
        self.assertEqual(context.impulse_observation.snapshot()["observed_prints"], 0)
        hub.close()


if __name__ == "__main__":
    unittest.main()
