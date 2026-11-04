"""Contract for real public OHLCV -> isolated, no-trade visual SIMULATION runs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.export_historical_replay import (
    MAX_BARS, build_market_only_document, write_run_document,
)
from research.historical_candle_feed import FIVE_MINUTES_MS


def fake_public_candles(count, omit=None):
    data = [
        {"time": str(i * FIVE_MINUTES_MS), "open": "100", "high": "102",
         "low": "98", "close": "101", "volume": "10"}
        for i in range(count) if i != omit
    ]

    def fetch(symbol, interval, limit, *, end_ms):
        if symbol != "BTCUSDT" or interval != "5":
            raise ValueError("unexpected public exchange interval")
        return [x for x in data if int(x["time"]) <= end_ms][-limit:][::-1]

    return fetch


class MarketOnlyExportTests(unittest.TestCase):
    def test_real_candle_export_has_no_fabricated_trades_or_future_bars(self):
        doc = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=24 * FIVE_MINUTES_MS,
            run_id="history-a", fetch_candles=fake_public_candles(28),
        )
        self.assertEqual(doc["source"], "SIMULATION")
        self.assertEqual(doc["mode"], "MARKET_ONLY")
        self.assertEqual(doc["market_data_source"], "BYBIT_PUBLIC_KLINE")
        self.assertEqual(doc["timeframe"], "5m")
        self.assertEqual(len(doc["events"]), 24)
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in doc["events"]))
        self.assertTrue(all(e["simulation_run_id"] == "history-a" for e in doc["events"]))
        self.assertEqual(
            [e["candle"]["end_ms"] for e in doc["events"]],
            [(i + 1) * FIVE_MINUTES_MS for i in range(24)],
        )
        self.assertTrue(all("trade_id" not in e and "side" not in e for e in doc["events"]))

    def test_export_draws_new_yellow_candidate_only_after_1h_pivots_confirmed(self):
        # Strict 2-left/2-right swings: L4-H6-L8-H10, known only
        # after hour 12 closes; no replay overlay may appear earlier.
        hourly = [
            (105,100), (110,102), (115,104), (107,99), (104,95),
            (110,103), (118,107), (113,104), (108,99), (112,106),
            (120,110), (116,108), (112,103),
        ]
        data = []
        for hour, (high, low) in enumerate(hourly):
            middle = (high + low)/2
            for minute in range(12):
                i = hour*12 + minute
                data.append({
                    "time": str(i*FIVE_MINUTES_MS),
                    "open": str(middle),
                    "close": str(middle),
                    "high": str(high if minute == 5 else middle + 1),
                    "low": str(low if minute == 6 else middle - 1),
                    "volume": "10",
                })
        def fetch(_symbol, _interval, limit, *, end_ms):
            return [x for x in data if int(x["time"]) <= end_ms][-limit:][::-1]

        document = build_market_only_document(
            symbol="BTCUSDT", start_ms=0,
            end_ms=13*12*FIVE_MINUTES_MS, run_id="visible-yellow",
            fetch_candles=fetch,
        )
        self.assertEqual(len(document["events"]), 13*12)
        yellow = [e for e in document["geometry"] if e["kind"] in ("MAIN_1H","TARGET_1H")]
        self.assertEqual(len(yellow), 2)
        self.assertEqual({x["kind"] for x in yellow}, {"MAIN_1H", "TARGET_1H"})
        self.assertEqual({x["available_at_ms"] for x in yellow}, {13*12*FIVE_MINUTES_MS})
        self.assertTrue(all(x["classification"] == "UNVALIDATED_GEOMETRY_ONLY" for x in yellow))
        self.assertTrue(all(x["available_at_ms"] > x["to_ms"] for x in yellow))
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in document["events"]))

    def test_missing_history_fails_without_a_report(self):
        with self.assertRaisesRegex(ValueError, "missing historical"):
            build_market_only_document(
                symbol="BTCUSDT", start_ms=0, end_ms=24 * FIVE_MINUTES_MS,
                run_id="gapped", fetch_candles=fake_public_candles(24, omit=9),
            )

    def test_rejects_invalid_bounds_identity_and_future(self):
        fetch = fake_public_candles(3)
        with self.assertRaises(ValueError):
            build_market_only_document(
                symbol="BTCUSDT", start_ms=0, end_ms=3 * FIVE_MINUTES_MS,
                run_id="../paper", fetch_candles=fetch,
            )
        with self.assertRaises(ValueError):
            build_market_only_document(
                symbol="BTCUSDT", start_ms=0, end_ms=(MAX_BARS + 1) * FIVE_MINUTES_MS,
                run_id="too-long", fetch_candles=fetch,
            )
        with self.assertRaises(ValueError):
            build_market_only_document(
                symbol="BTCUSDT", start_ms=0, end_ms=10_000_000_000_000,
                run_id="future", fetch_candles=fetch,
            )

    def test_reports_are_exclusive_and_cannot_touch_paper_files(self):
        doc = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=3 * FIVE_MINUTES_MS,
            run_id="test-exclusive", fetch_candles=fake_public_candles(3),
        )
        with TemporaryDirectory() as work:
            work_root = Path(work)
            paper = work_root / "paper_trades.json"
            paper.write_bytes(b"immutable PAPER accounting bytes")
            destination = work_root / "simulation_runs"
            first = write_run_document(doc, destination)
            self.assertEqual(first.name, "test-exclusive.json")
            self.assertIn(b'"mode":"MARKET_ONLY"', first.read_bytes())
            with self.assertRaises(FileExistsError):
                write_run_document(doc, destination)
            self.assertEqual(paper.read_bytes(), b"immutable PAPER accounting bytes")
            self.assertEqual(len(list(destination.iterdir())), 1)
            with self.assertRaises(ValueError):
                write_run_document({**doc, "source": "PAPER"}, destination)
            self.assertEqual(paper.read_bytes(), b"immutable PAPER accounting bytes")

    def test_existing_symlink_output_root_is_rejected(self):
        doc = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=2 * FIVE_MINUTES_MS,
            run_id="no-link", fetch_candles=fake_public_candles(2),
        )
        with TemporaryDirectory() as work:
            work_root = Path(work)
            unsafe = work_root / "paper_ledger"
            unsafe.mkdir()
            link = work_root / "simulation_runs"
            try:
                link.symlink_to(unsafe, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this test host")
            with self.assertRaisesRegex(ValueError, "symlink"):
                write_run_document(doc, link)
            self.assertFalse((unsafe / "no-link.json").exists())


if __name__ == "__main__":
    unittest.main()
