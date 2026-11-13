"""Historical Bybit L2 is a strict data source, not an OHLC fill substitute."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.simulator_v2.historical_orderbook import (
    HistoricalBybitOrderBook, iter_pinned_orderbook,
)


def frame(*, typ="snapshot", at=1000, u=10, seq=20, bids=None, asks=None):
    return {
        "topic": "orderbook.50.ICNTUSDT", "type": typ,
        "ts": at, "cts": at - 1,
        "data": {
            "s": "ICNTUSDT", "u": u, "seq": seq,
            "b": [["0.2900", "100"]] if bids is None else bids,
            "a": [["0.2902", "80"]] if asks is None else asks,
        },
    }


class HistoricalBookTests(unittest.TestCase):
    def test_snapshot_and_atomic_delta_reconstruct_actual_levels(self):
        book = HistoricalBybitOrderBook(symbol="ICNTUSDT")
        first = book.apply(frame())
        self.assertEqual(first.best_bid, (Decimal("0.2900"), Decimal("100")))
        self.assertEqual(first.best_ask, (Decimal("0.2902"), Decimal("80")))
        updated = book.apply(frame(
            typ="delta", at=1020, u=11, seq=21,
            bids=[["0.2900", "0"], ["0.2901", "20"]],
            asks=[["0.2902", "45"]],
        ))
        self.assertEqual(updated.best_bid, (Decimal("0.2901"), Decimal("20")))
        self.assertEqual(updated.best_ask, (Decimal("0.2902"), Decimal("45")))
        with self.assertRaisesRegex(ValueError, "crossed"):
            book.apply(frame(
                typ="delta", at=1030, u=12, seq=22,
                bids=[["0.2903", "10"]], asks=[],
            ))
        self.assertEqual(book.apply(frame(
            typ="delta", at=1040, u=12, seq=22, bids=[], asks=[],
        )).best_bid, updated.best_bid)

    def test_missing_snapshot_and_bad_sequence_fail_closed(self):
        book = HistoricalBybitOrderBook(symbol="ICNTUSDT")
        with self.assertRaisesRegex(ValueError, "without initial snapshot"):
            book.apply(frame(typ="delta"))
        book.apply(frame())
        with self.assertRaisesRegex(ValueError, "repeated"):
            book.apply(frame(typ="delta", at=1010, u=10, seq=21))
        with self.assertRaisesRegex(ValueError, "topic"):
            book.apply({**frame(at=1010, u=11, seq=21), "topic": "orderbook.50.ETHUSDT"})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            book.apply(frame(
                typ="delta", at=1010, u=11, seq=21,
                bids=[["0.2901", "1"], ["0.2901", "2"]], asks=[],
            ))
        book.apply(frame(typ="snapshot", at=1050, u=1, seq=25))
        self.assertEqual(book.apply(frame(
            typ="delta", at=1060, u=2, seq=26, bids=[], asks=[],
        )).update_id, 2)

    def test_pinned_jsonl_needs_snapshot_at_or_before_start(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "orderbook.jsonl"
            def write(events):
                payload = "".join(json.dumps(item) + "\n" for item in events).encode()
                path.write_bytes(payload)
                return hashlib.sha256(payload).hexdigest()
            proof = write([
                frame(at=1000),
                frame(typ="delta", at=1020, u=11, seq=21, bids=[], asks=[]),
            ])
            states = list(iter_pinned_orderbook(
                path, symbol="ICNTUSDT", depth=50, sha256=proof,
                start_ms=1000, end_exclusive_ms=1100,
            ))
            self.assertEqual([state.available_at_ms for state in states], [1000, 1020])
            with self.assertRaisesRegex(ValueError, "SHA mismatch"):
                list(iter_pinned_orderbook(
                    path, symbol="ICNTUSDT", depth=50, sha256="0" * 64,
                    start_ms=1000, end_exclusive_ms=1100,
                ))
            proof = write([
                frame(at=1005),
                frame(typ="delta", at=1020, u=11, seq=21, bids=[], asks=[]),
            ])
            with self.assertRaisesRegex(ValueError, "no at-or-before-window"):
                list(iter_pinned_orderbook(
                    path, symbol="ICNTUSDT", depth=50, sha256=proof,
                    start_ms=1000, end_exclusive_ms=1100,
                ))

    def test_market_tape_is_not_book_data(self):
        book = HistoricalBybitOrderBook(symbol="ICNTUSDT")
        with self.assertRaisesRegex(ValueError, "topic"):
            book.apply({
                "timestamp": "1794297780.0", "symbol": "ICNTUSDT",
                "side": "Buy", "price": "0.2898", "size": "1",
            })


if __name__ == "__main__":
    unittest.main()
