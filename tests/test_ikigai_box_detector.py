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


def _terminal_wick_two_impulses(direction=1, *, second=True):
    """HEI-style SHORT mirrored to LONG: terminal B is a rejection wick.

    A=0.12911, B=0.15198, terminal close=0.13819, two of four
    directional first-impulse candles, box retrace approx 65.2%.
    Synthetic shape guards the rule; it is NOT an archived Bybit feed.
    """
    raw = [
        {"open": 0.12925, "high": 0.12940,
         "low": 0.12915, "close": 0.12925}
        for _ in range(20)
    ]
    raw.extend([
        {"open": 0.12925, "high": 0.13470, "low": 0.12911, "close": 0.13450},
        {"open": 0.13450, "high": 0.14130, "low": 0.13445, "close": 0.14100},
        {"open": 0.14100, "high": 0.14120, "low": 0.13840, "close": 0.13850},
        {"open": 0.13850, "high": 0.15198, "low": 0.13790, "close": 0.13819},
    ])
    for hi, low, op, cl in (
        (0.1400, 0.13707, 0.13819, 0.13910),
        (0.1410, 0.13790, 0.13910, 0.14000),
        (0.1418, 0.13820, 0.14000, 0.13900),
        (0.1415, 0.13780, 0.13900, 0.13970),
        (0.1420, 0.13820, 0.13970, 0.14050),
        (0.1418, 0.13880, 0.14050, 0.14000),
    ):
        raw.append({"open": op, "high": hi, "low": low, "close": cl})
    box_end = len(raw) - 1
    if second:
        price = 0.1400
        for target in (0.1440, 0.1490, 0.1540, 0.1590, 0.1640):
            raw.append({
                "open": price,
                "high": target + 0.0002,
                "low": price - 0.00015,
                "close": target,
            })
            price = target
    if direction == -1:
        # Involution p -> (0.40-p) mirrors OHLC and candle color exactly.
        raw = [
            {
                "open": 0.40 - bar["open"],
                "high": 0.40 - bar["low"],
                "low": 0.40 - bar["high"],
                "close": 0.40 - bar["close"],
            }
            for bar in raw
        ]
    return pd.DataFrame(raw), box_end


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

    def test_terminal_rejection_wick_short_recovers_frozen_heistyle_a_b(self):
        frame, box_end = _terminal_wick_two_impulses()
        # A pure spike + shelf has no second same-direction impulse.
        self.assertIsNone(detect_ikigai_box(frame, as_of_index=box_end))
        found = detect_ikigai_box(frame)
        self.assertIsNotNone(found)
        self.assertEqual(found.direction, "SHORT")
        self.assertEqual((found.anchor_start_index, found.anchor_end_index), (20, 23))
        self.assertAlmostEqual(found.anchor_start_price, 0.12911)
        self.assertAlmostEqual(found.anchor_end_price, 0.15198)
        self.assertLess(found.anchor_end_index, found.box_start_index)
        self.assertLess(found.box_end_index, found.second_start_index)
        self.assertAlmostEqual(found.fibonacci_1_618, 0.16611366)
        self.assertAlmostEqual(found.fibonacci_2_618, 0.18898366)
        # No future second-leg wick can rebase first-impulse B.
        future = pd.concat([frame, pd.DataFrame([
            {"open": 0.1640, "high": 0.1850, "low": 0.1638, "close": 0.178}
        ])], ignore_index=True)
        self.assertEqual(
            detect_ikigai_box(future, as_of_index=len(frame) - 1), found
        )

    def test_terminal_rejection_wick_long_is_true_mirror(self):
        frame, _ = _terminal_wick_two_impulses(direction=-1)
        found = detect_ikigai_box(frame)
        self.assertIsNotNone(found)
        self.assertEqual(found.direction, "LONG")
        self.assertEqual((found.anchor_start_index, found.anchor_end_index), (20, 23))
        self.assertAlmostEqual(found.anchor_start_price, 0.27089)
        self.assertAlmostEqual(found.anchor_end_price, 0.24802)
        self.assertGreater(found.fibonacci_1_0, found.fibonacci_1_618)
        self.assertGreater(found.fibonacci_1_618, found.fibonacci_2_618)

    def test_terminal_wick_relaxation_not_applied_to_body_driven_box(self):
        frame, _ = _terminal_wick_two_impulses()
        # Make the terminal candle body-driven and keep the same 65.2%
        # retrace: only the wick-specific path may use the 70% tolerance.
        frame.loc[23, "close"] = 0.15070
        self.assertIsNone(detect_ikigai_box(
            frame, parameters=IkigaiBoxParameters(
                first_min_bars=4, first_max_bars=4,
                box_min_bars=6, box_max_bars=6,
            )
        ))

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
