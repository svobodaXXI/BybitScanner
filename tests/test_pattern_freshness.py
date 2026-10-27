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
# decision_time_ms is the OPEN time of the last closed candle the Scanner used
# (ikigai_box_scanner.box_robot_formation); the plan is created while the next candle
# forms (real plans: created >= 1.03 candles after it). FIRST is the first post-signal bar.
DECISION = 1_792_518_300_000  # aligned to the 5m grid
assert DECISION % STEP == 0
FIRST = DECISION + STEP


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
        rows = [(DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.0023, 0.0023),          # the decision candle: closed
                (FIRST, 0.0024, 0.0023, 0.0023)]             # forming
        candles, fresh = run_box(box(), rows, FIRST + 60_000)
        self.assertEqual(candles, ())
        self.assertTrue(fresh)

    def test_short_untouched_take_is_fresh(self):
        rows = [(DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.00232, 0.0023),
                (FIRST, 0.0024, 0.00232, 0.0023),
                (FIRST + STEP, 0.0024, 0.00232, 0.0023),
                (FIRST + 2 * STEP, 0.0001, 0.0001, 0.0001)]  # forming: ignored even if beyond TAKE
        candles, fresh = run_box(box(), rows, FIRST + 2 * STEP + 1000)
        self.assertEqual([c["time_ms"] for c in candles], [FIRST, FIRST + STEP])
        self.assertTrue(fresh)

    def test_short_take_reached_by_closed_candle_is_stale(self):
        rows = [(DECISION - STEP, 0.0024, 0.0023, 0.0023),
                (DECISION, 0.0024, 0.00232, 0.0023),
                (FIRST, 0.0024, 0.002316, 0.0023),  # first post-signal bar, low == take
                (FIRST + STEP, 0.0024, 0.0023, 0.0023)]  # forming
        self.assertFalse(run_box(box(), rows, FIRST + STEP + 1000)[1])

    def test_long_take_reached_is_stale_and_untouched_is_fresh(self):
        rows_hit = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1), (FIRST, 10.0, 1, 1), (FIRST + STEP, 1, 1, 1)]
        rows_miss = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1), (FIRST, 9.99, 1, 1), (FIRST + STEP, 1, 1, 1)]
        snapshot = box("LONG", take="10")
        self.assertFalse(run_box(snapshot, rows_hit, FIRST + STEP + 1000)[1])
        self.assertTrue(run_box(snapshot, rows_miss, FIRST + STEP + 1000)[1])

    def test_candles_up_to_and_including_the_decision_candle_do_not_count(self):
        # Regression (PR #597 review): the decision candle (open == decision_time_ms) was
        # already vetted by the Scanner's own completion gate. Its low may be <= TAKE without
        # P1 having been entered; re-judging it here would be a false EXPIRED.
        rows = [(DECISION - STEP, 0.0024, 0.001, 0.0023),   # before the plan
                (DECISION, 0.0024, 0.002316, 0.0023),       # decision candle, low == TAKE
                (FIRST, 0.0024, 0.00232, 0.0023),           # first post-signal bar: clean
                (FIRST + STEP, 0.0024, 0.00232, 0.0023)]    # forming
        candles, fresh = run_box(box(), rows, FIRST + STEP + 1000)
        self.assertEqual([c["time_ms"] for c in candles], [FIRST])
        self.assertTrue(fresh)
        long_rows = [(DECISION - STEP, 1, 1, 1), (DECISION, 10.0, 1, 1), (FIRST, 9.0, 1, 1), (FIRST + STEP, 1, 1, 1)]
        self.assertTrue(run_box(box("LONG", take="10"), long_rows, FIRST + STEP + 1000)[1])

    def test_first_counted_candle_is_exactly_the_one_after_the_decision_candle(self):
        rows = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1), (FIRST, 1, 1, 1),
                (FIRST + STEP, 1, 1, 1), (FIRST + 2 * STEP, 1, 1, 1)]
        candles, _ = run_box(box("LONG", take="10"), rows, FIRST + 2 * STEP + 1000)
        self.assertEqual([c["time_ms"] for c in candles], [FIRST, FIRST + STEP])

    def test_decision_candle_missing_from_closed_evidence_fails_closed(self):
        # Without the closed decision candle the newest kline might BE the decision candle
        # (still forming at the evidence time): the range cannot be proven contiguous from it.
        rows = [(DECISION - 2 * STEP, 1, 1, 1), (DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1)]  # last = forming
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=loader_for(rows), now_ms=DECISION + 1000)

    def test_gap_in_closed_range_fails_closed(self):
        rows = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1), (FIRST, 1, 1, 1),
                (FIRST + 2 * STEP, 1, 1, 1), (FIRST + 3 * STEP, 1, 1, 1)]   # FIRST+STEP missing
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=loader_for(rows),
                                           now_ms=FIRST + 3 * STEP + 1000)
        # a missing FIRST bar (evidence jumps over it) is a gap too
        rows = [(DECISION - STEP, 1, 1, 1), (DECISION, 1, 1, 1), (FIRST + STEP, 1, 1, 1), (FIRST + 2 * STEP, 1, 1, 1)]
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=loader_for(rows),
                                           now_ms=FIRST + 2 * STEP + 1000)

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
                now_ms=FIRST + (pf.MAX_LOOKBACK_CANDLES + 5) * STEP)
        self.assertEqual(loader.calls, [])

    def test_unavailable_or_malformed_evidence_fails_closed(self):
        for evidence in (None, pd.DataFrame(), frame([(DECISION, 1, 1, 1)])):
            with self.subTest(evidence=type(evidence).__name__):
                with self.assertRaises(pf.PatternFreshnessError):
                    pf.load_pattern_closed_candles(
                        "X", box(), candle_loader=lambda *a, **k: evidence, now_ms=FIRST + 1000)
        inverted = frame([(DECISION - STEP, 1, 1, 1), (DECISION, 1.0, 2.0, 1.5), (FIRST, 1, 1, 1)])
        with self.assertRaises(pf.PatternFreshnessError):
            pf.load_pattern_closed_candles("X", box(), candle_loader=lambda *a, **k: inverted,
                                           now_ms=FIRST + 1000)

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
        good = {"closed": True, "timeframe": str(TF), "time_ms": FIRST, "high": 1.0, "low": 0.5, "close": 0.7}
        pf.pattern_candidate_fresh(box(), (good,))
        for candles in (
            ({**good, "time_ms": DECISION},),                        # the decision candle is not post-signal
            ({**good, "time_ms": FIRST + STEP},),                    # skips the first post-signal bar
            ({**good, "timeframe": "1"},),
            ({**good, "closed": False},),
            (good, {**good, "time_ms": FIRST + 2 * STEP}),           # gap
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
        miss = lambda s, snap: (self.candle(FIRST, 0.0024, 0.00232),)
        hit = lambda s, snap: (self.candle(FIRST, 0.0024, 0.002316),)
        self.assertIs(self.verdict(box(), miss), True)
        self.assertIs(self.verdict(box(), hit), False)
        self.assertIs(self.verdict(box(), lambda s, snap: ()), True)

        def unavailable(s, snap):
            raise RuntimeError("evidence was not prepared")

        self.assertIsNone(self.verdict(box(), unavailable))
        self.assertIsNone(self.verdict(box(), None))
        # a gap in the evidence is unproven, never "fresh"
        self.assertIsNone(self.verdict(box(), lambda s, snap: (self.candle(FIRST + STEP, 1, 1),)))
        # the decision candle itself is not evidence either (it would be a false EXPIRED)
        self.assertIsNone(self.verdict(box(), lambda s, snap: (self.candle(DECISION, 0.0024, 0.002316),)))

    def test_l_shape_fresh_stale_and_unproven(self):
        first = BREAKOUT + STEP
        ok = lambda s, snap: (self.candle(first, 307.0, 306.0),)
        dead = lambda s, snap: (self.candle(first, 306.0, 304.0),)
        self.assertIs(self.verdict(l_shape(), ok), True)
        self.assertIs(self.verdict(l_shape(), dead), False)
        self.assertIsNone(self.verdict(l_shape(), lambda s, snap: (self.candle(first + STEP, 1, 1),)))


class MirrorFreshnessTests(unittest.TestCase):
    """MIRROR reuses the frozen target/stop evidence, never Wedge apex replay."""

    @staticmethod
    def snapshot(direction="SHORT"):
        base = l_shape(direction)
        base["pattern"] = "MIRROR"
        terms = base.pop("l_shape")
        # MIRROR's breakout_time_ms denotes the CONFIRMATION candle open.
        terms["breakout_time_ms"] = DECISION
        terms["confirmation"] = {
            "kind": "ENGULFING", "timeframe": str(TF),
            "open_time_ms": DECISION, "close_time_ms": FIRST,
        }
        base["mirror_entry"] = terms
        return base

    def test_mirror_uses_shared_freshness_and_paper_auto_runtime(self):
        snapshot = self.snapshot()
        self.assertEqual(pf.freshness_kind(snapshot), pf.KIND_MIRROR)
        self.assertEqual(pf.freshness_fetch(lambda *_: ("wedge",),
                                          pattern_fetch=lambda *_: ("mirror",))("X", snapshot), ("mirror",))
        verdict = RuntimeVerdictTests.verdict
        candle = RuntimeVerdictTests.candle
        self.assertIs(verdict(snapshot, lambda *_: ()), True)
        self.assertIs(verdict(snapshot, lambda *_: (candle(FIRST, 307.0, 306.0),)), True)
        self.assertIs(verdict(snapshot, lambda *_: (candle(FIRST, 306.0, 304.0),)), False)
        self.assertIsNone(verdict(snapshot, lambda *_: (candle(FIRST + STEP, 307.0, 306.0),)))

    def test_confirmation_candle_is_not_rejudged_as_post_entry(self):
        snapshot = self.snapshot()
        rows = [(DECISION - STEP, 307.0, 306.0, 306.5),
                (DECISION, 400.0, 1.0, 307.6),  # confirmed signal: not post-entry
                (FIRST, 307.0, 306.0, 306.5),
                (FIRST + STEP, 307.0, 306.0, 306.5)]  # forming
        candles = pf.load_pattern_closed_candles("ABCUSDT", snapshot,
                                                 candle_loader=loader_for(rows),
                                                 now_ms=FIRST + STEP + 1000)
        self.assertEqual([x["time_ms"] for x in candles], [FIRST])
        self.assertTrue(pf.pattern_candidate_fresh(snapshot, candles))


if __name__ == "__main__":
    unittest.main()
