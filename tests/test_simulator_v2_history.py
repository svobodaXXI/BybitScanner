"""Simulator 2.0 M1 history: offline mock-only, no Bybit calls or accounts."""
import json
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from research.simulator_v2.history import (
    fetch_public_m1_klines, iter_closed_m1_chunks, MINUTE_MS,
)

STEP = MINUTE_MS


def row(i, *, price="100"):
    return {
        "time": str(i * STEP), "open": price, "high": "101",
        "low": "99", "close": "100", "volume": "4",
    }


def closed_history(start, end, *, page_limit=None):
    """Simulated Bybit newest-first public OHLCV, including older candles."""
    records = [row(i) for i in range(start, end)]

    def fetch(symbol, interval, limit, *, end_ms):
        assert symbol == "BTCUSDT"
        assert interval == "1"
        return [r for r in reversed(records) if int(r["time"]) <= end_ms][:
            min(limit, page_limit or limit)
        ]
    return fetch


class M1HistoryTests(unittest.TestCase):
    def kwargs(self, **overrides):
        result = dict(
            symbol="BTCUSDT", start_ms=0, end_ms=11 * STEP,
            latest_closed_boundary_ms=11 * STEP,
            page_limit=3, chunk_minutes=4,
            source_id="FIXTURE_M1",
            fetch_candles=closed_history(0, 11),
        )
        result.update(overrides)
        return result

    def test_bounded_pages_contiguous_chronological_checksums(self):
        chunks = tuple(iter_closed_m1_chunks(**self.kwargs()))
        self.assertEqual([(c.start_ms, c.end_ms) for c in chunks], [
            (0, 4 * STEP), (4 * STEP, 8 * STEP), (8 * STEP, 11 * STEP),
        ])
        self.assertEqual([len(c.candles) for c in chunks], [4, 4, 3])
        self.assertEqual(
            [b.start_ms for c in chunks for b in c.candles],
            list(range(0, 11 * STEP, STEP)),
        )
        self.assertEqual(len(chunks[0].sha256), 64)
        self.assertEqual(chunks[0].source_id, "FIXTURE_M1")
        self.assertEqual(
            chunks, tuple(iter_closed_m1_chunks(**self.kwargs())),
        )

    def test_yields_only_complete_chunks_and_does_not_buffer_all_days(self):
        calls = []
        upstream = closed_history(0, 30)

        def fetch(*args, **kwargs):
            calls.append(kwargs["end_ms"])
            return upstream(*args, **kwargs)

        iterator = iter_closed_m1_chunks(**self.kwargs(
            end_ms=30 * STEP, latest_closed_boundary_ms=30 * STEP,
            fetch_candles=fetch,
        ))
        self.assertEqual(calls, [])
        first = next(iterator)
        self.assertEqual((first.start_ms, first.end_ms), (0, 4 * STEP))
        self.assertTrue(calls)
        self.assertLessEqual(max(calls), 4 * STEP - 1)
        next(iterator)
        self.assertGreater(max(calls), 4 * STEP - 1)

    def test_missing_one_bar_rejects_whole_chunk(self):
        fixture = closed_history(0, 11)
        def missing(*args, **kwargs):
            return [x for x in fixture(*args, **kwargs)
                    if int(x["time"]) != 2 * STEP]
        with self.assertRaisesRegex(ValueError, "gap"):
            tuple(iter_closed_m1_chunks(**self.kwargs(
                fetch_candles=missing, chunk_minutes=11, page_limit=30
            )))

    def test_broken_cursor_rejected(self):
        def stalled(*args, **kwargs):
            return [row(9)]
        with self.assertRaisesRegex(ValueError, "pagination"):
            tuple(iter_closed_m1_chunks(**self.kwargs(
                fetch_candles=stalled, chunk_minutes=11
            )))

    def test_conflicting_duplicate_rejected(self):
        def duplicate(*args, **kwargs):
            records = closed_history(0, 11)(*args, **kwargs)
            if records:
                records.append({**records[0], "open": "105", "high": "106"})
            return records
        with self.assertRaisesRegex(ValueError, "conflicting duplicate"):
            tuple(iter_closed_m1_chunks(**self.kwargs(
                fetch_candles=duplicate
            )))

    def test_unaligned_and_invalid_ohlc_rejected(self):
        def unaligned(*args, **kwargs):
            return [{**row(0), "time": "1"}]
        with self.assertRaisesRegex(ValueError, "unaligned"):
            tuple(iter_closed_m1_chunks(**self.kwargs(fetch_candles=unaligned)))
        def bad_ohlc(*args, **kwargs):
            return [{**row(0), "high": "50"}]
        with self.assertRaises(ValueError):
            tuple(iter_closed_m1_chunks(**self.kwargs(fetch_candles=bad_ohlc)))

    def test_range_rejects_forming_future_or_misaligned_minute(self):
        for changes in (
            {"latest_closed_boundary_ms": 10 * STEP},
            {"start_ms": 1},
            {"end_ms": 11 * STEP + 1},
            {"symbol": "BTCUSD"},
            {"page_limit": 1001},
            {"chunk_minutes": 0},
            {"source_id": "../../PAPER"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    tuple(iter_closed_m1_chunks(**self.kwargs(**changes)))

    def test_no_private_api_and_request_is_unsigned_public_market_get(self):
        payload = {"retCode": 0, "result": {"list": [
            ["60000", "100", "101", "99", "100", "2"],
        ]}}
        seen = []

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, size):
                return json.dumps(payload).encode()

        def open_stub(request, *, timeout):
            seen.append((request, timeout))
            return Response()

        with patch("research.simulator_v2.history.urlopen", side_effect=open_stub):
            result = fetch_public_m1_klines("BTCUSDT", "1", 20, end_ms=90000)
        self.assertEqual(result[0]["time"], "60000")
        request, timeout = seen[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 12)
        parsed = urlsplit(request.full_url)
        self.assertEqual(parsed.netloc, "api.bybit.com")
        self.assertEqual(parsed.path, "/v5/market/kline")
        self.assertEqual(parse_qs(parsed.query)["interval"], ["1"])
        self.assertIsNone(request.get_header("Authorization"))
        self.assertNotIn("/order", request.full_url)
        with self.assertRaises(ValueError):
            fetch_public_m1_klines("BTCUSDT", "5", 20, end_ms=90000)


if __name__ == "__main__":
    unittest.main()
