"""
tests.test_geometry_candidate_selection_freshness

Focused regression for the Geometry candidate-selection change:

- stale candidates are excluded BEFORE ranking, using the Pattern-layer
  freshness predicate injected by wedge/analyzer.py (Geometry never
  imports Wedge);
- eligible candidates are ordered by
  (mode_priority, -body_zone_breaches, geometry_score);
- CANONICAL priority and the existing geometry_score are unchanged.

The AEVOUSDT fixture lives in the gitignored debug/ directory, so the two
fixture-backed tests skip when it is absent.
"""

import json
import os
import unittest
from unittest.mock import patch

import geometry.engine as engine
from wedge.analyzer import _freshness_predicate
from wedge.detector import evaluate_structure_freshness


FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "debug",
    "AEVOUSDT_5m_rising_wedge_fixture.json",
)


def _load_fixture():
    import pandas as pd

    with open(FIXTURE, encoding="utf-8") as handle:
        fixture = json.load(handle)

    frame = pd.DataFrame(
        [
            {
                key: candle[key]
                for key in ("time", "open", "high", "low", "close", "volume")
            }
            for candle in fixture["candles"]
        ]
    )

    return fixture, frame


class _StubGeometry:
    """Minimal stand-in exposing only what candidate selection reads."""

    def __init__(
        self,
        name,
        score,
        body_breaches=0,
        mode="EXPLORATORY",
        start_index=0,
        end_index=100,
        apex_index=500.0,
        current_index=110,
    ):
        self.name = name
        self.score = score
        self.upper_line = {"anchor_index": 0, "slope": 0.0}
        self.lower_line = {"anchor_index": 0, "slope": 0.0}
        self.validation = {"valid": True}
        self.pair_metrics = {"geometry_mode": mode}
        self.apex = {"index": apex_index}
        self.start_index = start_index
        self.end_index = end_index
        self.current_index = current_index
        self.envelope_metrics = {
            "body_zone_breaches": {
                "upper_body_breach_indices": list(range(body_breaches)),
                "lower_body_breach_early_indices": [],
                "lower_body_breach_late_indices": [],
            }
        }


def _select(candidates):
    """Run the REAL selection in analyze_geometry over a controlled pool."""

    queue = list(candidates)

    def _pair(*args, **kwargs):
        return queue.pop(0)

    with patch.object(
        engine,
        "build_candidate_lines",
        side_effect=[["upper"], ["lower"] * len(queue)],
    ), patch.object(
        engine,
        "filter_candidates",
        side_effect=lambda items: items,
    ), patch.object(
        engine,
        "evaluate_candidate_pair",
        side_effect=_pair,
    ), patch.object(
        engine,
        "rank_geometry",
        side_effect=lambda geometry: geometry.score,
    ):

        return engine.analyze_geometry(
            highs=[{"index": index, "price": 1.0} for index in range(4)],
            lows=[{"index": index, "price": 1.0} for index in range(4)],
            current_index=110,
            candles=None,
            freshness_predicate=_freshness_predicate,
        )


class FixtureBaselineTest(unittest.TestCase):

    @unittest.skipUnless(os.path.exists(FIXTURE), "AEVOUSDT fixture not present")
    def test_full_fixture_winner_is_unchanged(self):
        """Case 1: clean CANONICAL winner, anchors and START=95 unchanged."""

        from pivots import find_pivots
        from wedge import analyze_wedge

        fixture, frame = _load_fixture()
        highs, lows = find_pivots(frame)

        result = analyze_wedge(
            highs,
            lows,
            current_index=len(frame) - 1,
            candles=frame,
        )

        geometry = result["geometry"]
        expected = fixture["geometry"]

        self.assertTrue(result["detection"]["detected"])
        self.assertEqual(result["pattern"], fixture["analysis"]["pattern"])
        self.assertEqual(geometry["start_index"], 95)
        self.assertEqual(geometry["start_index"], expected["start_index"])
        self.assertEqual(geometry["end_index"], expected["end_index"])
        self.assertEqual(
            geometry["upper_line"]["anchor_index"],
            expected["upper_line"]["anchor_index"],
        )
        self.assertEqual(
            geometry["lower_line"]["anchor_index"],
            expected["lower_line"]["anchor_index"],
        )
        self.assertEqual(
            geometry["pair_metrics"]["geometry_mode"],
            "CANONICAL",
        )
        self.assertEqual(result["score"], fixture["analysis"]["score"])

    @unittest.skipUnless(os.path.exists(FIXTURE), "AEVOUSDT fixture not present")
    def test_exploratory_only_pool_prefers_zero_body_breach_candidate(self):
        """Case 2: with no CANONICAL available, the clean candidate wins."""

        from pivots import find_pivots
        from wedge import analyze_wedge

        _, frame = _load_fixture()
        highs, lows = find_pivots(frame)

        original = engine.evaluate_candidate_pair

        def downgraded(*args, **kwargs):
            geometry = original(*args, **kwargs)
            if geometry is not None:
                pair_metrics = getattr(geometry, "pair_metrics", None)
                if isinstance(pair_metrics, dict):
                    pair_metrics["geometry_mode"] = "EXPLORATORY"
            return geometry

        with patch.object(
            engine,
            "evaluate_candidate_pair",
            side_effect=downgraded,
        ):
            result = analyze_wedge(
                highs,
                lows,
                current_index=len(frame) - 1,
                candles=frame,
            )

        geometry = result["geometry"]
        breaches = geometry["envelope_metrics"]["body_zone_breaches"]
        total = (
            len(breaches.get("upper_body_breach_indices") or [])
            + len(breaches.get("lower_body_breach_early_indices") or [])
            + len(breaches.get("lower_body_breach_late_indices") or [])
        )

        # Score-only ranking picks U20/L7 (geometry_score 236.746) with 49
        # body-zone breaches. The body-breach preference takes the clean
        # U156/L95 pair (geometry_score 227.229) instead, deliberately
        # giving up ~10 score points for containment.
        self.assertEqual(total, 0)
        self.assertEqual(geometry["upper_line"]["anchor_index"], 156)
        self.assertEqual(geometry["lower_line"]["anchor_index"], 95)
        self.assertNotEqual(geometry["upper_line"]["anchor_index"], 20)
        self.assertNotEqual(geometry["lower_line"]["anchor_index"], 7)
        self.assertEqual(
            geometry["pair_metrics"]["geometry_mode"],
            "EXPLORATORY",
        )


class SelectionOrderingTest(unittest.TestCase):

    def test_stale_candidate_never_replaces_fresh_candidate(self):
        """Case 3: staleness outweighs both a better score and fewer breaches."""

        # (a) stale because end_index is far behind current_index
        fresh = _StubGeometry("fresh", score=100.0, body_breaches=5, end_index=100)
        stale = _StubGeometry("stale", score=999.0, body_breaches=0, end_index=10)

        self.assertFalse(
            evaluate_structure_freshness(0, 10, 500.0, 110)["fresh"]
        )
        self.assertIs(_select([fresh, stale]), fresh)
        self.assertIs(_select([stale, fresh]), fresh)

        # (b) SAME end_index and SAME freshness_bars, but freshness_window
        # differs via structure length: 100 bars -> window 20, 5 bars ->
        # window 15 (the FRESHNESS_WINDOW_MIN_BARS floor). 18 bars is fresh
        # for the long structure and stale for the short one.
        wide = _StubGeometry(
            "wide",
            score=100.0,
            body_breaches=9,
            start_index=0,
            end_index=100,
            current_index=118,
        )
        narrow = _StubGeometry(
            "narrow",
            score=999.0,
            body_breaches=0,
            start_index=95,
            end_index=100,
            current_index=118,
        )

        self.assertEqual(wide.end_index, narrow.end_index)
        self.assertEqual(
            evaluate_structure_freshness(0, 100, 500.0, 118)["freshness_bars"],
            evaluate_structure_freshness(95, 100, 500.0, 118)["freshness_bars"],
        )
        self.assertNotEqual(
            evaluate_structure_freshness(0, 100, 500.0, 118)["freshness_window"],
            evaluate_structure_freshness(95, 100, 500.0, 118)["freshness_window"],
        )
        self.assertTrue(evaluate_structure_freshness(0, 100, 500.0, 118)["fresh"])
        self.assertFalse(evaluate_structure_freshness(95, 100, 500.0, 118)["fresh"])
        self.assertIs(_select([wide, narrow]), wide)
        self.assertIs(_select([narrow, wide]), wide)

        # (c) SAME end_index and window, before_apex differs
        ahead = _StubGeometry("ahead", score=100.0, body_breaches=9, apex_index=500.0)
        passed = _StubGeometry("passed", score=999.0, body_breaches=0, apex_index=105.0)

        self.assertFalse(
            evaluate_structure_freshness(0, 100, 105.0, 110)["before_apex"]
        )
        self.assertIs(_select([ahead, passed]), ahead)
        self.assertIs(_select([passed, ahead]), ahead)

    def test_equal_mode_and_breaches_preserve_score_ordering(self):
        """Case 4: existing geometry_score decides when the new keys tie."""

        low = _StubGeometry("low", score=100.0, body_breaches=3)
        high = _StubGeometry("high", score=200.0, body_breaches=3)

        self.assertIs(_select([low, high]), high)
        self.assertIs(_select([high, low]), high)

    def test_canonical_priority_outranks_cleaner_exploratory(self):
        """CANONICAL priority stays above the body-breach preference."""

        canonical = _StubGeometry(
            "canonical",
            score=1.0,
            body_breaches=50,
            mode="CANONICAL",
        )
        exploratory = _StubGeometry("exploratory", score=999.0, body_breaches=0)

        self.assertIs(_select([canonical, exploratory]), canonical)
        self.assertIs(_select([exploratory, canonical]), canonical)

    def test_all_stale_pool_keeps_previous_behaviour(self):
        """No fresh candidate: the pool is not emptied and ranking still applies."""

        first = _StubGeometry("first", score=100.0, body_breaches=0, end_index=10)
        second = _StubGeometry("second", score=200.0, body_breaches=0, end_index=10)

        self.assertIs(_select([first, second]), second)


if __name__ == "__main__":
    unittest.main()
