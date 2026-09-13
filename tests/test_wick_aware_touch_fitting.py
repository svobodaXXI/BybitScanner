"""
Focused regression coverage for
DOCUMENTS/CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-002.md:

- geometry.touches.count_touches (ATR-normalized touch_tolerance /
  violation_tolerance, graduated per-point score, bounded outlier
  allowance per line, legacy-percentage fallback when ATR is unavailable)
- geometry.touches.analyze_touches (preserved upper_touches / lower_touches
  / total_touches / valid contract, additive diagnostic fields)
- geometry.validation.touches.validate_touches (unchanged valid/reason
  contract, additive outlier/violation counts in details)
"""

import unittest

import pandas as pd

from geometry.touches import (
    count_touches,
    analyze_touches,
    ATR_PERIOD,
    TOUCH_TOLERANCE_ATR_MULTIPLIER,
    VIOLATION_TOLERANCE_ATR_MULTIPLIER,
    LEGACY_TOUCH_TOLERANCE_PERCENT,
)
from geometry.validation.touches import validate_touches


def _flat_candles(count=40, level=100.0, half_range=1.0):
    """Constant true-range candles so ATR(14) settles at a known value."""

    rows = []

    for _ in range(count):
        rows.append(
            {
                "open": level,
                "high": level + half_range,
                "low": level - half_range,
                "close": level,
            }
        )

    return pd.DataFrame(rows)


FLAT_LINE = {"slope": 0.0, "intercept": 100.0}


class CountTouchesAtrToleranceTests(unittest.TestCase):

    def setUp(self):
        # half_range=1.0 -> true range 2.0 every bar -> ATR(14) == 2.0
        # once warmed up (index >= ATR_PERIOD - 1).
        self.candles = _flat_candles()
        self.touch_tolerance = TOUCH_TOLERANCE_ATR_MULTIPLIER * 2.0
        self.violation_tolerance = VIOLATION_TOLERANCE_ATR_MULTIPLIER * 2.0

    def test_point_within_touch_tolerance_is_a_touch(self):
        points = [{"index": 20, "price": 100.0 + self.touch_tolerance * 0.5}]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["points"][0]["classification"], "touch")
        self.assertTrue(result["points"][0]["counted"])
        self.assertGreater(result["points"][0]["score"], 0.0)

    def test_point_at_zero_distance_scores_one(self):
        points = [{"index": 20, "price": 100.0}]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        self.assertEqual(result["points"][0]["score"], 1.0)

    def test_single_outlier_is_tolerated_and_still_counted(self):
        mid = (self.touch_tolerance + self.violation_tolerance) / 2
        points = [{"index": 20, "price": 100.0 + mid}]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["points"][0]["classification"], "outlier_tolerated")
        self.assertTrue(result["points"][0]["counted"])
        self.assertEqual(result["points"][0]["score"], 0.0)
        self.assertEqual(result["outlier_count"], 1)

    def test_second_outlier_on_same_line_is_excluded(self):
        mid = (self.touch_tolerance + self.violation_tolerance) / 2
        points = [
            {"index": 20, "price": 100.0 + mid},
            {"index": 21, "price": 100.0 - mid},
        ]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        # Only the first outlier is tolerated (outlier_allowance=1 per line).
        self.assertEqual(result["count"], 1)
        classifications = [p["classification"] for p in result["points"]]
        self.assertEqual(
            classifications,
            ["outlier_tolerated", "outlier_excluded"],
        )
        self.assertEqual(result["outlier_count"], 2)

    def test_point_beyond_violation_tolerance_is_a_violation_never_counted(self):
        points = [{"index": 20, "price": 100.0 + self.violation_tolerance * 2}]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["points"][0]["classification"], "violation")
        self.assertFalse(result["points"][0]["counted"])
        self.assertEqual(result["violation_count"], 1)

    def test_violation_does_not_consume_outlier_budget(self):
        mid = (self.touch_tolerance + self.violation_tolerance) / 2
        points = [
            {"index": 20, "price": 100.0 + self.violation_tolerance * 2},
            {"index": 21, "price": 100.0 + mid},
        ]
        result = count_touches(FLAT_LINE, points, candles=self.candles)
        classifications = [p["classification"] for p in result["points"]]
        self.assertEqual(classifications, ["violation", "outlier_tolerated"])
        self.assertEqual(result["count"], 1)


class CountTouchesLegacyFallbackTests(unittest.TestCase):
    """ATR unavailable (no candles, or pre-warm-up index) falls back to the
    pre-CR-SCANNER-GEOMETRY-002 fixed-percentage tolerance."""

    def test_no_candles_falls_back_to_legacy_percentage(self):
        predicted = 100.0
        tolerance = LEGACY_TOUCH_TOLERANCE_PERCENT * predicted
        points = [
            {"index": 5, "price": predicted + tolerance * 0.5},
            {"index": 6, "price": predicted + tolerance * 10},
        ]
        result = count_touches(FLAT_LINE, points, candles=None)
        self.assertEqual(result["points"][0]["classification"], "touch")
        self.assertEqual(result["points"][1]["classification"], "violation")

    def test_pre_warm_up_index_falls_back_to_legacy_percentage(self):
        # ATR_PERIOD=14 rolling window: index 5 has no ATR value yet even
        # though candles are supplied.
        candles = _flat_candles()
        predicted = 100.0
        tolerance = LEGACY_TOUCH_TOLERANCE_PERCENT * predicted
        points = [{"index": 5, "price": predicted + tolerance * 0.5}]
        result = count_touches(FLAT_LINE, points, candles=candles)
        self.assertEqual(result["points"][0]["classification"], "touch")

    def test_missing_line_or_points_returns_zero_result(self):
        self.assertEqual(
            count_touches(None, [{"index": 0, "price": 1}]),
            {"count": 0, "points": [], "outlier_count": 0, "violation_count": 0},
        )
        self.assertEqual(
            count_touches(FLAT_LINE, []),
            {"count": 0, "points": [], "outlier_count": 0, "violation_count": 0},
        )


class AnalyzeTouchesContractTests(unittest.TestCase):
    """Existing GeometryModel touches contract must be unaffected by the
    additive per-point diagnostics."""

    def test_existing_keys_preserved_with_unchanged_meaning(self):
        candles = _flat_candles()
        upper_line = {"slope": 0.0, "intercept": 110.0}
        lower_line = {"slope": 0.0, "intercept": 90.0}

        highs = [
            {"index": 20, "price": 110.0},
            {"index": 21, "price": 110.0},
        ]
        lows = [
            {"index": 20, "price": 90.0},
            {"index": 21, "price": 90.0},
        ]

        result = analyze_touches(upper_line, lower_line, highs, lows, candles=candles)

        self.assertEqual(result["upper_touches"], 2)
        self.assertEqual(result["lower_touches"], 2)
        self.assertEqual(result["total_touches"], 4)
        self.assertTrue(result["valid"])

        # Additive fields present and correctly shaped.
        self.assertIn("upper_touch_points", result)
        self.assertIn("lower_touch_points", result)
        self.assertEqual(len(result["upper_touch_points"]), 2)
        self.assertEqual(result["upper_outlier_count"], 0)
        self.assertEqual(result["upper_violation_count"], 0)

    def test_invalid_when_either_side_below_two_touches(self):
        candles = _flat_candles()
        upper_line = {"slope": 0.0, "intercept": 110.0}
        lower_line = {"slope": 0.0, "intercept": 90.0}

        highs = [{"index": 20, "price": 110.0}]
        lows = [
            {"index": 20, "price": 90.0},
            {"index": 21, "price": 90.0},
        ]

        result = analyze_touches(upper_line, lower_line, highs, lows, candles=candles)

        self.assertEqual(result["upper_touches"], 1)
        self.assertFalse(result["valid"])

    def test_candles_parameter_is_optional(self):
        # Backward compatibility: callers that do not supply candles (e.g.
        # tests.test_geometry, tests.test_geometry_pipeline) keep working.
        upper_line = {"slope": 0.0, "intercept": 110.0}
        lower_line = {"slope": 0.0, "intercept": 90.0}

        highs = [
            {"index": 20, "price": 110.0},
            {"index": 21, "price": 110.0},
        ]
        lows = [
            {"index": 20, "price": 90.0},
            {"index": 21, "price": 90.0},
        ]

        result = analyze_touches(upper_line, lower_line, highs, lows)

        self.assertEqual(result["upper_touches"], 2)
        self.assertEqual(result["lower_touches"], 2)
        self.assertTrue(result["valid"])


class ValidateTouchesContractTests(unittest.TestCase):
    """geometry.validation.touches.validate_touches: unchanged valid/reason
    contract, additive diagnostic counts in details only."""

    def test_valid_when_both_sides_meet_minimum(self):
        result = validate_touches(
            {
                "upper_touches": 3,
                "lower_touches": 2,
                "total_touches": 5,
                "upper_outlier_count": 1,
                "lower_violation_count": 2,
            }
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["reason"], "Touch confirmation acceptable")
        self.assertEqual(result["details"]["upper_touches"], 3)
        self.assertEqual(result["details"]["upper_outlier_count"], 1)
        self.assertEqual(result["details"]["lower_violation_count"], 2)

    def test_invalid_when_upper_below_minimum(self):
        result = validate_touches({"upper_touches": 1, "lower_touches": 4})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "Not enough upper line touches")

    def test_invalid_when_lower_below_minimum(self):
        result = validate_touches({"upper_touches": 4, "lower_touches": 1})
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "Not enough lower line touches")

    def test_missing_touches_data(self):
        result = validate_touches(None)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "Missing touches data")
        self.assertEqual(result["details"], {})

    def test_missing_diagnostic_fields_default_to_zero(self):
        # A touches dict from before this CR (no outlier/violation keys)
        # must not raise and must default the new fields to zero.
        result = validate_touches({"upper_touches": 3, "lower_touches": 3})
        self.assertTrue(result["valid"])
        self.assertEqual(result["details"]["upper_outlier_count"], 0)
        self.assertEqual(result["details"]["lower_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
