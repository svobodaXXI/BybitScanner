"""Issue #416: chronological Box completion, no PAPER runtime or network."""
from types import SimpleNamespace
import unittest

import pandas as pd

from geometry.ikigai_box_completion import box_first_grid_already_completed


def formation(direction):
    return SimpleNamespace(
        direction=direction, anchor_end_index=0, as_of_index=3,
        fibonacci_1_0=100 if direction == "LONG" else 100,
        fibonacci_1_618=80 if direction == "LONG" else 120,
    )


def rows(prices):
    return pd.DataFrame([{"high": hi, "low": lo} for lo, hi in prices])


class BoxCompletedSignalTests(unittest.TestCase):
    def test_long_completed_after_first_entry_then_return_to_take(self):
        candles = rows([(99, 101), (84, 91), (80, 85), (96, 100)])
        self.assertTrue(box_first_grid_already_completed(candles, formation("LONG")))

    def test_long_fresh_actionable_even_after_entry_area_touched(self):
        candles = rows([(99, 101), (90, 94), (83, 87), (85, 92)])
        self.assertFalse(box_first_grid_already_completed(candles, formation("LONG")))

    def test_short_completed_and_short_fresh_are_distinct(self):
        completed = rows([(99, 101), (108, 114), (115, 121), (99, 103)])
        fresh = rows([(99, 101), (107, 112), (116, 119), (111, 115)])
        self.assertTrue(box_first_grid_already_completed(completed, formation("SHORT")))
        self.assertFalse(box_first_grid_already_completed(fresh, formation("SHORT")))

    def test_single_candle_entry_and_take_cross_is_ambiguous_fail_closed(self):
        candles = rows([(99, 101), (87, 93), (84, 99), (85, 91)])
        self.assertTrue(box_first_grid_already_completed(candles, formation("LONG")))

    def test_invalid_or_insufficient_history_fails_closed(self):
        candles = rows([(99, 101), (85, 95), (86, 94), (87, 93)])
        invalid = formation("LONG")
        invalid.as_of_index = 30
        self.assertTrue(box_first_grid_already_completed(candles, invalid))
        candles.loc[2, "high"] = float("nan")
        self.assertTrue(box_first_grid_already_completed(candles, formation("LONG")))


if __name__ == "__main__":
    unittest.main()
