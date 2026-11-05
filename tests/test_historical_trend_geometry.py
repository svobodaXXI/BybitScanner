"""Causal geometry checks: no back-painted pivots/lines or invented entries."""
from decimal import Decimal
import unittest

from research.causal_trend_geometry import (
    CausalGeometryFeed, ConfirmedPivot, ConfirmedSwingStream,
    last_correction_reference, main_line_contact, recent_hourly_trend,
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
        # A wick beyond the interpolated slope must invalidate the candidate.
        pierced = list(bars)
        pierced[5] = make_bar(offset+5, 109, 100, FIVE_MINUTES_MS)
        self.assertIsNone(last_correction_reference(
            hourly=trend, five_minute_pivots=feed.pivots,
            five_minute_bars=tuple(pierced),
        ))

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
        self.assertEqual(last.pivot_sequence[3].index, 7)


if __name__ == "__main__":
    unittest.main()
