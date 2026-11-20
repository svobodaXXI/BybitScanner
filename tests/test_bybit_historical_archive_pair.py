"""Offline-only Bybit archive pair quality, unknown gaps and nontrading fence."""
from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from tools.inspect_bybit_historical_pair import (
    ArchiveEvidenceError, inspect_archive_pair,
)


class HistoricalArchivePairTests(unittest.TestCase):
    DAY = "2026-10-01"
    START = 1790812800000

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.trades = self.root / f"SOLUSDT{self.DAY}.csv.gz"
        self.book = self.root / f"{self.DAY}_SOLUSDT_ob200.data.zip"
        self.trade_rows = [
            {"timestamp": str(self.START / 1000 + 0.010),
             "symbol": "SOLUSDT", "side": "Buy", "price": "200",
             "size": "1", "trdMatchID": "id-a"},
            {"timestamp": str(self.START + 40),
             "symbol": "SOLUSDT", "side": "Sell", "price": "199",
             "size": "2", "trdMatchID": "id-b"},
        ]
        self.book_events = [
            self.event("snapshot", self.START + 15, 8, 18),
            self.event("delta", self.START + 40, 9, 19,
                       bids=[["199", "0"]]),
        ]
        self.write_files()

    def event(self, kind, stamp, u, seq, *, bids=None):
        return {
            "topic": "orderbook.200.SOLUSDT", "type": kind, "ts": stamp,
            "cts": stamp, "data": {
                "s": "SOLUSDT", "u": u, "seq": seq,
                "b": bids if bids is not None else [["199", "8"]],
                "a": [["200", "7"]],
            },
        }

    def write_files(self):
        with gzip.open(self.trades, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=("timestamp", "symbol", "side",
                                    "price", "size", "trdMatchID"),
            )
            writer.writeheader()
            writer.writerows(self.trade_rows)
        with ZipFile(self.book, "w") as archive:
            archive.writestr(
                "2026-10-01_SOLUSDT_ob200.data",
                "\n".join(json.dumps(e) for e in self.book_events) + "\n",
            )

    def inspect(self, **options):
        return inspect_archive_pair(
            "SOLUSDT", self.DAY, self.trades, self.book,
            start_ms=self.START, end_ms=self.START + 60_000,
            **options,
        )

    def test_pair_is_visible_but_never_a_live_source_certificate(self):
        result = self.inspect()
        self.assertTrue(result.scan_complete)
        self.assertEqual(result.trade_rows, 2)
        self.assertEqual(result.orderbook_rows, 2)
        self.assertEqual(result.trades_in_window, 2)
        self.assertEqual(result.book_events_in_window, 2)
        self.assertEqual(result.snapshots_seen_before_window_end, 1)
        self.assertEqual(result.book_delete_updates_in_window, 1)
        self.assertFalse(result.exchange_receipt_time_proven)
        self.assertFalse(result.orderbook_execution_attribution_proven)
        self.assertFalse(result.source_complete_for_live_entry)
        self.assertFalse(result.trading_authorized)

    def test_wrong_symbol_filename_fails_without_reading_unrelated_path(self):
        with self.assertRaises(ArchiveEvidenceError):
            inspect_archive_pair(
                "BTCUSDT", self.DAY, self.trades, self.book,
                start_ms=self.START, end_ms=self.START + 60_000,
            )

    def test_duplicate_trade_identity_is_blocked(self):
        self.trade_rows[-1]["trdMatchID"] = "id-a"
        self.write_files()
        with self.assertRaisesRegex(ArchiveEvidenceError, "duplicate"):
            self.inspect()

    def test_book_delta_before_snapshot_is_blocked(self):
        self.book_events.pop(0)
        self.write_files()
        with self.assertRaisesRegex(ArchiveEvidenceError, "snapshot"):
            self.inspect()

    def test_u1_restart_resnapshot_rebases_book_sequence(self):
        # Bybit may send an update with u=1 and a lower seq after restart.
        # Even when labelled delta this resets the ordered book lineage.
        self.book_events.append(
            self.event("delta", self.START + 50, 1, 1)
        )
        self.book_events.append(
            self.event("delta", self.START + 60, 2, 2)
        )
        self.write_files()
        result = self.inspect()
        self.assertTrue(result.scan_complete)
        self.assertEqual(result.snapshots_seen_before_window_end, 2)
        self.assertEqual(result.book_events_in_window, 4)
        self.assertFalse(result.trading_authorized)

    def test_book_sequence_regression_is_blocked(self):
        self.book_events[-1]["data"]["seq"] = 1
        self.write_files()
        with self.assertRaisesRegex(ArchiveEvidenceError, "ordered"):
            self.inspect()

    def test_partial_archive_scan_is_blocked(self):
        with self.assertRaisesRegex(ArchiveEvidenceError, "scan limit"):
            self.inspect(max_records=1)

    def test_l2_malformed_price_or_cross_day_fails_closed(self):
        self.book_events[-1]["data"]["b"] = [["199", "-1"]]
        self.write_files()
        with self.assertRaises(ArchiveEvidenceError):
            self.inspect()
        self.book_events[-1]["data"]["b"] = [["199", "0"]]
        self.book_events[-1]["cts"] += 86_400_000
        self.write_files()
        with self.assertRaisesRegex(ArchiveEvidenceError, "date"):
            self.inspect()

    def test_m5_only_interval_cannot_fake_M1_continuity(self):
        with self.assertRaisesRegex(ArchiveEvidenceError, "within one UTC day"):
            inspect_archive_pair(
                "SOLUSDT", self.DAY, self.trades, self.book,
                start_ms=self.START, end_ms=self.START + 86_400_000 + 1,
            )
        with self.assertRaisesRegex(ArchiveEvidenceError, "<= 1h"):
            inspect_archive_pair(
                "SOLUSDT", self.DAY, self.trades, self.book,
                start_ms=self.START, end_ms=self.START + 3_600_001,
            )


if __name__ == "__main__":
    unittest.main()
