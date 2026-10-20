"""MIRROR-FRESHNESS-1: closed-candle freshness proof for IKIGAI_BOX and L-shape.

Box and L-shape snapshots carry no scanner_geometry_cursor and no apex, so the
Wedge proof can never run on them. These tests pin the pattern-specific proof
and its fail-closed boundaries: nothing is synthesised, a gap / stale evidence /
unreadable term gives no verdict.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

import pandas as pd

import pattern_freshness as pf
from terminal.runtime.paper_runtime import PaperRuntime

TF = 5
STEP = TF * 60_000
DECISION = 1_792_518_300_000  # aligned to the 5m grid
assert DECISION % STEP == 0


def box(direction="SHORT", take="0.002316", **overrides):
    snapshot = {
        "pattern": "IKIGAI_BOX", "environment": "PAPER", "attempt": 1,
        "decision_time_ms": DECISION,
        "identity": {"symbol": "DOODUSDT", "timeframe": str(TF), "direction": direction},
        "plan": {"direction": direction, "take_price": take},
    }
    snapshot.update(overrides)
    return snapshot


BREAKOUT = DECISION - 10 * STEP


def l_shape(direction="SHORT", target="305.0", stop="308.9", reference="307.6"):
    return {
        "pattern": "L-shape", "robot_handoff_ready": True, "scanner_source_timeframe": str(TF),
        "timeframe": str(TF), "symbol": "ABCUSDT",
        "l_shape": {
            "direction": direction, "source_timeframe": str(TF), "breakout_time_ms": BREAKOUT,
            "extreme_time_ms": BREAKOUT - 5 * STEP, "reference": reference, "target": target,
            "stop": stop, "structural_stop": "312.7", "stop_kind": "RATIO_FALLBACK",
            "potential_percent": 0.85, "reward_risk": 2.0,
        },
    }


def frame(rows):
    """rows: (open_time_ms, high, low, close); the LAST row is the still-forming kline."""
    return pd.DataFrame(
        [{"time": t, "open": c, "high": h, "low": low, "close": c, "volume": 1.0} for t, h, low, c in rows]
    )


def loader_for(rows):
    calls = []

    def loader(symbol, timeframe, limit, minimum=50):
        calls.append((symbol, timeframe, limit))
        return frame(rows)

    loader.calls = calls
    return loader


def run_box(snapshot, rows, now_ms):
    candles = pf.load_pattern_closed_candles(
        "DOODUSDT", snapshot, candle_loader=loader_for(rows), now_ms=now_ms)
    return candles, pf.pattern_candidate_fresh(snapshot, candles)


class BoxFreshnessTests(unittest.TestCase):
    def test_no_candle_closed_since_decision_is_fresh_evidence(self):
        rows = [(DECISION - 2 * STEP, 0.0024, 0.0023, 0.0023),
                (DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.0023, 0.0023)]  # forming
        candles, fresh = run_box(box(), rows, DECISION + 60_000)
        self.assertEqual(candles, ())
        self.assertTrue(fresh)

    def test_short_untouched_take_is_fresh(self):
        rows = [(DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.00232, 0.0023),
                (DECISION + STEP, 0.0024, 0.00232, 0.0023),
                (DECISION + 2 * STEP, 0.0001, 0.0001, 0.0001)]  # forming: ignored even if beyond TAKE
        candles, fresh = run_box(box(), rows, DECISION + 2 * STEP + 1000)
        self.assertEqual([c["time_ms"] for c in candles], [DECISION, DECISION + STEP])
        self.assertTrue(fresh)

    def test_short_take_reached_by_closed_candle_is_stale(self):
        rows = [(DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.002316, 0.0023),  # low == take
                (DECISION + STEP, 0.0024, 0.0023, 0.0023)]
        self.assertFalse(run_box(box(), rows, DECISION + STEP + 1000)[1])

    def test_long_take_reached_is_stale_and_untouched_is_fresh(self):
        rows_hit = [(DECISION - STEP, 1, 1, 1), (DECISION, 10.0, 1, 1), (DECISION + STEP, 1, 1, 1)]
        rows_miss = [(DECISION - STEP, 1, 1, 1), (DECISION, 9.99, 1, 1), (DECISION + STEP, 1, 1, 1)]
        snapshot = box("LONG", take="10")
        self.assertFalse(run_box(snapshot, rows_hit, DECISION + STEP + 1000)[1])
        self.assertTrue(run_box(snapshot, rows_miss, DECISION + STEP + 1000)[1])

    def test_candle_before_decision_does_not_count(self):
        rows = [(DECISION - STEP, 0.0024, 0.001, 0.0023),  # touched TAKE before the plan existed
                (DECISION, 0.0024, 0.00232, 0.0023),
                (DECISION + STEP, 0.0024, 0.00232, 0.0023)]
        self.assertTrue(run_box(box(), rows, DECISION + STEP + 1000)[1])

    def test_gap_in_closed_range_fails_closed(self):
        rows = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1),
                (DECISION + 2 * STEP, 1, 1, 1), (DECISION + 3 * STEP, 1, 1, 1)]
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=loader_for(rows),
                                           now_ms=DECISION + 3 * STEP + 1000)

    def test_evidence_that_does_not_reach_the_signal_fails_closed(self):
        rows = [(DECISION - 5 * STEP, 1, 1, 1), (DECISION - 4 * STEP, 1, 1, 1),
                (DECISION - 3 * STEP, 1, 1, 1)]
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=loader_for(rows),
                                           now_ms=DECISION + STEP)

    def test_signal_too_old_to_cover_fails_closed_without_a_request(self):
        loader = loader_for([(DECISION, 1, 1, 1), (DECISION + STEP, 1, 1, 1)])
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles(
                "X", box(), candle_loader=loader,
                now_ms=DECISION + (pf.MAX_LOOKBACK_CANDLES + 5) * STEP)
        self.assertEqual(loader.calls, [])

    def test_unavailable_or_malformed_evidence_fails_closed(self):
        for evidence in (None, pd.DataFrame(), frame([(DECISION, 1, 1, 1)])):
            with self.subTest(evidence=type(evidence).__name__):
                with self.assertRaises(pf.PatternFreshnessError):
                    pf.load_pattern_closed_candles(
                        "X", box(), candle_loader=lambda *a, **k: evidence, now_ms=DECISION + STEP)
        inverted = frame([(DECISION - STEP, 1, 1, 1), (DECISION, 1.0, 2.0, 1.5), (DECISION + STEP, 1, 1, 1)])
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=lambda *a, **k: inverted,
                                           now_ms=DECISION + STEP + 1000)

    def test_unreadable_frozen_terms_fail_closed(self):
        bad = (
            box(decision_time_ms=DECISION + 1),                       # off the candle grid
            box(decision_time_ms=None),
            box(take="not-a-price"),
            box(take="0"),
            box("SHORT", identity={"symbol": "X", "timeframe": "5", "direction": "LONG"}),
            box(identity={"symbol": "X", "timeframe": "abc", "direction": "SHORT"}),
        )
        for snapshot in bad:
            with self.subTest(snapshot=str(snapshot)[:60]):
                with self.assertRaises(pf.PatternFreshnessError):
                    pf.pattern_candidate_fresh(snapshot, ())


class LShapeFreshnessTests(unittest.TestCase):
    FIRST = BREAKOUT + STEP

    def rows(self, *ohlc):
        out = [(BREAKOUT, 307.0, 306.0, 306.5)]
        for i, (h, low, c) in enumerate(ohlc):
            out.append((self.FIRST + i * STEP, h, low, c))
        out.append((self.FIRST + len(ohlc) * STEP, 999.0, 1.0, 1.0))  # forming
        return out

    def run_l(self, snapshot, *ohlc):
        rows = self.rows(*ohlc)
        now = rows[-1][0] + 1000
        candles = pf.load_pattern_closed_candles("ABCUSDT", snapshot, candle_loader=loader_for(rows), now_ms=now)
        return candles, pf.pattern_candidate_fresh(snapshot, candles)

    def test_untouched_target_and_stop_is_fresh(self):
        candles, fresh = self.run_l(l_shape(), (307.0, 306.0, 306.5), (307.2, 306.1, 306.4))
        self.assertEqual(len(candles), 2)
        self.assertTrue(fresh)

    def test_target_reached_is_stale(self):
        self.assertFalse(self.run_l(l_shape(), (307.0, 306.0, 306.5), (306.0, 304.9, 305.0))[1])

    def test_stop_reached_is_stale(self):
        self.assertFalse(self.run_l(l_shape(), (308.9, 306.0, 308.0))[1])

    def test_breakout_candle_itself_is_not_evidence(self):
        # The breakout bar (open == breakout_time_ms) already touched the target; it is not "after" it.
        rows = [(BREAKOUT, 400.0, 1.0, 300.0), (self.FIRST, 307.0, 306.0, 306.5), (self.FIRST + STEP, 1, 1, 1)]
        candles = pf.load_pattern_closed_candles("ABCUSDT", l_shape(), candle_loader=loader_for(rows),
                                                 now_ms=self.FIRST + STEP + 1000)
        self.assertTrue(pf.pattern_candidate_fresh(l_shape(), candles))

    def test_retest_after_breakout_is_not_a_freshness_failure(self):
        # Touching the retest reference is the entry trigger of the Robot lifecycle, not completion.
        self.assertTrue(self.run_l(l_shape(), (307.8, 306.5, 307.7))[1])

    def test_invalidation_after_a_retest_is_still_detected(self):
        self.assertFalse(self.run_l(l_shape(), (307.8, 306.5, 307.7), (306.0, 304.0, 304.5))[1])

    def test_long_direction_mirrors(self):
        long = l_shape("LONG", target="310.0", stop="305.0", reference="306.0")
        self.assertFalse(self.run_l(long, (310.0, 308.0, 309.0))[1])
        self.assertTrue(self.run_l(long, (309.0, 306.5, 308.0))[1])

    def test_unreadable_terms_fail_closed(self):
        broken = l_shape()
        broken["l_shape"]["target"] = "x"
        with self.assertRaises(pf.PatternFreshnessError):
            pf.pattern_candidate_fresh(broken, ())
        unaligned = l_shape()
        unaligned["l_shape"]["breakout_time_ms"] = BREAKOUT + 1
        with self.assertRaises(pf.PatternFreshnessError):
            pf.pattern_candidate_fresh(unaligned, ())


class BoundaryTests(unittest.TestCase):
    def test_wedge_is_not_handled_here(self):
        wedge = {"pattern": "Falling Wedge", "scanner_geometry_cursor": {}, "geometry": {"apex": {}}}
        self.assertIsNone(pf.freshness_kind(wedge))
        with self.assertRaises(pf.PatternFreshnessError):
            pf.pattern_candidate_fresh(wedge, ())
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", wedge, candle_loader=loader_for([]), now_ms=1)

    def test_non_contiguous_or_foreign_candles_are_rejected(self):
        good = {"closed": True, "timeframe": str(TF), "time_ms": DECISION, "high": 1.0, "low": 0.5, "close": 0.7}
        pf.pattern_candidate_fresh(box(), (good,))
        for candles in (
            ({**good, "time_ms": DECISION + STEP},),                 # skips the first post-signal bar
            ({**good, "timeframe": "1"},),
            ({**good, "closed": False},),
            (good, {**good, "time_ms": DECISION + 2 * STEP}),        # gap
        ):
            with self.assertRaises(pf.PatternFreshnessError):
                pf.pattern_candidate_fresh(box(), candles)

    def test_fetch_routes_only_box_and_l_shape_to_pattern_evidence(self):
        seen = []
        fetch = pf.freshness_fetch(lambda s, snap: seen.append(("wedge", s)) or ("w",),
                                   pattern_fetch=lambda s, snap: seen.append(("pattern", s)) or ("p",))
        wedge = {"pattern": "Falling Wedge"}
        self.assertEqual(fetch("A", wedge), ("w",))
        self.assertEqual(fetch("B", box()), ("p",))
        self.assertEqual(fetch("C", l_shape()), ("p",))
        self.assertEqual(seen, [("wedge", "A"), ("pattern", "B"), ("pattern", "C")])


class RuntimeVerdictTests(unittest.TestCase):
    """PaperRuntime._autopilot_candidate_fresh: policy-facing tri-state for Box / L-shape."""

    @staticmethod
    def verdict(snapshot, evidence):
        return PaperRuntime._autopilot_candidate_fresh(
            SimpleNamespace(robot_catchup_evidence=evidence), "DOODUSDT", snapshot)

    @staticmethod
    def candle(time_ms, high, low):
        return {"closed": True, "timeframe": str(TF), "time_ms": time_ms, "high": high, "low": low, "close": low}

    def test_box_fresh_stale_and_unproven(self):
        miss = lambda s, snap: (self.candle(DECISION, 0.0024, 0.00232),)
        hit = lambda s, snap: (self.candle(DECISION, 0.0024, 0.002316),)
        self.assertIs(self.verdict(box(), miss), True)
        self.assertIs(self.verdict(box(), hit), False)
        self.assertIs(self.verdict(box(), lambda s, snap: ()), True)

        def unavailable(s, snap):
            raise RuntimeError("evidence was not prepared")

        self.assertIsNone(self.verdict(box(), unavailable))
        self.assertIsNone(self.verdict(box(), None))
        # a gap in the evidence is unproven, never "fresh"
        self.assertIsNone(self.verdict(box(), lambda s, snap: (self.candle(DECISION + STEP, 1, 1),)))

    def test_l_shape_fresh_stale_and_unproven(self):
        first = BREAKOUT + STEP
        ok = lambda s, snap: (self.candle(first, 307.0, 306.0),)
        dead = lambda s, snap: (self.candle(first, 306.0, 304.0),)
        self.assertIs(self.verdict(l_shape(), ok), True)
        self.assertIs(self.verdict(l_shape(), dead), False)
        self.assertIsNone(self.verdict(l_shape(), lambda s, snap: (self.candle(first + STEP, 1, 1),)))


if __name__ == "__main__":
    unittest.main()
