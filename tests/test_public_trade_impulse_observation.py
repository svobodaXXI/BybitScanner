"""Exact publicTrade observation gates; no trading candidates or order side effects."""
import unittest
from decimal import Decimal
from unittest.mock import patch

from terminal.market_data.impulse_observation import (
    PublicTradeObservation, audit_recent_trade_overlap,
    audit_closed_m1_trade_parity, audit_closed_m1_triple_parity,
    audit_closed_m1_receipt_cutoff,
)


def frame(*prints, symbol="BTCUSDT"):
    return {"topic": "publicTrade." + symbol, "data": list(prints)}


def trade(identity="id1", timestamp=1000, side="Buy", price="100", qty="2", symbol="BTCUSDT", sequence=100):
    return {"i": identity, "T": timestamp, "S": side, "p": price, "v": qty, "s": symbol, "seq": sequence}


class PublicTradeObservationTests(unittest.TestCase):
    def test_optional_print_inbox_delivers_only_new_validated_prints(self):
        from queue import Queue, Empty
        source = PublicTradeObservation("BTCUSDT")
        inbox = Queue(maxsize=2)
        generation, invalid = source.attach_print_inbox(inbox)
        self.assertTrue(source.observe(frame(trade()), received_at_ms=1010))
        self.assertTrue(source.observe(frame(trade()), received_at_ms=1011))
        gen, bad, prints = inbox.get_nowait()
        self.assertEqual((gen, bad), (generation, invalid))
        self.assertEqual([(p.trade_id, p.received_at_ms) for p in prints], [("id1", 1010)])
        with self.assertRaises(Empty):
            inbox.get_nowait()
        self.assertTrue(source.print_inbox_current(inbox, generation, invalid))
        self.assertFalse(source.observe(frame(trade("invalid", 1002, side="UNKNOWN"))))
        self.assertFalse(source.print_inbox_current(inbox, generation, invalid))
        source.mark_gap()
        self.assertFalse(source.print_inbox_current(inbox, generation, invalid))
        source.detach_print_inbox(inbox)
        self.assertFalse(source.print_inbox_current(inbox, 1, 0))

    def test_print_inbox_overflow_fences_geometry_without_losing_ingress(self):
        from queue import Queue
        source = PublicTradeObservation("BTCUSDT")
        inbox = Queue(maxsize=1)
        gen, bad = source.attach_print_inbox(inbox)
        self.assertTrue(source.observe(frame(trade())))
        self.assertTrue(source.observe(frame(trade("next", 1001))))
        self.assertFalse(source.print_inbox_current(inbox, gen, bad))
        self.assertEqual(source.snapshot()["observed_prints"], 2)
        self.assertEqual(source.snapshot()["invalid_frames"], 0)
        self.assertTrue(source.observe(frame(trade("third", 1002))))
        self.assertEqual(source.snapshot()["observed_prints"], 3)
        self.assertEqual(inbox.qsize(), 1)

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

    def test_invalid_frame_fence_resets_only_for_new_source_generation(self):
        """Old malformed frames cannot permanently poison a fresh source."""
        for reset in ("mark_gap", "enable_certification_buffer"):
            with self.subTest(reset=reset):
                source = PublicTradeObservation("BTCUSDT")
                self.assertTrue(source.observe(
                    frame(trade("old", 120_000, sequence=100)),
                    received_at_ms=120_010,
                ))
                self.assertFalse(source.observe(
                    frame(trade("bad", 120_001, side="UNKNOWN", sequence=101)),
                    received_at_ms=120_020,
                ))
                stale = source.snapshot()
                self.assertEqual(stale["invalid_frames"], 1)
                self.assertEqual(stale["observed_prints"], 1)
                getattr(source, reset)()
                fresh = source.snapshot()
                self.assertEqual(fresh["generation"], stale["generation"] + 1)
                self.assertEqual(fresh["invalid_frames"], 0)
                self.assertEqual(fresh["observed_prints"], 0)
                self.assertTrue(fresh["gap_or_truncation"])
                self.assertFalse(fresh["order_authority"])
                self.assertTrue(source.observe(
                    frame(trade("fresh", 180_000, sequence=102)),
                    received_at_ms=180_010,
                ))
                self.assertEqual(
                    [row.trade_id for row in source.snapshot()["prints"]],
                    ["fresh"],
                )
                self.assertEqual(source.snapshot()["invalid_frames"], 0)

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

    def test_opt_in_preserves_600_exact_prints_across_two_closed_minutes(self):
        """Original 512 overflow, but bounded opt-in+REST exact parity can prove 600."""
        from terminal.market_data.impulse_observation import (
            audit_closed_m1_triple_parity, audit_closed_m1_receipt_cutoff,
        )
        source = PublicTradeObservation("BTCUSDT")
        self.assertEqual(source.snapshot()["buffer_capacity"], 512)
        self.assertTrue(source.enable_certification_buffer())
        self.assertFalse(source.enable_certification_buffer())
        self.assertEqual(source.snapshot()["buffer_capacity"], 1000)
        prev = [
            trade(f"p-{i}", 120_000 + i * 200, "Buy", "100", "1",
                  sequence=100+i)
            for i in range(300)
        ]
        current = [
            trade(f"c-{i}", 180_000 + i * 200, "Buy", "101", "1",
                  sequence=400+i)
            for i in range(300)
        ]
        boundary = (
            trade("before", 119_999, "Sell", "100", "1", sequence=90),
            *prev, *current,
            trade("after", 240_000, "Sell", "101", "1", sequence=700),
        )
        for i in range(0, len(boundary), 90):
            self.assertTrue(source.observe(
                frame(*boundary[i:i+90]), received_at_ms=241_000,
            ))
        snapshot = source.snapshot()
        # Rolling minute retention intentionally prunes the older REST
        # bracketing trade; it must still be present in the independent
        # REST page, NOT in the two-minute WS proof window.
        self.assertEqual(snapshot["observed_prints"], 601)
        self.assertEqual(snapshot["prints"][0].trade_id, "p-0")
        self.assertFalse(snapshot["order_authority"])
        self.assertEqual(snapshot["continuity"], "UNPROVEN")
        recent = recent_response(*(recent_record(x) for x in reversed(boundary)))
        recent["time"] = 241_000
        for start, price in ((120_000, "100"), (180_000, "101")):
            kline = closed_m1_response(
                start=start, open_px=price, high=price, low=price,
                close=price, volume="300",
                turnover="30000" if price == "100" else "30300",
                server_time=241_000,
            )
            proof = audit_closed_m1_triple_parity(
                snapshot, recent, kline,
                start_ms=start, observed_at_ms=242_000,
            )
            self.assertEqual(proof.status, "EXACT_CLOSED_M1_TRIPLE_PARITY")
            self.assertEqual(proof.matched_prints, 300)
            receipt = audit_closed_m1_receipt_cutoff(
                snapshot, start_ms=start, decision_ms=242_000,
            )
            self.assertEqual(receipt.status, "TIMELY_OBSERVED_ONLY")
            self.assertEqual(receipt.observed_prints, 300)
        clipped = dict(recent)
        clipped["result"] = {
            "category": "linear",
            "list": [row for row in recent["result"]["list"]
                     if row["execId"] != "p-18"],
        }
        self.assertEqual(audit_closed_m1_triple_parity(
            snapshot, clipped, closed_m1_response(
                start=120_000, open_px="100", high="100", low="100",
                close="100", volume="300", turnover="30000",
                server_time=241_000,
            ), start_ms=120_000, observed_at_ms=242_000,
        ).status, "UNPROVEN")
        source.mark_gap()
        self.assertEqual(source.snapshot()["observed_prints"], 0)
        self.assertEqual(source.snapshot()["buffer_capacity"], 1000)

    def test_certification_buffer_is_bounded_and_fences_old_source(self):
        source = PublicTradeObservation("BTCUSDT")
        self.assertTrue(source.observe(
            frame(trade("old", 120_000)), received_at_ms=120_010,
        ))
        source.enable_certification_buffer()
        self.assertEqual(source.snapshot()["observed_prints"], 0)
        self.assertEqual(source.snapshot()["generation"], 1)
        for index in range(1001):
            self.assertTrue(source.observe(frame(trade(
                f"more-{index}", 180_000 + index,
                sequence=index + 101,
            )), received_at_ms=181_100))
        snapshot = source.snapshot()
        self.assertEqual(snapshot["buffer_capacity"], 1000)
        self.assertEqual(snapshot["observed_prints"], 1000)
        self.assertTrue(snapshot["gap_or_truncation"])
        self.assertEqual(snapshot["prints"][0].trade_id, "more-1")
        # Crossing two more minute boundaries prunes older unused prints.
        self.assertTrue(source.observe(frame(trade(
            "new-minute", 360_000, sequence=1105,
        )), received_at_ms=360_010))
        self.assertEqual(source.snapshot()["prints"][0].trade_id, "new-minute")

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
        with patch("terminal.market_data.hub.time.time", return_value=3.25):
            hub._dispatch(frame(trade()))
        self.assertEqual(context.impulse_observation.snapshot()["observed_prints"], 1)
        self.assertEqual(
            context.impulse_observation.snapshot()["prints"][0].received_at_ms, 3250,
        )
        # The legacy public-trade aggregate buffer may IGNORE a raw frame;
        # observation must still inspect it and latch malformed provenance.
        context.public_trades.apply_message = lambda message: "IGNORED"
        with patch("terminal.market_data.hub.time.time", return_value=3.5):
            hub._dispatch(frame(trade("id2", 1001)))
        self.assertEqual(context.impulse_observation.snapshot()["observed_prints"], 2)
        malformed = trade("bad", 1002)
        del malformed["seq"]
        hub._dispatch(frame(malformed))
        untrusted = context.impulse_observation.snapshot()
        self.assertEqual(untrusted["observed_prints"], 2)
        self.assertEqual(untrusted["invalid_frames"], 1)
        self.assertEqual(untrusted["continuity"], "UNPROVEN")
        self.assertFalse(untrusted["order_authority"])
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


def closed_m1_response(*, start=120000, open_px="100", high="101",
                       low="100", close="101", volume="5", turnover="503",
                       server_time=181000, symbol="BTCUSDT"):
    return {
        "retCode": 0, "time": server_time,
        "result": {"symbol": symbol, "category": "linear", "list": [
            [str(start), open_px, high, low, close, volume, turnover]
        ]},
    }


class ClosedM1TradeParityTests(unittest.TestCase):
    def setUp(self):
        self.observer = PublicTradeObservation("BTCUSDT")
        self.before = trade("before", 119999, "Buy", "99", "1", sequence=10)
        self.first = trade("first", 120001, "Buy", "100", "2", sequence=20)
        self.second = trade("second", 130005, "Sell", "101", "3", sequence=21)
        self.after = trade("after", 180000, "Buy", "102", "1", sequence=30)
        self.assertTrue(self.observer.observe(frame(
            self.before, self.first, self.second, self.after,
        )))
        self.closed = closed_m1_response()

    def audit(self, *, snapshot=None, response=None, start=120000, at=182000):
        return audit_closed_m1_trade_parity(
            self.observer.snapshot() if snapshot is None else snapshot,
            self.closed if response is None else response,
            start_ms=start, observed_at_ms=at,
        )

    def test_exact_ohlc_base_volume_quote_turnover_but_no_order_authority(self):
        result = self.audit()
        self.assertEqual(result.status, "EXACT_CLOSED_M1_AGGREGATE_PARITY")
        self.assertEqual(result.matched_prints, 2)
        self.assertEqual(result.known_at_ms, 182000)
        self.assertFalse(result.source_complete)
        self.assertFalse(result.trading_authorized)
        self.assertEqual(self.observer.snapshot()["continuity"], "UNPROVEN")

    def test_missing_trade_and_mismatched_turnover_fail_closed(self):
        partial = PublicTradeObservation("BTCUSDT")
        self.assertTrue(partial.observe(frame(self.before, self.first, self.after)))
        self.assertEqual(self.audit(snapshot=partial.snapshot()).status, "UNPROVEN")
        wrong = closed_m1_response(turnover="502")
        self.assertEqual(self.audit(response=wrong).status, "UNPROVEN")

    def test_wrong_ohlc_volume_symbol_or_candle_boundary_fail_closed(self):
        for change in (
            {"volume": "5.00000001"},
            {"open_px": "101"}, {"high": "100"},
            {"low": "99"}, {"close": "100"},
            {"symbol": "ETHUSDT"}, {"start": 60000},
        ):
            self.assertEqual(
                self.audit(response=closed_m1_response(**change)).status,
                "UNPROVEN",
            )

    def test_no_future_candle_and_no_stale_source_can_qualify(self):
        for response in (
            closed_m1_response(server_time=179999),
            closed_m1_response(server_time=182001),
            closed_m1_response(server_time=100000),
        ):
            self.assertEqual(self.audit(response=response).status, "UNPROVEN")
        self.assertEqual(self.audit(at=215000).status, "UNPROVEN")
        for start, at in ((120001, 182000), (120000, 179999), (-60000, 182000)):
            with self.assertRaises(ValueError):
                self.audit(start=start, at=at)

    def test_invalid_frame_and_missing_source_identity_fail_closed(self):
        snap = self.observer.snapshot()
        for changed in (
            {"invalid_frames": 1},
            {"observed_frames": 0},
            {"order_authority": True},
            {"continuity": "READY"},
            {"generation": "1"},
        ):
            bad = dict(snap, **changed)
            self.assertEqual(self.audit(snapshot=bad).status, "UNPROVEN")

    def test_kline_parity_cannot_verify_taker_side_and_is_never_a_signal(self):
        # Public klines contain traded totals, NOT side of the taker.
        different_sides = PublicTradeObservation("BTCUSDT")
        wrong_side = dict(self.first, S="Sell")
        self.assertTrue(different_sides.observe(frame(
            self.before, wrong_side, self.second, self.after,
        )))
        parity = self.audit(snapshot=different_sides.snapshot())
        self.assertEqual(parity.status, "EXACT_CLOSED_M1_AGGREGATE_PARITY")
        self.assertFalse(parity.source_complete)
        self.assertFalse(parity.trading_authorized)


class ClosedMinuteTripleParityTests(unittest.TestCase):
    def setUp(self):
        self.source = PublicTradeObservation("BTCUSDT")
        self.trades = (
            trade("older", 119999, sequence=10),
            trade("buy", 120001, "Buy", "100", "2", sequence=20),
            trade("sell", 130005, "Sell", "101", "3", sequence=21),
            trade("newer", 180000, sequence=30),
        )
        self.assertTrue(self.source.observe(frame(*self.trades)))
        self.kline = closed_m1_response()
        self.recent = {
            "retCode": 0, "time": 181500, "result": {
                "category": "linear",
                "list": [recent_record(p) for p in reversed(self.trades)],
            },
        }

    def audit(self, *, observer=None, recent=None, kline=None, at=182000):
        return audit_closed_m1_triple_parity(
            (observer or self.source).snapshot(),
            self.recent if recent is None else recent,
            self.kline if kline is None else kline,
            start_ms=120000, observed_at_ms=at,
        )

    def test_three_source_agreement_is_still_not_order_authority(self):
        proof = self.audit()
        self.assertEqual(proof.status, "EXACT_CLOSED_M1_TRIPLE_PARITY")
        self.assertEqual(proof.matched_prints, 2)
        self.assertEqual(proof.known_at_ms, 182000)
        self.assertFalse(proof.source_complete)
        self.assertFalse(proof.trading_authorized)

    def test_side_conflict_passes_aggregates_but_fails_exact_rest_ids(self):
        wrong = [dict(record) for record in self.recent["result"]["list"]]
        wrong[1]["side"] = "Buy" if wrong[1]["side"] == "Sell" else "Sell"
        different = dict(self.recent, result={"category": "linear", "list": wrong})
        self.assertEqual(self.audit(recent=different).status, "UNPROVEN")

    def test_rest_unbracketed_invalid_or_not_yet_available_is_unproven(self):
        records = self.recent["result"]["list"]
        for recent in (
            dict(self.recent, result={"category": "linear", "list": records[:-1]}),
            dict(self.recent, result={"category": "linear", "list": records[1:]}),
            dict(self.recent, time=120000),
            dict(self.recent, time=185000),
            dict(self.recent, time="181500"),
        ):
            self.assertEqual(self.audit(recent=recent).status, "UNPROVEN")
        self.assertEqual(self.audit(at=212000).status, "UNPROVEN")
        self.assertEqual(
            self.audit(kline=closed_m1_response(turnover="504")).status,
            "UNPROVEN",
        )

    def test_reconnect_does_not_recover_pre_gap_execution_coverage(self):
        self.source.mark_gap()
        self.assertTrue(self.source.observe(frame(*self.trades[2:])))
        self.assertEqual(self.audit().status, "UNPROVEN")


class CausalReceiptAuditTests(unittest.TestCase):
    def setUp(self):
        self.first = trade("first", 120001, "Buy", "100", "2", sequence=100)
        self.second = trade("second", 130001, "Sell", "101", "3", sequence=101)
        self.o = PublicTradeObservation("BTCUSDT")

    def test_first_arrival_is_included_without_changing_exchange_identity(self):
        self.assertTrue(self.o.observe(
            frame(self.first, self.second), received_at_ms=179500,
        ))
        snap = self.o.snapshot()
        self.assertEqual([p.received_at_ms for p in snap["prints"]], [179500, 179500])
        # Duplicate observations preserve earliest causal reception.
        self.assertTrue(self.o.observe(frame(self.first), received_at_ms=181000))
        self.assertEqual(self.o.snapshot()["prints"][0].received_at_ms, 179500)
        timely = audit_closed_m1_receipt_cutoff(
            self.o.snapshot(), start_ms=120000, decision_ms=180000,
        )
        self.assertEqual(timely.status, "TIMELY_OBSERVED_ONLY")
        self.assertEqual(timely.latest_received_at_ms, 179500)
        self.assertEqual(timely.observed_prints, 2)
        self.assertFalse(timely.source_complete)
        self.assertFalse(timely.trading_authorized)
        # Receipt metadata must not taint REST exact-execution comparison.
        from terminal.market_data.impulse_observation import ObservedPrint
        self.assertEqual(
            snap["prints"][0],
            ObservedPrint("first", 120001, 100, "Buy", Decimal("100"), Decimal("2")),
        )

    def test_late_print_is_never_mistaken_for_available_at_decision(self):
        self.assertTrue(self.o.observe(frame(self.first), received_at_ms=179500))
        self.assertTrue(self.o.observe(frame(self.second), received_at_ms=181001))
        result = audit_closed_m1_receipt_cutoff(
            self.o.snapshot(), start_ms=120000, decision_ms=180000,
        )
        self.assertEqual(result.status, "LATE_OBSERVED_PRINT")
        self.assertEqual(result.latest_received_at_ms, 181001)
        self.assertFalse(result.trading_authorized)
        # A later decision can corroborate arrival, never retroactively
        # authorize the earlier one or prove complete exchange history.
        later = audit_closed_m1_receipt_cutoff(
            self.o.snapshot(), start_ms=120000, decision_ms=182000,
        )
        self.assertEqual(later.status, "TIMELY_OBSERVED_ONLY")
        self.assertFalse(later.source_complete)

    def test_missing_arrival_stays_unproven_and_reconnect_discards_it(self):
        self.assertTrue(self.o.observe(frame(self.first)))
        result = audit_closed_m1_receipt_cutoff(
            self.o.snapshot(), start_ms=120000, decision_ms=180000,
        )
        self.assertEqual(result.status, "UNPROVEN")
        self.o.mark_gap()
        self.assertEqual(
            audit_closed_m1_receipt_cutoff(
                self.o.snapshot(), start_ms=120000, decision_ms=180000,
            ).status,
            "UNPROVEN",
        )

    def test_invalid_receive_clock_fences_whole_frame(self):
        for bad in (-1, True, "180000", 1.1):
            self.assertFalse(self.o.observe(frame(self.first), received_at_ms=bad))
        self.assertEqual(self.o.snapshot()["observed_prints"], 0)
        self.assertEqual(self.o.snapshot()["invalid_frames"], 4)
        self.assertEqual(
            audit_closed_m1_receipt_cutoff(
                self.o.snapshot(), start_ms=120000, decision_ms=180000,
            ).status,
            "UNPROVEN",
        )

    def test_bad_window_and_nonprint_snapshot_cannot_prove_availability(self):
        for start, cutoff in ((120001, 180000), (-60000, 180000), (120000, 179999)):
            with self.assertRaises(ValueError):
                audit_closed_m1_receipt_cutoff(
                    self.o.snapshot(), start_ms=start, decision_ms=cutoff,
                )
        self.assertEqual(
            audit_closed_m1_receipt_cutoff(
                {"symbol": "BTCUSDT", "prints": []},
                start_ms=120000, decision_ms=180000,
            ).status,
            "UNPROVEN",
        )

if __name__ == "__main__":
    unittest.main()
