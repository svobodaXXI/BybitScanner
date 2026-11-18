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
    def source(cls, *, drop_ws=False, late=False, wrong_kline=False):
        c = cls.CLOSE
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
                tid, ts, seq, side, Decimal(px), Decimal(size),
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
                {"execId": tid, "symbol": "BTCUSDT", "time": str(ts),
                 "seq": str(seq), "side": side, "price": px, "size": size}
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
