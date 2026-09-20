"""G2b0: compare frozen boundary anchors against signal-time pivot evidence."""

import copy
import unittest
from unittest.mock import patch

import pandas as pd

from geometry.start_diagnostics import compare_start_anchor_evidence
from pivots import find_pivots


class StartDiagnosticsTests(unittest.TestCase):
    def candles(self, timeframe=1, down=False):
        close = [104, 102, 101, 107, 112, 115, 119,
                 117, 115, 114, 116, 113, 112]
        if down:
            close = [220 - price for price in close]
        return pd.DataFrame({
            "time": [1_700_000_000_000 + i * timeframe * 60_000
                     for i in range(len(close))],
            "open": close,
            "high": [price + 1 for price in close],
            "low": [price - 1 for price in close],
            "close": close,
        })

    def pivots(self, candles, right=2):
        return find_pivots(
            candles.copy(deep=True), left=1, right=right, min_change=0,
        )

    def compare(self, candles, highs=None, lows=None, **changes):
        if highs is None or lows is None:
            highs, lows = self.pivots(candles, right=changes.get("right", 2))
        settings = {
            "baseline_start_index": 8, "upper_anchor_index": 8,
            "lower_anchor_index": 9, "as_of_index": 9, "right": 2,
        }
        settings.update(changes)
        return compare_start_anchor_evidence(
            candles, highs, lows, **settings,
        )

    @staticmethod
    def candidate(result, index, side):
        return next(c for c in result["candidates"]
                    if c["index"] == index and c["side"] == side)

    def test_up_terminal_high_before_both_separate_line_anchors(self):
        frame = self.candles()
        result = self.compare(frame)
        self.assertEqual(result["status"], "EVIDENCE_AVAILABLE")
        self.assertEqual(result["baseline_start"],
                         {"index": 8, "time_ms": frame.iloc[8]["time"]})
        self.assertEqual(result["upper_anchor"]["index"], 8)
        self.assertEqual(result["lower_anchor"]["index"], 9)
        self.assertNotEqual(result["upper_anchor"]["time_ms"],
                            result["lower_anchor"]["time_ms"])
        high = self.candidate(result, 6, "HIGH")
        self.assertEqual(high["direction"], "UP")
        self.assertEqual(high["previous_opposing_index"], 2)
        self.assertEqual(high["confirmed_at_index"], 8)
        self.assertEqual(high["bars_before_baseline"], 2)
        self.assertEqual(high["relative_to_baseline"], "EARLIER")
        self.assertIn("BETWEEN_ANCHORS_NOT_EVALUATED",
                      result["coverage_limitations"])
        self.assertIn("LEFT_HISTORY_TRUNCATED",
                      result["coverage_limitations"])
        self.assertNotIn("selected_start_index", result)
        self.assertNotIn("subtype", result)

    def test_down_terminal_low_is_observational_not_selected(self):
        result = self.compare(
            self.candles(down=True),
            upper_anchor_index=9, lower_anchor_index=8,
        )
        low = self.candidate(result, 6, "LOW")
        self.assertEqual(result["status"], "EVIDENCE_AVAILABLE")
        self.assertEqual(low["direction"], "DOWN")
        self.assertEqual(low["previous_opposing_index"], 2)
        self.assertEqual(low["bars_before_baseline"], 2)
        self.assertEqual(result["lower_anchor"]["index"], 8)
        self.assertEqual(result["upper_anchor"]["index"], 9)

    def test_future_pivot_membership_is_invisible_until_confirmation(self):
        frame = self.candles()
        right = 3
        full_highs, full_lows = self.pivots(frame, right=right)
        for as_of in (8, 9):
            with self.subTest(as_of=as_of):
                prefix = frame.iloc[:as_of + 1].copy()
                early_highs, early_lows = self.pivots(prefix, right=right)
                options = {
                    "right": right, "as_of_index": as_of,
                    "lower_anchor_index": 8,
                }
                full = self.compare(frame, full_highs, full_lows, **options)
                truncated = self.compare(
                    prefix, early_highs, early_lows, **options,
                )
                self.assertEqual(full, truncated)
                self.assertFalse(any(
                    c["index"] == 6 for c in full["candidates"]
                )) if as_of == 8 else self.assertEqual(
                    self.candidate(full, 6, "HIGH")["confirmed_at_index"], 9,
                )

    def test_only_earliest_anchor_horizon_is_observed(self):
        frame = self.candles()
        result = self.compare(
            frame, lower_anchor_index=11, as_of_index=11,
        )
        self.assertEqual(result["window"]["terminal_end_index"], 8)
        self.assertEqual(result["window"]["end_index"], 10)
        self.assertTrue(all(c["index"] <= 8 for c in result["candidates"]))
        self.assertIn("BETWEEN_ANCHORS_NOT_EVALUATED",
                      result["coverage_limitations"])

    def test_appended_invalid_future_data_cannot_change_a_past_result(self):
        frame = self.candles()
        highs, lows = self.pivots(frame)
        prefix = frame.iloc[:10].copy()
        expected = self.compare(prefix, highs, lows)
        poisoned = frame.astype(object)
        poisoned.loc[10:, :] = "FUTURE NOT OBSERVABLE"
        self.assertEqual(
            expected,
            self.compare(poisoned, highs, lows),
        )

    def test_missing_opposing_swing_and_shortlist_clipping_are_explicit(self):
        frame = self.candles()
        highs, lows = self.pivots(frame)
        missing = self.compare(frame, highs, [])
        self.assertEqual(missing["status"], "INSUFFICIENT_HISTORY")
        self.assertIsNone(self.candidate(missing, 6, "HIGH")[
            "previous_opposing_index"
        ])
        clipped = self.compare(frame, highs, lows, max_candidates=1)
        self.assertEqual(clipped["status"], "AMBIGUOUS")
        self.assertIn("CANDIDATE_SHORTLIST_TRUNCATED",
                      clipped["coverage_limitations"])
        self.assertEqual(len(clipped["candidates"]), 1)

    def test_wrong_baseline_future_anchor_or_misaligned_times_are_invalid(self):
        frame = self.candles()
        for changes in (
            {"baseline_start_index": 9},
            {"upper_anchor_index": 10},
            {"lower_anchor_index": 10},
            {"as_of_index": 8},
            {"right": -1},
            {"as_of_index": True},
            {"lookback": 0},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.compare(frame, **changes)["status"],
                                 "INVALID_INPUT")
        broken = frame.copy()
        broken.loc[9, "time"] = broken.loc[8, "time"]
        self.assertEqual(self.compare(broken)["status"], "INVALID_INPUT")

    def test_one_and_five_minute_source_indices_and_times(self):
        first = self.compare(self.candles(timeframe=1))
        fifth = self.compare(self.candles(timeframe=5))
        for result, minutes in ((first, 1), (fifth, 5)):
            high = self.candidate(result, 6, "HIGH")
            self.assertEqual(high["confirmed_at_index"], 8)
            self.assertEqual(high["bars_before_baseline"], 2)
            self.assertEqual(
                result["lower_anchor"]["time_ms"]
                - result["upper_anchor"]["time_ms"],
                minutes * 60_000,
            )

    def test_pure_reuse_does_not_mutate_candles_or_supplied_pivots(self):
        frame = self.candles()
        highs, lows = self.pivots(frame)
        previous = frame.copy(deep=True)
        original_pivots = copy.deepcopy((highs, lows))
        with patch(
            "geometry.start_diagnostics.collect_impulse_terminal_evidence",
            wraps=__import__(
                "geometry.pre_pattern", fromlist=["collect_impulse_terminal_evidence"]
            ).collect_impulse_terminal_evidence,
        ) as evidence:
            result = self.compare(frame, highs, lows)
        evidence.assert_called_once()
        pd.testing.assert_frame_equal(frame, previous)
        self.assertEqual((highs, lows), original_pivots)
        result["candidates"][0]["price"] = -999
        self.assertEqual((highs, lows), original_pivots)


if __name__ == "__main__":
    unittest.main()
