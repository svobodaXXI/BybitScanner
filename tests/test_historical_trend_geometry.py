"""Causal geometry checks: no back-painted pivots/lines or invented entries."""
from decimal import Decimal
import unittest

from research.causal_trend_geometry import (
    CausalGeometryFeed, ConfirmedPivot, ConfirmedSwingStream,
    last_correction_reference, main_line_contact, recent_hourly_trend,
    original_reversal_trend, trend_from_frozen_first_pair,
    wick_tight_hourly_line,
)
from research.historical_candle_feed import FIVE_MINUTES_MS, ONE_HOUR_MS
from research.historical_market_replay import Candle


def make_bar(i, high, low, span=ONE_HOUR_MS):
    return Candle(i*span, span, (high+low)/2, high, low, (high+low)/2, 10)


BULL = [
    (110,100), (109,101), (107,98), (116,107), (111,102),
    (119,110), (114,106), (121,115), (117,109),
]
BEAR = [
    (115,105), (119,110), (124,113), (114,104), (120,111),
    (112,102), (118,108),
]


class ConfirmedGeometryTests(unittest.TestCase):
    def test_first_h1_candle_is_candidate_until_right_wing_closes(self):
        # A genuine boundary extremum may be point 1, but is not published
        # on its own close. The completed point 4 is the release gate.
        bars = [
            (110, 100), (115, 105), (112, 104),
            (117, 107), (113, 106), (119, 110),
        ]
        stream = ConfirmedSwingStream(
            timeframe_ms=ONE_HOUR_MS, wing=1, seed_first_pivot=True,
        )
        states = []
        for i, (high, low) in enumerate(bars):
            stream.observe_closed(make_bar(i, high, low))
            states.append(recent_hourly_trend(stream.pivots))
        self.assertEqual(stream.pivots[0].index, 0)
        self.assertEqual(stream.pivots[0].confirmed_at_ms, 2 * ONE_HOUR_MS)
        self.assertTrue(all(state is None for state in states[:4]))
        self.assertIsNotNone(states[4])
        trend = states[4]
        self.assertEqual([p.index for p in trend.pivot_sequence], [0, 1, 2, 3])
        self.assertEqual(trend.available_at_ms, 5 * ONE_HOUR_MS)
        self.assertEqual(trend.side, "BULL")
        # Default non-boundary detector remains unchanged, e.g. M5.
        plain = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(bars[:2]):
            plain.observe_closed(make_bar(i, high, low))
        self.assertEqual(plain.pivots, ())

    def test_first_h1_boundary_rejects_unconfirmed_or_ambiguous_extreme(self):
        for second in ((115, 95), (109, 99)):
            stream = ConfirmedSwingStream(
                timeframe_ms=ONE_HOUR_MS, wing=1, seed_first_pivot=True,
            )
            stream.observe_closed(make_bar(0, 110, 100))
            self.assertEqual(stream.pivots, ())
            stream.observe_closed(make_bar(1, *second))
            if second == (115, 95):
                self.assertEqual(stream.pivots, ())
            else:
                # The first candle is an upper extremum, not a lower pivot.
                self.assertEqual([p.kind for p in stream.pivots], ["HIGH"])

    def test_bull_yellow_lines_require_last_confirming_hour_and_narrow(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        snapshots = []
        for i, (high, low) in enumerate(BULL):
            stream.observe_closed(make_bar(i, high, low))
            snapshots.append(recent_hourly_trend(stream.pivots))
        self.assertTrue(all(x is None for x in snapshots[:6]))
        first = snapshots[6]
        self.assertIsNotNone(first)
        self.assertEqual(first.side, "BULL")
        self.assertEqual([p.index for p in first.pivot_sequence], [2,3,4,5])
        self.assertEqual(first.available_at_ms, 7*ONE_HOUR_MS)
        self.assertEqual(first.main.value_at(3*ONE_HOUR_MS), Decimal(100))
        self.assertEqual(first.target.value_at(3*ONE_HOUR_MS), Decimal(116))
        self.assertGreater(
            first.target.value_at(3*ONE_HOUR_MS) - first.main.value_at(3*ONE_HOUR_MS),
            first.target.value_at(5*ONE_HOUR_MS) - first.main.value_at(5*ONE_HOUR_MS)
        )
        self.assertIsNone(snapshots[7])  # 1h newest pivot is only the intervening low
        second = snapshots[8]
        self.assertEqual([p.index for p in second.pivot_sequence], [4,5,6,7])
        self.assertGreater(second.available_at_ms, first.available_at_ms)

    def test_same_direction_h1_revision_preserves_original_first_wick_anchors(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        versions = []
        # The next HIGH must be a true confirmed pivot, AND the line must
        # pass all intervening wicks. Hour 7 HIGH=122 preserves
        # the narrowing H1 corridor and just clears hour 5's wick=119.
        # HIGH=121 pierces the original H1 target boundary.
        compatible = BULL[:7] + [(122, 115)] + BULL[8:]
        for hour, (high, low) in enumerate(compatible):
            for minute in range(12):
                index = hour * 12 + minute
                five = make_bar(index, high, low, FIVE_MINUTES_MS)
                closed_hour = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(five, closed_hour)
            versions.append(trend)
        first, next_version = versions[6], versions[8]
        self.assertIsNotNone(first)
        self.assertIsNotNone(next_version)
        self.assertEqual(first.side, "BULL")
        self.assertEqual(next_version.side, "BULL")
        self.assertEqual(first.main.first, next_version.main.first)
        self.assertEqual(first.target.first, next_version.target.first)
        self.assertEqual(next_version.main.first.index, 2)
        self.assertEqual(next_version.target.first.index, 3)
        self.assertGreater(next_version.main.second.index, first.main.second.index)
        self.assertGreaterEqual(next_version.target.second.index, first.target.second.index)
        # Both second anchors are confirmed original H1 pivots, not wicks
        # silently substituted to force a valid-looking envelope.
        for candidate_line, upper in (
            (next_version.main, False), (next_version.target, True),
        ):
            for bar in feed._hourly.bars[candidate_line.first.index + 1:
                                        next_version.pivot_sequence[3].index + 1]:
                level = candidate_line.value_at(bar.start_ms)
                if upper:
                    self.assertGreaterEqual(level, bar.high)
                else:
                    self.assertLessEqual(level, bar.low)
        self.assertEqual(first.main.first.price, Decimal(98))
        self.assertEqual(next_version.main.first.price, Decimal(98))
        self.assertGreater(next_version.available_at_ms, first.available_at_ms)

    def test_h1_rejects_later_wick_pierced_revision_without_moving_pivots(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        versions = []
        priors = []
        for hour, (high, low) in enumerate(BULL):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                closed_hour = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(five, closed_hour)
            versions.append(trend)
            priors.append(feed.confirmed_hourly_prior)
        first = versions[6]
        self.assertIsNotNone(first)
        self.assertEqual(first.main.second.index, 4)
        self.assertEqual(first.target.second.index, 5)
        # Later 4 valid structural pivots do not license substituting the
        # intermediate H1 wick at 5: the original version stays immutable.
        self.assertEqual(versions[8], first)
        self.assertEqual(priors[8], Decimal(106))

    def test_h1_upper_line_rejects_nonpivot_wick_piercing(self):
        bars = (
            make_bar(0, 120, 100),
            make_bar(1, 119, 106),
            make_bar(2, 130, 108),
            make_bar(3, 125, 115),
            make_bar(4, 135, 116),
        )
        start = ConfirmedPivot("HIGH", 0, bars[0].start_ms,
                               bars[1].end_ms, Decimal(120))
        candidate = ConfirmedPivot("HIGH", 4, bars[4].start_ms,
                                   bars[4].end_ms, Decimal(135))
        # Hour 2 HIGH=130 cuts through the confirmed 0→4 line.
        # It is NOT a new significant 4-pivot anchor: reject, don't refit.
        self.assertIsNone(wick_tight_hourly_line(
            start, candidate, bars, boundary="UPPER",
            available_at_ms=bars[-1].end_ms,
        ))
        compatible = list(bars)
        compatible[2] = make_bar(2, 127, 108)
        line = wick_tight_hourly_line(
            start, candidate, tuple(compatible), boundary="UPPER",
            available_at_ms=compatible[-1].end_ms,
        )
        self.assertIsNotNone(line)
        self.assertEqual((line.first, line.second), (start, candidate))
        for bar in compatible[1:]:
            self.assertGreaterEqual(line.value_at(bar.start_ms), bar.high)
        self.assertIsNone(wick_tight_hourly_line(
            start, candidate, tuple(compatible), boundary="UPPER",
            available_at_ms=compatible[3].end_ms,
        ))

    def test_h1_lower_line_rejects_nonpivot_wick_piercing(self):
        bars = (
            make_bar(0, 110, 100),
            make_bar(1, 113, 102),
            make_bar(2, 117, 103),
            make_bar(3, 119, 108),
            make_bar(4, 120, 110),
        )
        start = ConfirmedPivot("LOW", 0, bars[0].start_ms,
                               bars[1].end_ms, Decimal(100))
        candidate = ConfirmedPivot("LOW", 4, bars[4].start_ms,
                                   bars[4].end_ms, Decimal(110))
        # Hour 2 LOW=103 is below the 0→4 confirmed pivot line.
        self.assertIsNone(wick_tight_hourly_line(
            start, candidate, bars, boundary="LOWER",
            available_at_ms=bars[-1].end_ms,
        ))
        compatible = list(bars)
        compatible[1] = make_bar(1, 113, 103)
        compatible[2] = make_bar(2, 117, 105)
        line = wick_tight_hourly_line(
            start, candidate, tuple(compatible), boundary="LOWER",
            available_at_ms=compatible[-1].end_ms,
        )
        self.assertIsNotNone(line)
        self.assertEqual((line.first, line.second), (start, candidate))
        for bar in compatible[1:]:
            self.assertLessEqual(line.value_at(bar.start_ms), bar.low)

    def test_real_grass_august_22_h1_upper_wick_rejects_pivot_substitution(self):
        # Public GRASSUSDT H1 evidence (2026-08-22, UTC): the wick at
        # 17:00 high=0.31490 exceeds the real H1 pivot 1--3 upper line.
        # Only the intervening candles unrelated to this boundary are
        # controlled synthetic values; no real archive is reconstructed.
        start = 1787414400000  # 2026-08-22 16:00 UTC, HIGH pivot 1
        high1, high3 = Decimal("0.31580"), Decimal("0.30570")
        bars = []
        for i in range(10):
            interpolated = high1 + (high3 - high1) * Decimal(i) / Decimal(9)
            high = high1 if i == 0 else high3 if i == 9 else interpolated - Decimal("0.001")
            if i == 1:
                high = Decimal("0.31490")  # actual archived 17:00 H1 wick
            bars.append(Candle(
                start + i * ONE_HOUR_MS, ONE_HOUR_MS,
                high - Decimal("0.001"), high, Decimal("0.28000"),
                high - Decimal("0.001"), Decimal("10"),
            ))
        p1 = ConfirmedPivot("HIGH", 0, start,
                            start + 3 * ONE_HOUR_MS, high1)
        p3 = ConfirmedPivot("HIGH", 9, start + 9 * ONE_HOUR_MS,
                            start + 12 * ONE_HOUR_MS, high3)
        available = p3.confirmed_at_ms
        self.assertIsNone(wick_tight_hourly_line(
            p1, p3, tuple(bars), boundary="UPPER",
            available_at_ms=available,
        ))
        line_price = high1 + (high3 - high1) / Decimal(9)
        self.assertGreater(Decimal("0.31490"), line_price)
        # Replacing the single violating HIGH with a sub-line wick makes
        # the very same genuine confirmed-pivot anchors valid.
        corrected = list(bars)
        corrected[1] = Candle(
            start + ONE_HOUR_MS, ONE_HOUR_MS,
            Decimal("0.31360"), Decimal("0.31460"),
            Decimal("0.28000"), Decimal("0.31360"), Decimal("10"),
        )
        fitted = wick_tight_hourly_line(
            p1, p3, tuple(corrected), boundary="UPPER",
            available_at_ms=available,
        )
        self.assertIsNotNone(fitted)
        self.assertEqual((fitted.first, fitted.second), (p1, p3))

    def test_reversal_anchors_first_confirmed_impulse_extreme_not_latest_four(self):
        # A later four-pivot suffix would start from HIGH=113 instead of
        # the first movement high=120. The earliest LOW=80 is the target
        # anchor; both remain frozen when points 3/4 are revised.
        points = [
            ("HIGH", 0, 120), ("LOW", 2, 80),
            ("HIGH", 5, 112), ("LOW", 7, 81),
            ("HIGH", 11, 113), ("LOW", 14, 78),
            ("HIGH", 17, 110), ("LOW", 20, 74),
        ]
        pivots = tuple(
            ConfirmedPivot(kind, i, i * ONE_HOUR_MS,
                           (i + 3) * ONE_HOUR_MS, Decimal(price))
            for kind, i, price in points
        )
        # Fourth pivot is not yet confirmed; showing a main/target line
        # at this earlier instant would be an H1 look-ahead.
        self.assertIsNone(original_reversal_trend(
            pivots[:6], side="BEAR", source_start_ms=0,
            known_at_ms=16 * ONE_HOUR_MS,
        ))
        first = original_reversal_trend(
            pivots[:6], side="BEAR", source_start_ms=0,
            known_at_ms=17 * ONE_HOUR_MS,
        )
        self.assertIsNotNone(first)
        self.assertEqual([p.index for p in first.pivot_sequence], [0, 2, 11, 14])
        self.assertEqual(first.available_at_ms, 17 * ONE_HOUR_MS)
        self.assertEqual((first.main.first.price, first.target.first.price),
                         (Decimal(120), Decimal(80)))
        revised = original_reversal_trend(
            pivots, side="BEAR", source_start_ms=0,
            known_at_ms=23 * ONE_HOUR_MS,
        )
        self.assertIsNotNone(revised)
        self.assertEqual([p.index for p in revised.pivot_sequence], [0, 2, 17, 20])
        self.assertEqual(revised.main.first, first.main.first)
        self.assertEqual(revised.target.first, first.target.first)
        self.assertEqual(
            trend_from_frozen_first_pair(
                pivots, first.main.first, first.target.first,
            ).pivot_sequence, revised.pivot_sequence,
        )
        # Symmetric BULL origin: initial deepest low, then first high.
        opposite = tuple(
            ConfirmedPivot("LOW" if p.kind == "HIGH" else "HIGH",
                           p.index, p.at_ms, p.confirmed_at_ms,
                           Decimal(200) - p.price)
            for p in pivots
        )
        bull = original_reversal_trend(
            opposite[:6], side="BULL", source_start_ms=0,
            known_at_ms=17 * ONE_HOUR_MS,
        )
        self.assertIsNotNone(bull)
        self.assertEqual([p.index for p in bull.pivot_sequence], [0, 2, 11, 14])

    def test_bear_main_is_through_highs_and_target_through_lows(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BEAR):
            stream.observe_closed(make_bar(i, high, low))
        result = recent_hourly_trend(stream.pivots)
        self.assertIsNotNone(result)
        self.assertEqual(result.side, "BEAR")
        self.assertEqual([p.index for p in result.pivot_sequence], [2,3,4,5])
        self.assertEqual(result.main.first.price, Decimal(124))
        self.assertEqual(result.main.second.price, Decimal(120))
        self.assertEqual(result.target.first.price, Decimal(104))
        self.assertEqual(result.target.second.price, Decimal(102))

    def test_cannot_confirm_pivot_or_line_using_future_candle(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        partial = [make_bar(i, high, low) for i, (high, low) in enumerate(BULL)]
        events = []
        for bar in partial:
            new_pivot = stream.observe_closed(bar)
            events.append(new_pivot)
            if new_pivot is not None:
                self.assertLessEqual(new_pivot.confirmed_at_ms, bar.end_ms)
        self.assertIsNone(events[2])  # swing-low center 2 is NOT known on bar 2
        self.assertEqual(events[3].index, 2)
        self.assertEqual(events[3].confirmed_at_ms, 4*ONE_HOUR_MS)
        fresh = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        prefix = []
        for b in partial[:7]:
            fresh.observe_closed(b)
            prefix.append(recent_hourly_trend(fresh.pivots))
        self.assertEqual(prefix[-1], recent_hourly_trend(stream.pivots[:4]))
        with self.assertRaisesRegex(ValueError, "missing|duplicate"):
            stream.observe_closed(partial[-1])  # duplicate/overlap

    def test_five_minute_blue_reference_rejects_wick_piercing(self):
        hourly_stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BULL[:7]):
            hourly_stream.observe_closed(make_bar(i, high, low))
        trend = recent_hourly_trend(hourly_stream.pivots)
        self.assertIsNotNone(trend)
        offset = 100
        highs = [101,104,110,105,103,106,108,102]
        lows =  [96, 98,104,101, 96,100,103, 98]
        bars = tuple(
            make_bar(offset+i, high, low, FIVE_MINUTES_MS)
            for i, (high, low) in enumerate(zip(highs,lows))
        )
        feed = ConfirmedSwingStream(timeframe_ms=FIVE_MINUTES_MS, wing=1)
        for bar in bars:
            feed.observe_closed(bar)
        self.assertEqual([p.kind for p in feed.pivots[-3:]], ["HIGH","LOW","HIGH"])
        line = last_correction_reference(
            hourly=trend, five_minute_pivots=feed.pivots,
            five_minute_bars=bars,
        )
        self.assertIsNotNone(line)
        self.assertEqual(line.first.price, Decimal(110))
        self.assertEqual(line.second.price, Decimal(108))
        self.assertGreater(line.available_at_ms, line.second.at_ms)
        # An intermediate wick cannot replace the significant HIGH pivot 3.
        # The line must be rejected, not tightened to a non-pivot candle.
        self.assertEqual(line.second, feed.pivots[-1])
        pierced = list(bars)
        pierced[5] = make_bar(offset+5, 109, 100, FIVE_MINUTES_MS)
        self.assertIsNone(last_correction_reference(
            hourly=trend, five_minute_pivots=feed.pivots,
            five_minute_bars=tuple(pierced),
        ))
        # A forged price at the actual pivot candle is not accepted either.
        mismatched = list(bars)
        mismatched[6] = make_bar(offset+6, 107, 103, FIVE_MINUTES_MS)
        self.assertIsNone(last_correction_reference(
            hourly=trend, five_minute_pivots=feed.pivots,
            five_minute_bars=tuple(mismatched),
        ))

    def test_m5_lower_reference_rejects_nonpivot_wick_symmetrically(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BEAR):
            stream.observe_closed(make_bar(i, high, low))
        trend = recent_hourly_trend(stream.pivots)
        self.assertIsNotNone(trend)
        self.assertEqual(trend.side, "BEAR")
        # Three alternating confirmed LOW-HIGH-LOW extrema, with an
        # intervening closed wick dipping below the initially fitted line.
        p = ConfirmedPivot("LOW", 0, 100 * FIVE_MINUTES_MS,
                           101 * FIVE_MINUTES_MS, Decimal(90))
        middle = ConfirmedPivot("HIGH", 2, 102 * FIVE_MINUTES_MS,
                                103 * FIVE_MINUTES_MS, Decimal(99))
        q = ConfirmedPivot("LOW", 6, 106 * FIVE_MINUTES_MS,
                           107 * FIVE_MINUTES_MS, Decimal(96))
        bars = tuple(make_bar(100 + i, 110 if i == 2 else 100,
                              91 if i == 4 else (90 if i == 0 else 96),
                              FIVE_MINUTES_MS) for i in range(7))
        # The hour-4 LOW=91 pierces the rising 1--3 boundary; it is not
        # an additional confirmed LOW pivot and cannot become point 3.
        self.assertIsNone(last_correction_reference(
            hourly=trend, five_minute_pivots=(p, middle, q),
            five_minute_bars=bars,
        ))
        compatible = list(bars)
        compatible[4] = make_bar(104, 100, 95, FIVE_MINUTES_MS)
        line = last_correction_reference(
            hourly=trend, five_minute_pivots=(p, middle, q),
            five_minute_bars=tuple(compatible),
        )
        self.assertIsNotNone(line)
        self.assertEqual((line.first, line.second), (p, q))
        for bar in compatible[1:]:
            self.assertLessEqual(line.value_at(bar.start_ms), bar.low)

    def test_blue_publication_requires_four_confirmed_m5_pivots(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL[:7]):
            for minute in range(12):
                bar = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                h1 = make_bar(hour, high, low) if minute == 11 else None
                trend, blue = feed.observe_closed(bar, h1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend.side, "BULL")
        # HIGH 144 -> LOW 120 -> lower HIGH 137 is only 1-2-3.
        # The fourth structurally lower LOW has not been confirmed.
        path = [
            (140, 132), (144, 135), (141, 131),
            (130, 120), (137, 127), (132, 126),
        ]
        for minute, (high, low) in enumerate(path):
            bar = make_bar(84 + minute, high, low, FIVE_MINUTES_MS)
            _, blue = feed.observe_closed(bar, None)
            self.assertIsNone(blue, "three pivots must never publish blue")

    def test_only_one_blue_correction_until_its_actual_next_m5_open_break(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL[:7]):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                h1 = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(five, h1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend.side, "BULL")
        # Four CONFIRMED pivots: HIGH144 - LOW120 - lower HIGH137 -
        # lower LOW117. The last LOW is confirmed only at candle 8 close.
        path = [
            (140, 132), (144, 135), (141, 131), (130, 120),
            (137, 127), (132, 126), (130, 121), (128, 117),
            (155, 143), (130, 120),
            (155, 143),  # Next M5 OPEN 149 above already published blue.
        ]
        created = None
        for minute, (high, low) in enumerate(path):
            five = make_bar(84 + minute, high, low, FIVE_MINUTES_MS)
            _, blue = feed.observe_closed(five, None)
            if minute < 8:
                self.assertIsNone(blue, "fourth M5 pivot not yet confirmed")
            if minute == 8:
                self.assertIsNotNone(blue)
                created = blue
                self.assertEqual(created.first.price, Decimal(144))
                self.assertEqual(created.second.price, Decimal(137))
                self.assertEqual(created.available_at_ms, five.end_ms)
            if minute == 9:
                self.assertEqual(blue, created, "confirmed correction stays active")
            if minute == 10:
                self.assertIsNone(blue, "later M5 OPEN retires active blue")
        self.assertEqual(feed._blue_broken_at_ms, (84 + 11) * FIVE_MINUTES_MS)

    def test_m5_deeper_correction_revisions_keep_first_wick_and_replay_history(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL[:7]):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                h1 = make_bar(hour, high, low) if minute == 11 else None
                feed.observe_closed(five, h1)

        # Publish only when fourth lower LOW=80 is confirmed, then lengthen
        # with a new LOW=79 followed by a confirmed returning HIGH=139.
        path = [
            (140, 132), (144, 135), (141, 131), (130, 120),
            (137, 127), (132, 126),
            (126, 80), (139, 90), (128, 85), (130, 79),
            (130, 100), (139, 90), (128, 85),
            (150, 140),
        ]
        versions = []
        for minute, (high, low) in enumerate(path):
            five = make_bar(84 + minute, high, low, FIVE_MINUTES_MS)
            _, blue = feed.observe_closed(five, None)
            versions.append(blue)
        self.assertTrue(all(v is None for v in versions[:7]))
        original = versions[7]
        revised = versions[12]
        self.assertIsNotNone(original)
        self.assertIsNotNone(revised)
        self.assertEqual(original.first.price, Decimal(144))
        self.assertEqual(original.second.price, Decimal(137))
        self.assertTrue(all(v == original for v in versions[8:12]))
        self.assertEqual(revised.first, original.first)
        self.assertEqual(revised.second.price, Decimal(139))
        self.assertEqual(revised.second.index, 95)
        self.assertGreater(revised.available_at_ms, original.available_at_ms)
        self.assertIsNone(versions[13])
        self.assertEqual(versions[7].second.price, Decimal(137))
        for bar in feed._five.bars[original.first.index + 1:96]:
            self.assertGreaterEqual(revised.value_at(bar.start_ms), bar.high)

    def test_m5_revision_lower_boundary_mirrors_deeper_low_rule(self):
        # Bearish H1 uses rising LOW--HIGH--LOW correction boundaries;
        # a new highest HIGH triggers the symmetrical second-anchor refit.
        hourly_stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BEAR):
            hourly_stream.observe_closed(make_bar(i, high, low))
        trend = recent_hourly_trend(hourly_stream.pivots)
        self.assertIsNotNone(trend)
        first = ConfirmedPivot("LOW", 0, 100 * FIVE_MINUTES_MS,
                               101 * FIVE_MINUTES_MS, Decimal(90))
        middle = ConfirmedPivot("HIGH", 2, 102 * FIVE_MINUTES_MS,
                                103 * FIVE_MINUTES_MS, Decimal(104))
        q = ConfirmedPivot("LOW", 5, 105 * FIVE_MINUTES_MS,
                           106 * FIVE_MINUTES_MS, Decimal(96))
        # Later HIGH 112 is higher than 104, with a newer LOW 98.
        new_middle = ConfirmedPivot("HIGH", 8, 108 * FIVE_MINUTES_MS,
                                    109 * FIVE_MINUTES_MS, Decimal(112))
        new_q = ConfirmedPivot("LOW", 10, 110 * FIVE_MINUTES_MS,
                               111 * FIVE_MINUTES_MS, Decimal(98))
        bars = tuple(make_bar(100 + i, 115 if i == 8 else 110,
                              90 if i == 0 else (96 if i == 5 else
                              98 if i == 10 else 100),
                              FIVE_MINUTES_MS) for i in range(11))
        old = last_correction_reference(
            hourly=trend, five_minute_pivots=(first, middle, q),
            five_minute_bars=bars[:6],
        )
        updated = last_correction_reference(
            hourly=trend, five_minute_pivots=(first, new_middle, new_q),
            five_minute_bars=bars,
        )
        self.assertIsNotNone(old)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.first, old.first)
        self.assertGreater(updated.second.at_ms, old.second.at_ms)
        for bar in bars[1:11]:
            self.assertLessEqual(updated.value_at(bar.start_ms), bar.low)

    def test_main_hourly_contact_requires_frozen_line_and_trend_side_close(self):
        for side, source in (("BULL", BULL[:7]), ("BEAR", BEAR)):
            stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
            for i, (high, low) in enumerate(source):
                stream.observe_closed(make_bar(i, high, low))
            trend = recent_hourly_trend(stream.pivots)
            self.assertIsNotNone(trend)
            self.assertEqual(trend.side, side)
            t = trend.available_at_ms
            line_at = trend.main.value_at(t)
            sign = 1 if side == "BULL" else -1
            touch = Candle(
                t, FIVE_MINUTES_MS, line_at + sign,
                line_at + 3, line_at - 3, line_at + sign, 10,
            )
            self.assertEqual(main_line_contact(trend, touch),
                             trend.main.value_at(t + FIVE_MINUTES_MS))
            early = Candle(
                t - FIVE_MINUTES_MS, FIVE_MINUTES_MS, line_at + sign,
                line_at + 3, line_at - 3, line_at + sign, 10,
            )
            self.assertIsNone(main_line_contact(trend, early))
            failed = Candle(
                t, FIVE_MINUTES_MS, line_at,
                line_at + 3, line_at - 3, line_at - sign, 10,
            )
            self.assertIsNone(main_line_contact(trend, failed))
            self.assertIsNone(main_line_contact(None, touch))

    def test_opposite_yellow_trend_waits_for_closed_h1_prior_break_and_confirmed_anchors(self):
        # First a BULL 1--3/2--4 candidate is confirmed; an H1 close below
        # its prior LOW=106 at hour 9 and the next H1 OPEN below it at hour 10
        # retire it. A later BEAR line is revealed only when its own fourth
        # alternating swing is confirmed, never projected backward to break.
        hours = BULL + [
            (103, 93), (99, 90), (103, 90), (96, 83), (98, 89),
            (92, 80), (97, 86), (91, 77),
        ]
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        observations = {}
        priors = {}
        for hour, (high, low) in enumerate(hours):
            for minute in range(12):
                m5 = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                newly_closed = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(m5, newly_closed)
                observations[hour, minute] = trend
                priors[hour, minute] = feed.confirmed_hourly_prior

        original = observations[8, 11]
        self.assertIsNotNone(original)
        self.assertEqual(original.side, "BULL")
        # Refit of the yellow 1–3 was rejected; true point 3 remains 102.
        # Independently confirmed H1 contact at 106 still advances the prior.
        self.assertEqual(original.main.second.price, Decimal(102))
        self.assertEqual(priors[8, 11], Decimal(106))
        self.assertEqual(observations[9, 11].side, "BULL")
        # A first H1 OPEN outside the purple prior is observed only after the
        # first completed M5; until then the last H1 close alone isn't enough.
        self.assertIsNone(observations[10, 0])
        self.assertIsNone(observations[14, 11])
        reversed_trend = observations[15, 11]
        self.assertIsNotNone(reversed_trend)
        self.assertEqual(reversed_trend.side, "BEAR")
        self.assertEqual(reversed_trend.main.first.kind, "HIGH")
        self.assertEqual(reversed_trend.main.second.kind, "HIGH")
        self.assertLess(reversed_trend.main.second.price, reversed_trend.main.first.price)
        self.assertEqual(reversed_trend.main.available_at_ms, 16 * ONE_HOUR_MS)
        self.assertEqual(reversed_trend.available_at_ms, 16 * ONE_HOUR_MS)
        self.assertTrue(all(
            observations[hour, minute] is None
            for hour in range(10, 15) for minute in range(12)
        ))

    def test_reversal_uses_last_confirmed_purple_prior_not_old_yellow_second(self):
        # The first BULL line has LOW=102; after another confirmed touch
        # and a higher CLOSED H1 high the purple prior advances to LOW=106.
        # A close/open at 104 then breaks 106, but would incorrectly survive
        # the old 102 yellow anchor.
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        observed = {}
        actual_breaks = []
        for hour, (high, low) in enumerate(BULL + [(113, 95), (112, 96)]):
            for minute in range(12 if hour < 10 else 1):
                bar = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                newly_closed = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(bar, newly_closed)
                if feed.confirmed_hourly_prior_break is not None:
                    actual_breaks.append(feed.confirmed_hourly_prior_break)
                if minute == 11 or hour == 10:
                    observed[hour, minute] = (
                        trend.side if trend is not None else None,
                        feed.confirmed_hourly_prior,
                    )
        self.assertEqual(observed[6, 11], ("BULL", Decimal(102)))
        self.assertEqual(observed[8, 11], ("BULL", Decimal(106)))
        # Last known purple prior is 106, whereas the original yellow
        # line's earlier second wick was 102; break needs CLOSE then OPEN.
        self.assertEqual(observed[9, 11], ("BULL", Decimal(106)))
        self.assertEqual(observed[10, 0][0], None)
        self.assertEqual(feed._waiting_for_side, "BEAR")
        self.assertEqual(feed._reversal_known_at_ms,
                         10 * ONE_HOUR_MS + FIVE_MINUTES_MS)
        self.assertEqual(len(actual_breaks), 1)
        self.assertEqual(actual_breaks[0]["prior_price"], Decimal(106))
        self.assertEqual(actual_breaks[0]["previous_side"], "BULL")
        self.assertEqual(actual_breaks[0]["new_side"], "BEAR")
        self.assertEqual(actual_breaks[0]["hourly_close_ms"], 10 * ONE_HOUR_MS)
        self.assertEqual(actual_breaks[0]["next_hour_open_ms"], 10 * ONE_HOUR_MS)
        self.assertEqual(actual_breaks[0]["confirmed_at_ms"],
                         10 * ONE_HOUR_MS + FIVE_MINUTES_MS)

    def test_yellow_prior_break_needs_close_and_next_open_not_a_wick_or_recovery(self):
        for breaking, continued in (
            # Wick through the prior but close remains above 106.
            ((120, 102), (99, 90)),
            # H1 close beyond prior, but next hour OPENS back above.
            ((103, 93), (120, 110)),
        ):
            feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
            result = None
            for hour, (high, low) in enumerate(BULL + [breaking, continued]):
                for minute in range(12):
                    bar = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                    hour_bar = make_bar(hour, high, low) if minute == 11 else None
                    result, _ = feed.observe_closed(bar, hour_bar)
                    if hour == 10 and minute == 0:
                        self.assertIsNotNone(result)
                        self.assertEqual(result.side, "BULL")

    def test_next_hour_open_beyond_prior_break_survives_immediate_reclaim(self):
        # Owner GRASS I-IV: bearish old prior, higher-high-confirmed
        # rising support and its own purple prior; then a new H1 OPEN
        # beyond that prior, while price recovers during the SAME M5.
        # The first M5 CLOSE is only the earliest *observability* point.
        # It must not be misinterpreted as requiring the M5 close to stay
        # outside or as a licence to revoke the already confirmed break.
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL + [(113, 95)]):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                hourly = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(five, hourly)
        self.assertEqual(trend.side, "BULL")
        self.assertEqual(feed.confirmed_hourly_prior, Decimal(106))
        t = 10 * ONE_HOUR_MS
        # Next H1 opens 104 < prior 106, but the very first five-minute
        # candle recovers to 112 > 106 (a bullish body over the broken level).
        reclaimed = Candle(t, FIVE_MINUTES_MS, 104, 113, 103, 112, 10)
        after, _ = feed.observe_closed(reclaimed, None)
        broken = feed.confirmed_hourly_prior_break
        self.assertIsNone(after)
        self.assertIsNotNone(broken)
        self.assertEqual(broken["previous_side"], "BULL")
        self.assertEqual(broken["new_side"], "BEAR")
        self.assertEqual(broken["prior_price"], Decimal(106))
        self.assertEqual(broken["next_hour_open_ms"], t)
        self.assertEqual(broken["confirmed_at_ms"], t + FIVE_MINUTES_MS)
        self.assertEqual(feed._waiting_for_side, "BEAR")
        self.assertEqual(feed._reversal_source_start_ms,
                         trend.main.first.at_ms)
        # A later rebound cannot resurrect the retired BULL trend, create
        # a second break, or prematurely draw a new BEAR four-pivot line.
        recovered = Candle(t + FIVE_MINUTES_MS, FIVE_MINUTES_MS,
                           112, 114, 109, 113, 10)
        again, _ = feed.observe_closed(recovered, None)
        self.assertIsNone(again)
        self.assertIsNone(feed.confirmed_hourly_prior_break)
        self.assertEqual(feed._waiting_for_side, "BEAR")

    def test_geometry_feed_does_not_emit_lines_before_confirmed_hourly(self):
        geometry = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        first_times = []
        last = None
        for i, (high, low) in enumerate(BULL):
            for minute in range(12):
                five_index = i*12+minute
                next_5m = make_bar(five_index, 105, 100, FIVE_MINUTES_MS)
                next_hour = make_bar(i, high, low) if minute == 11 else None
                last, blue = geometry.observe_closed(next_5m, next_hour)
                if last is not None and not first_times:
                    first_times.append(next_5m.end_ms)
                self.assertTrue(last is None or last.available_at_ms <= next_5m.end_ms)
                self.assertTrue(blue is None or blue.available_at_ms <= next_5m.end_ms)
        self.assertEqual(first_times, [7*ONE_HOUR_MS])
        # A pierced later 2–4 proposal cannot replace the frozen
        # structurally valid original target pivot at hour 5.
        self.assertEqual(last.pivot_sequence[3].index, 5)
        self.assertEqual(last.target.second.price, Decimal(119))
        for bar in geometry._hourly.bars[last.target.first.index + 1:8]:
            self.assertGreaterEqual(last.target.value_at(bar.start_ms), bar.high)


if __name__ == "__main__":
    unittest.main()
