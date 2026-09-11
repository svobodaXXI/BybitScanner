import unittest
from unittest.mock import patch

from geometry.evaluation import evaluate_candidate_pair
from geometry.model import GeometryModel
from geometry.ranking import rank_geometry
from wedge.detector import detect_structure
from wedge.integrity import evaluate_directional_envelope


def _envelope(
    upper_outside=0,
    lower_outside=0,
    above=(),
    below=(),
    upper_body_breaches=(),
    lower_strict_breaches=(),
    lower_late_breaches=(),
):
    return {
        "upper": {
            "support_count": 3,
            "support_span": 10,
            "outside_count": upper_outside,
            "outside_ratio": upper_outside / 10,
            "max_outside_percent": float(upper_outside)
        },
        "lower": {
            "support_count": 3,
            "support_span": 10,
            "outside_count": lower_outside,
            "outside_ratio": lower_outside / 10,
            "max_outside_percent": float(lower_outside)
        },
        "candle_containment": {
            "evaluated_count": 10,
            "upper_early_max_run": 0,
            "lower_early_max_run": 0,
            "fully_above_upper_indices": list(above),
            "fully_below_lower_indices": list(below)
        },
        "body_zone_breaches": {
            "upper_body_breach_indices": list(upper_body_breaches),
            "lower_body_breach_early_indices": list(lower_strict_breaches),
            "lower_body_breach_late_indices": list(lower_late_breaches),
        }
    }


def _geometry(upper_slope, lower_slope, envelope=None):
    return {
        "upper_line": {"slope": upper_slope, "intercept": 100.0},
        "lower_line": {"slope": lower_slope, "intercept": 90.0},
        "compression": {"is_compressing": True},
        "touches": {"valid": True, "total_touches": 4},
        "validation": {"valid": True, "checks": {}, "failed_checks": []},
        "apex": {"index": 20},
        "end_index": 10,
        "current_index": 10,
        "pair_metrics": {
            "common_span": 10,
            "anchor_balance": 1.0,
            "slope_balance": 1.0,
            "boundary_order_valid": True,
            "true_converging": True
        },
        "envelope_metrics": envelope or _envelope()
    }


class DirectionalEnvelopeQualityTests(unittest.TestCase):
    def test_falling_roles(self):
        result = evaluate_directional_envelope(
            _geometry(-1.0, -0.5, _envelope(2, 4)),
            "Falling Wedge"
        )
        self.assertEqual(result["boundaries"]["upper"]["role"], "STRICT")
        self.assertEqual(result["boundaries"]["lower"]["role"], "EXCURSION")
        self.assertEqual(result["strict_outside_count"], 2)
        self.assertEqual(result["excursion_outside_count"], 4)
        self.assertFalse(result["hard_rejection"])
        self.assertEqual(result["score_effect"], 0.0)

    def test_rising_roles(self):
        result = evaluate_directional_envelope(
            _geometry(0.5, 1.0, _envelope(4, 2)),
            "Rising Wedge"
        )
        self.assertEqual(result["boundaries"]["upper"]["role"], "EXCURSION")
        self.assertEqual(result["boundaries"]["lower"]["role"], "STRICT")
        self.assertEqual(result["strict_outside_count"], 2)
        self.assertEqual(result["excursion_outside_count"], 4)

    def test_triangle_roles(self):
        result = evaluate_directional_envelope(
            _geometry(-1.0, 1.0),
            "Triangle Compression"
        )
        self.assertEqual(result["strict_sides"], ["upper", "lower"])
        self.assertEqual(result["excursion_sides"], [])

    def test_same_metrics_receive_pattern_specific_roles(self):
        geometry = _geometry(-1.0, -0.5, _envelope(3, 3))
        falling = evaluate_directional_envelope(geometry, "Falling Wedge")
        rising = evaluate_directional_envelope(geometry, "Rising Wedge")
        self.assertEqual(falling["boundaries"]["upper"]["role"], "STRICT")
        self.assertEqual(rising["boundaries"]["upper"]["role"], "EXCURSION")

    def test_falling_wedge_containment_violations_no_longer_reject_detection(self):
        # DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md replaces the
        # old hard containment reject with a soft signal.quality tier
        # penalty. detect_structure() must still detect the structure and
        # merely report the violation counts.
        result = detect_structure(
            _geometry(-1.0, -0.5, _envelope(upper_body_breaches=(1, 2, 3)))
        )
        self.assertTrue(result["detected"])
        self.assertEqual(
            result["features"]["containment_violations"]["upper_violations"], 3
        )

    def test_falling_wedge_lower_strict_and_flexible_breaches_are_counted(self):
        result = detect_structure(
            _geometry(
                -1.0, -0.5,
                _envelope(lower_strict_breaches=(1, 2), lower_late_breaches=(9,))
            )
        )
        self.assertTrue(result["detected"])
        violations = result["features"]["containment_violations"]
        self.assertEqual(violations["lower_strict_violations"], 2)
        # No candles supplied -> the late breach cannot be confirmed as
        # reversal-pattern-excused, so it counts as a violation by default.
        self.assertEqual(violations["lower_flexible_unrecognized_breaches"], 1)

    def test_rising_wedge_and_triangle_get_no_containment_violations_yet(self):
        # Explicit, currently-accepted scope gap: the mirrored Rising Wedge
        # rule is separate future work, so these patterns get zero
        # violations (and are therefore never penalized by containment)
        # until that future decision is authorized.
        rising = detect_structure(
            _geometry(0.5, 1.0, _envelope(upper_body_breaches=(1, 2, 3)))
        )
        triangle = detect_structure(
            _geometry(-1.0, 1.0, _envelope(upper_body_breaches=(1, 2, 3)))
        )
        self.assertTrue(rising["detected"])
        self.assertTrue(triangle["detected"])
        self.assertEqual(
            rising["features"]["containment_violations"],
            {
                "upper_violations": 0,
                "lower_strict_violations": 0,
                "lower_flexible_unrecognized_breaches": 0,
            }
        )

    @patch("geometry.evaluation.detect_pre_pattern_impulse", return_value={})
    @patch("geometry.evaluation.calculate_envelope_metrics")
    @patch("geometry.evaluation.calculate_pair_metrics")
    @patch("geometry.evaluation.validate_geometry", return_value={"valid": True})
    @patch("geometry.evaluation.analyze_touches", return_value={"valid": True})
    @patch("geometry.evaluation.calculate_compression", return_value={"is_compressing": True})
    @patch("geometry.evaluation.calculate_apex", return_value={"index": 20})
    def test_geometry_evaluation_has_no_directional_outside_downgrade(
        self,
        _apex,
        _compression,
        _touches,
        _validation,
        pair_metrics,
        envelope_metrics,
        _impulse
    ):
        pair_metrics.return_value = {
            "anchor_sequence": {"family": "rising", "valid": True}
        }
        envelope_metrics.return_value = _envelope(upper_outside=9)
        upper = {
            "line": {"slope": 1.0, "intercept": 100.0},
            "points": [{"index": 0, "price": 100.0}, {"index": 10, "price": 110.0}]
        }
        lower = {
            "line": {"slope": 0.5, "intercept": 90.0},
            "points": [{"index": 0, "price": 90.0}, {"index": 10, "price": 95.0}]
        }
        result = evaluate_candidate_pair(upper, lower, current_index=10)
        self.assertEqual(result.pair_metrics["geometry_mode"], "CANONICAL")
        self.assertNotIn("strict_outside_ratio", result.pair_metrics)

    def test_rank_geometry_is_symmetric_for_swapped_envelopes(self):
        first = GeometryModel(
            upper_line={}, lower_line={}, apex={}, compression={}, touches={},
            validation={}, pair_metrics={"common_span": 10},
            envelope_metrics={"upper": _envelope(1, 2)["upper"], "lower": _envelope(1, 2)["lower"]}
        )
        second = GeometryModel(
            upper_line={}, lower_line={}, apex={}, compression={}, touches={},
            validation={}, pair_metrics={"common_span": 10},
            envelope_metrics={"upper": _envelope(1, 2)["lower"], "lower": _envelope(1, 2)["upper"]}
        )
        self.assertAlmostEqual(rank_geometry(first), rank_geometry(second))


if __name__ == "__main__":
    unittest.main()
