import unittest

import pandas as pd

from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    ScannerGeometryCursorProvider,
    build_scanner_geometry_cursor_anchor,
    load_scanner_catchup_closed_candles,
    project_latest_geometry_index,
)


def _snapshot(anchor=None, *, apex_index=220):
    result = {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": apex_index, "price": 90.0, "valid_intersection": True},
            "current_index": 199,
        },
    }
    if anchor is not None:
        result["scanner_geometry_cursor"] = anchor
    return result


def _frame(times):
    return pd.DataFrame(
        [
            {
                "time": time_ms,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
                "turnover": 1.0,
            }
            for time_ms in times
        ]
    )


class ScannerGeometryCursorTests(unittest.TestCase):
    def test_anchor_freezes_scanner_index_and_source_candle_time(self):
        anchor = build_scanner_geometry_cursor_anchor(
            geometry_index=199,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        )
        self.assertEqual(anchor["geometry_index"], 199)
        self.assertEqual(anchor["source_candle_time_ms"], 1_800_000)
        self.assertEqual(anchor["timeframe"], "1")

    def test_projection_advances_in_frozen_index_space(self):
        snapshot = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=199,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        ))
        self.assertEqual(
            project_latest_geometry_index(
                snapshot,
                latest_closed_candle_time_ms=2_100_000,
            ),
            204,
        )

    def test_projection_rejects_backward_or_unaligned_time(self):
        snapshot = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=199,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        ))
        with self.assertRaisesRegex(ScannerGeometryCursorError, "predates"):
            project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=1_740_000)
        with self.assertRaisesRegex(ScannerGeometryCursorError, "aligned"):
            project_latest_geometry_index(snapshot, latest_closed_candle_time_ms=1_830_000)

    def test_legacy_snapshot_fails_before_market_data_read(self):
        calls = []
        provider = ScannerGeometryCursorProvider(
            lambda symbol: calls.append(symbol) or 2_100_000
        )
        with self.assertRaisesRegex(ScannerGeometryCursorError, "no Scanner geometry cursor anchor"):
            provider("TESTUSDT", _snapshot())
        self.assertEqual(calls, [])

    def test_two_same_symbol_snapshots_keep_independent_index_spaces(self):
        latest = 2_400_000
        provider = ScannerGeometryCursorProvider(lambda symbol: latest)
        first = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=100,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        ))
        second = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=150,
            source_candle_time_ms=2_100_000,
            timeframe="1",
        ))
        self.assertEqual(provider("TESTUSDT", first), 110)
        self.assertEqual(provider("TESTUSDT", second), 155)

    def test_catchup_returns_exact_contiguous_closed_range_after_anchor(self):
        snapshot = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=199,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        ))
        calls = []

        def loader(symbol, timeframe, limit, minimum=50):
            calls.append((symbol, timeframe, limit, minimum))
            return _frame([
                1_800_000,
                1_860_000,
                1_920_000,
                1_980_000,
                2_040_000,  # newest/forming; deliberately excluded
            ])

        candles = load_scanner_catchup_closed_candles(
            "TESTUSDT",
            snapshot,
            candle_loader=loader,
        )

        self.assertEqual(calls, [("TESTUSDT", "1", 22, 2)])
        self.assertEqual([item["time_ms"] for item in candles], [1_860_000, 1_920_000, 1_980_000])
        self.assertEqual([item["geometry_index"] for item in candles], [200, 201, 202])
        self.assertTrue(all(item["closed"] is True for item in candles))
        self.assertTrue(all(item["timeframe"] == "1" for item in candles))

    def test_catchup_fails_closed_on_missing_minute(self):
        snapshot = _snapshot(build_scanner_geometry_cursor_anchor(
            geometry_index=199,
            source_candle_time_ms=1_800_000,
            timeframe="1",
        ))

        def loader(symbol, timeframe, limit, minimum=50):
            return _frame([
                1_800_000,
                1_860_000,
                1_980_000,  # 1_920_000 is missing
                2_040_000,
            ])

        with self.assertRaisesRegex(ScannerGeometryCursorError, "incomplete or non-contiguous"):
            load_scanner_catchup_closed_candles(
                "TESTUSDT",
                snapshot,
                candle_loader=loader,
            )

    def test_catchup_returns_only_latest_closed_candle_once_apex_is_reached(self):
        snapshot = _snapshot(
            build_scanner_geometry_cursor_anchor(
                geometry_index=199,
                source_candle_time_ms=1_800_000,
                timeframe="1",
            ),
            apex_index=202,
        )

        def loader(symbol, timeframe, limit, minimum=50):
            # Historical minutes are intentionally absent.  They are no longer
            # required once the latest proven closed candle itself reaches apex.
            return _frame([
                1_800_000,
                1_980_000,
                2_040_000,
            ])

        candles = load_scanner_catchup_closed_candles(
            "TESTUSDT",
            snapshot,
            candle_loader=loader,
        )

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["time_ms"], 1_980_000)
        self.assertEqual(candles[0]["geometry_index"], 202)

    def test_catchup_validates_snapshot_before_market_data_read(self):
        calls = []

        def loader(*args, **kwargs):
            calls.append((args, kwargs))
            return _frame([1_800_000, 1_860_000])

        with self.assertRaisesRegex(ScannerGeometryCursorError, "no Scanner geometry cursor anchor"):
            load_scanner_catchup_closed_candles(
                "TESTUSDT",
                _snapshot(),
                candle_loader=loader,
            )

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
