"""Offline tests of automatic pinned M1 day preparation."""
from datetime import date, datetime, timezone, timedelta
from tempfile import TemporaryDirectory
from pathlib import Path
import csv
import gzip
import unittest

from research.local_replay_viewer.m1_preparation import (
    prepare_m1_manifest, required_trade_days,
)
from research.simulator_v2.trade_range import TradeDayProof
from research.simulator_v2.trade_archive import import_trade_day_into_cache

DAY = 86_400_000
MINUTE = 60_000
FIRST = date(2026, 10, 1)
START = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp() * 1000)
SYMBOL = "GRASSUSDT"


def write_day(path, *, symbol, utc_day, byte_limit, count=1440):
    stamp = int(datetime(utc_day.year, utc_day.month, utc_day.day,
                         tzinfo=timezone.utc).timestamp())
    with gzip.open(path, "wt", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["timestamp", "symbol", "price", "size", "trdMatchID"])
        for i in range(count):
            writer.writerow([stamp + 60*i, symbol, "1.25", "2", str(i)])
    return path.stat().st_size


class PreparationTests(unittest.TestCase):
    def args(self, folder):
        return dict(data_dir=folder, symbol=SYMBOL, start_ms=START+DAY,
                    end_inclusive_ms=START+2*DAY-MINUTE, window_bars=120,
                    latest_closed_boundary_ms=START+4*DAY)

    def test_warmup_and_exact_day_window(self):
        self.assertEqual(required_trade_days(start_ms=START+DAY,
            end_inclusive_ms=START+2*DAY-MINUTE, window_bars=120,
            latest_closed_boundary_ms=START+2*DAY),
            (FIRST, FIRST+timedelta(days=1)))
        with self.assertRaisesRegex(ValueError, "UTC"):
            required_trade_days(start_ms=START+DAY, end_inclusive_ms=START+2*DAY,
                window_bars=120, latest_closed_boundary_ms=START+2*DAY+MINUTE)

    def test_empty_partial_and_repeat_use_only_missing_days(self):
        calls = []
        def fetch(path, **kwargs):
            calls.append(kwargs["utc_day"])
            return write_day(path, **kwargs)
        with TemporaryDirectory() as temp:
            args = self.args(Path(temp))
            first = prepare_m1_manifest(**args, fetch_day=fetch)
            self.assertEqual(calls, [FIRST, FIRST+timedelta(days=1)])
            self.assertEqual(first["days"], 2)
            calls.clear()
            self.assertEqual(prepare_m1_manifest(**args, fetch_day=fetch), first)
            self.assertEqual(calls, [])
            extended = prepare_m1_manifest(
                **{**args, "end_inclusive_ms": START+3*DAY-MINUTE}, fetch_day=fetch)
            self.assertEqual(calls, [FIRST+timedelta(days=2)])
            self.assertEqual(extended["day_provenance"][:2], first["day_provenance"])

    def test_existing_imported_manifest_days_are_reused(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / f"{SYMBOL}{FIRST.isoformat()}.csv.gz"
            write_day(raw, symbol=SYMBOL, utc_day=FIRST, byte_limit=128_000_000)
            chunk, digest = import_trade_day_into_cache(raw, cache_dir=root/"m1-cache",
                symbol=SYMBOL, utc_day=FIRST, latest_closed_boundary_ms=START+4*DAY)
            raw.unlink()
            calls = []
            def fetch(path, **kwargs):
                calls.append(kwargs["utc_day"])
                return write_day(path, **kwargs)
            manifest = prepare_m1_manifest(**self.args(root),
                legacy_proofs=(TradeDayProof(FIRST, digest, chunk.sha256),), fetch_day=fetch)
            self.assertEqual(calls, [FIRST+timedelta(days=1)])
            self.assertEqual(manifest["day_provenance"][0]["raw_archive_sha256"], digest)

    def test_failed_day_preserves_previous_verified_day_without_claiming_range(self):
        with TemporaryDirectory() as temp:
            args = self.args(Path(temp))
            def broken(path, **kwargs):
                return write_day(path, **kwargs,
                    count=1440 if kwargs["utc_day"] == FIRST else 1439)
            with self.assertRaisesRegex(ValueError, "missing 1 trade-derived M1"):
                prepare_m1_manifest(**args, fetch_day=broken)
            calls = []
            def fetch(path, **kwargs):
                calls.append(kwargs["utc_day"])
                return write_day(path, **kwargs)
            result = prepare_m1_manifest(**args, fetch_day=fetch)
            self.assertEqual(calls, [FIRST+timedelta(days=1)])
            self.assertEqual(result["days"], 2)

    def test_corrupt_cached_day_fails_closed_without_refetch(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            args = self.args(root)
            prepare_m1_manifest(**args, fetch_day=write_day)
            next((root/"m1-cache").glob("*.json")).write_text("{}")
            with self.assertRaises(ValueError):
                prepare_m1_manifest(**args, fetch_day=lambda *a, **k: self.fail("corrupt cache must not be overwritten"))
