"""Causal geometry checks: no back-painted pivots/lines or invented entries."""
from decimal import Decimal
import unittest

from research.causal_trend_geometry import (
    CausalGeometryFeed, ConfirmedPivot, ConfirmedSwingStream,
    last_acceleration_boundary, last_correction_reference, main_line_contact, recent_hourly_trend,
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
        for hour, (high, low) in enumerate(BULL):
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
        # An earlier higher wick may become the correct slope-tight second
        # anchor even after a later, absolute high pivot is confirmed.
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

    def test_h1_wick_envelope_uses_worst_slope_not_absolute_wick(self):
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
        line = wick_tight_hourly_line(
            start, candidate, bars, boundary="UPPER",
            available_at_ms=bars[-1].end_ms,
        )
        self.assertIsNotNone(line)
        self.assertEqual(line.first, start)
        # HIGH at hour 2 (130) gives a steeper upper envelope than
        # the absolute maximum 135 at hour 4.
        self.assertEqual(line.second.index, 2)
        self.assertEqual(line.second.price, Decimal(130))
        for bar in bars[1:]:
            self.assertGreaterEqual(line.value_at(bar.start_ms), bar.high)
        self.assertIsNone(wick_tight_hourly_line(
            start, candidate, bars, boundary="UPPER",
            available_at_ms=bars[3].end_ms,
        ))

    def test_h1_lower_envelope_mirrors_upper_wick_constraint(self):
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
        line = wick_tight_hourly_line(
            start, candidate, bars, boundary="LOWER",
            available_at_ms=bars[-1].end_ms,
        )
        self.assertIsNotNone(line)
        self.assertEqual(line.first, start)
        self.assertEqual(line.second.index, 2)
        self.assertEqual(line.second.price, Decimal(103))
        for bar in bars[1:]:
            self.assertLessEqual(line.value_at(bar.start_ms), bar.low)

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

    def test_equal_wick_plateaus_confirm_last_peak_and_trough_on_both_timeframes(self):
        # On the strict >/< detector, neither 16 high and neither 7 low
        # was ever recognized. They are real price extrema, not tiny swings.
        # A plateau is only known after the right-hand wing has CLOSED.
        prices = [
            (10, 8), (14, 9), (16, 11), (16, 12), (13, 10),
            (12, 9), (11, 7), (10, 7), (12, 9), (13, 10),
        ]
        for timeframe in (ONE_HOUR_MS, FIVE_MINUTES_MS):
            with self.subTest(timeframe=timeframe):
                stream = ConfirmedSwingStream(timeframe_ms=timeframe, wing=2)
                discovered = []
                for index, (high, low) in enumerate(prices):
                    discovered.append(stream.observe_closed(
                        make_bar(index, high, low, timeframe)))
                    self.assertTrue(all(
                        p.confirmed_at_ms <= (index + 1) * timeframe
                        for p in stream.pivots))
                self.assertTrue(all(item is None for item in discovered[:5]))
                self.assertEqual(
                    [(p.kind, p.index, p.price, p.confirmed_at_ms)
                     for p in stream.pivots],
                    [("HIGH", 3, Decimal(16), 6 * timeframe),
                     ("LOW", 7, Decimal(7), 10 * timeframe)],
                )
                self.assertIsNone(recent_hourly_trend(stream.pivots),
                                  "two plateaus cannot invent a four-point trend")

    def test_ambiguous_outside_candle_cannot_assign_both_sides_without_intrabar_order(self):
        prices = [(10, 7), (11, 8), (20, 1), (12, 9), (11, 8)]
        for timeframe in (ONE_HOUR_MS, FIVE_MINUTES_MS):
            stream = ConfirmedSwingStream(timeframe_ms=timeframe, wing=2)
            for index, (high, low) in enumerate(prices):
                self.assertIsNone(stream.observe_closed(
                    make_bar(index, high, low, timeframe)))
            self.assertEqual(stream.pivots, ())

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

    def test_hourly_fitted_line_retains_original_four_confirmed_structural_pivots(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BULL[:7]):
            stream.observe_closed(make_bar(i, high, low))
        structural = recent_hourly_trend(stream.pivots)
        self.assertIsNotNone(structural)
        from research.causal_trend_geometry import wick_tight_hourly_trend
        fitted = wick_tight_hourly_trend(structural, stream.bars)
        self.assertIsNotNone(fitted)
        self.assertEqual(fitted.pivot_sequence, structural.pivot_sequence)
        self.assertTrue(all(
            pivot in stream.pivots for pivot in fitted.pivot_sequence
        ))
        self.assertLessEqual(
            max(p.confirmed_at_ms for p in fitted.pivot_sequence),
            fitted.available_at_ms,
        )

    def test_last_m5_acceleration_requires_four_closed_swings_and_known_h1_target_touch(self):
        stream = ConfirmedSwingStream(timeframe_ms=ONE_HOUR_MS, wing=1)
        for i, (high, low) in enumerate(BULL[:7]):
            stream.observe_closed(make_bar(i, high, low))
        hourly = recent_hourly_trend(stream.pivots)
        self.assertIsNotNone(hourly)
        self.assertEqual(hourly.side, "BULL")
        start = 100
        m5 = FIVE_MINUTES_MS
        bars = tuple(make_bar(start + i, 95 if i == 2 else 93,
                              80 + i if i <= 4 else 82, m5)
                     for i in range(10))
        p1 = ConfirmedPivot("LOW", 0, bars[0].start_ms,
                            bars[3].end_ms, Decimal(80))
        p2 = ConfirmedPivot("HIGH", 2, bars[2].start_ms,
                            bars[5].end_ms, Decimal(95))
        p3 = ConfirmedPivot("LOW", 4, bars[4].start_ms,
                            bars[7].end_ms, Decimal(84))
        fourth_price = max(Decimal(99), hourly.target.value_at(bars[6].start_ms))
        p4 = ConfirmedPivot("HIGH", 6, bars[6].start_ms,
                            bars[9].end_ms, fourth_price)
        pivots = (p1, p2, p3, p4)
        self.assertIsNone(last_acceleration_boundary(
            hourly=hourly, five_minute_pivots=pivots[:3],
            five_minute_bars=bars,
        ))
        candidate = last_acceleration_boundary(
            hourly=hourly, five_minute_pivots=pivots,
            five_minute_bars=bars,
        )
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.first, p1)
        self.assertEqual(candidate.second, p3)
        self.assertEqual(candidate.available_at_ms, p4.confirmed_at_ms)
        self.assertIsNone(last_acceleration_boundary(
            hourly=hourly, five_minute_pivots=(
                p1, p2, p3, ConfirmedPivot("HIGH", 6, p4.at_ms,
                    p4.confirmed_at_ms, Decimal(98)),
            ),
            five_minute_bars=bars,
        ), "without touching the H1 target, no confirmed acceleration is published")
        self.assertIsNone(last_acceleration_boundary(
            hourly=hourly, five_minute_pivots=(
                p1, p2, p3, ConfirmedPivot("LOW", 6, p4.at_ms,
                    p4.confirmed_at_ms, p4.price),
            ),
            five_minute_bars=bars,
        ), "a mismatched fourth pivot cannot be accepted")

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
        # The strongest wick protrusion becomes the updated second anchor,
        # not a rejection and not a move of the original first point.
        pierced = list(bars)
        pierced[5] = make_bar(offset+5, 109, 100, FIVE_MINUTES_MS)
        tightened = last_correction_reference(
            hourly=trend, five_minute_pivots=feed.pivots,
            five_minute_bars=tuple(pierced),
        )
        self.assertIsNotNone(tightened)
        self.assertEqual(tightened.first, line.first)
        self.assertEqual(tightened.second.at_ms, pierced[5].start_ms)
        self.assertEqual(tightened.second.price, Decimal(109))
        self.assertGreaterEqual(tightened.available_at_ms, pierced[5].end_ms)
        for bar in pierced:
            if tightened.first.at_ms < bar.start_ms <= line.second.at_ms:
                self.assertGreaterEqual(tightened.value_at(bar.start_ms), bar.high)

    def test_m5_lower_reference_uses_strongest_low_wick_symmetrically(self):
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
        line = last_correction_reference(
            hourly=trend, five_minute_pivots=(p, middle, q),
            five_minute_bars=bars,
        )
        self.assertIsNotNone(line)
        self.assertEqual(line.first, p)
        self.assertEqual(line.second.at_ms, bars[4].start_ms)
        self.assertEqual(line.second.price, Decimal(91))
        for bar in bars[1:]:
            self.assertLessEqual(line.value_at(bar.start_ms), bar.low)

    def test_only_one_blue_correction_until_its_actual_next_m5_open_break(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL[:7]):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                h1 = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(five, h1)
        self.assertIsNotNone(trend)
        self.assertEqual(trend.side, "BULL")
        # No blue line with only HIGH-LOW-HIGH: the fourth lower LOW
        # must itself be causally confirmed before publication.
        path = [
            (140, 132), (144, 135), (141, 131), (130, 120),
            (137, 127), (132, 126), (130, 121), (128, 117),
            (155, 143),  # Confirms fourth LOW; may only publish at this CLOSE.
            (130, 120),
            (160, 150),  # NEXT M5 OPEN=155 crosses already-published blue.
            (130, 120),
        ]
        blue = None
        created = None
        for minute, (high, low) in enumerate(path):
            five = make_bar(84 + minute, high, low, FIVE_MINUTES_MS)
            _, blue = feed.observe_closed(five, None)
            if minute < 8:
                self.assertIsNone(blue, "3 pivots cannot publish a confirmed blue line")
            if minute == 8:
                self.assertIsNotNone(blue)
                created = blue
                self.assertEqual(created.first.price, Decimal(144))
                self.assertEqual(created.second.price, Decimal(137))
                self.assertEqual(created.available_at_ms, five.end_ms)
            if minute == 9:
                self.assertEqual(blue, created, "new pivots cannot replace an active correction")
            if minute >= 10:
                self.assertIsNone(blue, "a broken correction stays retired until new pivots")
        self.assertEqual(feed._blue_broken_at_ms, (84 + 11) * FIVE_MINUTES_MS)

    def test_m5_deeper_correction_revisions_keep_first_wick_and_replay_history(self):
        feed = CausalGeometryFeed(wing_1h=1, wing_5m=1)
        for hour, (high, low) in enumerate(BULL[:7]):
            for minute in range(12):
                five = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                h1 = make_bar(hour, high, low) if minute == 11 else None
                feed.observe_closed(five, h1)

        # A countertrend M5 swing is published after HIGH-LOW-HIGH-LOW.
        # The NEW deepest low (79 vs 80) and subsequent confirmed HIGH 139
        # justify changing only the second HIGH, not starting a new blue line.
        path = [
            (140, 132), (144, 135), (141, 131), (130, 120),
            (137, 127), (132, 126),
            (126, 80), (139, 90), (128, 85), (130, 79),
            (130, 90), (139, 93), (130, 91),
            (150, 140),
        ]
        versions = []
        for minute, (high, low) in enumerate(path):
            five = make_bar(84 + minute, high, low, FIVE_MINUTES_MS)
            _, blue = feed.observe_closed(five, None)
            versions.append(blue)
        original = versions[7]
        revised = versions[12]
        self.assertTrue(all(item is None for item in versions[:7]))
        self.assertIsNotNone(original)
        self.assertIsNotNone(revised)
        self.assertEqual(original.first.price, Decimal(144))
        self.assertEqual(original.second.price, Decimal(137))
        self.assertEqual(versions[8], original)
        self.assertEqual(versions[11], original)  # Low alone is insufficient.
        self.assertEqual(revised.first, original.first)
        self.assertEqual(revised.second.price, Decimal(139))
        self.assertEqual(revised.second.index, 95)
        self.assertGreater(revised.available_at_ms, original.available_at_ms)
        self.assertIsNone(versions[13])  # Next M5 OPEN 145 crosses the line.
        # Earlier emitted objects never change retroactively.
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
        for hour, (high, low) in enumerate(hours):
            for minute in range(12):
                m5 = make_bar(hour * 12 + minute, high, low, FIVE_MINUTES_MS)
                newly_closed = make_bar(hour, high, low) if minute == 11 else None
                trend, _ = feed.observe_closed(m5, newly_closed)
                observations[hour, minute] = trend

        original = observations[8, 11]
        self.assertIsNotNone(original)
        self.assertEqual(original.side, "BULL")
        self.assertEqual(original.main.second.price, Decimal(106))
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
        # Structural point 4 remains the REAL confirmed H1 pivot at hour 7.
        # A fitted drawing endpoint is not silently reclassified as point 4.
        self.assertEqual(last.pivot_sequence[3].index, 7)
        self.assertEqual(last.target.second.index, 5)
        self.assertEqual(last.target.second.price, Decimal(119))
        for bar in geometry._hourly.bars[last.target.first.index + 1:8]:
            self.assertGreaterEqual(last.target.value_at(bar.start_ms), bar.high)


if __name__ == "__main__":
    unittest.main()
