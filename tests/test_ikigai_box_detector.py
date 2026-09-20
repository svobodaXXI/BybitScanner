"""Narrow offline, closed-candle geometry tests: no Scanner/Robot side effects."""

import math
import unittest

import pandas as pd

from geometry.ikigai_box import (
    IkigaiBoxParameters,
    detect_ikigai_box,
)


def _bar(start, finish):
    return {
        "open": start,
        "high": max(start, finish) + 0.15,
        "low": min(start, finish) - 0.15,
        "close": finish,
    }


def _two_impulses(direction=1, *, second_steps=6):
    """Twenty calm bars, a directional leg, a shelf, and a SAME-direction leg."""
    start = 200.0 if direction < 0 else 100.0
    candles = [_bar(start, start) for _ in range(20)]
    price = start
    for _ in range(8):
        nxt = price + direction
        candles.append(_bar(price, nxt))
        price = nxt
    impulse_end = len(candles) - 1
    # First-impulse terminal wick is frozen BEFORE this consolidation.
    shelf = price - direction * 0.4
    for target in (shelf, shelf - direction * 0.1) * 3:
        candles.append(_bar(price, target))
        price = target
    shelf_end = len(candles) - 1
    for _ in range(second_steps):
        nxt = price + direction * 1.0
        candles.append(_bar(price, nxt))
        price = nxt
    return pd.DataFrame(candles), impulse_end, shelf_end


class IkigaiBoxDetectorTests(unittest.TestCase):
    def test_up_up_box_short_and_first_impulse_fibonacci(self):
        frame, first_end, shelf_end = _two_impulses()
        found = detect_ikigai_box(frame)
        self.assertIsNotNone(found)
        self.assertEqual(found.direction, "SHORT")
        self.assertLess(found.impulse_end_index, found.box_start_index)
        self.assertLess(found.box_end_index, found.second_start_index)
        self.assertLessEqual(found.anchor_end_index, first_end)
        self.assertLess(found.anchor_start_index, found.anchor_end_index)
        self.assertLess(found.box_end_index, shelf_end + 1)
        self.assertLess(found.fibonacci_1_0, found.fibonacci_1_618)
        self.assertLess(found.fibonacci_1_618, found.fibonacci_2_618)
        for level, expected in (
            (0, found.anchor_start_price),
            (1, found.anchor_end_price),
            (1.618, found.fibonacci_1_618),
            (2.618, found.fibonacci_2_618),
        ):
            self.assertTrue(math.isclose(found.fibonacci_price(level), expected))
        self.assertTrue(math.isclose(
            found.fibonacci_2_618 - found.fibonacci_1_0,
            1.618 * (found.anchor_end_price - found.anchor_start_price),
        ))

    def test_down_down_box_long_mirrors_levels(self):
        frame, first_end, _ = _two_impulses(-1)
        found = detect_ikigai_box(frame)
        self.assertIsNotNone(found)
        self.assertEqual(found.direction, "LONG")
        self.assertLessEqual(found.anchor_end_index, first_end)
        self.assertGreater(found.fibonacci_1_0, found.fibonacci_1_618)
        self.assertGreater(found.fibonacci_1_618, found.fibonacci_2_618)
        self.assertAlmostEqual(
            found.fibonacci_1_618,
            found.anchor_start_price
            + 1.618 * (found.anchor_end_price - found.anchor_start_price),
        )

    def test_generic_horizontal_range_without_two_impulses_is_not_ikigai_box(self):
        frame = pd.DataFrame([
            _bar(100.0, 100.1 if i % 2 else 99.9) for i in range(90)
        ])
        self.assertIsNone(detect_ikigai_box(frame))

    def test_first_impulse_and_box_without_second_impulse_are_not_ikigai(self):
        frame, _, shelf_end = _two_impulses()
        self.assertIsNone(detect_ikigai_box(frame, as_of_index=shelf_end))

    def test_as_of_never_reads_future_ohlc(self):
        frame, _, _ = _two_impulses()
        cutoff = len(frame) - 1
        original = detect_ikigai_box(frame)
        self.assertIsNotNone(original)
        future = pd.concat([
            frame,
            pd.DataFrame([
                _bar(300.0, 305.0),
                _bar(250.0, 240.0),
                _bar(1000.0, 980.0),
            ]),
        ], ignore_index=True)
        observed = detect_ikigai_box(future, as_of_index=cutoff)
        self.assertEqual(observed, original)
        self.assertEqual(observed.as_of_index, cutoff)

    def test_second_extension_can_approach_2_618_without_reanchoring(self):
        frame, first_end, _ = _two_impulses(second_steps=14)
        found = detect_ikigai_box(frame)
        self.assertIsNotNone(found)
        self.assertLessEqual(found.anchor_end_index, first_end)
        self.assertGreater(
            found.fibonacci_2_618, found.fibonacci_1_618
        )
        self.assertLess(
            abs(found.second_extreme - found.fibonacci_2_618),
            found.anchor_end_price - found.anchor_start_price,
        )

    def test_missing_and_invalid_prefix_fail_closed(self):
        frame, _, _ = _two_impulses()
        self.assertIsNone(detect_ikigai_box(frame, as_of_index=len(frame)))
        self.assertIsNone(detect_ikigai_box(frame, as_of_index=-1))
        self.assertIsNone(detect_ikigai_box(frame[["open", "close"]]))
        frame.loc[0, "high"] = float("nan")
        self.assertIsNone(detect_ikigai_box(frame))

    def test_unsupported_geometry_parameters_rejected(self):
        frame, _, _ = _two_impulses()
        with self.assertRaises(ValueError):
            detect_ikigai_box(
                frame, parameters=IkigaiBoxParameters(box_min_bars=0)
            )


if __name__ == "__main__":
    unittest.main()
