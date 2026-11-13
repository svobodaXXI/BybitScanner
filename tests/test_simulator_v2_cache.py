"""Offline regression for the dedicated Simulator 2.0 public OHLCV cache."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from research.simulator_v2.cache import iter_cached_m1_chunks
from research.simulator_v2.timeline import IsolatedTimeline, MINUTE_MS

STEP = MINUTE_MS


def row(i):
    return {
        "time": str(i * STEP), "open": "100", "high": "102",
        "low": "98", "close": "101", "volume": "3",
    }


def public_fixture(total, calls):
    records = [row(i) for i in range(total)]

    def fetch(symbol, interval, limit, *, end_ms):
        calls.append((symbol, interval, limit, end_ms))
        return [bar for bar in reversed(records)
                if int(bar["time"]) <= end_ms][:limit]

    return fetch


class M1CacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory(prefix="sim-v2-cache-test-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / "simulator-v2-public-m1"

    def chunks(self, *, fetch_candles, **changes):
        options = dict(
            cache_dir=self.root, symbol="BTCUSDT",
            start_ms=0, end_ms=11 * STEP,
            latest_closed_boundary_ms=11 * STEP,
            chunk_minutes=4, page_limit=3,
            source_id="FIXTURE_1", fetch_candles=fetch_candles,
        )
        options.update(changes)
        return tuple(iter_cached_m1_chunks(**options))

    def test_cache_hit_fetches_no_network_and_preserves_hashes(self):
        calls = []
        first = self.chunks(fetch_candles=public_fixture(11, calls))
        self.assertEqual(len(first), 3)
        self.assertGreater(len(calls), 0)
        self.assertEqual([len(chunk.candles) for chunk in first], [4, 4, 3])
        before_files = sorted(self.root.iterdir())

        def no_fetch(*_args, **_kwargs):
            raise AssertionError("cache hit must not fetch market data")

        second = self.chunks(fetch_candles=no_fetch)
        self.assertEqual(first, second)
        self.assertEqual(sorted(self.root.iterdir()), before_files)
        self.assertTrue(all(len(c.sha256) == 64 for c in second))

    def test_corrupt_cache_fails_closed_without_reloading_or_overwrite(self):
        self.chunks(fetch_candles=public_fixture(11, []))
        target = sorted(self.root.iterdir())[0]
        payload = json.loads(target.read_text())
        payload["candles"][0][1] = "199"
        target.write_text(json.dumps(payload))
        original = target.read_bytes()

        def no_fetch(*_args, **_kwargs):
            raise AssertionError("must not re-fetch to hide damaged cache")

        with self.assertRaises(ValueError):
            self.chunks(fetch_candles=no_fetch)
        self.assertEqual(target.read_bytes(), original)

    def test_gap_rejects_chunk_without_creating_partial_file(self):
        def missing(symbol, interval, limit, *, end_ms):
            return [
                item for item in public_fixture(11, [])(
                    symbol, interval, limit, end_ms=end_ms
                ) if int(item["time"]) != 2 * STEP
            ]

        with self.assertRaises(ValueError):
            self.chunks(fetch_candles=missing)
        self.assertEqual(list(self.root.glob("*.json")), [])

    def test_unrelated_user_file_is_never_modified(self):
        self.root.mkdir(parents=True)
        sentinel = self.root / "my-notes.txt"
        sentinel.write_bytes(b"owner-owned-file")
        self.chunks(fetch_candles=public_fixture(11, []))
        self.assertEqual(sentinel.read_bytes(), b"owner-owned-file")

    def test_source_id_separates_cache_without_reuse(self):
        first = self.chunks(
            fetch_candles=public_fixture(11, []), source_id="SOURCE_A",
        )
        with self.assertRaises(AssertionError):
            self.chunks(
                fetch_candles=lambda *_a, **_kw: (_ for _ in ()).throw(
                    AssertionError("different source requires real fetch")
                ), source_id="SOURCE_B",
            )
        second = self.chunks(
            fetch_candles=public_fixture(11, []), source_id="SOURCE_B",
        )
        self.assertEqual(first[0].sha256, second[0].sha256)
        self.assertNotEqual(first[0].source_id, second[0].source_id)
        self.assertEqual(len(tuple(self.root.glob("*.json"))), 6)

    def test_future_candle_is_rejected_even_if_cached(self):
        self.chunks(fetch_candles=public_fixture(11, []))
        with self.assertRaises(ValueError):
            self.chunks(
                fetch_candles=lambda *_a, **_kw: (),
                latest_closed_boundary_ms=10 * STEP,
            )

    def test_cached_chunks_feed_existing_timeline(self):
        self.chunks(
            fetch_candles=public_fixture(65, []),
            end_ms=65 * STEP, latest_closed_boundary_ms=65 * STEP,
            chunk_minutes=7, page_limit=5,
        )
        timeline = IsolatedTimeline(
            simulation_run_id="cache-fixture", symbol="BTCUSDT",
        )
        for chunk in iter_cached_m1_chunks(
            cache_dir=self.root, symbol="BTCUSDT",
            start_ms=0, end_ms=65 * STEP,
            latest_closed_boundary_ms=65 * STEP,
            chunk_minutes=7, page_limit=5,
            source_id="FIXTURE_1",
            fetch_candles=lambda *_a, **_kw: (_ for _ in ()).throw(
                AssertionError("unexpected fetch")
            ),
        ):
            for candle in chunk.candles:
                timeline.step(candle)
        self.assertEqual(timeline.processed_minutes, 65)
        self.assertEqual(
            sum(event.kind == "H1_CLOSED" for event in timeline.events), 1,
        )

    def test_cache_rejects_symlink_file_and_unsafe_source(self):
        self.chunks(fetch_candles=public_fixture(11, []))
        cache_file = sorted(self.root.glob("*.json"))[0]
        sentinel = self.root / "foreign"
        sentinel.write_bytes(b"owner-owned-file")
        cache_file.unlink()  # only this test's own disposable fixture
        try:
            cache_file.symlink_to(sentinel)
        except (NotImplementedError, OSError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(ValueError):
            self.chunks(
                fetch_candles=lambda *_a, **_kw: (),
            )
        self.assertEqual(sentinel.read_bytes(), b"owner-owned-file")
        with self.assertRaises(ValueError):
            self.chunks(
                fetch_candles=public_fixture(11, []), source_id="../PAPER",
            )


if __name__ == "__main__":
    unittest.main()
