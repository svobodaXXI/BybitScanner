"""Contract for real public OHLCV -> isolated, no-trade visual SIMULATION runs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.export_historical_replay import (
    MAX_BARS, build_market_only_document, write_run_document,
)
from research.h017_real_bybit_readonly_acceptance import retrospective_first_touch_study
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

    def test_preloaded_hourly_pivots_make_line_available_without_visible_prehistory(self):
        # The original 13h fixture has a strict confirmed 1-3 / 2-4
        # construction. Displaying only hours 13-15 without prehistory
        # must not fabricate a line; 13h warmup makes it causally known.
        hourly = [
            (105,100), (110,102), (115,104), (107,99), (104,95),
            (110,103), (118,107), (113,104), (108,99), (112,106),
            (120,110), (116,108), (112,103), (113,102), (111,101),
        ]
        data = []
        for hour, (high, low) in enumerate(hourly):
            middle = (high + low)/2
            for within in range(12):
                data.append({
                    "time": str((hour*12 + within)*FIVE_MINUTES_MS),
                    "open": str(middle), "close": str(middle),
                    "high": str(high if within == 5 else middle + 1),
                    "low": str(low if within == 6 else middle - 1),
                    "volume": "10",
                })
        def fetch(_symbol, _interval, limit, *, end_ms):
            return [x for x in data if int(x["time"]) <= end_ms][-limit:][::-1]

        start_ms, end_ms = 13*12*FIVE_MINUTES_MS, 15*12*FIVE_MINUTES_MS
        no_seed = build_market_only_document(
            symbol="BTCUSDT", start_ms=start_ms, end_ms=end_ms,
            run_id="no-seed", fetch_candles=fetch,
        )
        seeded = build_market_only_document(
            symbol="BTCUSDT", start_ms=start_ms, end_ms=end_ms,
            run_id="with-seed", fetch_candles=fetch,
            geometry_warmup_bars=13*12,
        )
        self.assertEqual(no_seed["geometry"], [])
        self.assertEqual(len(seeded["events"]), 24)
        self.assertEqual(seeded["events"][0]["candle"]["start_ms"], start_ms)
        self.assertEqual(seeded["geometry_warmup_hours"], 13)
        kinds = {line["kind"] for line in seeded["geometry"]}
        self.assertTrue({"MAIN_1H", "TARGET_1H"}.issubset(kinds))
        self.assertTrue(all(line["from_ms"] < start_ms
                            for line in seeded["geometry"]
                            if line["kind"] in {"MAIN_1H", "TARGET_1H"}))
        self.assertTrue(all(line["available_at_ms"] >= start_ms
                            for line in seeded["geometry"]))
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED"
                            for e in seeded["events"]))
        self.assertEqual(seeded["dmi_5m"]["points"][0]["plus_di"], None)

    def test_replay_records_contact_then_next_close_reaction_without_trades(self):
        # Confirm H1 1--3 / 2--4 by hour 13 using ONLY the warmup.
        hourly = [
            (105,100), (110,102), (115,104), (107,99), (104,95),
            (110,103), (118,107), (113,104), (108,99), (112,106),
            (120,110), (116,108), (112,103),
        ]
        data = []
        for hour, (high, low) in enumerate(hourly):
            middle = (high + low) / 2
            for within in range(12):
                data.append({
                    "time": str((hour * 12 + within) * FIVE_MINUTES_MS),
                    "open": str(middle), "close": str(middle),
                    "high": str(high if within == 5 else middle + 1),
                    "low": str(low if within == 6 else middle - 1),
                    "volume": "10",
                })
        first = 13 * 12 * FIVE_MINUTES_MS
        # Hourly BULL main line through L4=95 and L8=99 -> at H13=104.
        data.extend([
            {"time": str(first), "open": "104", "high": "106",
             "low": "103.5", "close": "104.5", "volume": "10"},
            {"time": str(first + FIVE_MINUTES_MS), "open": "104.5",
             "high": "106", "low": "104.3", "close": "105.5", "volume": "10"},
        ])
        def fetch(_symbol, _interval, limit, *, end_ms):
            return [x for x in data if int(x["time"]) <= end_ms][-limit:][::-1]

        doc = build_market_only_document(
            symbol="BTCUSDT", start_ms=first, end_ms=first + 2 * FIVE_MINUTES_MS,
            run_id="touch-not-fill", fetch_candles=fetch, geometry_warmup_bars=156,
        )
        marks = doc["observations"]
        self.assertEqual([x["kind"] for x in marks],
                         ["MAIN_1H_TOUCH", "MAIN_1H_REACTION"])
        self.assertEqual([x["time_ms"] for x in marks],
                         [first + FIVE_MINUTES_MS, first + 2 * FIVE_MINUTES_MS])
        self.assertEqual(marks[1]["touch_time_ms"], marks[0]["time_ms"])
        self.assertTrue(all(x["classification"] == "UNVALIDATED_GEOMETRY_ONLY"
                            for x in marks))
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in doc["events"]))
        self.assertFalse(any("trade_id" in e for e in doc["events"]))

    def test_exported_adx_matches_only_closed_5m_bars_and_wilder_warmup(self):
        document = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=40 * FIVE_MINUTES_MS,
            run_id="dmi-40", fetch_candles=fake_public_candles(40),
        )
        indicator = document["dmi_5m"]
        self.assertEqual(indicator["source"], "SIMULATION")
        self.assertEqual(indicator["timeframe"], "5m")
        self.assertEqual((indicator["di_length"], indicator["adx_smoothing"]), (14, 14))
        points = indicator["points"]
        self.assertEqual(len(points), 40)
        self.assertEqual(
            [x["time_ms"] for x in points],
            [e["time_ms"] for e in document["events"]],
        )
        self.assertTrue(all(p["plus_di"] is None and p["minus_di"] is None
                            for p in points[:14]))
        self.assertTrue(all(p["adx"] is None for p in points[:27]))
        self.assertIsNotNone(points[14]["plus_di"])
        self.assertIsNotNone(points[14]["minus_di"])
        self.assertIsNotNone(points[27]["adx"])
        # Later OHLC history must not change an already-known indicator sample.
        shorter = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=30 * FIVE_MINUTES_MS,
            run_id="dmi-30", fetch_candles=fake_public_candles(40),
        )
        self.assertEqual(shorter["dmi_5m"]["points"], points[:30])
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in document["events"]))

    def test_exported_dmi_crossings_are_closed_bar_evidence_not_trade_signals(self):
        # Reversing an actual OHLC leg produces directional DI/ADX/20
        # crossings. The exporter must preserve their exact closed time.
        heights = ([100 + 2 * i for i in range(22)] +
                   [144 - 3 * i for i in range(21)] +
                   [81 + 3 * i for i in range(21)])
        data = [
            {"time": str(i * FIVE_MINUTES_MS), "open": str(high - 1),
             "high": str(high), "low": str(high - 2),
             "close": str(high - 1), "volume": "10"}
            for i, high in enumerate(heights)
        ]

        def fetch(_symbol, _interval, limit, *, end_ms):
            return [row for row in data if int(row["time"]) <= end_ms][-limit:][::-1]

        full = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=len(data) * FIVE_MINUTES_MS,
            run_id="dmi-crosses", fetch_candles=fetch,
        )
        points = full["dmi_5m"]["points"]
        crosses = [cross for point in points for cross in point["crossings"]]
        self.assertTrue(crosses, "reversal fixture must generate real Wilder crossings")
        self.assertTrue(all(
            cross["time_ms"] == point["time_ms"]
            for point in points for cross in point["crossings"]
        ))
        self.assertTrue(all(
            cross["side"] in {"PLUS", "MINUS"} and
            cross["comparator"] in {"OPPOSITE_DI", "ADX", "LEVEL_20"} and
            cross["direction"] in {"UP", "DOWN"}
            for cross in crosses
        ))
        self.assertEqual(full["mode"], "MARKET_ONLY")
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" for e in full["events"]))
        prefix = build_market_only_document(
            symbol="BTCUSDT", start_ms=0, end_ms=40 * FIVE_MINUTES_MS,
            run_id="dmi-crosses-prefix", fetch_candles=fetch,
        )
        self.assertEqual(prefix["dmi_5m"]["points"], points[:40])

    def test_real_archive_first_touch_study_keeps_ambiguous_and_dmi_timing_honest(self):
        m5 = FIVE_MINUTES_MS
        bars = [
            {"start_ms": i * m5, "end_ms": (i + 1) * m5,
             "high": h, "low": lo, "open": "100"}
            for i, (h, lo) in enumerate([
                ("101", "99.5"), ("101", "99.5"),
                ("106", "99.5"), ("106", "98"),
                ("101", "98"), ("101", "99.5"),
            ])
        ]
        def candidate(index):
            return {"open_ms": index * m5, "time_ms": (index + 1) * m5,
                    "side": "LONG", "stop_price": "99.3",
                    "target_price": "105", "risk_status": "RISK_PASS"}
        dmi = [
            {"time_ms": (i + 1) * m5, "adx": "21",
             "crossings": [{"time_ms": m5, "side": "PLUS"}] if i == 0 else []}
            for i in range(len(bars))
        ]
        results = retrospective_first_touch_study(
            bars, [candidate(i) for i in (1, 3, 4, 5)], dmi,
        )
        self.assertEqual(results["DMI_PREVIOUS_CLOSE_ONE_OR_MORE"]["TARGET_FIRST"], 1)
        self.assertEqual(results["DMI_PREVIOUS_CLOSE_ZERO"]["BOTH_SAME_M5"], 1)
        self.assertEqual(results["DMI_PREVIOUS_CLOSE_ZERO"]["STOP_FIRST"], 1)
        self.assertEqual(results["DMI_PREVIOUS_CLOSE_ZERO"]["UNRESOLVED"], 1)
        self.assertEqual(sum(sum(x.values()) for x in results.values()), 4)
        self.assertEqual(retrospective_first_touch_study(bars, [candidate(1)], [])[
            "DMI_UNAVAILABLE_OR_NOT_WARM"]["TARGET_FIRST"], 1)
        # No look-ahead: a crossover on candidate bar's own close is not prior evidence.
        dmi[0]["crossings"] = []
        dmi[1]["crossings"] = [{"time_ms": 2 * m5, "side": "PLUS"}]
        self.assertEqual(retrospective_first_touch_study(bars, [candidate(1)], dmi)[
            "DMI_PREVIOUS_CLOSE_ZERO"]["TARGET_FIRST"], 1)

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
