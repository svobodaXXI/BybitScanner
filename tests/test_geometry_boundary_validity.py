"""
tests.test_geometry_boundary_validity

Focused regression for the Geometry-layer boundary-validity admission
(DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, "Approved narrow
exception").

A candidate is rejected only when, on ONE boundary and at the SAME bar:

- a confirmed pivot of that boundary's own type lies outside the line
  (already filtered with the existing pivot-line tolerance), AND
- the candle body breaches that same line, AND
- the bar is at or after that boundary's own primary anchor, AND
- the bar is no later than the existing formation END.

Post-END action is never a formation defect, and nothing here rejects on
breach count or ratio.

The AEVOUSDT fixture lives in the gitignored debug/ directory, so the
fixture-backed test skips when it is absent.
"""

import json
import os
import unittest
from unittest.mock import patch

import geometry.engine as engine
from wedge.analyzer import _freshness_predicate


FIXTURE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "debug",
    "AEVOUSDT_5m_rising_wedge_fixture.json",
)


class _StubGeometry:
    """Minimal stand-in exposing only what the admission gate reads."""

    def __init__(
        self,
        name,
        score=100.0,
        upper_anchor=100,
        lower_anchor=100,
        start_index=100,
        end_index=190,
        current_index=199,
        upper_outside=(),
        lower_outside=(),
        upper_body=(),
        lower_body_early=(),
        lower_body_late=(),
    ):
        self.name = name
        self.score = score
        self.upper_line = {"anchor_index": upper_anchor, "slope": 0.0}
        self.lower_line = {"anchor_index": lower_anchor, "slope": 0.0}
        self.validation = {"valid": True}
        self.pair_metrics = {"geometry_mode": "EXPLORATORY"}
        self.apex = {"index": 500.0}
        self.start_index = start_index
        self.end_index = end_index
        self.current_index = current_index
        self.envelope_metrics = {
            "upper": {"outside_indices": list(upper_outside)},
            "lower": {"outside_indices": list(lower_outside)},
            "body_zone_breaches": {
                "upper_body_breach_indices": list(upper_body),
                "lower_body_breach_early_indices": list(lower_body_early),
                "lower_body_breach_late_indices": list(lower_body_late),
            },
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
            current_index=199,
            candles=None,
            freshness_predicate=_freshness_predicate,
        )


class BoundaryContradictionTest(unittest.TestCase):

    def test_contradicted_boundary_is_rejected_even_with_the_best_key(self):
        """Pivot outside AND body breach on the same boundary at bar 150."""

        # Both carry the SAME body-breach count, so the existing ranking key
        # cannot separate them and only the new gate can.
        bad = _StubGeometry(
            "bad", score=999.0, upper_outside=[150], upper_body=[148, 150, 152]
        )
        good = _StubGeometry(
            "good", score=1.0, upper_body=[148, 150, 152]
        )

        self.assertIs(_select([bad, good]), good)
        self.assertIs(_select([good, bad]), good)

    def test_empty_pool_returns_no_geometry_without_fallback(self):
        only = _StubGeometry(
            "only", score=999.0, upper_outside=[150], upper_body=[150]
        )

        self.assertIsNone(_select([only]))

    def test_outside_pivot_without_a_body_breach_is_admitted(self):
        """INJ semantics: an extreme pokes out, the bodies stay inside."""

        candidate = _StubGeometry(
            "outside_only", score=999.0, lower_outside=[150]
        )

        self.assertIs(_select([candidate]), candidate)

    def test_body_breach_without_an_outside_pivot_is_admitted(self):
        """No breach count or ratio gate: bodies alone never reject."""

        candidate = _StubGeometry(
            "bodies_only",
            score=999.0,
            upper_body=[140, 141, 142, 143, 144, 145, 146, 147],
        )

        self.assertIs(_select([candidate]), candidate)

    def test_evidence_on_two_different_boundaries_is_not_a_contradiction(self):
        """Same bar, but the pivot is upper and the body breach is lower."""

        candidate = _StubGeometry(
            "split", score=999.0, upper_outside=[150], lower_body_early=[150]
        )

        self.assertIs(_select([candidate]), candidate)

    def test_contradiction_after_end_is_a_breakout_not_a_defect(self):
        """PONS semantics: END=190, the contradiction sits at bar 193."""

        candidate = _StubGeometry(
            "post_end",
            score=999.0,
            end_index=190,
            upper_outside=[193],
            upper_body=[193, 195],
        )

        self.assertIs(_select([candidate]), candidate)

    def test_contradiction_before_its_own_anchor_is_not_applicable(self):
        """The boundary does not describe bars preceding its own anchor."""

        candidate = _StubGeometry(
            "pre_anchor",
            score=999.0,
            start_index=100,
            upper_anchor=160,
            lower_anchor=100,
            upper_outside=[120],
            upper_body=[120],
        )

        self.assertIs(_select([candidate]), candidate)

    def test_lower_boundary_contradiction_uses_both_zone_lists(self):
        early = _StubGeometry(
            "early", score=999.0, lower_outside=[150], lower_body_early=[150]
        )
        late = _StubGeometry(
            "late", score=999.0, lower_outside=[185], lower_body_late=[185]
        )
        # Same single body breach, no contradicting pivot.
        good = _StubGeometry(
            "good", score=1.0, lower_body_early=[150]
        )

        self.assertIs(_select([early, good]), good)
        self.assertIs(_select([late, good]), good)

    def test_contradiction_exactly_at_end_is_still_a_defect(self):
        """END itself belongs to the formation."""

        candidate = _StubGeometry(
            "at_end",
            score=999.0,
            end_index=190,
            upper_outside=[190],
            upper_body=[190],
        )

        self.assertIsNone(_select([candidate]))


class ConfirmedCaseUnchangedTest(unittest.TestCase):

    @unittest.skipUnless(os.path.exists(FIXTURE), "AEVOUSDT fixture not present")
    def test_aevo_winner_is_unchanged(self):
        import pandas as pd

        from pivots import find_pivots

        with open(FIXTURE, encoding="utf-8") as handle:
            fixture = json.load(handle)

        frame = pd.DataFrame(
            [
                {key: candle[key] for key in
                 ("time", "open", "high", "low", "close", "volume")}
                for candle in fixture["candles"]
            ]
        )
        highs, lows = find_pivots(frame.copy())
        geometry = engine.analyze_geometry(
            highs,
            lows,
            current_index=len(frame) - 1,
            candles=frame,
            freshness_predicate=_freshness_predicate,
        )
        expected = fixture["geometry"]

        self.assertIsNotNone(geometry)
        self.assertEqual(geometry.start_index, expected["start_index"])
        self.assertEqual(geometry.end_index, expected["end_index"])
        self.assertEqual(
            geometry.upper_line["anchor_index"],
            expected["upper_line"]["anchor_index"],
        )
        self.assertEqual(
            geometry.lower_line["anchor_index"],
            expected["lower_line"]["anchor_index"],
        )
        self.assertEqual(geometry.pair_metrics["geometry_mode"], "CANONICAL")


if __name__ == "__main__":
    unittest.main()
