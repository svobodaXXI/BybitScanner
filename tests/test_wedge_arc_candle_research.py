"""Exact-boundary OHLC/candle arc research gates, no executable Robot path."""
from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
import unittest

from robot_entry_flow_evidence import FlowTransition
from terminal.market_data.wedge_arc_candle_research import (
    observe_closed_wedge_arc_candles,
)


class FrozenWedgeArcCandlesTests(unittest.TestCase):
    @staticmethod
    def host(pattern="Falling Wedge"):
        direction = "LONG" if pattern == "Falling Wedge" else "SHORT"
        upper, lower = (
            ({"slope": -0.1, "intercept": 107}, {"slope": -0.02, "intercept": 99.2})
            if direction == "LONG"
            else ({"slope": 0.02, "intercept": 105.8}, {"slope": 0.1, "intercept": 97})
        )
        return SimpleNamespace(
            candidate_id="wedge-arc-1", state_revision=3, status="APPROVED",
            symbol=SimpleNamespace(value="BTCUSDT"),
            signal_snapshot={
                "pattern": pattern,
                "scanner_geometry_cursor": {
                    "version": "1.0", "timeframe": "1",
                    "geometry_index": 6, "source_candle_time_ms": 60_000,
                },
                "robot_geometry": {
                    "current_index": 6,
                    "upper_line": upper, "lower_line": lower,
                    "apex": {"index": 25, "valid_intersection": True},
                },
            },
            robot_state={
                "pattern": pattern, "direction": direction,
                "phase": "WAITING_BREAKOUT", "state_version": "1.0",
                "geometry_cursor": 10,
            },
        )

    @staticmethod
    def bullish():
        values = [
            (101, 101.2, 100, 100.6),
            (100.6, 100.8, 99.6, 100),
            (100, 100.3, 99.4, 99.8),
            (100.1, 100.2, 99.2, 99.4),
            (99.35, 100.5, 99.3, 100.3),
        ]
        return tuple(dict(time=(i + 1)*60_000, open=o, high=h, low=l, close=c)
                     for i, (o, h, l, c) in enumerate(values))

    @staticmethod
    def bearish():
        values = [
            (103, 105, 102.8, 104),
            (104, 105.5, 103.8, 105),
            (105, 105.8, 104.9, 105.4),
            (105, 106, 104.8, 105.6),
            (105.7, 105.9, 104.3, 104.5),
        ]
        return tuple(dict(time=(i + 1)*60_000, open=o, high=h, low=l, close=c)
                     for i, (o, h, l, c) in enumerate(values))

    @staticmethod
    def flow(direction="LONG"):
        return FlowTransition(
            known_at_ms=360_010, current_delta_fraction=Decimal("0"),
            current_price_change_bps=Decimal("0"),
            buy_wave_accelerating=False, sell_wave_accelerating=False,
            sell_impact_fading=direction == "LONG",
            buy_impact_fading=direction == "SHORT",
            bid_refill_observed=None, ask_refill_observed=None,
            sell_absorption_candidate=None, buy_absorption_candidate=None,
        )

    @classmethod
    def evaluate(cls, *, host=None, bars=None, flow=None, **kw):
        host = cls.host() if host is None else host
        direction = host.robot_state["direction"]
        rows = bars if bars is not None else (
            cls.bearish() if direction == "SHORT" else cls.bullish()
        )
        arguments = dict(
            decision_ms=360_020, atr=Decimal("2"),
            max_boundary_distance_atr=Decimal("0.25"),
            doji_body_fraction=Decimal("0.1"),
            source_id="historical-closed-OHLC-research",
        )
        arguments.update(kw)
        return observe_closed_wedge_arc_candles(
            host, rows, cls.flow(direction) if flow is None else flow,
            **arguments,
        )

    def test_long_closed_bullish_engulfing_near_frozen_lower_arc(self):
        result = self.evaluate()
        self.assertIsNotNone(result)
        self.assertEqual(result.outcome, "ARC_CANDLE_CONTEXT_RESEARCH")
        self.assertEqual(result.candle_patterns, ("BULLISH_ENGULFING",))
        self.assertTrue(result.arc_shape_observed)
        self.assertTrue(result.near_frozen_edge)
        self.assertEqual(result.confluence.outcome,
                         "FLOW_FADE_WITH_CANDLE_CONTEXT_RESEARCH")
        self.assertEqual(len(result.confluence.candle_event_outcomes), 1)
        self.assertFalse(result.trading_authorized)
        self.assertFalse(result.source_complete)
        self.assertFalse(result.confluence.arc_geometry_attested)

    def test_short_closed_bearish_engulfing_uses_mirrored_geometry(self):
        result = self.evaluate(host=self.host("Rising Wedge"))
        self.assertEqual(result.direction, "SHORT")
        self.assertEqual(result.candle_patterns, ("BEARISH_ENGULFING",))
        self.assertTrue(result.arc_shape_observed)
        self.assertEqual(result.confluence.outcome,
                         "FLOW_FADE_WITH_CANDLE_CONTEXT_RESEARCH")
        self.assertFalse(result.trading_authorized)

    def test_existing_morning_star_recognizer_is_reused(self):
        rows = list(deepcopy(self.bullish()))
        rows[2] = dict(time=180_000, open=100.5, high=100.6,
                       low=99.5, close=99.7)
        rows[3] = dict(time=240_000, open=99.3, high=99.5,
                       low=99.25, close=99.35)
        rows[4] = dict(time=300_000, open=99.35, high=100.4,
                       low=99.3, close=100.3)
        result = self.evaluate(bars=tuple(rows))
        self.assertEqual(result.candle_patterns, ("MORNING_STAR",))
        self.assertFalse(result.trading_authorized)

    def test_hammer_and_doji_have_distinct_directionality(self):
        rows = list(deepcopy(self.bullish()))
        rows[-1] = dict(time=300_000, open=99.8, high=100.05,
                        low=99.3, close=100)
        hammer = self.evaluate(bars=tuple(rows))
        self.assertEqual(hammer.candle_patterns, ("HAMMER",))
        rows[-1] = dict(time=300_000, open=99.8, high=100,
                        low=99.3, close=99.81)
        doji = self.evaluate(bars=tuple(rows))
        self.assertEqual(doji.candle_patterns, ("DOJI",))
        self.assertEqual(doji.confluence.candle_event_outcomes[0][1],
                         "INDECISION")

    def test_outside_frozen_edge_never_attaches_candle_confluence(self):
        result = self.evaluate(max_boundary_distance_atr=Decimal("0.05"))
        self.assertEqual(result.outcome, "OUTSIDE_FROZEN_EDGE_ZONE")
        self.assertIsNone(result.confluence)
        self.assertEqual(result.candle_patterns, ())

    def test_non_rounding_prices_do_not_attach_candles(self):
        rows = list(deepcopy(self.bullish()))
        # Down -> up -> down invalidates every 4-6-candle rounded arc.
        rows[3]["low"] = 99.6
        rows[3]["close"] = 99.7  # preserve valid OHLC while breaking the arc
        result = self.evaluate(bars=tuple(rows))
        self.assertEqual(result.outcome, "ARC_NOT_OBSERVED")
        self.assertIsNone(result.confluence)

    def test_future_or_gapped_m1_is_rejected(self):
        self.assertIsNone(self.evaluate(decision_ms=359_999))
        rows = list(deepcopy(self.bullish()))
        rows[1]["time"] += 60_000
        self.assertIsNone(self.evaluate(bars=tuple(rows)))
        rows = list(deepcopy(self.bullish()))
        rows[4]["close"] = 200
        self.assertIsNone(self.evaluate(bars=tuple(rows)))

    def test_mismatched_frozen_cursor_apex_or_phase_is_rejected(self):
        host = self.host()
        host.robot_state["geometry_cursor"] = 9
        self.assertIsNone(self.evaluate(host=host))
        host = self.host()
        host.signal_snapshot["robot_geometry"]["apex"]["index"] = 10
        self.assertIsNone(self.evaluate(host=host))
        host = self.host()
        host.robot_state["phase"] = "RETEST_DETECTED"
        self.assertIsNone(self.evaluate(host=host))
        host = self.host()
        host.signal_snapshot["scanner_geometry_cursor"]["source_candle_time_ms"] += 1
        self.assertIsNone(self.evaluate(host=host))

    def test_untrusted_numeric_tolerance_never_authorizes_research(self):
        self.assertIsNone(self.evaluate(atr=Decimal("-1")))
        self.assertIsNone(self.evaluate(max_boundary_distance_atr=Decimal("NaN")))
        self.assertIsNone(self.evaluate(doji_body_fraction=Decimal("0.8")))
        self.assertIsNone(self.evaluate(source_id=""))


if __name__ == "__main__":
    unittest.main()
