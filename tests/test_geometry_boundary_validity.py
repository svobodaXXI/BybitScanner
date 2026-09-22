"""Sustained own-boundary body mismatch; 2026-09-22 contract replaces #180.

A single pivot-plus-body event is no longer an admission veto. Historical
AEVO/INJ/WLD evidence is preserved in test_geometry_formation_fit.
"""
import unittest
import pandas as pd
from geometry.envelope_metrics import evaluate_formation_body_fit
from geometry.engine import _is_boundary_structurally_valid
from tests.test_geometry_candidate_selection_freshness import _StubGeometry, _select


def candidate(upper=(), lower=(), *, end=32, upper_anchor=10, lower_anchor=10):
    frame = pd.DataFrame([dict(open=100., high=101., low=99., close=100.) for _ in range(45)])
    for index in upper:
        frame.loc[index, ["close", "high"]] = [110., 111.]
    for index in lower:
        frame.loc[index, ["close", "low"]] = [90., 89.]
    item = _StubGeometry("fixture", 999., start_index=10, end_index=end, current_index=39)
    item.upper_line = dict(slope=0., intercept=105., anchor_index=upper_anchor)
    item.lower_line = dict(slope=0., intercept=95., anchor_index=lower_anchor)
    item.envelope_metrics["formation_body_fit"] = evaluate_formation_body_fit(
        item.upper_line, item.lower_line, frame, end
    )
    return item


class SustainedBoundaryTest(unittest.TestCase):
    def test_seven_consecutive_body_breaches_reject_both_sides(self):
        for side in ("upper", "lower"):
            with self.subTest(side=side):
                bad = candidate(**{side: range(20, 27)})
                good = candidate()
                good.score = 1.
                self.assertIs(_select([bad, good]), good)
                self.assertIs(_select([good, bad]), good)
                self.assertIsNone(_select([bad]))

    def test_six_breaches_are_not_automatically_rejected(self):
        self.assertTrue(_is_boundary_structurally_valid(candidate(upper=range(20, 26))))

    def test_isolated_breach_even_with_outside_pivot_does_not_reject(self):
        item = candidate(upper=[20])
        item.envelope_metrics["upper"] = {"outside_indices": [20]}
        self.assertIs(_select([item]), item)

    def test_many_separated_breaches_do_not_become_a_run(self):
        item = candidate(upper=range(12, 33, 2))
        self.assertTrue(_is_boundary_structurally_valid(item))
        self.assertEqual(item.envelope_metrics["formation_body_fit"]["upper"]["max_consecutive_breaches"], 1)

    def test_opposite_boundaries_do_not_combine(self):
        self.assertTrue(_is_boundary_structurally_valid(candidate(upper=range(20, 24), lower=range(24, 28))))

    def test_post_end_breakout_does_not_reject_or_increase_selection_count(self):
        item = candidate(upper=range(33, 43))
        self.assertIs(_select([item]), item)
        self.assertEqual(item.envelope_metrics["formation_body_fit"]["upper"]["body_breach_indices"], [])

    def test_end_is_inclusive_and_cannot_be_shortened_to_excuse_a_run(self):
        self.assertFalse(_is_boundary_structurally_valid(candidate(upper=range(26, 33))))

    def test_own_anchor_clips_only_its_boundary(self):
        ignored = candidate(upper=range(14, 21), upper_anchor=25)
        self.assertTrue(_is_boundary_structurally_valid(ignored))
        prefix = candidate(lower=range(14, 21), upper_anchor=25)
        self.assertFalse(_is_boundary_structurally_valid(prefix))
        self.assertEqual(prefix.envelope_metrics["formation_body_fit"]["lower"]["breach_runs"], [[14, 20]])

    def test_candle_free_geometry_exposes_unavailable_not_measured_zero(self):
        self.assertIsNone(evaluate_formation_body_fit(
            dict(anchor_index=10), dict(anchor_index=20), None, 32
        ))


if __name__ == "__main__":
    unittest.main()
