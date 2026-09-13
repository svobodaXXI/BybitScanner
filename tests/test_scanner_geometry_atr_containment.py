"""
Focused regression coverage for
DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md:

- geometry.envelope_metrics.evaluate_body_zone_breaches (ATR-normalized,
  zone-split, direction-neutral raw body breaches)
- geometry.reversal_patterns (Bullish Engulfing / Morning Star / Arc)
- wedge.integrity.evaluate_containment_violations (disabled defaults and
  preserved Falling Wedge interpretation + reversal-pattern exception)
- signal.quality's containment severity / tier-downgrade scale
- wedge.detector's proportional freshness window and removal of the old
  hard containment reject
"""

import unittest
from unittest.mock import patch

import pandas as pd

from geometry.envelope_metrics import evaluate_body_zone_breaches
from geometry.reversal_patterns import (
    is_bullish_engulfing,
    is_morning_star,
    is_smooth_arc,
    has_reversal_exception,
)
import wedge.integrity as integrity
from wedge.integrity import evaluate_containment_violations
from wedge.detector import detect_structure, FRESHNESS_WINDOW_MIN_BARS, FRESHNESS_WINDOW_FACTOR
from signal.quality import evaluate_quality


BASE_ROW = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}


def _make_candles(overrides, count=30):
    """count identical BASE_ROW candles (true range == 2.0 throughout, so
    ATR(14) stabilizes to exactly 2.0 after warm-up), with specific rows
    replaced per `overrides` ({index: {field: value}})."""

    rows = []

    for index in range(count):
        row = dict(BASE_ROW)
        if index in overrides:
            row.update(overrides[index])
        rows.append(row)

    return pd.DataFrame(rows, columns=["open", "high", "low", "close"])


UPPER_LINE = {"slope": 0.0, "intercept": 105.0}
LOWER_LINE = {"slope": 0.0, "intercept": 95.0}


class BodyZoneBreachTests(unittest.TestCase):
    def test_upper_body_breach_detected_anywhere_in_structure(self):
        candles = _make_candles({17: {"open": 105.0, "close": 106.0}})

        result = evaluate_body_zone_breaches(
            UPPER_LINE, LOWER_LINE, candles, start_index=15, current_index=25
        )

        self.assertIn(17, result["upper_body_breach_indices"])
        self.assertEqual(result["lower_body_breach_early_indices"], [])
        self.assertEqual(result["lower_body_breach_late_indices"], [])

    def test_lower_body_breach_in_early_zone_is_strict(self):
        candles = _make_candles({18: {"open": 95.0, "close": 94.0}})

        result = evaluate_body_zone_breaches(
            UPPER_LINE, LOWER_LINE, candles, start_index=15, current_index=25
        )

        self.assertIn(18, result["lower_body_breach_early_indices"])
        self.assertEqual(result["lower_body_breach_late_indices"], [])

    def test_lower_body_breach_in_late_zone_is_flexible(self):
        # midpoint = 15 + round((25-15)*0.6) = 21; index 23 is late-zone.
        candles = _make_candles({23: {"open": 95.0, "close": 94.0}})

        result = evaluate_body_zone_breaches(
            UPPER_LINE, LOWER_LINE, candles, start_index=15, current_index=25
        )

        self.assertEqual(result["midpoint_index"], 21)
        self.assertIn(23, result["lower_body_breach_late_indices"])
        self.assertEqual(result["lower_body_breach_early_indices"], [])

    def test_wick_only_breach_is_not_a_body_breach(self):
        # low dips well below the lower line, but the body (open/close)
        # stays inside tolerance -> not counted anywhere.
        candles = _make_candles({23: {"low": 90.0}})

        result = evaluate_body_zone_breaches(
            UPPER_LINE, LOWER_LINE, candles, start_index=15, current_index=25
        )

        self.assertEqual(result["lower_body_breach_late_indices"], [])
        self.assertEqual(result["lower_body_breach_early_indices"], [])

    def test_returns_none_without_required_inputs(self):
        self.assertIsNone(
            evaluate_body_zone_breaches(None, LOWER_LINE, _make_candles({}), 0, 10)
        )
        self.assertIsNone(
            evaluate_body_zone_breaches(UPPER_LINE, LOWER_LINE, None, 0, 10)
        )


class ReversalPatternTests(unittest.TestCase):
    def test_bullish_engulfing_detected(self):
        candles = _make_candles({
            10: {"open": 140.0, "close": 120.0, "high": 141.0, "low": 119.0},
            11: {"open": 115.0, "close": 145.0, "high": 146.0, "low": 114.0},
        })
        self.assertTrue(is_bullish_engulfing(candles, 11))

    def test_bullish_engulfing_false_when_not_covering_previous_body(self):
        candles = _make_candles({
            10: {"open": 140.0, "close": 120.0, "high": 141.0, "low": 119.0},
            11: {"open": 125.0, "close": 135.0, "high": 136.0, "low": 124.0},
        })
        self.assertFalse(is_bullish_engulfing(candles, 11))

    def test_morning_star_detected(self):
        candles = _make_candles({
            10: {"open": 150.0, "close": 100.0, "high": 152.0, "low": 98.0},
            11: {"open": 95.0, "close": 95.5, "high": 97.0, "low": 94.0},
            12: {"open": 96.0, "close": 140.0, "high": 142.0, "low": 95.0},
        })
        self.assertTrue(is_morning_star(candles, 12))

    def test_morning_star_false_when_second_body_not_small(self):
        candles = _make_candles({
            10: {"open": 150.0, "close": 100.0, "high": 152.0, "low": 98.0},
            11: {"open": 80.0, "close": 95.0, "high": 97.0, "low": 78.0},
            12: {"open": 96.0, "close": 140.0, "high": 142.0, "low": 95.0},
        })
        self.assertFalse(is_morning_star(candles, 12))

    def test_smooth_arc_detected(self):
        lows = [100.0, 98.0, 96.0, 96.0, 98.0, 100.0]
        overrides = {
            10 + i: {"low": low, "high": low + 2.0}
            for i, low in enumerate(lows)
        }
        candles = _make_candles(overrides)
        self.assertTrue(is_smooth_arc(candles, 15))

    def test_sharp_v_is_not_a_smooth_arc(self):
        # single-candle plunge and immediate recovery: exceeds the
        # max-single-step-vs-ATR guard, so it must not read as an Arc.
        lows = [100.0, 100.0, 100.0, 60.0, 100.0, 100.0]
        overrides = {
            10 + i: {"low": low, "high": low + 2.0}
            for i, low in enumerate(lows)
        }
        candles = _make_candles(overrides)
        self.assertFalse(is_smooth_arc(candles, 15, atr_value=2.0))

    def test_monotonic_decline_is_not_an_arc(self):
        lows = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0]
        overrides = {
            10 + i: {"low": low, "high": low + 2.0}
            for i, low in enumerate(lows)
        }
        candles = _make_candles(overrides)
        self.assertFalse(is_smooth_arc(candles, 15))

    def test_has_reversal_exception_true_for_any_recognized_pattern(self):
        candles = _make_candles({
            10: {"open": 140.0, "close": 120.0, "high": 141.0, "low": 119.0},
            11: {"open": 115.0, "close": 145.0, "high": 146.0, "low": 114.0},
        })
        self.assertTrue(has_reversal_exception(candles, 11))

    def test_has_reversal_exception_false_with_no_pattern(self):
        candles = _make_candles({})
        self.assertFalse(has_reversal_exception(candles, 15))


class ContainmentViolationsTests(unittest.TestCase):
    def _geometry(self, breaches):
        return {
            "envelope_metrics": {
                "body_zone_breaches": breaches
            }
        }

    def test_disabled_by_default_returns_zero_for_all_patterns_with_breaches(self):
        self.assertIs(integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED, False)
        breaches = {
            "upper_body_breach_indices": [17],
            "lower_body_breach_early_indices": [18],
            "lower_body_breach_late_indices": [23],
        }
        candles = _make_candles({23: {"open": 95.0, "close": 94.0}})
        for pattern in ("Falling Wedge", "Rising Wedge", "Triangle Compression"):
            with self.subTest(pattern=pattern):
                result = evaluate_containment_violations(
                    self._geometry(breaches), pattern, candles
                )
                self.assertEqual(result, integrity.ZERO_CONTAINMENT_VIOLATIONS)
                self.assertIsNot(result, integrity.ZERO_CONTAINMENT_VIOLATIONS)

    @patch("wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED", True)
    def test_falling_wedge_counts_all_three_kinds(self):
        candles = _make_candles({
            23: {"open": 95.0, "close": 94.0},  # unrecognized late breach
        })
        breaches = {
            "upper_body_breach_indices": [17],
            "lower_body_breach_early_indices": [18],
            "lower_body_breach_late_indices": [23],
        }
        result = evaluate_containment_violations(
            self._geometry(breaches), "Falling Wedge", candles
        )
        self.assertEqual(result["upper_violations"], 1)
        self.assertEqual(result["lower_strict_violations"], 1)
        self.assertEqual(result["lower_flexible_unrecognized_breaches"], 1)

    @patch("wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED", True)
    def test_late_breach_excused_by_bullish_engulfing_is_not_counted(self):
        candles = _make_candles({
            22: {"open": 100.0, "close": 94.0, "high": 100.5, "low": 93.5},
            23: {"open": 93.0, "close": 101.0, "high": 101.5, "low": 92.5},
        })
        breaches = {
            "upper_body_breach_indices": [],
            "lower_body_breach_early_indices": [],
            "lower_body_breach_late_indices": [23],
        }
        result = evaluate_containment_violations(
            self._geometry(breaches), "Falling Wedge", candles
        )
        self.assertEqual(result["lower_flexible_unrecognized_breaches"], 0)
        self.assertIn(23, result["lower_flexible_excused_indices"])

    @patch("wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED", True)
    def test_rising_wedge_and_triangle_are_not_yet_covered(self):
        breaches = {
            "upper_body_breach_indices": [17],
            "lower_body_breach_early_indices": [18],
            "lower_body_breach_late_indices": [23],
        }
        candles = _make_candles({})
        for pattern in ("Rising Wedge", "Triangle Compression", "Unknown"):
            result = evaluate_containment_violations(
                self._geometry(breaches), pattern, candles
            )
            self.assertEqual(result["upper_violations"], 0)
            self.assertEqual(result["lower_strict_violations"], 0)
            self.assertEqual(result["lower_flexible_unrecognized_breaches"], 0)

    @patch("wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED", True)
    def test_missing_candles_still_counts_resolved_breaches(self):
        # upper/lower-strict counts need no candle lookup (already resolved
        # index lists); only the late-zone reversal-pattern exception needs
        # candles, and without them an unverifiable breach counts as a
        # violation rather than being silently excused.
        breaches = {
            "upper_body_breach_indices": [17],
            "lower_body_breach_early_indices": [18],
            "lower_body_breach_late_indices": [23],
        }
        result = evaluate_containment_violations(
            self._geometry(breaches), "Falling Wedge", None
        )
        self.assertEqual(result["upper_violations"], 1)
        self.assertEqual(result["lower_strict_violations"], 1)
        self.assertEqual(result["lower_flexible_unrecognized_breaches"], 1)


class QualitySeverityDowngradeTests(unittest.TestCase):
    def _elite_inputs(self):
        geometry = {
            "validation": {"valid": True},
            "compression": {"compression_percent": 20},
            "touches": {"total_touches": 6},
        }
        confirmation = {
            "breakout": True,
            "volume": True,
            "retest": True,
            "confirmation_score": 30,
        }
        return geometry, confirmation

    def test_zero_severity_keeps_elite(self):
        geometry, confirmation = self._elite_inputs()
        result = evaluate_quality(
            "Falling Wedge", geometry, confirmation, 90,
            containment_violations={
                "upper_violations": 0,
                "lower_strict_violations": 0,
                "lower_flexible_unrecognized_breaches": 0,
            }
        )
        self.assertEqual(result["quality"], "Elite Setup")

    def test_severity_one_downgrades_elite_to_a(self):
        geometry, confirmation = self._elite_inputs()
        result = evaluate_quality(
            "Falling Wedge", geometry, confirmation, 90,
            containment_violations={
                "lower_flexible_unrecognized_breaches": 1,
            }
        )
        self.assertEqual(result["quality"], "A Setup")
        self.assertIn("Downgraded from Elite Setup", result["reason"])

    def test_severity_two_from_single_strict_violation_downgrades_one_step(self):
        geometry, confirmation = self._elite_inputs()
        result = evaluate_quality(
            "Falling Wedge", geometry, confirmation, 90,
            containment_violations={"upper_violations": 1}
        )
        self.assertEqual(result["quality"], "A Setup")

    def test_severity_three_to_four_downgrades_two_steps(self):
        geometry, confirmation = self._elite_inputs()
        result = evaluate_quality(
            "Falling Wedge", geometry, confirmation, 90,
            containment_violations={"upper_violations": 2}
        )
        self.assertEqual(result["quality"], "B Setup")

    def test_severity_five_or_more_downgrades_three_steps(self):
        geometry, confirmation = self._elite_inputs()
        result = evaluate_quality(
            "Falling Wedge", geometry, confirmation, 90,
            containment_violations={"upper_violations": 3}
        )
        self.assertEqual(result["quality"], "Watch")

    def test_downgrade_never_goes_below_weak_setup(self):
        geometry = {
            "validation": {"valid": True},
            "compression": {"compression_percent": 0},
            "touches": {"total_touches": 0},
        }
        result = evaluate_quality(
            "Falling Wedge", geometry, {}, 10,
            containment_violations={"upper_violations": 10}
        )
        self.assertEqual(result["quality"], "Weak Setup")

    def test_invalid_tier_is_not_affected_by_containment(self):
        result = evaluate_quality(
            "No wedge", None, {}, 0,
            containment_violations={"upper_violations": 10}
        )
        self.assertEqual(result["quality"], "Invalid")


class FreshnessWindowTests(unittest.TestCase):
    def _geometry(self, start_index, end_index, current_index, apex_index):
        return {
            "upper_line": {"slope": -1.0, "intercept": 100.0},
            "lower_line": {"slope": -0.5, "intercept": 90.0},
            "compression": {"is_compressing": True},
            "touches": {"valid": True, "total_touches": 4},
            "validation": {"valid": True},
            "apex": {"index": apex_index},
            "start_index": start_index,
            "end_index": end_index,
            "current_index": current_index,
            "pair_metrics": {},
            "envelope_metrics": {},
        }

    def test_freshness_window_scales_with_structure_length(self):
        # structure_length = 100, factor 0.20 -> window 20 (> the 15 floor)
        geometry = self._geometry(
            start_index=0, end_index=100, current_index=118, apex_index=200
        )
        result = detect_structure(geometry, candles=None)
        self.assertEqual(
            result["features"]["freshness_window"],
            max(FRESHNESS_WINDOW_MIN_BARS, round(100 * FRESHNESS_WINDOW_FACTOR))
        )
        self.assertTrue(result["features"]["freshness"])

    def test_freshness_window_floors_at_minimum_for_short_structures(self):
        # structure_length = 10 -> 0.20*10 = 2, floored to FRESHNESS_WINDOW_MIN_BARS
        geometry = self._geometry(
            start_index=0, end_index=10, current_index=14, apex_index=200
        )
        result = detect_structure(geometry, candles=None)
        self.assertEqual(
            result["features"]["freshness_window"],
            FRESHNESS_WINDOW_MIN_BARS
        )

    @patch("wedge.integrity.CONTAINMENT_VIOLATION_EVALUATION_ENABLED", True)
    def test_containment_no_longer_blocks_detection(self):
        # Heavy containment violations must not flip detected to False;
        # only signal.quality may downgrade the tier now.
        geometry = self._geometry(
            start_index=0, end_index=10, current_index=10, apex_index=20
        )
        geometry["envelope_metrics"] = {
            "body_zone_breaches": {
                "upper_body_breach_indices": [1, 2, 3, 4, 5],
                "lower_body_breach_early_indices": [1, 2, 3],
                "lower_body_breach_late_indices": [9],
            }
        }
        result = detect_structure(geometry, candles=None)
        self.assertTrue(result["detected"])
        self.assertEqual(
            result["features"]["containment_violations"]["upper_violations"], 5
        )


if __name__ == "__main__":
    unittest.main()
