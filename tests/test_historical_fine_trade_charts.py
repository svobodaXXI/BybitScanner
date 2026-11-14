"""Original public prints -> truthful local 15s/M1, no Robot or PAPER IO."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import gzip
import unittest

from research.local_replay_viewer.fine_trades import aggregate_owner_trade_bars


START = int(datetime(2026, 11, 10, 8, tzinfo=timezone.utc).timestamp() * 1000)
DAY = "2026-11-10"
SYMBOL = "ICNTUSDT"
GZ = f"{SYMBOL}{DAY}.csv.gz"
ZIP = f"{SYMBOL}_{DAY}_sources.zip"


class FineTradesTests(unittest.TestCase):
    def archive(self) -> bytes:
        header = "timestamp,symbol,price,size,trdMatchID\n"
        def trade(delta: int, price: str, size: str, identity: str):
            return f"{(START + delta) / 1000:.3f},{SYMBOL},{price},{size},{identity}\n"
        # Deliberately unsorted. Same-ms order follows stable trade ID.
        records = [
            trade(75_000, "103", "1", "g"),
            trade(14_000, "100", "1", "b"),
            trade(0, "99", "1", "a"),
            trade(15_000, "102", "3", "e"),
            trade(15_000, "101", "2", "d"),
            trade(60_000, "104", "1", "f"),
        ]
        return gzip.compress((header + "".join(records)).encode("utf-8"), mtime=0)

    def test_original_print_order_and_no_fabricated_empty_15s(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/GZ
            path.write_bytes(self.archive())
            result = aggregate_owner_trade_bars(path, filename=GZ, symbol=SYMBOL,
                start_ms=START, end_ms=START + 120_000)
        self.assertEqual(result["source"], "BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE")
        self.assertEqual(result["trades_scanned"], 6)
        self.assertEqual(len(result["m1"]), 2)
        self.assertEqual(len(result["s15"]), 3)
        self.assertEqual(result["missing_m1"], 0)
        self.assertEqual(result["missing_15s"], 5)
        self.assertEqual(result["m1"][0]["open"], 99)
        self.assertEqual(result["m1"][0]["close"], 102)
        self.assertEqual(result["m1"][0]["volume"], 7)
        self.assertEqual(result["s15"][1]["open"], 101)
        self.assertEqual(result["s15"][1]["close"], 102)
        self.assertEqual(result["pinned_original_icnt"], False)
        self.assertTrue(result["l2_executions_unchanged"])

    def test_zip_container_uses_only_exact_daily_gzip(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/ZIP
            with ZipFile(path,"w") as z:
                z.writestr(GZ,self.archive())
                z.writestr("unused.txt","no archive access")
            result = aggregate_owner_trade_bars(path,filename=ZIP,symbol=SYMBOL,
                start_ms=START,end_ms=START+120_000)
        self.assertEqual(len(result["s15"]),3)

    def test_wrong_provenance_day_or_period_does_not_backfill(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/GZ
            path.write_bytes(self.archive())
            with self.assertRaises(ValueError):
                aggregate_owner_trade_bars(path,filename=GZ,symbol="BTCUSDT",
                    start_ms=START,end_ms=START+60_000)
            with self.assertRaises(ValueError):
                aggregate_owner_trade_bars(path,filename=GZ,symbol=SYMBOL,
                    start_ms=START,end_ms=START+6*3_600_000+60_000)
            with self.assertRaises(ValueError):
                aggregate_owner_trade_bars(path,filename=GZ,symbol=SYMBOL,
                    start_ms=START,end_ms=START+86_400_000+60_000)


if __name__ == "__main__":
    unittest.main()
