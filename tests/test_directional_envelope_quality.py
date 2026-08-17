import unittest
from unittest.mock import patch

from geometry.evaluation import evaluate_candidate_pair
from geometry.model import GeometryModel
from geometry.ranking import rank_geometry
from wedge.detector import detect_structure
from wedge.integrity import evaluate_directional_envelope


def _envelope(upper_outside=0, lower_outside=0, above=(), below=()):
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

    def test_strict_run_over_two_rejects_falling(self):
        result = detect_structure(
            _geometry(-1.0, -0.5, _envelope(above=(1, 2, 3)))
        )
        self.assertFalse(result["detected"])
        self.assertEqual(result["features"]["containment_strict_side"], "upper")
        self.assertEqual(result["features"]["containment_strict_run"], 3)

    def test_strict_run_over_two_rejects_rising(self):
        result = detect_structure(
            _geometry(0.5, 1.0, _envelope(below=(1, 2, 3)))
        )
        self.assertFalse(result["detected"])
        self.assertEqual(result["features"]["containment_strict_side"], "lower")

    def test_triangle_rejects_breach_on_either_strict_side(self):
        upper = detect_structure(
            _geometry(-1.0, 1.0, _envelope(above=(1, 2, 3)))
        )
        lower = detect_structure(
            _geometry(-1.0, 1.0, _envelope(below=(1, 2, 3)))
        )
        self.assertFalse(upper["detected"])
        self.assertFalse(lower["detected"])
        self.assertEqual(upper["features"]["containment_strict_side"], "both")

    def test_two_strict_breaches_remain_allowed(self):
        result = detect_structure(
            _geometry(-1.0, -0.5, _envelope(above=(1, 2)))
        )
        self.assertTrue(result["detected"])

    def test_excursion_run_does_not_reject(self):
        falling = detect_structure(
            _geometry(-1.0, -0.5, _envelope(below=(1, 2, 3, 4)))
        )
        rising = detect_structure(
            _geometry(0.5, 1.0, _envelope(above=(1, 2, 3, 4)))
        )
        self.assertTrue(falling["detected"])
        self.assertTrue(rising["detected"])

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
