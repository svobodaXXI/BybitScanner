"""Offline multi-day real-archive provenance and replay integration tests."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import gzip
import unittest
from dataclasses import replace

from research.simulator_v2.trade_range import (
    TradeDayProof, import_local_trade_range, run_cached_trade_range,
)
from research.simulator_v2.trade_archive import SOURCE_ID

D = Decimal
SYMBOL = "GRASSUSDT"
START_DAY = date(2026, 10, 1)
START_MS = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()*1000)
DAY_MS = 86_400_000
END = START_MS + 2*DAY_MS


def fixture_file(directory: Path, day: date) -> Path:
    filename = f"{SYMBOL}{day.isoformat()}.csv.gz"
    path = directory / filename
    start_sec = int(datetime(day.year, day.month, day.day,
                             tzinfo=timezone.utc).timestamp())
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(
            fp, fieldnames=["timestamp", "symbol", "price", "size", "trdMatchID"]
        )
        writer.writeheader()
        for minute in range(1440):
            writer.writerow({
                "timestamp": f"{start_sec + 60*minute}.005",
                "symbol": SYMBOL, "price": "1.234",
                "size": "2", "trdMatchID": f"day{day.isoformat()}_{minute}",
            })
    return path


class TradeRangeTests(unittest.TestCase):
    def files(self, base: Path) -> Path:
        archive = base / "input"
        archive.mkdir()
        for day_offset in (0, 1):
            fixture_file(archive, START_DAY + timedelta(days=day_offset))
        return archive

    def test_two_day_real_trade_format_to_cache_then_replay_offline(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = self.files(base)
            cache = base / "sim-cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache,
                symbol=SYMBOL, start_day=START_DAY, days=2,
                latest_closed_boundary_ms=END,
            )
            self.assertEqual(len(proofs), 2)
            self.assertEqual(len(list(cache.glob("*.json"))), 2)
            self.assertNotEqual(proofs[0].raw_archive_sha256, proofs[1].raw_archive_sha256)
            self.assertTrue(proofs[0].source_id.startswith(SOURCE_ID))
            self.assertIn("source_url", proofs[0].to_payload(symbol=SYMBOL))
            for raw in archive.iterdir():
                raw.unlink()  # Tests that range replay never needs raw files/network.
            options = dict(
                cache_dir=cache, symbol=SYMBOL, proofs=proofs,
                latest_closed_boundary_ms=END, simulation_run_id="month-test",
                initial_balance=D("1000"),
            )
            report = run_cached_trade_range(**options)
            second = run_cached_trade_range(**options)
            self.assertEqual(report, second)
            self.assertEqual(report.minutes, 2880)
            self.assertEqual(report.chunks, 2)
            self.assertEqual(len(report.daily_equity), 2)
            self.assertEqual(report.virtual_fills, 0)
            self.assertEqual(report.total_net_pnl, D("0"))
            self.assertEqual(report.return_percent, D("0"))
            self.assertEqual((report.first_open_ms, report.last_closed_ms), (START_MS, END))
            self.assertEqual(report.chunk_sha256, tuple(x.m1_sha256 for x in proofs))
            self.assertTrue(report.source_id.startswith("BYBIT_PUBLIC_TRADES_RANGE_"))

    def test_invalid_provenance_and_broken_order_refuse_replay(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = self.files(base)
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=base/"sim-cache",
                symbol=SYMBOL, start_day=START_DAY, days=2,
                latest_closed_boundary_ms=END,
            )
            base_kwargs = dict(
                cache_dir=base/"sim-cache", symbol=SYMBOL,
                latest_closed_boundary_ms=END,
                simulation_run_id="bad-manifest", initial_balance=D("1000"),
            )
            for bad in (tuple(reversed(proofs)), proofs[:1]+proofs[:1]):
                with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "reordered|duplicate"):
                    run_cached_trade_range(proofs=bad, **base_kwargs)
            modified = replace(proofs[0], m1_sha256="0"*64)
            with self.assertRaisesRegex(ValueError, "checksum"):
                run_cached_trade_range(proofs=(modified,proofs[1]), **base_kwargs)
            with self.assertRaisesRegex(ValueError, "incomplete future"):
                run_cached_trade_range(
                    proofs=proofs, **{**base_kwargs, "latest_closed_boundary_ms": END-DAY_MS},
                )
            with self.assertRaises(ValueError):
                TradeDayProof(START_DAY, "invalid", "f"*64)

    def test_missing_day_preflight_preserves_unrelated_files(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = base/"input"
            archive.mkdir()
            fixture_file(archive, START_DAY)
            protected = archive/"owner-notes.txt"
            protected.write_text("untouched", encoding="utf-8")
            cache = base/"sim-cache"
            with self.assertRaises(FileNotFoundError):
                import_local_trade_range(
                    archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                    start_day=START_DAY, days=2,
                    latest_closed_boundary_ms=END,
                )
            self.assertFalse(cache.exists())
            self.assertEqual(protected.read_text(encoding="utf-8"), "untouched")

    def test_tampered_cached_day_and_absent_cache_are_not_downloaded(self):
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            archive = self.files(base)
            cache = base/"sim-cache"
            proofs = import_local_trade_range(
                archive_dir=archive, cache_dir=cache, symbol=SYMBOL,
                start_day=START_DAY, days=2, latest_closed_boundary_ms=END,
            )
            kwargs = dict(
                cache_dir=cache, symbol=SYMBOL, proofs=proofs,
                latest_closed_boundary_ms=END, simulation_run_id="tamper",
                initial_balance=D("1000"),
            )
            cached = sorted(cache.glob("*.json"))
            original = cached[0].read_bytes()
            cached[0].write_bytes(original.replace(b'"sha256":"', b'"sha256":"bad'))
            with self.assertRaises(ValueError):
                run_cached_trade_range(**kwargs)
            self.assertNotEqual(cached[0].read_bytes(), original)
            cached[0].unlink()
            with self.assertRaises(FileNotFoundError):
                run_cached_trade_range(**kwargs)


if __name__ == "__main__":
    unittest.main()
