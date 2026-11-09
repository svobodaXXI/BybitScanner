"""Bybit public linear trade CSV.gz -> strictly attributed derived M1, offline."""
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import gzip
import unittest

from research.simulator_v2.report import run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_archive import parse_local_trade_day, SOURCE_ID
from research.simulator_v2.virtual_exchange import MarketRequest
from research.simulator_v2.history import MINUTE_MS

UTC_DAY = date(2026, 10, 1)
START = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)
END = START + 1440 * MINUTE_MS
D = Decimal


def records(*, missing_minute=None):
    rows = []
    for i in range(1440):
        if i == missing_minute:
            continue
        ts = START // 1000 + i * 60
        rows.append({
            "timestamp": f"{ts}.100", "symbol": "BTCUSDT", "side": "Buy",
            "size": "1", "price": "100", "trdMatchID": f"buy_{i}",
        })
        rows.append({
            "timestamp": f"{ts}.900", "symbol": "BTCUSDT", "side": "Sell",
            "size": "2", "price": "101", "trdMatchID": f"sell_{i}",
        })
    return rows


def write_archive(folder, rows, filename="BTCUSDT2026-10-01.csv.gz"):
    path = Path(folder) / filename
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(
            handle, fieldnames=["timestamp", "symbol", "side", "size", "price", "trdMatchID"]
        )
        w.writeheader()
        w.writerows(rows)
    return path


class TradeArchiveTests(unittest.TestCase):
    def test_complete_day_and_reversed_row_order_same_derived_candles(self):
        with TemporaryDirectory() as td:
            path = write_archive(td, records())
            first, raw_checksum = parse_local_trade_day(
                path, symbol="BTCUSDT", utc_day=UTC_DAY,
                latest_closed_boundary_ms=END,
            )
            self.assertEqual(len(first.candles), 1440)
            self.assertEqual((first.start_ms, first.end_ms), (START, END))
            self.assertEqual(first.source_id, SOURCE_ID)
            self.assertEqual(len(first.sha256), 64)
            self.assertEqual(len(raw_checksum), 64)
            self.assertEqual(
                (first.candles[0].open, first.candles[0].high,
                 first.candles[0].low, first.candles[0].close,
                 first.candles[0].volume),
                (D("100"), D("101"), D("100"), D("101"), D("3")),
            )
            write_archive(td, list(reversed(records())))
            reversed_chunk, reversed_hash = parse_local_trade_day(
                path, symbol="BTCUSDT", utc_day=UTC_DAY,
                latest_closed_boundary_ms=END,
            )
            self.assertEqual(first, reversed_chunk)
            self.assertNotEqual(raw_checksum, reversed_hash)

    def test_missing_minute_rejected_not_forward_filled(self):
        with TemporaryDirectory() as td:
            path = write_archive(td, records(missing_minute=400))
            with self.assertRaisesRegex(ValueError, "missing 1"):
                parse_local_trade_day(
                    path, symbol="BTCUSDT", utc_day=UTC_DAY,
                    latest_closed_boundary_ms=END,
                )

    def test_bad_symbol_malformed_trade_and_future_boundary_fail(self):
        rows = records()
        for modification, message in [
            ({"symbol": "ETHUSDT"}, "foreign"),
            ({"price": "-100"}, "invalid"),
            ({"size": "NaN"}, "invalid"),
            ({"timestamp": str(END // 1000)}, "foreign UTC"),
            ({"trdMatchID": ""}, "identifier"),
        ]:
            with self.subTest(modification=modification), TemporaryDirectory() as td:
                changed = [dict(r) for r in rows]
                changed[0].update(modification)
                path = write_archive(td, changed)
                with self.assertRaisesRegex(ValueError, message):
                    parse_local_trade_day(
                        path, symbol="BTCUSDT", utc_day=UTC_DAY,
                        latest_closed_boundary_ms=END,
                    )
        with TemporaryDirectory() as td:
            path = write_archive(td, rows)
            with self.assertRaisesRegex(ValueError, "unclosed"):
                parse_local_trade_day(
                    path, symbol="BTCUSDT", utc_day=UTC_DAY,
                    latest_closed_boundary_ms=END - MINUTE_MS,
                )

    def test_invalid_path_schema_gzip_and_symlink_rejected(self):
        with TemporaryDirectory() as td:
            path = write_archive(td, records(), filename="BAD.csv.gz")
            with self.assertRaisesRegex(ValueError, "name mismatch"):
                parse_local_trade_day(
                    path, symbol="BTCUSDT", utc_day=UTC_DAY,
                    latest_closed_boundary_ms=END,
                )
            path = Path(td) / "BTCUSDT2026-10-01.csv.gz"
            path.write_bytes(b"not gzip")
            with self.assertRaises((gzip.BadGzipFile, OSError, EOFError)):
                parse_local_trade_day(
                    path, symbol="BTCUSDT", utc_day=UTC_DAY,
                    latest_closed_boundary_ms=END,
                )
            path.unlink()
            ordinary = Path(td) / "owner-file.txt"
            ordinary.write_text("protected", encoding="utf-8")
            try:
                path.symlink_to(ordinary)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unsupported")
            with self.assertRaisesRegex(ValueError, "regular local"):
                parse_local_trade_day(
                    path, symbol="BTCUSDT", utc_day=UTC_DAY,
                    latest_closed_boundary_ms=END,
                )
            self.assertEqual(ordinary.read_text(), "protected")

    def test_trade_derived_candles_run_through_original_virtual_account(self):
        with TemporaryDirectory() as td:
            path = write_archive(td, records())
            market, raw_hash = parse_local_trade_day(
                path, symbol="BTCUSDT", utc_day=UTC_DAY,
                latest_closed_boundary_ms=END,
            )
            session = VirtualReplaySession(
                simulation_run_id="trade_csv_fixture",
                symbol="BTCUSDT", initial_balance=D("1000"),
                taker_fee_rate=D("0"),
            )
            report = run_verified_chunks(session, [market], order_schedule={
                START + MINUTE_MS: MarketRequest("entry", "BUY", D("1")),
                START + 2 * MINUTE_MS: MarketRequest("exit", "SELL", D("1")),
            })
            self.assertEqual(report.minutes, 1440)
            self.assertEqual(report.virtual_fills, 2)
            self.assertEqual(report.source_id, SOURCE_ID)
            self.assertEqual(report.final_balance, D("1000"))
            self.assertEqual(len(report.daily_equity), 1)
            self.assertEqual(len(raw_hash), 64)


if __name__ == "__main__":
    unittest.main()
