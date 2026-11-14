"""Offline-only Simulator 2.0 scenario reports, not claims about Robot strategy."""
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import run_cached_archive, run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.virtual_exchange import MarketRequest

D = Decimal
STEP = MINUTE_MS


def bar(i, opening="100", closing="100"):
    return Candle(
        start_ms=i * STEP, interval_ms=STEP,
        open=D(opening), high=max(D(opening), D(closing), D("110")),
        low=min(D(opening), D(closing), D("90")), close=D(closing),
        volume=D("2"),
    )


def chunk(candles, source="FIXTURE_REPORT"):
    candles = tuple(candles)
    return HistoryChunk(
        "BTCUSDT", candles[0].start_ms, candles[-1].end_ms,
        source, candles, _checksum(_rows(candles)),
    )


def session(run_id="report"):
    return VirtualReplaySession(
        simulation_run_id=run_id, symbol="BTCUSDT",
        initial_balance=D("1000"), taker_fee_rate=D("0.001"),
    )


class ReplayReportTests(unittest.TestCase):
    def test_three_minute_trade_sequence_total_net_return_and_drawdown(self):
        s = session()
        bars = [bar(0), bar(1, "100", "110"), bar(2, "105", "100")]
        schedule = {
            STEP: MarketRequest("entry", "BUY", D("1")),
            2*STEP: MarketRequest("exit", "SELL", D("1")),
        }
        result = run_verified_chunks(s, (chunk(bars[:1]), chunk(bars[1:])),
                                     order_schedule=schedule)
        self.assertEqual(result.namespace, "SIMULATION")
        self.assertEqual(result.scenario_type, "EXPLICIT_TEST_ORDERS_NOT_STRATEGY")
        self.assertEqual((result.minutes, result.chunks, result.virtual_fills), (3, 2, 2))
        self.assertEqual(result.final_balance, D("1004.795"))
        self.assertEqual(result.final_equity, D("1004.795"))
        self.assertEqual(result.realized_net_pnl, D("4.795"))
        self.assertEqual(result.total_fees, D("0.205"))
        self.assertEqual(result.return_percent, D("0.4795"))
        self.assertEqual(result.final_position_quantity, D("0"))
        self.assertIsNone(result.pending_order_id)
        self.assertGreater(result.max_drawdown_percent, 0)
        self.assertLess(result.max_drawdown_percent, D("1"))
        self.assertEqual(result.last_closed_ms, 3*STEP)
        self.assertEqual(len(result.daily_equity), 1)
        payload = result.to_payload()
        self.assertEqual(payload["total_net_pnl"], "4.795")
        self.assertEqual(payload["virtual_fills"], 2)
        self.assertEqual(payload["chunk_sha256"], list(result.chunk_sha256))

    def test_without_orders_does_not_invent_trades_or_profit(self):
        result = run_verified_chunks(session(), [chunk([bar(0), bar(1)])])
        self.assertEqual(result.virtual_fills, 0)
        self.assertEqual(result.total_net_pnl, D("0"))
        self.assertEqual(result.return_percent, D("0"))
        self.assertEqual(result.max_drawdown_percent, D("0"))
        self.assertEqual(result.daily_equity[0].equity, D("1000"))

    def test_utc_daily_equity_boundaries(self):
        bars = [bar(1439), bar(1440), bar(1441)]
        result = run_verified_chunks(session(), [chunk(bars)])
        self.assertEqual([day.utc_date for day in result.daily_equity],
                         ["1970-01-01", "1970-01-02"])
        self.assertEqual([day.last_closed_ms for day in result.daily_equity],
                         [1440*STEP, 1442*STEP])

    def test_corrupt_missing_reordered_or_foreign_chunks_fail(self):
        correct = chunk([bar(0), bar(1)])
        altered = HistoryChunk(
            correct.symbol, correct.start_ms, correct.end_ms, correct.source_id,
            correct.candles, "f"*64,
        )
        with self.assertRaisesRegex(ValueError, "checksum"):
            run_verified_chunks(session(), [altered])
        with self.assertRaisesRegex(ValueError, "gap"):
            run_verified_chunks(session(), [chunk([bar(0)]), chunk([bar(2)])])
        with self.assertRaisesRegex(ValueError, "source"):
            run_verified_chunks(session(), [chunk([bar(0)]), chunk([bar(1)], "OTHER")])
        with self.assertRaisesRegex(ValueError, "duration"):
            run_verified_chunks(session(), [chunk([bar(0), bar(2)])])
        with self.assertRaises(ValueError):
            run_verified_chunks(session(), [])

    def test_schedule_cannot_reference_absent_minute_or_reuse_session(self):
        s = session()
        with self.assertRaisesRegex(ValueError, "outside"):
            run_verified_chunks(s, [chunk([bar(0)])], order_schedule={
                7*STEP: MarketRequest("x", "BUY", D("1")),
            })
        with self.assertRaisesRegex(ValueError, "new, unused"):
            run_verified_chunks(s, [chunk([bar(0)])])

    def test_ending_with_pending_order_is_explicitly_reported(self):
        result = run_verified_chunks(session(), [chunk([bar(0)])],
                                     order_schedule={
                                         STEP: MarketRequest("pending", "BUY", D("1"))
                                     })
        self.assertEqual(result.pending_order_id, "pending")
        self.assertEqual(result.virtual_fills, 0)

    def test_offline_entrypoint_never_downloads_missing_cache(self):
        with TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                run_cached_archive(
                    cache_dir=Path(td), simulation_run_id="no-network",
                    symbol="BTCUSDT", initial_balance=D("1000"),
                    start_ms=0, end_ms=STEP, latest_closed_boundary_ms=STEP,
                    chunk_minutes=1, source_id="FIXTURE_REPORT",
                )


if __name__ == "__main__":
    unittest.main()
