import unittest

import pandas as pd

from robot_state_machine import boundary_price

from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    ScannerGeometryCursorProvider,
    build_scanner_geometry_cursor_anchor,
    load_scanner_catchup_closed_candles,
    project_frozen_geometry_to_robot_1m,
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

    def test_5m_geometry_projects_exactly_into_robot_1m_coordinate(self):
        source = {
            "upper_line": {"slope": -5.0, "intercept": 1100.0},
            "lower_line": {"slope": -2.5, "intercept": 600.0},
            "apex": {"index": 220.5, "price": 0.0, "valid_intersection": True},
            "current_index": 199,
            "pair_metrics": {"reference_price": 100.0, "start_width": 20.0},
        }

        projected = project_frozen_geometry_to_robot_1m(
            source, source_timeframe="5",
        )

        self.assertEqual(projected["current_index"], 199)
        self.assertEqual(projected["upper_line"]["slope"], -1.0)
        self.assertEqual(projected["lower_line"]["slope"], -0.5)
        self.assertEqual(projected["apex"]["index"], 306.5)
        self.assertEqual(projected["robot_coordinate_timeframe"], "1")
        self.assertEqual(projected["scanner_source_timeframe"], "5")

        # Anchor price is invariant.
        source_upper_now = -5.0 * 199 + 1100.0
        robot_upper_now = (
            projected["upper_line"]["slope"] * 199
            + projected["upper_line"]["intercept"]
        )
        self.assertEqual(robot_upper_now, source_upper_now)

        # Five 1m Robot steps equal one 5m Scanner step.
        source_upper_next = -5.0 * 200 + 1100.0
        robot_upper_after_five = (
            projected["upper_line"]["slope"] * 204
            + projected["upper_line"]["intercept"]
        )
        self.assertEqual(robot_upper_after_five, source_upper_next)

        # Projection never mutates the native Scanner geometry.
        self.assertEqual(source["upper_line"]["slope"], -5.0)
        self.assertEqual(source["apex"]["index"], 220.5)

    def test_real_at_wedge_uses_frozen_robot_1m_slope_only_once(self):
        # The verified ATUSDT 2026-10-31 snapshot already projects Scanner M5
        # slopes to Robot M1. Reprojecting it gives a false early breakout.
        snapshot = {
            "pattern": "Falling Wedge",
            "scanner_geometry_cursor": build_scanner_geometry_cursor_anchor(
                geometry_index=199,
                source_candle_time_ms=1793451300000,  # 12:55 UTC
                timeframe="1",
            ),
            "robot_geometry": {
                "current_index": 199,
                "robot_coordinate_timeframe": "1",
                "scanner_source_timeframe": "5",
                "upper_line": {
                    "slope": -1.3187500000000005e-05,
                    "intercept": 0.1296415,
                },
                "lower_line": {
                    "slope": -9.954022988505749e-06,
                    "intercept": 0.1277033793103448,
                },
                "apex": {"index": 599.3921350810972, "valid_intersection": True},
            },
        }
        index = project_latest_geometry_index(
            snapshot, latest_closed_candle_time_ms=1793452200000,
        )  # Last closed 13:10 UTC 1m candle
        self.assertEqual(index, 214)
        self.assertAlmostEqual(
            boundary_price(snapshot, side="upper", geometry_index=index),
            0.126819375, places=10,
        )
        self.assertAlmostEqual(
            boundary_price(snapshot, side="lower", geometry_index=index),
            0.125573218, places=9,
        )
        # PAPER fill 0.12681 alone is NOT above the boundary at index 214.
        self.assertLess(0.12681, boundary_price(
            snapshot, side="upper", geometry_index=index,
        ))

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
