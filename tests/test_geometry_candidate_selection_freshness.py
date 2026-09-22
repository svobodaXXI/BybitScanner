"""
tests.test_geometry_candidate_selection_freshness

Focused regression for the Geometry candidate-selection change:

- stale candidates are excluded BEFORE ranking, using the Pattern-layer
  freshness predicate injected by wedge/analyzer.py (Geometry never
  imports Wedge);
- eligible candidates are ordered by
  (mode_priority, -body_zone_breaches, geometry_score);
- CANONICAL priority and the existing geometry_score are unchanged.

Historical reference revisions are covered in test_geometry_formation_fit.
"""

import unittest
from unittest.mock import patch

import geometry.engine as engine
from wedge.analyzer import _freshness_predicate
from wedge.detector import evaluate_structure_freshness


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
            # 200-bar analysis window: keeps every stub span (<=100) inside
            # the locality gate so these tests still exercise ordering only.
            current_index=199,
            candles=None,
            freshness_predicate=_freshness_predicate,
        )


# AEVO is now covered by tests.test_geometry_formation_fit, including the
# old lower-boundary runs that invalidate the former immutable reference.


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
