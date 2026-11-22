"""Independent Impulse Flow cannot become a Robot candidate or place orders.

The two-M1 proof remains a read-only entry-timing input, not a new pattern.
"""
import unittest
from decimal import Decimal

from pattern_robot_integration import is_robot_executable_signal
from terminal.application.robot_admission import scanner_candidate_admission_error
from terminal.market_data.impulse_producer import certified_snapshot
from terminal.market_data.impulse_observation import ObservedPrint


class PatternFlowSourceTests(unittest.TestCase):
    CLOSE = 1_800_000

    @classmethod
    def source(cls, *, drop_ws=False, late=False, wrong_kline=False,
               close_ms=None, id_prefix="", sequence_offset=0):
        c = cls.CLOSE if close_ms is None else close_ms
        trades = [
            ("pre", c - 120_100, 1, "Sell", "99", "1"),
            ("a", c - 119_000, 2, "Buy", "100", "1"),
            ("b", c - 118_000, 3, "Sell", "99", "1"),
            ("c", c - 59_000, 4, "Buy", "100", "2"),
            ("d", c - 58_000, 5, "Buy", "102", "2"),
            ("post", c + 100, 6, "Sell", "102", "1"),
        ]
        prints = tuple(
            ObservedPrint(
                id_prefix + tid, ts, seq + sequence_offset, side, Decimal(px), Decimal(size),
                c + 20_000 if late and tid == "d" else ts + 50,
            )
            for tid, ts, seq, side, px, size in trades[1:5]
            if not (drop_ws and tid == "c")
        )
        observation = {
            "symbol": "BTCUSDT", "generation": 3, "observed_frames": 4,
            "invalid_frames": 0, "order_authority": False,
            "continuity": "UNPROVEN", "gap_or_truncation": True,
            "prints": prints,
        }
        recent = {
            "retCode": 0, "time": c + 5,
            "result": {"category": "linear", "list": [
                {"execId": id_prefix + tid, "symbol": "BTCUSDT", "time": str(ts),
                 "seq": str(seq + sequence_offset), "side": side, "price": px, "size": size}
                for tid, ts, seq, side, px, size in trades
            ]},
        }
        def kline(start, o, h, l, cl, vol, turnover):
            return {
                "retCode": 0, "time": c + 5,
                "result": {"category": "linear", "symbol": "BTCUSDT",
                           "list": [[str(start), o, h, l, cl, vol, turnover]]},
            }
        previous = kline(c - 120_000, "100", "100", "99", "99", "2", "199")
        current = kline(c - 60_000, "100", "102", "100", "102",
                        "3" if wrong_kline else "4", "404")
        return observation, recent, previous, current

    @classmethod
    def fading_source(cls):
        """Complete Bybit-like facts but NO qualifying entry acceleration."""
        from dataclasses import replace

        observed, recent, previous, current = cls.source()
        observed["prints"] = tuple(
            replace(item, price=Decimal("100")) if item.trade_id == "d"
            else item for item in observed["prints"]
        )
        for row in recent["result"]["list"]:
            if row["execId"] == "d":
                row["price"] = "100"
        current["result"]["list"][0][1:7] = [
            "100", "100", "100", "100", "4", "400",
        ]
        return observed, recent, previous, current

    def test_source_only_certifies_facts_without_inventing_entry_signal(self):
        source = self.fading_source()
        self.assertIsNone(certified_snapshot(
            *source, closed_at_ms=self.CLOSE,
            decision_ms=self.CLOSE + 10,
        ))
        facts = certified_snapshot(
            *source, closed_at_ms=self.CLOSE,
            decision_ms=self.CLOSE + 10, source_only=True,
        )
        self.assertIsNotNone(facts)
        self.assertEqual(facts["flow_observation"]["direction"], None)
        self.assertFalse(
            facts["flow_observation"]["transition"].buy_wave_accelerating
        )
        self.assertEqual(facts["flow_source"]["print_count"], 4)
        self.assertTrue(facts["flow_source"]["source_complete"])
        self.assertEqual(len(facts["flow_source"]["print_facts_sha256"]), 64)
        self.assertFalse(is_robot_executable_signal(facts, timeframe="1"))
        # Missing source parity remains forbidden even for mere observations.
        bad = list(self.fading_source())
        bad[0]["prints"] = bad[0]["prints"][:-1]
        self.assertIsNone(certified_snapshot(
            *bad, closed_at_ms=self.CLOSE,
            decision_ms=self.CLOSE + 10, source_only=True,
        ))

    def test_two_certified_minutes_are_readonly_pattern_flow_evidence(self):
        item = certified_snapshot(
            *self.source(), closed_at_ms=self.CLOSE,
            decision_ms=self.CLOSE + 10,
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["flow_observation"]["direction"], "LONG")
        self.assertEqual(item["flow_observation"]["known_at_ms"], self.CLOSE + 10)
        self.assertEqual(item["flow_source"]["scope"], "TWO_CLOSED_M1")
        self.assertEqual(item["flow_source"]["print_count"], 4)
        self.assertNotIn("pattern", item)
        self.assertNotIn("robot_handoff_ready", item)
        self.assertNotIn("candidate_id", item)
        self.assertFalse(is_robot_executable_signal(item, timeframe="1"))

    def test_600_prints_pass_whole_pattern_source_contract_without_lookahead(self):
        """Three-source truth at 600 trades, then same-candidate overlay binding."""
        from terminal.market_data.impulse_observation import PublicTradeObservation
        from tests.test_public_trade_impulse_observation import (
            frame, trade, recent_record, recent_response, closed_m1_response,
        )
        from robot_entry_flow_evidence import (
            CandidateBoundFlowEvidence, ExistingPatternEntryScope,
            match_existing_pattern_flow,
        )
        source = PublicTradeObservation("BTCUSDT")
        source.enable_certification_buffer()
        previous = [
            trade(f"p-{i}", 120_000 + i * 200,
                  "Buy" if i % 2 == 0 else "Sell", "100", "1",
                  sequence=i + 100)
            for i in range(300)
        ]
        current = [
            trade(f"c-{i}", 180_000 + i * 200, "Buy",
                  "100" if i == 0 else "102", "1", sequence=i + 400)
            for i in range(300)
        ]
        all_trades = (
            trade("before", 119_999, "Sell", "100", "1", sequence=90),
            *previous, *current,
            trade("after", 240_000, "Sell", "102", "1", sequence=700),
        )
        for start in range(0, len(all_trades), 90):
            self.assertTrue(source.observe(
                frame(*all_trades[start:start+90]),
                received_at_ms=241_000,
            ))
        rest = recent_response(*(recent_record(p) for p in reversed(all_trades)))
        rest["time"] = 241_000
        old_kline = closed_m1_response(
            start=120_000, open_px="100", high="100", low="100",
            close="100", volume="300", turnover="30000",
            server_time=241_000,
        )
        new_kline = closed_m1_response(
            start=180_000, open_px="100", high="102", low="100",
            close="102", volume="300", turnover="30598",
            server_time=241_000,
        )
        kwargs = {"closed_at_ms": 240_000, "decision_ms": 242_000}
        result = certified_snapshot(
            source.snapshot(), rest, old_kline, new_kline, **kwargs,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["flow_observation"]["direction"], "LONG")
        self.assertEqual(result["flow_source"]["print_count"], 600)
        self.assertEqual(len(result["flow_source"]["print_facts_sha256"]), 64)
        self.assertTrue(
            result["flow_observation"]["transition"].buy_wave_accelerating,
        )
        src = result["flow_source"]
        receipt = CandidateBoundFlowEvidence(
            candidate_id="wedge-exact-1", symbol="BTCUSDT",
            direction=result["flow_observation"]["direction"],
            state_revision=7, source_kind=src["kind"],
            closed_at_ms=src["closed_at_ms"], decision_ms=src["decision_ms"],
            print_facts_sha256=src["print_facts_sha256"],
            source_complete=src["source_complete"],
            receipt_cutoff_proven=src["receipt_cutoff_proven"],
            transport_generation_proven=src["transport_generation_proven"],
            transition=result["flow_observation"]["transition"],
        )
        scope = ExistingPatternEntryScope(
            "wedge-exact-1", "BTCUSDT", "Falling Wedge", "LONG",
            7, "APPROVED", "RETEST_DETECTED",
        )
        self.assertTrue(match_existing_pattern_flow(
            scope, receipt, now_ms=242_000,
        ))
        # No stale/foreign revision may authorize the original order.
        other = ExistingPatternEntryScope(
            "wedge-exact-1", "BTCUSDT", "Falling Wedge", "LONG",
            8, "APPROVED", "RETEST_DETECTED",
        )
        self.assertFalse(match_existing_pattern_flow(
            other, receipt, now_ms=242_000,
        ))
        # Removal of one real REST execution invalidates both the source
        # certificate and any derived entry-timing evidence.
        incomplete = dict(rest, result={
            "category": "linear",
            "list": [row for row in rest["result"]["list"]
                     if row["execId"] != "c-25"],
        })
        self.assertIsNone(certified_snapshot(
            source.snapshot(), incomplete, old_kline, new_kline, **kwargs,
        ))

    def test_reconnect_requires_two_fresh_minutes_before_certifying(self):
        """A corrupt old epoch cannot poison a new complete, causal tape."""
        from terminal.market_data.impulse_observation import PublicTradeObservation
        from tests.test_public_trade_impulse_observation import frame, trade

        source = PublicTradeObservation("BTCUSDT")
        source.enable_certification_buffer()

        def feed(item):
            self.assertTrue(source.observe(
                frame(trade(
                    item.trade_id, item.timestamp_ms, item.side,
                    str(item.price), str(item.quantity), sequence=item.sequence,
                )), received_at_ms=item.received_at_ms,
            ))

        old, recent, previous, current = self.source()
        # The first minute belongs exclusively to the old source generation.
        for item in old["prints"][:2]:
            feed(item)
        self.assertFalse(source.observe(frame(trade(
            "malformed", self.CLOSE - 117_000, side="UNKNOWN",
        )), received_at_ms=self.CLOSE - 116_950))
        old_generation = source.snapshot()["generation"]
        self.assertEqual(source.snapshot()["invalid_frames"], 1)
        source.mark_gap()

        # Independent REST and candle facts cannot bridge the missing WS
        # minute across a reconnect; only post-reconnect observations count.
        for item in old["prints"][2:]:
            feed(item)
        recent["time"] = self.CLOSE + 105
        self.assertIsNone(certified_snapshot(
            source.snapshot(), recent, previous, current,
            closed_at_ms=self.CLOSE, decision_ms=self.CLOSE + 110,
        ))

        # Collect a wholly new two-minute window with different IDs/times,
        # without resetting again or copying the discarded executions.
        next_close = self.CLOSE + 120_000
        fresh, recent, previous, current = self.source(
            close_ms=next_close, id_prefix="fresh-", sequence_offset=10,
        )
        recent["time"] = next_close + 105
        for item in fresh["prints"]:
            feed(item)
        result = certified_snapshot(
            source.snapshot(), recent, previous, current,
            closed_at_ms=next_close, decision_ms=next_close + 110,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["flow_source"]["generation"], old_generation + 1)
        self.assertTrue(result["flow_source"]["source_complete"])
        self.assertEqual(result["flow_source"]["print_count"], 4)
        self.assertEqual(result["flow_observation"]["direction"], "LONG")
        self.assertFalse(is_robot_executable_signal(result, timeframe="1"))

    def test_receive_before_exchange_event_cannot_certify_source(self):
        """Full REST/candle parity cannot rescue impossible receipt causality."""
        from dataclasses import replace

        observed, recent, previous, current = self.source()
        observed["prints"] = tuple(
            replace(item, received_at_ms=item.timestamp_ms - 1)
            if item.trade_id == "d" else item
            for item in observed["prints"]
        )
        self.assertIsNone(certified_snapshot(
            observed, recent, previous, current,
            closed_at_ms=self.CLOSE, decision_ms=self.CLOSE + 10,
        ))

    def test_partial_missing_late_or_mismatched_source_stays_unknown(self):
        for fault in ("drop_ws", "late", "wrong_kline"):
            with self.subTest(fault=fault):
                result = certified_snapshot(
                    *self.source(**{fault: True}),
                    closed_at_ms=self.CLOSE, decision_ms=self.CLOSE + 10,
                )
                self.assertIsNone(result)
        self.assertIsNone(certified_snapshot(
            *self.source(), closed_at_ms=self.CLOSE,
            decision_ms=self.CLOSE + 60_001,
        ))

    def test_old_standalone_impulse_pattern_not_executable_or_admissible(self):
        snapshot = {
            "pattern": "IMPULSE_FLOW", "symbol": "BTCUSDT",
            "robot_handoff_ready": True, "scanner_observational_only": False,
        }
        self.assertFalse(is_robot_executable_signal(snapshot, timeframe="1"))
        self.assertEqual(
            scanner_candidate_admission_error({
                "status": "AVAILABLE", "symbol": "BTCUSDT",
                "timeframe": "1", "signal_snapshot": snapshot,
            }),
            "Scanner candidate pattern is not supported by Robot",
        )


if __name__ == "__main__":
    unittest.main()
