"""
Focused regression coverage for the pivots raw-detection extraction
(DOCUMENTS/WEDGE_LOCAL_EPISODE_REFERENCE_AND_IMPLEMENTATION_PLAN_2026-09-20.md
section 5A.8, slice S3-1a):

- pivots.find_pivots keeps its signature, defaults, output structure and
  legacy in-place coercion of the caller's frame;
- pivots.detect_pivots exposes the same left/right extreme detection without
  the same-side filtering, on a copy, and never looks outside the frame it is
  given.

No geometry, ranking, START, signal, Telegram or Robot behaviour is involved.
"""

import inspect
import unittest

import pandas as pd

from pivots import detect_pivots, filter_pivots, find_pivots


def frame(rows, index=None):
    """rows: list of (high, low); open/close sit inside the bar."""
    data = [
        {
            "time": 1_700_000_000_000 + position * 300_000,
            "open": (high + low) / 2,
            "high": high,
            "low": low,
            "close": (high + low) / 2,
        }
        for position, (high, low) in enumerate(rows)
    ]
    built = pd.DataFrame(data)

    if index is not None:
        built.index = index

    return built


SWING = frame([
    (10.0, 9.0), (10.1, 9.1), (10.2, 9.2), (12.0, 9.3), (10.3, 9.4), (10.2, 9.2),
    (10.1, 8.0), (10.4, 9.5), (10.5, 9.6), (10.6, 9.7), (13.0, 9.8), (10.7, 9.9),
    (10.8, 10.0), (10.9, 8.5), (11.0, 10.1), (11.1, 10.2),
])


class FindPivotsContractTest(unittest.TestCase):

    def test_signature_and_defaults_are_unchanged(self):
        signature = inspect.signature(find_pivots)

        self.assertEqual(
            list(signature.parameters),
            ["df", "left", "right", "min_change"]
        )
        self.assertEqual(find_pivots.__defaults__, (3, 3, 0.003))

    def test_output_structure_is_unchanged(self):
        highs, lows = find_pivots(SWING.copy())

        self.assertTrue(highs and lows)

        for point in highs + lows:
            self.assertEqual(
                sorted(point),
                ["index", "price", "type"]
            )
            self.assertIn(point["type"], ("high", "low"))
            self.assertIsInstance(point["index"], int)

    def test_find_pivots_equals_detect_plus_filter(self):
        source = SWING.copy()

        expected_highs, expected_lows = detect_pivots(source)
        actual_highs, actual_lows = find_pivots(source.copy())

        self.assertEqual(actual_highs, filter_pivots(expected_highs, 0.003))
        self.assertEqual(actual_lows, filter_pivots(expected_lows, 0.003))

    def test_legacy_in_place_float_coercion_is_preserved(self):
        source = SWING.copy()
        source["high"] = source["high"].astype(object)
        source["low"] = source["low"].astype(object)

        find_pivots(source)

        self.assertEqual(source["high"].tolist(), SWING["high"].tolist())
        self.assertEqual(source["low"].tolist(), SWING["low"].tolist())

    def test_empty_and_missing_columns_return_empty_lists(self):
        empty = pd.DataFrame({"time": [], "high": [], "low": []})

        self.assertEqual(find_pivots(empty), ([], []))
        self.assertEqual(detect_pivots(empty), ([], []))
        self.assertEqual(find_pivots(None), ([], []))
        self.assertEqual(detect_pivots(None), ([], []))

        without_low = pd.DataFrame({"time": [1, 2, 3], "high": [1.0, 2.0, 3.0]})

        self.assertEqual(find_pivots(without_low), ([], []))
        self.assertEqual(detect_pivots(without_low), ([], []))

    def test_frame_shorter_than_windows_has_no_pivots(self):
        short = frame([(10.0 + step, 9.0 + step) for step in range(5)])

        self.assertEqual(find_pivots(short.copy()), ([], []))
        self.assertEqual(detect_pivots(short.copy()), ([], []))


class DetectPivotsTest(unittest.TestCase):

    def test_detect_does_not_mutate_the_caller_frame(self):
        source = SWING.copy()
        before = source.to_dict("list")

        detect_pivots(source)

        self.assertEqual(source.to_dict("list"), before)

    def test_raw_detection_is_a_superset_of_the_filtered_result(self):
        raw_highs, raw_lows = detect_pivots(SWING.copy())
        filtered_highs, filtered_lows = find_pivots(SWING.copy())

        self.assertTrue(
            {point["index"] for point in filtered_highs}
            <= {point["index"] for point in raw_highs}
        )
        self.assertTrue(
            {point["index"] for point in filtered_lows}
            <= {point["index"] for point in raw_lows}
        )
        self.assertGreaterEqual(len(raw_highs), len(filtered_highs))
        self.assertGreaterEqual(len(raw_lows), len(filtered_lows))

    def test_indices_are_positions_after_dropna_and_reset(self):
        with_gap = SWING.copy()
        with_gap.loc[1, "low"] = None
        with_gap.index = range(100, 100 + len(with_gap))

        cleaned = SWING.drop(index=1).reset_index(drop=True)

        self.assertEqual(
            detect_pivots(with_gap),
            detect_pivots(cleaned)
        )

    def test_outside_bar_is_reported_on_both_sides(self):
        outside = frame([
            (10.0, 9.0), (10.0, 9.0), (10.0, 9.0), (12.0, 7.0),
            (10.0, 9.0), (10.0, 9.0), (10.0, 9.0), (10.0, 9.0),
        ])

        highs, lows = detect_pivots(outside)

        self.assertEqual([point["index"] for point in highs], [3])
        self.assertEqual([point["index"] for point in lows], [3])

    def test_detection_never_uses_candles_outside_the_given_frame(self):
        full_highs, full_lows = detect_pivots(SWING.copy())

        cutoff = 12
        prefix = SWING.iloc[:cutoff].copy()
        prefix_highs, prefix_lows = detect_pivots(prefix)

        self.assertEqual(
            prefix_highs,
            [point for point in full_highs if point["index"] + 3 <= cutoff - 1]
        )
        self.assertEqual(
            prefix_lows,
            [point for point in full_lows if point["index"] + 3 <= cutoff - 1]
        )


if __name__ == "__main__":
    unittest.main()
