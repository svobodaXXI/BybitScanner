"""GEO-U1 Slice B shadow pair contracts; synthetic evidence + PONS Gold."""

import json
import unittest

import pandas as pd

from geometry.consensus_boundary import BoundaryConsensus, BoundaryQuality
from geometry.consensus_pair import (
    PairQuality,
    build_envelope_pair_consensus,
    consensus_envelope_shadow_report,
)
from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest
from wedge.detector import detect_structure


def _line(side, index):
    return (110 - 0.02 * index) if side == "upper" else (90 + 0.02 * index)


def _candles(events, length=100):
    """Channel path that visits the supplied ordered boundary events."""
    targets = [(0, 100.0)] + [
        (index, _line(side, index)) for side, index in events
    ] + [(length - 1, 100.0)]
    closes = [100.0] * length
    for (left, left_price), (right, right_price) in zip(targets, targets[1:]):
        for index in range(left, right + 1):
            ratio = (index - left) / max(1, right - left)
            closes[index] = left_price + ratio * (right_price - left_price)
    frame = pd.DataFrame({
        "open": closes,
        "close": closes,
        "high": [value + 0.2 for value in closes],
        "low": [value - 0.2 for value in closes],
    })
    for side, index in events:
        if side == "upper":
            frame.loc[index, "high"] = _line(side, index)
        else:
            frame.loc[index, "low"] = _line(side, index)
    return frame


def _boundary(side, clusters, *, slope=None, intercept=None):
    indices = tuple(index for cluster in clusters for index in cluster)
    if slope is None:
        slope = -0.02 if side == "upper" else 0.02
    if intercept is None:
        intercept = 110 if side == "upper" else 90
    quality = BoundaryQuality(True, len(clusters), 0.75, 60, -0.01, -0.02, 0)
    return BoundaryConsensus(
        side=side,
        seed_anchor_indices=(indices[0], indices[-1]),
        slope=slope,
        intercept=intercept,
        inlier_pivot_indices=indices,
        touch_cluster_indices=tuple(tuple(cluster) for cluster in clusters),
        touch_count_distinct=len(clusters),
        support_span=indices[-1] - indices[0],
        support_coverage_ratio=0.75,
        mean_residual_atr=0.01,
        max_residual_atr=0.02,
        first_supported_pivot=indices[0],
        last_supported_pivot=indices[-1],
        excursion_pivot_indices=(),
        body_breach_runs=(),
        max_consecutive_body_breaches=0,
        body_integrity=True,
        quality_tuple=quality,
    )


def _build(frame, upper, lower, **overrides):
    parameters = dict(
        as_of_index=99,
        episode_start_index=14,
        episode_end_index=90,
        touch_band_atr=0.25,
        minimum_swing_width_fraction=0.30,
        minimum_swing_atr=0.5,
        minimum_side_touch_clusters=2,
    )
    parameters.update(overrides)
    return build_envelope_pair_consensus(frame, upper, lower, **parameters)


class EnvelopePairConsensusTests(unittest.TestCase):
    def test_true_alternation_beats_one_side_hugging(self):
        healthy_events = (("upper", 20), ("lower", 35), ("upper", 50),
                          ("lower", 65), ("upper", 80))
        healthy = _build(
            _candles(healthy_events),
            (_boundary("upper", ((20,), (50,), (80,))),),
            (_boundary("lower", ((35,), (65,))),),
        )[0]

        hugging_events = (("upper", 20), ("upper", 35), ("upper", 50),
                          ("lower", 65), ("upper", 80))
        hugging = _build(
            _candles(hugging_events),
            (_boundary("upper", ((20,), (35,), (50,), (80,))),),
            (_boundary("lower", ((65,),)),),
        )[0]

        self.assertTrue(healthy.pair_valid)
        self.assertEqual(healthy.alternating_touch_sequence,
                         (("upper", 20), ("lower", 35), ("upper", 50),
                          ("lower", 65), ("upper", 80)))
        self.assertEqual(healthy.cross_boundary_traversal_count, 4)
        self.assertEqual(healthy.opposite_boundary_reach_fraction, 1.0)
        self.assertEqual(hugging.lower_touch_count, 1)
        self.assertLess(hugging.touch_balance, healthy.touch_balance)
        self.assertLess(hugging.cross_boundary_traversal_count,
                        healthy.cross_boundary_traversal_count)
        self.assertGreater(healthy.quality_tuple, hugging.quality_tuple)

    def test_cluster_members_and_same_side_runs_do_not_inflate_alternation(self):
        events = (("upper", 20), ("upper", 50), ("lower", 80))
        pair = _build(
            _candles(events),
            (_boundary("upper", ((20, 21, 22), (50, 51))),),
            (_boundary("lower", ((80, 81, 82),)),),
        )[0]
        self.assertEqual(pair.upper_touch_count, 2)
        self.assertEqual(pair.lower_touch_count, 1)
        self.assertEqual(pair.touch_event_sequence,
                         (("upper", 20, (20, 21, 22)),
                          ("upper", 50, (50, 51)),
                          ("lower", 80, (80, 81, 82))))
        self.assertEqual(pair.alternating_touch_sequence,
                         (("upper", 50), ("lower", 80)))
        self.assertEqual(pair.alternating_touch_count, 2)
        self.assertEqual(pair.cross_boundary_traversal_count, 1)

    def test_crossing_pair_preserves_deterministic_invalid_reason(self):
        events = (("upper", 20), ("lower", 35), ("upper", 50), ("lower", 65))
        upper = _boundary("upper", ((20,), (50,)), slope=-0.2, intercept=110)
        lower = _boundary("lower", ((35,), (65,)), slope=0.2, intercept=90)
        pair = _build(_candles(events), (upper,), (lower,))[0]
        self.assertFalse(pair.pair_valid)
        self.assertTrue(pair.boundaries_cross_inside_episode)
        self.assertEqual(pair.boundary_intersection_index, 50)
        self.assertEqual(
            pair.pair_invalid_reasons,
            ("BOUNDARY_ORDER_INVALID_AT_EPISODE_END",
             "BOUNDARIES_CROSS_INSIDE_EPISODE"),
        )
        self.assertLess(pair.minimum_signed_width, 0)

        inverted = _build(
            _candles(events),
            (_boundary("upper", ((20,), (50,)), slope=0, intercept=90),),
            (_boundary("lower", ((35,), (65,)), slope=0, intercept=100),),
        )[0]
        self.assertFalse(inverted.boundaries_cross_inside_episode)
        self.assertEqual(
            inverted.pair_invalid_reasons,
            ("BOUNDARY_ORDER_INVALID_AT_EPISODE_START",
             "BOUNDARY_ORDER_INVALID_AT_EPISODE_END"),
        )
        self.assertIsNone(inverted.width_change_ratio)
        self.assertIsNone(inverted.compression_ratio)

    def test_mid_channel_move_is_not_a_traversal(self):
        # Price hugs the upper line; a 3-point dip near 35 never reaches the
        # lower band, so the labelled lower clusters prove no two-sided use.
        frame = _candles((("upper", 20), ("upper", 50), ("upper", 80)))
        frame.loc[30:40, ["open", "high", "low", "close"]] -= 3.0
        pair = _build(
            frame,
            (_boundary("upper", ((20,), (50,), (80,))),),
            (_boundary("lower", ((35,), (65,))),),
        )[0]
        self.assertEqual(pair.cross_boundary_traversal_count, 0)
        self.assertEqual(pair.opposite_boundary_reach_fraction, 0.0)
        self.assertIsNone(pair.first_two_sided_interaction)

    def test_compression_and_expansion_width_metrics_have_no_family_label(self):
        events = (("upper", 20), ("lower", 35), ("upper", 50), ("lower", 65))
        frame = _candles(events)
        converging = _build(
            frame,
            (_boundary("upper", ((20,), (50,))),),
            (_boundary("lower", ((35,), (65,))),),
        )[0]
        expanding = _build(
            frame,
            (_boundary("upper", ((20,), (50,)), slope=0.02, intercept=106),),
            (_boundary("lower", ((35,), (65,)), slope=-0.02, intercept=94),),
        )[0]
        self.assertAlmostEqual(converging.width_at_start, 19.44)
        self.assertAlmostEqual(converging.width_at_end, 16.4)
        self.assertAlmostEqual(converging.compression_ratio, 16.4 / 19.44)
        self.assertLess(converging.width_change_ratio, 0)
        self.assertAlmostEqual(expanding.width_at_start, 12.56)
        self.assertAlmostEqual(expanding.width_at_end, 15.6)
        self.assertGreater(expanding.width_change_ratio, 0)
        self.assertFalse(hasattr(converging, "classification"))

    def test_candidate_order_and_future_rows_do_not_change_pair_order(self):
        events = (("upper", 20), ("lower", 35), ("upper", 50),
                  ("lower", 65), ("upper", 80))
        frame = _candles(events)
        uppers = (
            _boundary("upper", ((20,), (50,), (80,))),
            _boundary("upper", ((20,), (80,))),
        )
        lowers = (
            _boundary("lower", ((35,), (65,))),
            _boundary("lower", ((35,), (80,))),
        )
        expected = _build(frame, uppers, lowers)
        self.assertEqual(_build(frame, reversed(uppers), reversed(lowers)), expected)
        future = pd.DataFrame({name: [float("nan")] * 10
                               for name in ("open", "high", "low", "close")})
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(_build(extended, uppers, lowers), expected)
        self.assertEqual(_build(frame, uppers, lowers), expected)

    def test_invalid_parameters_fail_closed(self):
        frame = _candles((("upper", 20), ("lower", 40)))
        upper = (_boundary("upper", ((20,),)),)
        lower = (_boundary("lower", ((40,),)),)
        for overrides in (
            {"episode_start_index": 90},
            {"episode_end_index": 100},
            {"touch_band_atr": 0},
            {"minimum_swing_width_fraction": float("nan")},
            {"minimum_side_touch_clusters": 0},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                _build(frame, upper, lower, **overrides)
        future_upper = (_boundary("upper", ((20,), (101,))),)
        with self.assertRaises(ValueError):
            _build(frame, future_upper, lower)


class GoldShadowPairInvarianceTests(unittest.TestCase):
    def test_pons_report_is_json_deterministic_and_production_inert(self):
        case = next(c for c in load_manifest()["cases"]
                    if c["case_id"] == "PONS-formation-fit-positive-anchor")
        frame = _load_frame(case)
        pristine = frame.copy(deep=True)
        highs, lows, before = _analyze(frame)
        self.assertEqual(geometry_identity(before), case["expectation"]["geometry_identity"])
        before_model = json.dumps(vars(before), sort_keys=True)
        before_classification = detect_structure(before, candles=frame)
        parameters = dict(
            as_of_index=case["as_of_index"],
            episode_start_index=0,
            episode_end_index=case["as_of_index"],
            inlier_band_atr=0.2,
            separation_atr=0.75,
            touch_band_atr=0.2,
            minimum_swing_width_fraction=0.30,
            minimum_swing_atr=0.5,
        )

        report = consensus_envelope_shadow_report(frame, **parameters)
        self.assertEqual(report["mode"], "SHADOW_ONLY")
        self.assertTrue(report["upper"])
        self.assertTrue(report["lower"])
        self.assertTrue(report["pairs"])
        self.assertEqual(report["pair_quality_fields"], PairQuality._fields)
        json.dumps(report, sort_keys=True, allow_nan=False)
        self.assertEqual(json.dumps(vars(before), sort_keys=True), before_model)
        pd.testing.assert_frame_equal(frame, pristine)

        after_highs, after_lows, after = _analyze(frame)
        self.assertEqual((after_highs, after_lows), (highs, lows))
        self.assertEqual(json.dumps(vars(after), sort_keys=True), before_model)
        self.assertEqual(detect_structure(after, candles=frame), before_classification)


if __name__ == "__main__":
    unittest.main()
