"""Exact publicTrade observation gates; no trading candidates or order side effects."""
import unittest
from decimal import Decimal

from terminal.market_data.impulse_observation import (PublicTradeObservation, audit_recent_trade_overlap)


def frame(*prints, symbol="BTCUSDT"):
    return {"topic": "publicTrade." + symbol, "data": list(prints)}


def trade(identity="id1", timestamp=1000, side="Buy", price="100", qty="2", symbol="BTCUSDT", sequence=100):
    return {"i": identity, "T": timestamp, "S": side, "p": price, "v": qty, "s": symbol, "seq": sequence}


class PublicTradeObservationTests(unittest.TestCase):
    def test_actual_taker_side_and_notional_read_only(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade(), trade("id2", 1001, "Sell", "99", "3"))))
        s = o.snapshot()
        self.assertEqual([x.side for x in s["prints"]], ["Buy", "Sell"])
        self.assertEqual([x.notional for x in s["prints"]], [Decimal("200"), Decimal("297")])
        self.assertEqual(s["continuity"], "UNPROVEN")
        self.assertEqual(s["last_cross_sequence"], 100)
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
            trade(sequence=-1), trade(sequence=None),
        ]
        o = PublicTradeObservation("BTCUSDT")
        for item in bad:
            self.assertFalse(o.observe(frame(item)))
        self.assertFalse(o.observe(frame(trade(), symbol="ETHUSDT")))
        self.assertFalse(o.observe({"topic": "publicTrade.BTCUSDT", "data": "wrong"}))
        self.assertEqual(o.snapshot()["observed_prints"], 0)

    def test_sequence_equal_across_frames_is_valid_not_a_gap_claim(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade("id1", 1000, sequence=400))))
        self.assertTrue(o.observe(frame(trade("id2", 1001, sequence=400))))
        self.assertTrue(o.observe(frame(trade("id3", 1002, sequence=405))))
        self.assertEqual(o.snapshot()["observed_prints"], 3)
        self.assertEqual(o.snapshot()["last_cross_sequence"], 405)
        self.assertEqual(o.snapshot()["continuity"], "UNPROVEN")

    def test_sequence_regression_rejects_entire_batch_and_latches_gap(self):
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(trade("id1", 1000, sequence=20))))
        self.assertFalse(o.observe(frame(
            trade("id2", 1001, sequence=21),
            trade("id3", 1002, sequence=19),
        )))
        s = o.snapshot()
        self.assertEqual([p.trade_id for p in s["prints"]], ["id1"])
        self.assertEqual(s["last_cross_sequence"], 20)
        self.assertEqual(s["invalid_frames"], 1)
        self.assertTrue(s["gap_or_truncation"])
        # Fresh generation cannot inherit old sequence or accumulated evidence.
        o.mark_gap()
        self.assertTrue(o.observe(frame(trade("fresh", 2000, sequence=1))))
        self.assertEqual(o.snapshot()["last_cross_sequence"], 1)

    def test_missing_sequence_is_fail_closed_not_assumed_complete(self):
        o = PublicTradeObservation("BTCUSDT")
        item = trade()
        del item["seq"]
        self.assertFalse(o.observe(frame(item)))
        self.assertEqual(o.snapshot()["observed_prints"], 0)
        self.assertEqual(o.snapshot()["continuity"], "UNPROVEN")

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




def recent_record(item):
    return {
        "execId": item["i"], "symbol": item["s"],
        "time": str(item["T"]), "seq": str(item["seq"]),
        "side": item["S"], "price": item["p"], "size": item["v"],
    }


def recent_response(*records):
    return {"retCode": 0, "result": {"category": "linear", "list": list(records)}}


class RecentTradeOverlapAuditTests(unittest.TestCase):
    def setUp(self):
        self.observation = PublicTradeObservation("BTCUSDT")
        self.before = trade("before", 999, sequence=90)
        self.first = trade("first", 1000, sequence=100)
        self.second = trade("second", 1100, "Sell", "99", "3", sequence=110)
        self.after = trade("after", 1200, sequence=120)
        self.assertTrue(self.observation.observe(frame(
            self.before, self.first, self.second, self.after,
        )))
        self.rest = recent_response(*(
            recent_record(item)
            for item in (self.after, self.second, self.first, self.before)
        ))

    def audit(self, response=None, snapshot=None, start=1000, end=1200):
        return audit_recent_trade_overlap(
            self.observation.snapshot() if snapshot is None else snapshot,
            self.rest if response is None else response,
            start_ms=start, end_ms=end,
        )

    def test_exact_closed_overlap_is_diagnostic_only(self):
        result = self.audit()
        self.assertEqual(result.status, "EXACT_OVERLAP_MATCH")
        self.assertEqual(result.matched_count, 2)
        self.assertFalse(result.source_complete)
        self.assertFalse(result.trading_authorized)
        self.assertEqual(self.observation.snapshot()["continuity"], "UNPROVEN")

    def test_missing_bracket_prevents_completeness_claim(self):
        records = self.rest["result"]["list"]
        for subset in (records[:-1], records[1:]):
            self.assertEqual(self.audit(recent_response(*subset)).status, "UNPROVEN")

    def test_missing_trade_from_either_source_is_unproven(self):
        records = self.rest["result"]["list"]
        missing_rest = [x for x in records if x["execId"] != "first"]
        self.assertEqual(self.audit(recent_response(*missing_rest)).status, "UNPROVEN")
        o = PublicTradeObservation("BTCUSDT")
        self.assertTrue(o.observe(frame(self.before, self.second, self.after)))
        self.assertEqual(self.audit(snapshot=o.snapshot()).status, "UNPROVEN")

    def test_same_id_conflicting_execution_facts_refused(self):
        records = [dict(x) for x in self.rest["result"]["list"]]
        for x in records:
            if x["execId"] == "second":
                x["price"] = "98"
        self.assertEqual(self.audit(recent_response(*records)).status, "UNPROVEN")

    def test_duplicate_foreign_and_malformed_rest_are_unproven(self):
        records = self.rest["result"]["list"]
        self.assertEqual(
            self.audit(recent_response(*(records + [records[0]]))).status, "UNPROVEN")
        foreign = [dict(x) for x in records]
        foreign[0]["symbol"] = "ETHUSDT"
        self.assertEqual(self.audit(recent_response(*foreign)).status, "UNPROVEN")
        bad_seq = [dict(x) for x in records]
        bad_seq[1]["seq"] = "-1"
        self.assertEqual(self.audit(recent_response(*bad_seq)).status, "UNPROVEN")
        bad_response = {"retCode": 10001, "result": {"category": "linear", "list": records}}
        self.assertEqual(self.audit(bad_response).status, "UNPROVEN")

    def test_no_trades_and_unsupported_snapshot_never_grant_authority(self):
        self.assertEqual(self.audit(start=1001, end=1099).status, "UNPROVEN")
        self.assertEqual(
            self.audit(snapshot={"symbol": "BTCUSDT", "prints": ()}).status,
            "UNPROVEN")
        with self.assertRaises(ValueError):
            self.audit(start=1200, end=1000)

    def test_reconnect_invalidates_observed_window(self):
        self.observation.mark_gap()
        result = self.audit()
        self.assertEqual(result.status, "UNPROVEN")
        self.assertFalse(result.trading_authorized)

if __name__ == "__main__":
    unittest.main()
