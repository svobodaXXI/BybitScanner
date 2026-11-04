"""Independent seed checks, crossing chronology and 4h no-look-ahead DMI tests."""
from decimal import Decimal
import unittest

from research.historical_market_replay import Candle
from research.historical_candle_feed import (
    FIVE_MINUTES_MS, FOUR_HOURS_MS, replay_with_closed_context,
)
from research.wilder_dmi import WilderDmi


def bar(i: int, high: int, interval: int = FIVE_MINUTES_MS) -> Candle:
    return Candle(i * interval, interval, high - 1, high, high - 2, high - 1, 10)


class WilderDmiTests(unittest.TestCase):
    def test_wilder_seed_and_constant_uptrend_are_numerically_grounded(self):
        stream = WilderDmi(timeframe_ms=FIVE_MINUTES_MS, di_length=3, adx_smoothing=3)
        records = [stream.observe_closed(bar(i, 100 + 2 * i)) for i in range(9)]
        self.assertIsNone(records[2].plus_di)
        self.assertLess(abs(records[3].plus_di - Decimal(72)), Decimal("1e-20"))
        self.assertEqual(records[3].minus_di, Decimal(0))
        self.assertIsNone(records[4].adx)
        self.assertEqual(records[5].adx, Decimal(100))
        self.assertTrue(records[5].ready)
        self.assertEqual(records[5].crossings, ())
        self.assertEqual(records[8].adx, Decimal(100))

    def test_standard_14_14_never_uses_unfinished_warmup(self):
        stream = WilderDmi(timeframe_ms=FOUR_HOURS_MS)
        data = [stream.observe_closed(bar(i, 100 + 2*i, FOUR_HOURS_MS)) for i in range(29)]
        self.assertTrue(all(x.plus_di is None for x in data[:14]))
        self.assertIsNotNone(data[14].plus_di)
        self.assertTrue(all(x.adx is None for x in data[:27]))
        self.assertEqual(data[27].adx, Decimal(100))
        self.assertEqual(data[27].time_ms, 28*FOUR_HOURS_MS)

    def test_directional_crossings_are_separate_and_causal(self):
        def observed(all_highs):
            stream = WilderDmi(timeframe_ms=FIVE_MINUTES_MS, di_length=3, adx_smoothing=3)
            return [stream.observe_closed(bar(i, h)) for i, h in enumerate(all_highs)]

        highs = [100 + 2*i for i in range(12)] + [122 - 4*i for i in range(10)]
        final = observed(highs)
        events = [x for snap in final for x in snap.crossings]
        self.assertTrue(any(
            e.side == "MINUS" and e.direction == "UP" and e.comparator == "OPPOSITE_DI"
            for e in events
        ), events)
        self.assertTrue(any(
            e.side == "PLUS" and e.direction == "DOWN" and e.comparator == "LEVEL_20"
            for e in events
        ), events)
        prefix = observed(highs[:15])
        self.assertEqual(prefix, final[:15])  # Later trend cannot rewrite an earlier crossing.
        self.assertTrue(all(e.time_ms == snap.time_ms for snap in final for e in snap.crossings))

    def test_zero_direction_and_missing_4h_bar_fail_closed(self):
        zero = WilderDmi(timeframe_ms=FOUR_HOURS_MS, di_length=3, adx_smoothing=3)
        data = [
            zero.observe_closed(Candle(i*FOUR_HOURS_MS, FOUR_HOURS_MS, 100, 100, 100, 100, 0))
            for i in range(8)
        ]
        self.assertEqual(data[-1].plus_di, 0)
        self.assertEqual(data[-1].minus_di, 0)
        self.assertEqual(data[-1].adx, 0)
        self.assertEqual(data[-1].crossings, ())
        with self.assertRaisesRegex(ValueError, "missing|duplicate|overlapping"):
            zero.observe_closed(Candle(9*FOUR_HOURS_MS, FOUR_HOURS_MS, 100, 100, 100, 100, 0))

    def test_replay_exposes_adx_only_after_fully_closed_4h_candle(self):
        observed = []

        def observe(ctx):
            i = len(ctx.five_minute.closed_history) - 1
            if i in (46, 47, 48, 1342, 1343):
                observed.append((
                    i, ctx.five_minute.signal_time_ms,
                    None if ctx.last_closed_dmi_4h is None else ctx.last_closed_dmi_4h.time_ms,
                    None if ctx.last_closed_dmi_4h is None else ctx.last_closed_dmi_4h.adx,
                    ctx.newly_closed_4h is not None,
                ))
            return None

        bars = [
            Candle(i*FIVE_MINUTES_MS, FIVE_MINUTES_MS,
                   Decimal(100)+Decimal(i)/100,
                   Decimal(101)+Decimal(i)/100,
                   Decimal(99)+Decimal(i)/100,
                   Decimal(100)+Decimal(i)/100, 100)
            for i in range(28*48)
        ]
        result = replay_with_closed_context(
            simulation_run_id="causal-adx-4h",
            candles=bars, on_closed_context=observe,
        )
        self.assertEqual(result.trades, ())
        self.assertEqual(observed[0][2], None)
        self.assertEqual(observed[1][2], FOUR_HOURS_MS)
        self.assertEqual(observed[2][2], FOUR_HOURS_MS)
        self.assertIsNone(observed[3][3])  # 27th 4h bar only; ADX warmup incomplete.
        self.assertEqual(observed[4][2], 28*FOUR_HOURS_MS)
        self.assertIsNotNone(observed[4][3])
        self.assertTrue(observed[4][4])


if __name__ == "__main__":
    unittest.main()
