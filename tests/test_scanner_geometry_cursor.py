import unittest

from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    ScannerGeometryCursorProvider,
    build_scanner_geometry_cursor_anchor,
    project_latest_geometry_index,
)


def _snapshot(anchor=None):
    result = {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 220, "price": 90.0, "valid_intersection": True},
            "current_index": 199,
        },
    }
    if anchor is not None:
        result["scanner_geometry_cursor"] = anchor
    return result


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


if __name__ == "__main__":
    unittest.main()
