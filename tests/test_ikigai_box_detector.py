"""Narrow offline, closed-candle geometry tests: no Scanner/Robot side effects."""

import math
import unittest

import pandas as pd

from geometry.ikigai_box import (
    IkigaiBoxParameters,
    detect_ikigai_box,
    detect_ikigai_box_watches,
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

    def test_wick_box_is_watch_before_second_impulse_and_full_extension(self):
        frame, box_end = _terminal_wick_two_impulses()
        # The independent WATCH exists at the end of consolidation, when
        # confirmed detector still correctly requires a second impulse.
        self.assertIsNone(detect_ikigai_box(frame, as_of_index=box_end))
        watches = detect_ikigai_box_watches(frame, as_of_index=box_end)
        matching = [w for w in watches if w.anchor_identity == ("SHORT", 20, 23)]
        self.assertEqual(len(matching), 1)
        early = matching[0]
        self.assertEqual(early.phase, "BOX_READY")
        self.assertIsNone(early.first_box_exit_index)
        self.assertEqual((early.box_start_index, early.box_end_index), (24, 29))
        self.assertAlmostEqual(early.box_low, 0.13707)
        self.assertAlmostEqual(early.box_high, 0.1420)
        self.assertAlmostEqual(early.fibonacci_1_0, 0.15198)
        self.assertAlmostEqual(early.fibonacci_1_618, 0.16611366)
        self.assertAlmostEqual(early.fibonacci_2_618, 0.18898366)
        self.assertEqual((early.anchor_start_price, early.anchor_end_price),
                         (0.12911, 0.15198))

    def test_watch_records_first_break_without_requiring_second_progress(self):
        frame, box_end = _terminal_wick_two_impulses()
        first = detect_ikigai_box_watches(frame, as_of_index=box_end)
        prior = next(w for w in first if w.anchor_identity == ("SHORT", 20, 23))
        continued = pd.concat([frame, pd.DataFrame([
            {"open": 0.1400, "high": 0.1456,
             "low": 0.1398, "close": 0.14412},
            {"open": 0.14412, "high": 0.1450,
             "low": 0.1390, "close": 0.1400},
        ])], ignore_index=True)
        # The first breakout candle does not cross B=0.15198, so the old
        # confirmed detector stays silent; the WATCH has a first-exit index.
        self.assertIsNone(detect_ikigai_box(
            continued, as_of_index=box_end + 1,
        ))
        on_break = detect_ikigai_box_watches(
            continued, as_of_index=box_end + 1,
        )
        breakout = next(
            w for w in on_break if w.anchor_identity == prior.anchor_identity
        )
        self.assertEqual(breakout.phase, "BOX_BREAK_OBSERVED")
        self.assertEqual(breakout.first_box_exit_index, box_end + 1)
        self.assertEqual(breakout.box_end_index, prior.box_end_index)
        self.assertEqual(breakout.fibonacci_1_618, prior.fibonacci_1_618)
        # After a re-entry the pure stateless WATCH may observe a wider shelf.
        # The caller must persist the first frozen box by anchor_identity.
        after_reentry = detect_ikigai_box_watches(continued)
        self.assertTrue(any(
            w.anchor_identity == prior.anchor_identity for w in after_reentry
        ))

    def test_sequential_watch_freezes_box_through_reentry_and_second_break(self):
        frame, box_end = _terminal_wick_two_impulses(second=False)
        # At T0 an observed qualified shelf is not yet a confirmed leg two.
        prior = detect_ikigai_box_watches(frame, as_of_index=box_end)
        target = ("SHORT", 20, 23)
        ready = next(w for w in prior if w.anchor_identity == target)
        self.assertEqual(ready.phase, "BOX_READY")
        self.assertEqual((ready.box_start_index, ready.box_end_index), (24, 29))
        extra = pd.DataFrame([
            # T1: first close above the frozen shelf high.
            {"open": 0.1400, "high": 0.14560, "low": 0.1398, "close": 0.14412},
            # T2–T5: returns inside; do not absorb T1 into a wider box.
            {"open": 0.14412, "high": 0.1450, "low": 0.1390, "close": 0.1400},
            {"open": 0.1400, "high": 0.1410, "low": 0.1388, "close": 0.1394},
            {"open": 0.1394, "high": 0.1412, "low": 0.1388, "close": 0.1400},
            {"open": 0.1400, "high": 0.1415, "low": 0.1390, "close": 0.1398},
            # T6–T7: another break; the old first-exit evidence stays frozen.
            {"open": 0.1398, "high": 0.1444, "low": 0.1397, "close": 0.1440},
            {"open": 0.1440, "high": 0.1460, "low": 0.1439, "close": 0.1458},
        ])
        history = pd.concat([frame, extra], ignore_index=True)
        frozen = None
        for end in range(box_end + 1, len(history)):
            current = detect_ikigai_box_watches(
                history, as_of_index=end, previous_watches=prior,
            )
            assert current
            found = next(w for w in current if w.anchor_identity == target)
            self.assertEqual(found.as_of_index, end)
            self.assertEqual(found.phase, "BOX_BREAK_OBSERVED")
            self.assertEqual(found.first_box_exit_index, box_end + 1)
            self.assertEqual((found.box_start_index, found.box_end_index), (24, 29))
            self.assertAlmostEqual(found.box_high, 0.1420)
            self.assertEqual(found.fibonacci_1_618, ready.fibonacci_1_618)
            if frozen is None:
                frozen = found
            else:
                self.assertEqual(found.box_end_index, frozen.box_end_index)
                self.assertEqual(found.first_box_exit_index, frozen.first_box_exit_index)
            prior = current

    def test_sequential_watch_does_not_freeze_while_shelf_continues(self):
        frame, box_end = _terminal_wick_two_impulses(second=False)
        previous = detect_ikigai_box_watches(frame, as_of_index=box_end)
        extended = pd.concat([frame, pd.DataFrame([
            {"open": 0.1400, "high": 0.1415, "low": 0.1380, "close": 0.1404},
        ])], ignore_index=True)
        current = detect_ikigai_box_watches(
            extended, as_of_index=box_end + 1, previous_watches=previous,
        )
        found = next(w for w in current if w.anchor_identity == ("SHORT", 20, 23))
        self.assertEqual(found.phase, "BOX_READY")
        self.assertIsNone(found.first_box_exit_index)
        self.assertEqual(found.box_end_index, box_end + 1)

    def test_sequential_watch_rejects_future_or_ambiguous_prior_state(self):
        from dataclasses import replace
        frame, box_end = _terminal_wick_two_impulses(second=False)
        prior = detect_ikigai_box_watches(frame, as_of_index=box_end)
        target = next(w for w in prior if w.anchor_identity == ("SHORT", 20, 23))
        continuation = pd.concat([frame, pd.DataFrame([{
            "open": 0.1400, "high": 0.14560,
            "low": 0.1398, "close": 0.14412,
        }])], ignore_index=True)
        for bad in (
            replace(target, as_of_index=box_end + 1),
            replace(target, box_high=0.99),
            replace(target, anchor_end_price=0.99),
            replace(target, phase="BOX_BREAK_OBSERVED",
                    first_box_exit_index=None),
        ):
            with self.subTest(prior=bad):
                with self.assertRaises(ValueError):
                    detect_ikigai_box_watches(
                        continuation, previous_watches=(bad,),
                    )
        with self.assertRaises(ValueError):
            detect_ikigai_box_watches(
                continuation, previous_watches=(target, target),
            )

    def test_sequential_watch_drops_frozen_zone_after_actual_touch(self):
        frame, box_end = _terminal_wick_two_impulses(second=False)
        prior = detect_ikigai_box_watches(frame)
        target = ("SHORT", 20, 23)
        touch = pd.concat([frame, pd.DataFrame([{
            "open": 0.1400, "high": 0.17, "low": 0.1398, "close": 0.168,
        }])], ignore_index=True)
        later = detect_ikigai_box_watches(
            touch, previous_watches=prior,
        )
        self.assertNotIn(target, {w.anchor_identity for w in later})

    def test_watch_rejects_stale_entry_after_extension_touch(self):
        frame, box_end = _terminal_wick_two_impulses()
        touch = pd.DataFrame([{
            "open": 0.1400, "high": 0.1700,
            "low": 0.1398, "close": 0.1680,
        }])
        later = pd.concat([frame, touch], ignore_index=True)
        watches = detect_ikigai_box_watches(later)
        self.assertFalse(any(
            w.anchor_identity == ("SHORT", 20, 23) for w in watches
        ))
        self.assertEqual(
            next(w for w in detect_ikigai_box_watches(
                frame, as_of_index=box_end,
            ) if w.anchor_identity == ("SHORT", 20, 23)).as_of_index,
            box_end,
        )

    def test_watch_long_is_mirror_and_has_no_future_peeking(self):
        frame, box_end = _terminal_wick_two_impulses(
            direction=-1, second=False,
        )
        original = detect_ikigai_box_watches(frame, as_of_index=box_end)
        match = next(w for w in original if w.anchor_identity == ("LONG", 20, 23))
        self.assertEqual(match.phase, "BOX_READY")
        self.assertGreater(match.fibonacci_1_0, match.fibonacci_1_618)
        future = pd.concat([frame, pd.DataFrame([
            {"open": 0.1, "high": 0.101, "low": 0.099, "close": 0.1},
        ])], ignore_index=True)
        self.assertEqual(
            original,
            detect_ikigai_box_watches(future, as_of_index=box_end),
        )

    def test_watch_does_not_redefine_standalone_range_as_box(self):
        frame = pd.DataFrame([
            _bar(100.0, 100.1 if i % 2 else 99.9) for i in range(90)
        ])
        self.assertEqual(detect_ikigai_box_watches(frame), ())
        self.assertEqual(
            detect_ikigai_box_watches(frame, as_of_index=len(frame)), ()
        )

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
