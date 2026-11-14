"""90-day end-to-end offline integration on real project modules.

Uses synthetic OHLCV only. Proves long-run source -> timeline -> virtual fill ->
account -> PnL report without a real exchange, trading account, Robot or VPS.
"""
from decimal import Decimal
import unittest

from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.virtual_exchange import MarketRequest

D = Decimal
DAY_MINUTES = 1440
DAYS = 90
SOURCE = "SYNTHETIC_90D_OFFLINE_FIXTURE"


def fixture_chunks():
    """Stream one day at a time, never hold 129600 M1 candles in memory."""
    for day in range(DAYS):
        start = day * DAY_MINUTES
        bars = []
        for offset in range(DAY_MINUTES):
            idx = start + offset
            closing = D("110") if idx == 2 else D("90") if idx == 3 else D("100")
            bars.append(Candle(
                start_ms=idx * MINUTE_MS,
                interval_ms=MINUTE_MS,
                open=D("100"), high=D("110"), low=D("90"),
                close=closing, volume=D("1"),
            ))
        chunk = tuple(bars)
        yield HistoryChunk(
            symbol="BTCUSDT",
            start_ms=start * MINUTE_MS,
            end_ms=(start + DAY_MINUTES) * MINUTE_MS,
            source_id=SOURCE, candles=chunk,
            sha256=_checksum(_rows(chunk)),
        )


class LongOfflineReplayTests(unittest.TestCase):
    def test_90_days_full_pipeline_two_virtual_fills_and_equity_drawdown(self):
        session = VirtualReplaySession(
            simulation_run_id="replay-90d",
            symbol="BTCUSDT",
            initial_balance=D("1000"),
            taker_fee_rate=D("0"),
        )
        schedule = {
            1 * MINUTE_MS: MarketRequest("enter", "BUY", D("1")),
            5 * MINUTE_MS: MarketRequest("exit", "SELL", D("1")),
        }
        report = run_verified_chunks(session, fixture_chunks(), order_schedule=schedule)
        self.assertEqual(report.minutes, 129600)
        self.assertEqual(report.chunks, DAYS)
        self.assertEqual(len(report.daily_equity), DAYS)
        self.assertEqual(len(report.chunk_sha256), DAYS)
        self.assertEqual(report.virtual_fills, 2)
        self.assertEqual(report.final_position_quantity, D("0"))
        self.assertEqual(report.final_balance, D("1000"))
        self.assertEqual(report.final_equity, D("1000"))
        self.assertEqual(report.total_net_pnl, D("0"))
        self.assertEqual(report.total_fees, D("0"))
        self.assertEqual(report.return_percent, D("0"))
        self.assertGreater(report.max_drawdown_percent, D("1"))
        self.assertLess(report.max_drawdown_percent, D("2"))
        self.assertIsNone(report.pending_order_id)
        self.assertEqual(report.source_id, SOURCE)
        self.assertEqual(session.virtual_time_ms, DAYS * DAY_MINUTES * MINUTE_MS)
        self.assertEqual(
            [fill.price for fill in session.account.fills],
            [D("100"), D("100")],
        )


if __name__ == "__main__":
    unittest.main()
