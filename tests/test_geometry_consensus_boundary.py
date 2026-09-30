"""GEO-U1 boundary-only shadow contracts; synthetic controls + exact PONS Gold."""

import json
import unittest
from unittest.mock import patch

import pandas as pd

import geometry.consensus_boundary as consensus
from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest
from tests.test_geometry_future_candle_invariance import _with_adversarial_future
from wedge.detector import detect_structure


def _candles(pivot_indices=(20, 40, 60, 80), *, congestion=False):
    """Synthetic rising resistance; equal mirrored support uses identical rules.

    Rising pivot prices clear the unchanged find_pivots min_change filter.
    In congestion, bodies stay near resistance even between wick contacts.
    """
    rows = []
    for i in range(100):
        line = 100 + 0.1 * i
        retreat = 0.6 if congestion else 3.0
        body = line - retreat
        rows.append({"open": body, "close": body,
                     "high": line - (0.5 if congestion else 2), "low": line - 4})
    frame = pd.DataFrame(rows)
    for i in pivot_indices:
        frame.loc[i, "high"] = 100 + 0.1 * i
    return frame


def _mirror(frame):
    result = frame.copy(deep=True)
    for col in ("open", "close"):
        result[col] = 300 - frame[col]
    result["high"] = 300 - frame.low
    result["low"] = 300 - frame.high
    return result


def _build(frame, side="upper", **overrides):
    parameters = dict(as_of_index=len(frame) - 1, episode_start_index=14,
                      inlier_band_atr=0.2, separation_atr=0.75)
    parameters.update(overrides)
    return consensus.build_boundary_consensus(frame, side=side, **parameters)


class BoundaryConsensusTests(unittest.TestCase):
    def test_distributed_multitouch_beats_two_anchor_and_local_support(self):
        distributed = _build(_candles())[0]
        two_anchor = _build(_candles((20, 80)))[0]
        local = _build(_candles((20, 27, 34, 41)))[0]
        self.assertEqual(distributed.inlier_pivot_indices, (20, 40, 60, 80))
        self.assertEqual(distributed.touch_cluster_indices, ((20,), (40,), (60,), (80,)))
        self.assertEqual(distributed.touch_count_distinct, 4)
        self.assertGreater(distributed.quality_tuple, two_anchor.quality_tuple)
        self.assertGreater(distributed.quality_tuple, local.quality_tuple)
        self.assertEqual(distributed.support_span, 60)
        self.assertEqual(distributed.support_coverage_ratio, 60 / 85)
        self.assertAlmostEqual(distributed.slope, 0.1)
        self.assertAlmostEqual(distributed.intercept, 100)

    def test_congestion_requires_body_retreat_and_return_for_a_new_cluster(self):
        frame = _candles((20, 27, 34, 60), congestion=True)
        # One true inward departure, between the congested contacts and retest.
        frame.loc[42:48, ["open", "close", "high"]] -= 3.0
        for side, candles in (("upper", frame), ("lower", _mirror(frame))):
            with self.subTest(side=side):
                result = _build(candles, side)[0]
                self.assertEqual(result.inlier_pivot_indices, (20, 27, 34, 60))
                self.assertEqual(result.touch_cluster_indices, ((20, 27, 34), (60,)))
                self.assertEqual(result.touch_count_distinct, 2)

    def test_long_time_gap_without_price_departure_does_not_reset_cluster(self):
        result = _build(_candles(congestion=True))[0]
        self.assertEqual(result.touch_cluster_indices, ((20, 40, 60, 80),))
        self.assertEqual(result.touch_count_distinct, 1)

    def test_refit_uses_all_inliers_and_reports_final_residuals(self):
        frame = _candles()
        frame.loc[40, "high"] += 0.2
        result = _build(frame)[0]
        # Analytic OLS for x=(20,40,60,80), y=(102,104.2,106,108).
        self.assertAlmostEqual(result.slope, 0.099)
        self.assertAlmostEqual(result.intercept, 100.1)
        self.assertGreater(result.mean_residual_atr, 0)
        self.assertGreaterEqual(result.max_residual_atr, result.mean_residual_atr)
        self.assertLessEqual(result.max_residual_atr, 0.2)

    def test_isolated_pierce_is_diagnostic_and_does_not_drag_consensus(self):
        frame = _candles()
        frame.loc[50, "high"] = 120  # wick only; body is unchanged
        for side, candles in (("upper", frame), ("lower", _mirror(frame))):
            with self.subTest(side=side):
                result = _build(candles, side)[0]
                self.assertEqual(result.inlier_pivot_indices, (20, 40, 60, 80))
                self.assertEqual(result.excursion_pivot_indices, (50,))
                self.assertAlmostEqual(result.slope, 0.1 if side == "upper" else -0.1)
                self.assertTrue(result.body_integrity)
                self.assertEqual(result.body_breach_runs, ())

    def test_body_run_diagnostics_preserve_seven_bar_boundary_and_ignore_post_end(self):
        for length in (6, 7):
            frame = _candles()
            for i in range(45, 45 + length):
                frame.loc[i, ["open", "close", "high"]] = 102 + 0.1 * i
            # No isolated high is added by the monotone breach run.
            frame.loc[85:, ["open", "close", "high"]] += 30
            for side, candles in (("upper", frame), ("lower", _mirror(frame))):
                with self.subTest(length=length, side=side):
                    results = _build(candles, side)
                    result = next(r for r in results if r.inlier_pivot_indices == (20, 40, 60, 80))
                    self.assertEqual(result.max_consecutive_body_breaches, length)
                    self.assertEqual(result.body_integrity, length < 7)
                    self.assertEqual(result.body_breach_runs, ((45, 44 + length),))

    def test_reversed_seed_enumeration_preserves_canonical_seed_and_order(self):
        frame = _candles()
        frame.loc[50, "high"] = 120
        expected = _build(frame)
        self.assertGreater(len(expected), 1)
        pairs = consensus._seed_pairs
        with patch.object(consensus, "_seed_pairs", lambda points: reversed(list(pairs(points)))):
            self.assertEqual(_build(frame), expected)
        self.assertEqual(expected[0].seed_anchor_indices, (20, 40))

    def test_cutoff_excludes_unconfirmed_pivot_and_future_ohlc(self):
        frame = _candles((20, 40, 60, 80, 98))
        expected = _build(frame)
        self.assertTrue(all(98 not in r.inlier_pivot_indices for r in expected))
        future = _candles().iloc[:20].copy()
        # Future-only invalid rows must not even be validated at cutoff 99.
        future.loc[:, "high"] = float("nan")
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(_build(extended, as_of_index=99), expected)

    def test_episode_scope_and_missing_atr_do_not_create_false_support(self):
        frame = _candles((5, 20, 40, 60, 80))
        self.assertEqual(_build(frame, episode_start_index=41)[0].inlier_pivot_indices, (60, 80))
        self.assertTrue(all(5 not in r.inlier_pivot_indices
                            for r in _build(frame, episode_start_index=0)))
        self.assertEqual(_build(frame.iloc[:13], episode_start_index=0), ())
        flat = pd.DataFrame({name: [100.0] * 30 for name in ("open", "high", "low", "close")})
        self.assertEqual(_build(flat, episode_start_index=0), ())

    def test_invalid_history_or_parameters_reject_without_compressing_indices(self):
        for overrides in ({"side": "bad"}, {"as_of_index": 100},
                          {"episode_start_index": -1}, {"inlier_band_atr": 0},
                          {"separation_atr": 0.1}, {"inlier_band_atr": float("nan")}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                _build(_candles(), **overrides)
        frame = _candles()
        frame.loc[22, "high"] = float("nan")
        with self.assertRaises(ValueError):
            _build(frame)


class GoldShadowInvarianceTests(unittest.TestCase):
    def test_pons_determinism_future_stability_and_production_invariance(self):
        case = next(c for c in load_manifest()["cases"]
                    if c["case_id"] == "PONS-formation-fit-positive-anchor")
        frame = _load_frame(case)
        pristine = frame.copy(deep=True)
        parameters = dict(as_of_index=case["as_of_index"], episode_start_index=0,
                          inlier_band_atr=0.2, separation_atr=0.75)
        highs, lows, before = _analyze(frame)
        self.assertEqual(geometry_identity(before), case["expectation"]["geometry_identity"])
        before_model = json.dumps(vars(before), sort_keys=True)
        before_classification = detect_structure(before, candles=frame)

        report = consensus.boundary_consensus_report(frame, **parameters)
        self.assertTrue(report["upper"])
        self.assertTrue(report["lower"])
        self.assertEqual(consensus.boundary_consensus_report(frame, **parameters), report)
        self.assertEqual(consensus.boundary_consensus_report(
            _with_adversarial_future(frame), **parameters), report)
        pairs = consensus._seed_pairs
        with patch.object(consensus, "_seed_pairs", lambda points: reversed(list(pairs(points)))):
            self.assertEqual(consensus.boundary_consensus_report(frame, **parameters), report)
        json.dumps(report, allow_nan=False)  # usable in existing JSON reports
        self.assertEqual(report["quality_fields"], consensus.BoundaryQuality._fields)
        self.assertEqual(json.dumps(vars(before), sort_keys=True), before_model)
        pd.testing.assert_frame_equal(frame, pristine)

        # Real production path, identical arguments after opt-in shadow work.
        after_highs, after_lows, after = _analyze(frame)
        self.assertEqual((after_highs, after_lows), (highs, lows))
        self.assertEqual(json.dumps(vars(after), sort_keys=True), before_model)
        self.assertEqual(detect_structure(after, candles=frame), before_classification)


if __name__ == "__main__":
    unittest.main()
