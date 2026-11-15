"""Source-time Wedge decision/Editor archive must never use a forming candle."""

import unittest
from unittest.mock import patch

import pandas as pd

from analyzer import core


NOW_MS = 1_800_000_150_000


def _frame(timeframe="5", *, last_closed=False):
    step = int(timeframe) * 60_000
    last_open = (NOW_MS // step) * step
    times = [last_open - (59 - i) * step for i in range(60)]
    if last_closed:
        times[-1] -= step
        times = [times[0] - step] + times[:-1]
    return pd.DataFrame({
        "time": times,
        "open": [100.0] * 60,
        "high": [101.0] * 60,
        "low": [99.0] * 60,
        "close": [100.0] * 60,
        "volume": [1.0] * 60,
        "turnover": [1.0] * 60,
    })


class ScannerWedgeClosedCandleCutoffTests(unittest.TestCase):
    def _early_result(self, frame, timeframe="5"):
        with patch.object(core, "load_candles", return_value=frame), \
             patch.object(core, "find_pivots", return_value=([], [])) as pivots, \
             patch.object(core.time, "time_ns", return_value=NOW_MS * 1_000_000):
            result = core.analyze_symbol("TESTUSDT", timeframe=timeframe)
        return result, pivots.call_args.args[0]

    def test_forming_candle_is_excluded_before_pivot_search_for_both_timeframes(self):
        for timeframe in ("1", "5"):
            with self.subTest(timeframe=timeframe):
                frame = _frame(timeframe)
                result, examined = self._early_result(frame, timeframe)
                self.assertEqual(len(examined), 59)
                self.assertEqual(examined.iloc[-1]["time"], frame.iloc[-2]["time"])
                # Other Scanner observers still receive their original fetched frame.
                self.assertIs(result["data"], frame)

    def test_in_progress_candle_cannot_change_confirmed_pivot_input(self):
        frame = _frame()
        changed = frame.copy()
        changed.loc[59, ["high", "low", "close"]] = [900.0, 0.1, 800.0]
        _, first = self._early_result(frame)
        _, second = self._early_result(changed)
        pd.testing.assert_frame_equal(first, second)

    def test_wedge_evaluation_and_editor_source_share_closed_decision_frame(self):
        frame = _frame()
        pivots = [{"index": i, "price": 100.0} for i in (2, 10, 20, 30)]
        geometry = {
            "upper_line": {"anchor_index": 10},
            "lower_line": {"anchor_index": 2},
        }
        with patch.object(core, "load_candles", return_value=frame), \
             patch.object(core, "find_pivots", return_value=(pivots, pivots)), \
             patch.object(core, "analyze_wedge", return_value={
                 "geometry": geometry, "pattern": "Rising Wedge",
             }) as wedge, \
             patch.object(core, "confirm_signal", return_value={}), \
             patch.object(core, "calculate_final_score", return_value=0), \
             patch.object(core, "evaluate_quality", return_value={}), \
             patch.object(core, "evaluate_signal", return_value={}), \
             patch.object(core, "create_signal_payload", return_value={}), \
             patch.object(core, "project_frozen_geometry_to_robot_1m", return_value={}), \
             patch.object(core, "build_scanner_geometry_cursor_anchor", return_value={}), \
             patch.object(core, "create_chart"), \
             patch.object(core, "create_report"), \
             patch.object(core.time, "time_ns", return_value=NOW_MS * 1_000_000):
            result = core.analyze_symbol("TESTUSDT", timeframe="5")
        decided = wedge.call_args.kwargs["candles"]
        self.assertEqual(wedge.call_args.kwargs["current_index"], len(decided) - 1)
        self.assertEqual(len(decided), 59)
        pd.testing.assert_frame_equal(decided, result["wedge_decision_candles"])
        self.assertIs(result["data"], frame)
        self.assertEqual(result["result"]["scanner_source_candle_time_ms"],
                         int(decided.iloc[-1]["time"]))

    def test_fully_closed_latest_bar_is_retained(self):
        frame = _frame()
        cutoff = int(frame.iloc[-1]["time"]) + 5 * 60_000
        with patch.object(core, "load_candles", return_value=frame), \
             patch.object(core, "find_pivots", return_value=([], [])) as pivots, \
             patch.object(core.time, "time_ns", return_value=cutoff * 1_000_000):
            core.analyze_symbol("TESTUSDT", timeframe="5")
        self.assertEqual(len(pivots.call_args.args[0]), 60)


    def test_gold_real_engine_ignores_forming_candle(self):
        """Run the actual Pivot -> Geometry Engine -> Wedge path on a frozen Gold window."""
        from tests.geometry_gold import _analyze, _load_frame, geometry_identity, load_manifest

        case = next(c for c in load_manifest()["cases"]
                    if c["case_id"] == "PONS-formation-fit-positive-anchor")
        closed = _load_frame(case)
        _, _, baseline = _analyze(closed)
        self.assertEqual(geometry_identity(baseline),
                         case["expectation"]["geometry_identity"])

        interval_ms = int(closed["time"].iloc[-1] - closed["time"].iloc[-2])
        self.assertEqual(interval_ms, int(case["timeframe"]) * 60_000)
        decision_as_of_ms = int(closed["time"].iloc[-1]) + interval_ms

        for extreme in (False, True):
            with self.subTest(extreme=extreme):
                forming = closed.iloc[[-1]].copy()
                forming.loc[:, "time"] = decision_as_of_ms
                if extreme:
                    forming.loc[:, "high"] = float(closed["high"].max()) * 3
                    forming.loc[:, "low"] = float(closed["low"].min()) / 3
                fetched = pd.concat([closed, forming], ignore_index=True)
                with patch.object(core, "load_candles", return_value=fetched), \
                     patch.object(core, "confirm_signal", return_value={}), \
                     patch.object(core, "calculate_final_score", return_value=0), \
                     patch.object(core, "evaluate_quality", return_value={}), \
                     patch.object(core, "evaluate_signal", return_value={}), \
                     patch.object(core, "create_signal_payload", return_value={}), \
                     patch.object(core, "project_frozen_geometry_to_robot_1m", return_value={}), \
                     patch.object(core, "build_scanner_geometry_cursor_anchor", return_value={}), \
                     patch.object(core, "create_chart"), \
                     patch.object(core, "create_report"), \
                     patch.object(core.time, "time_ns",
                                  return_value=decision_as_of_ms * 1_000_000):
                    actual = core.analyze_symbol(case["symbol"], timeframe=case["timeframe"])

                pd.testing.assert_frame_equal(actual["wedge_decision_candles"], closed)
                self.assertIs(actual["data"], fetched)
                geometry = actual["result"]["geometry"]
                actual_identity = [
                    int(geometry["upper_line"]["anchor_index"]),
                    int(geometry["upper_line"]["second_index"]),
                    int(geometry["lower_line"]["anchor_index"]),
                    int(geometry["lower_line"]["second_index"]),
                    int(geometry["start_index"]),
                    int(geometry["end_index"]),
                ]
                self.assertEqual(actual_identity, case["expectation"]["geometry_identity"])


if __name__ == "__main__":
    unittest.main()
