"""GEO-U1 Slice C SHADOW pair selection + terminal width evidence contracts."""

import json
import unittest

import pandas as pd

from geometry.consensus_boundary import build_boundary_consensus
from geometry.consensus_selection import (
    SelectionQuality,
    select_envelope_pair_shadow,
    shadow_selection_record,
)
from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest
from tests.test_geometry_consensus_pair import _boundary
from wedge.detector import detect_structure

PEAKS = (15, 27, 39, 51, 63, 75, 87)      # period 12, peak at i % 12 == 3
TROUGHS = (21, 33, 45, 57, 69, 81)


def _frame(upper_at, lower_at, length=100, fill=0.9, end_tiny=False):
    """Triangle-wave price between two lines; touches reach the line exactly."""
    rows = []
    for i in range(length):
        d = (i - 3) % 12
        tri = 1 - 2 * min(d, 12 - d) / 6
        mid = (upper_at(i) + lower_at(i)) / 2
        half = (upper_at(i) - lower_at(i)) / 2
        close = mid + tri * half * fill
        rows.append([close, close + 0.05, close - 0.05, close])
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    for i in PEAKS:
        frame.loc[i, "high"] = upper_at(i)
    for i in TROUGHS:
        frame.loc[i, "low"] = lower_at(i)
    if end_tiny:
        frame.loc[90, ["open", "close"]] = 100.0
        frame.loc[90, "high"], frame.loc[90, "low"] = 100.02, 99.98
    return frame


CONVERGING = (lambda i: 110 - 0.05 * i, lambda i: 90 + 0.05 * i)
PARALLEL = (lambda i: 110 - 0.0 * i, lambda i: 90 + 0.0 * i)
DIVERGING = (lambda i: 105 + 0.05 * i, lambda i: 95 - 0.05 * i)


def _healthy_upper(slope=-0.05, intercept=110):
    return _boundary("upper", tuple((i,) for i in PEAKS),
                     slope=slope, intercept=intercept)


def _healthy_lower(slope=0.05, intercept=90):
    return _boundary("lower", tuple((i,) for i in TROUGHS),
                     slope=slope, intercept=intercept)


def _select(frame, uppers, lowers, **overrides):
    parameters = dict(
        as_of_index=99, episode_start_index=10, episode_end_index=90,
        touch_band_atr=0.25, minimum_swing_width_fraction=0.30,
        minimum_swing_atr=0.5, minimum_side_touch_clusters=2,
        min_cross_boundary_traversals=2, min_alternating_touches=4,
        min_touch_balance=0.5, min_shared_support_coverage=0.5,
        max_support_gap_fraction=0.5, terminal_window_bars=36,
        terminal_segments=3, compression_max_ratio=0.9,
        expansion_min_ratio=1.1, segment_tolerance=0.05,
        single_bar_narrow_ratio=0.5,
    )
    parameters.update(overrides)
    return select_envelope_pair_shadow(frame, uppers, lowers, **parameters)


class SelectionTests(unittest.TestCase):
    def test_healthy_converging_pair_beats_locally_concentrated_alternative(self):
        frame = _frame(*CONVERGING)
        concentrated_upper = _boundary("upper", ((15,), (27,)),
                                       slope=-0.05, intercept=110)
        concentrated_lower = _boundary("lower", ((21,), (33,)),
                                       slope=0.05, intercept=90)
        uppers = (concentrated_upper, _healthy_upper())
        lowers = (concentrated_lower, _healthy_lower())
        result = _select(frame, uppers, lowers)
        self.assertEqual(result.selection_status, "SELECTED")
        self.assertTrue(result.admissible)
        self.assertEqual(result.selected_pair_identity,
                         (("upper", PEAKS), ("lower", TROUGHS)))
        self.assertEqual(result.terminal.terminal_width_trend,
                         "PERSISTENT_COMPRESSION")
        self.assertLess(result.terminal.terminal_compression_ratio, 0.9)
        self.assertLess(result.terminal.terminal_width_slope, 0)
        self.assertEqual(result.candidate_count, 4)
        self.assertEqual(result.admissible_count, 1)
        rejected = {(row.upper_boundary_identity[1], row.lower_boundary_identity[1]): row
                    for row in result.selection_trace if not row.admissible}
        reasons = rejected[((15, 27), (21, 33))].rejection_reasons
        self.assertIn("INSUFFICIENT_SHARED_SUPPORT", reasons)
        self.assertIn("STALE_SHARED_SUPPORT", reasons)
        self.assertIsNotNone(result.runner_up_identity)
        self.assertEqual(result.deciding_component, "admissible")
        self.assertEqual(result.quality_fields, SelectionQuality._fields)

    def test_one_side_hugging_pair_loses_with_reason(self):
        frame = _frame(*CONVERGING)
        hugging = _boundary("lower", ((21,),), slope=0.05, intercept=90)
        result = _select(frame, (_healthy_upper(),), (hugging, _healthy_lower()))
        self.assertEqual(result.selected_pair_identity[1], ("lower", TROUGHS))
        row = next(r for r in result.selection_trace
                   if r.lower_boundary_identity == ("lower", (21,)))
        self.assertFalse(row.admissible)
        self.assertIn("SIDE_NOT_MATERIALLY_USED", row.rejection_reasons)
        only = _select(frame, (_healthy_upper(),), (hugging,))
        self.assertEqual(only.selection_status, "NO_ADMISSIBLE_PAIR")
        self.assertIsNone(only.selected_pair_identity)
        self.assertIn("SIDE_NOT_MATERIALLY_USED", only.rejection_reasons)

    def test_good_structure_without_terminal_compression_is_distinguishable(self):
        converging = _select(_frame(*CONVERGING), (_healthy_upper(),),
                             (_healthy_lower(),))
        parallel = _select(
            _frame(*PARALLEL),
            (_healthy_upper(slope=0, intercept=110),),
            (_healthy_lower(slope=0, intercept=90),),
        )
        self.assertTrue(converging.admissible and parallel.admissible)
        self.assertEqual(converging.terminal.terminal_width_trend,
                         "PERSISTENT_COMPRESSION")
        self.assertEqual(parallel.terminal.terminal_width_trend,
                         "NO_PERSISTENT_WIDTH_TREND")
        self.assertFalse(parallel.terminal.persistent_compression)
        self.assertAlmostEqual(parallel.terminal.terminal_compression_ratio, 1.0)
        self.assertTrue(converging.final_quality_tuple.terminal_width_trend_persistent)
        self.assertFalse(parallel.final_quality_tuple.terminal_width_trend_persistent)

    def test_single_bar_terminal_narrowing_is_not_persistent_compression(self):
        # Lines converge but realized price range is constant; only the very
        # last bar is tiny. Segment ranges over >=3 bars cannot see one bar.
        frame = _frame(*PARALLEL, end_tiny=True)
        result = _select(frame, (_healthy_upper(),), (_healthy_lower(),))
        terminal = result.terminal
        self.assertIsNotNone(terminal)
        self.assertFalse(terminal.persistent_compression)
        self.assertEqual(terminal.terminal_width_trend, "NO_PERSISTENT_WIDTH_TREND")
        self.assertTrue(terminal.full_window_compression_ok is False
                        or terminal.shifted_window_compression_ok is False)
        self.assertTrue(terminal.single_bar_narrowing_only)
        self.assertLessEqual(terminal.last_bar_range_ratio, 0.5)
        self.assertGreater(terminal.realized_contraction_ratio, 0.9)

    def test_diverging_width_reports_expansion_not_compression(self):
        frame = _frame(*DIVERGING)
        result = _select(
            frame,
            (_healthy_upper(slope=0.05, intercept=105),),
            (_healthy_lower(slope=-0.05, intercept=95),),
        )
        terminal = result.terminal
        self.assertEqual(terminal.terminal_width_trend, "EXPANSION")
        self.assertTrue(terminal.expansion)
        self.assertFalse(terminal.persistent_compression)
        self.assertGreater(terminal.terminal_compression_ratio, 1.1)
        self.assertGreater(terminal.terminal_width_slope, 0)
        self.assertFalse(hasattr(result, "classification"))

    def test_invalid_crossing_pair_is_rejected(self):
        frame = _frame(*CONVERGING)
        crossing_upper = _boundary("upper", tuple((i,) for i in PEAKS),
                                   slope=-0.2, intercept=110)
        crossing_lower = _boundary("lower", tuple((i,) for i in TROUGHS),
                                   slope=0.2, intercept=90)
        result = _select(frame, (crossing_upper,), (crossing_lower,))
        self.assertEqual(result.selection_status, "NO_ADMISSIBLE_PAIR")
        self.assertFalse(result.admissible)
        self.assertIsNone(result.selected_pair_identity)
        self.assertIn("PAIR_BOUNDARIES_CROSS_INSIDE_EPISODE",
                      result.rejection_reasons)
        self.assertEqual(result.terminal.terminal_width_trend, "NON_POSITIVE_WIDTH")

    def test_equal_quality_tie_is_resolved_by_identity_not_order(self):
        frame = _frame(*CONVERGING)
        lower_a = _boundary("lower", ((21, 22), (33,), (45,), (57,), (69,), (81,)),
                            slope=0.05, intercept=90)
        lower_b = _healthy_lower()
        result = _select(frame, (_healthy_upper(),), (lower_b, lower_a))
        self.assertEqual(result.runner_up_quality_tuple, result.final_quality_tuple)
        self.assertEqual(result.deciding_component, "IDENTITY_TIE_BREAK")
        self.assertEqual(result.selected_pair_identity[1],
                         ("lower", (21, 22, 33, 45, 57, 69, 81)))
        self.assertEqual(
            _select(frame, (_healthy_upper(),), (lower_a, lower_b)), result)

    def test_determinism_candidate_order_and_future_rows(self):
        frame = _frame(*CONVERGING)
        uppers = (_healthy_upper(),
                  _boundary("upper", ((15,), (27,)), slope=-0.05, intercept=110))
        lowers = (_healthy_lower(),
                  _boundary("lower", ((21,), (33,)), slope=0.05, intercept=90))
        expected = _select(frame, uppers, lowers)
        self.assertEqual(_select(frame, uppers, lowers), expected)
        self.assertEqual(_select(frame, reversed(uppers), reversed(lowers)), expected)
        future = pd.DataFrame({name: [float("nan")] * 10
                               for name in ("open", "high", "low", "close")})
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(_select(extended, uppers, lowers), expected)
        self.assertEqual(json.dumps(shadow_selection_record(expected),
                                    sort_keys=True, allow_nan=False),
                         json.dumps(shadow_selection_record(
                             _select(extended, uppers, lowers)),
                             sort_keys=True, allow_nan=False))

    def test_invalid_parameters_fail_closed(self):
        frame = _frame(*CONVERGING)
        upper, lower = (_healthy_upper(),), (_healthy_lower(),)
        for overrides in (
            {"terminal_window_bars": 35}, {"terminal_segments": 1},
            {"terminal_window_bars": 6, "terminal_segments": 3},
            {"compression_max_ratio": 1.0}, {"expansion_min_ratio": 1.0},
            {"min_touch_balance": 1.5}, {"segment_tolerance": float("nan")},
            {"max_support_gap_fraction": -1},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                _select(frame, upper, lower, **overrides)
        self.assertEqual(_select(frame, (), ()).selection_status, "NO_CANDIDATES")
        short = _select(frame, upper, lower, episode_start_index=70,
                        terminal_window_bars=36)
        self.assertEqual(short.terminal.terminal_width_trend, "INSUFFICIENT_WINDOW")


class GoldShadowSelectionInvarianceTests(unittest.TestCase):
    def test_pons_selection_is_deterministic_and_production_inert(self):
        case = next(c for c in load_manifest()["cases"]
                    if c["case_id"] == "PONS-formation-fit-positive-anchor")
        frame = _load_frame(case)
        pristine = frame.copy(deep=True)
        highs, lows, before = _analyze(frame)
        self.assertEqual(geometry_identity(before),
                         case["expectation"]["geometry_identity"])
        before_model = json.dumps(vars(before), sort_keys=True)
        before_classification = detect_structure(before, candles=frame)

        as_of = case["as_of_index"]
        boundary = dict(as_of_index=as_of, episode_start_index=0,
                        inlier_band_atr=0.2, separation_atr=0.75)
        uppers = build_boundary_consensus(frame, side="upper", **boundary)
        lowers = build_boundary_consensus(frame, side="lower", **boundary)
        parameters = dict(
            as_of_index=as_of, episode_start_index=0, episode_end_index=as_of,
            touch_band_atr=0.2, minimum_swing_width_fraction=0.30,
            minimum_swing_atr=0.5, min_cross_boundary_traversals=1,
            min_alternating_touches=3, min_touch_balance=0.25,
            min_shared_support_coverage=0.25, max_support_gap_fraction=0.5,
            terminal_window_bars=30, terminal_segments=3,
            compression_max_ratio=0.9, expansion_min_ratio=1.1,
            segment_tolerance=0.05, single_bar_narrow_ratio=0.5,
        )
        result = select_envelope_pair_shadow(frame, uppers, lowers, **parameters)
        self.assertEqual(result.mode, "SHADOW_ONLY")
        self.assertGreater(result.candidate_count, 0)
        self.assertEqual(result.candidate_count,
                         result.admissible_count + result.rejected_count)
        json.dumps(shadow_selection_record(result), sort_keys=True, allow_nan=False)
        self.assertEqual(select_envelope_pair_shadow(
            frame, reversed(uppers), reversed(lowers), **parameters), result)
        future = pd.DataFrame({name: [float("nan")] * 10
                               for name in ("open", "high", "low", "close")})
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(select_envelope_pair_shadow(
            extended, uppers, lowers, **parameters), result)

        self.assertEqual(json.dumps(vars(before), sort_keys=True), before_model)
        pd.testing.assert_frame_equal(frame, pristine)
        after_highs, after_lows, after = _analyze(frame)
        self.assertEqual((after_highs, after_lows), (highs, lows))
        self.assertEqual(json.dumps(vars(after), sort_keys=True), before_model)
        self.assertEqual(detect_structure(after, candles=frame), before_classification)


if __name__ == "__main__":
    unittest.main()
