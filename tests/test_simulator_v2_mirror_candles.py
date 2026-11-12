"""Local MIRROR source uses only committed historical M1, never Bybit/PAPER."""
from decimal import Decimal
import unittest

from research.historical_market_replay import Candle
from research.simulator_v2.mirror_candles import (
    FIVE_MS, MINUTE_MS, LocalMirrorClosedCandles,
)


def candle(index: int, *, price: str = "100") -> Candle:
    close = Decimal(price)
    return Candle(
        start_ms=index * MINUTE_MS, interval_ms=MINUTE_MS,
        open=close, high=close + Decimal("1"),
        low=close - Decimal("1"), close=close, volume=Decimal("1"),
    )


class LocalMirrorClosedCandlesTests(unittest.TestCase):
    def test_m5_is_hidden_until_five_m1_have_committed_and_fine_m1_is_exact(self):
        source = LocalMirrorClosedCandles("BTCUSDT")
        for i in range(4):
            bar = candle(i, price=str(100 + i))
            source.append_committed(bar, committed_time_ms=bar.end_ms)
            self.assertEqual(source.closed_candles("candidate", "BTCUSDT", 0), ())
        last = candle(4, price="104")
        source.append_committed(last, committed_time_ms=last.end_ms)
        rows = source.closed_candles("candidate", "BTCUSDT", 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["open_time_ms"], rows[0]["close_time_ms"]),
                         (0, FIVE_MS))
        self.assertEqual((rows[0]["open"], rows[0]["close"]), (100.0, 104.0))
        self.assertEqual((rows[0]["low"], rows[0]["high"]), (99.0, 105.0))
        self.assertEqual(len(source.fine_candles("BTCUSDT", rows[0])), 5)
        self.assertTrue(all(row["closed"] is True
                            for row in source.fine_candles("BTCUSDT", rows[0])))
        self.assertEqual(source.closed_candles("candidate", "BTCUSDT", FIVE_MS), ())

    def test_rejects_future_gap_duplicate_and_cross_symbol(self):
        source = LocalMirrorClosedCandles("BTCUSDT")
        first = candle(0)
        with self.assertRaisesRegex(ValueError, "committed"):
            source.append_committed(first, committed_time_ms=2 * MINUTE_MS)
        source.append_committed(first, committed_time_ms=first.end_ms)
        with self.assertRaisesRegex(ValueError, "missing, duplicate"):
            source.append_committed(first, committed_time_ms=first.end_ms)
        with self.assertRaisesRegex(ValueError, "missing, duplicate"):
            source.append_committed(candle(2), committed_time_ms=3 * MINUTE_MS)
        with self.assertRaisesRegex(ValueError, "cross-symbol"):
            source.closed_candles("candidate", "ETHUSDT", 0)
        with self.assertRaisesRegex(ValueError, "beyond committed"):
            source.closed_candles("candidate", "BTCUSDT", FIVE_MS)

    def test_expired_prefix_never_silently_replays_later_candles(self):
        source = LocalMirrorClosedCandles("BTCUSDT", max_minutes=10)
        for i in range(15):
            bar = candle(i)
            source.append_committed(bar, committed_time_ms=bar.end_ms)
        with self.assertRaisesRegex(ValueError, "prefix"):
            source.closed_candles("candidate", "BTCUSDT", 0)
        rows = source.closed_candles("candidate", "BTCUSDT", FIVE_MS)
        self.assertEqual(len(rows), 2)
        with self.assertRaisesRegex(ValueError, "missing or expired"):
            source.fine_candles("BTCUSDT", {
                "open_time_ms": 0, "close_time_ms": FIVE_MS,
            })
        with self.assertRaisesRegex(ValueError, "future"):
            source.fine_candles("BTCUSDT", {
                "open_time_ms": 3 * FIVE_MS, "close_time_ms": 4 * FIVE_MS,
            })

    def test_no_fake_m5_from_partial_start(self):
        source = LocalMirrorClosedCandles("BTCUSDT")
        for i in range(2, 5):
            bar = candle(i)
            source.append_committed(bar, committed_time_ms=bar.end_ms)
        self.assertEqual(source.closed_candles("candidate", "BTCUSDT", 0), ())
        for i in range(5, 10):
            bar = candle(i)
            source.append_committed(bar, committed_time_ms=bar.end_ms)
        with self.assertRaisesRegex(ValueError, "prefix"):
            source.closed_candles("candidate", "BTCUSDT", 0)
        self.assertEqual(len(source.closed_candles("candidate", "BTCUSDT", FIVE_MS)), 1)
