"""Offline cross-channel preflight fixtures, without simulation or PAPER."""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from research.simulator_v2.audit_l2_archive import DAY_BEGIN_MS
from research.simulator_v2.audit_l2_trade_join import inspect


def _sources(td: Path) -> tuple[Path, str, Path, str]:
    l2 = td / "book.data.zip"
    ticks = td / "Impulse_ICNT_ADA_2026-11-10.zip"
    events = []
    for n, at in enumerate((1490, 2000, 3000)):
        events.append({
            "topic": "orderbook.200.ICNTUSDT",
            "type": "snapshot" if n == 0 else "delta",
            "ts": DAY_BEGIN_MS + at, "cts": DAY_BEGIN_MS + at - 5,
            "data": {
                "s": "ICNTUSDT", "u": 100 + n, "seq": 200 + n,
                "b": [["0.29", "20"]], "a": [["0.30", "10"]],
            },
        })
    with ZipFile(l2, "w", compression=ZIP_DEFLATED) as z:
        z.writestr("2026-11-10_ICNTUSDT_ob200.data",
                   "".join(json.dumps(x) + "\n" for x in events))
    csv_data = (
        "timestamp,symbol,side,size,price,trdMatchID\n"
        f"{DAY_BEGIN_MS/1000 + 1.0127:.4f},ICNTUSDT,Sell,1,0.29,id1\n"
        f"{DAY_BEGIN_MS/1000 + 1.4900:.4f},ICNTUSDT,Buy,1,0.29,id2\n"
        f"{DAY_BEGIN_MS/1000 + 2.7500:.4f},ICNTUSDT,Sell,1,0.29,id3\n"
    ).encode()
    original = gzip.compress(csv_data)
    with ZipFile(ticks, "w", compression=ZIP_DEFLATED) as z:
        z.writestr("ICNTUSDT2026-11-10.csv.gz", original)
        z.writestr("ADAUSDT2026-11-10.csv.gz", b"unrelated")
        z.writestr("source_manifest.json", b"{}")
    return (
        l2, hashlib.sha256(l2.read_bytes()).hexdigest(),
        ticks, hashlib.sha256(original).hexdigest(),
    )


class L2TradeCrossChannelTests(unittest.TestCase):
    def test_original_multi_member_bundle_and_equal_timestamp(self):
        with TemporaryDirectory() as tmp:
            l2, l2_sha, trades, trade_sha = _sources(Path(tmp))
            report = inspect(
                l2_zip=l2, l2_sha256=l2_sha,
                trade_source=trades, trade_sha256=trade_sha,
                expected_books=3, expected_trades=3,
            )
            self.assertEqual(report["public_trades"], 3)
            self.assertEqual(report["same_ms_trade_vs_book_ts"]["millisecond_buckets"], 1)
            self.assertEqual(report["book_asof_trade_ts"]["trades_before_first_book"], 1)
            self.assertEqual(report["book_asof_trade_ts"]["trades_book_older_than_250ms"], 1)
            self.assertEqual(report["virtual_fills"], "NOT_EXECUTED")
            self.assertEqual(report["virtual_pnl"], "NOT_COMPUTED")

    def test_wrong_trade_sha_and_l2_sha_fail_closed(self):
        with TemporaryDirectory() as tmp:
            l2, l2_sha, trades, trade_sha = _sources(Path(tmp))
            with self.assertRaisesRegex(ValueError, "inner trade gzip SHA-256 mismatch"):
                inspect(
                    l2_zip=l2, l2_sha256=l2_sha,
                    trade_source=trades, trade_sha256="0" * 64,
                    expected_books=3, expected_trades=3,
                )
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                inspect(
                    l2_zip=l2, l2_sha256="0" * 64,
                    trade_source=trades, trade_sha256=trade_sha,
                    expected_books=3, expected_trades=3,
                )


if __name__ == "__main__":
    unittest.main()
