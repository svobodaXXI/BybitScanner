"""Scanner G1a: available pre-pattern history without geometry or loader changes."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import chart_clean


class ChartWindowTests(unittest.TestCase):
    def candles(self, count, timeframe):
        x = np.arange(count)
        close = 114 + 2 * np.sin(x / 12)
        return pd.DataFrame({
            "time": 1_700_000_000_000 + x * int(timeframe) * 60_000,
            "open": close - 0.2, "high": close + 0.5,
            "low": close - 0.7, "close": close,
        })

    def result(self, timeframe, upper=180, lower=230):
        return {
            "timeframe": timeframe, "scanner_source_timeframe": timeframe,
            "pattern": "Falling Wedge",
            "geometry": {
                "upper_line": {"slope": -0.04, "intercept": 130,
                               "anchor_index": upper},
                "lower_line": {"slope": 0.02, "intercept": 105,
                               "anchor_index": lower},
                # Deliberately disagrees: window must use actual line anchors.
                "pair_metrics": {"anchor_sequence": {"primary_anchor": 280}},
                "apex": {"index": 416},
            },
        }

    def test_sufficient_history_uses_earlier_boundary_and_one_formation_span(self):
        for timeframe in ("1", "5"):
            for upper, lower in ((180, 230), (230, 180)):
                with self.subTest(timeframe=timeframe, upper=upper):
                    df = self.candles(300, timeframe)
                    offset, warning = chart_clean._chart_window(
                        df, self.result(timeframe, upper, lower))
                    self.assertEqual(offset, 51)  # 180 - 119 - 10
                    self.assertIsNone(warning)
                    self.assertEqual(df.iloc[180]["time"] - df.iloc[offset]["time"],
                                     129 * int(timeframe) * 60_000)

    def test_actual_short_response_and_no_preceding_history_are_reported(self):
        for timeframe in ("1", "5"):
            for earliest in (0, 30):
                with self.subTest(timeframe=timeframe, earliest=earliest):
                    offset, warning = chart_clean._chart_window(
                        self.candles(200, timeframe), self.result(timeframe, earliest, 60))
                    self.assertEqual(offset, 0)
                    self.assertEqual(warning, "Предшествующий импульс показан не полностью")

    def test_cap_prioritizes_pattern_and_distinguishes_missing_start(self):
        for timeframe in ("1", "5"):
            for earliest, expected in (
                (900, "Предшествующий импульс показан не полностью"),
                (500, "Начало паттерна раньше окна графика"),
            ):
                with self.subTest(timeframe=timeframe, earliest=earliest):
                    df = self.candles(1600, timeframe)
                    offset, warning = chart_clean._chart_window(
                        df, self.result(timeframe, earliest, earliest + 50))
                    self.assertEqual(len(df.iloc[offset:]), 1000)
                    self.assertEqual(warning, expected)

    def test_missing_candles_inside_context_do_not_claim_complete_history(self):
        for timeframe in ("1", "5"):
            df = self.candles(300, timeframe)
            df.loc[100:, "time"] += int(timeframe) * 60_000
            _, warning = chart_clean._chart_window(df, self.result(timeframe))
            self.assertEqual(warning, "Предшествующий импульс показан не полностью")

    def test_missing_or_invalid_anchors_retain_available_window_with_warning(self):
        for invalid in (None, float("nan"), 999, 1.5):
            result = self.result("1")
            result["geometry"]["upper_line"]["anchor_index"] = invalid
            offset, warning = chart_clean._chart_window(self.candles(300, "1"), result)
            self.assertEqual(offset, 180)
            self.assertIn("неизвестны исходные якоря", warning)
        self.assertEqual(chart_clean._chart_window(self.candles(300, "1"), None),
                         (180, None))

    def test_scanner_source_interval_is_not_robot_projected_interval(self):
        result = self.result("5")
        result["timeframe"] = "1"
        result["scanner_geometry_cursor"] = {"timeframe": "1", "geometry_index": 1495}
        self.assertEqual(chart_clean._chart_window(self.candles(300, "5"), result),
                         (51, None))

    def test_real_png_preserves_prices_anchors_start_and_inputs(self):
        for timeframe in ("1", "5"):
            for count, upper, lower in ((300, 180, 230), (200, 30, 60),
                                        (1600, 500, 550)):
                with self.subTest(timeframe=timeframe, count=count):
                    df = self.candles(count, timeframe)
                    result = self.result(timeframe, upper, lower)
                    original_df, original_result = df.copy(deep=True), copy.deepcopy(result)
                    offset, warning = chart_clean._chart_window(df, result)
                    captured = {}
                    real_plot = chart_clean.mpf.plot

                    def capture(frame, **kwargs):
                        captured.update(frame=frame.copy(), addplots=kwargs["addplot"])
                        fig, axes = real_plot(frame, **kwargs)
                        captured["axes"] = axes
                        return fig, axes

                    with tempfile.TemporaryDirectory() as directory:
                        with patch.object(chart_clean, "CHARTS_DIR", directory), \
                             patch.object(chart_clean.mpf, "plot", side_effect=capture):
                            chart_clean.draw_chart(df, [], [], "G1A", result)
                        png = Path(directory, "G1A_analysis.png").read_bytes()
                        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
                    np.testing.assert_array_equal(captured["frame"]["time"],
                                                  df.iloc[offset:]["time"])
                    for line, actual in zip(("upper_line", "lower_line"), captured["addplots"]):
                        frozen = result["geometry"][line]
                        source_x = np.arange(offset, count)
                        expected = np.where(source_x >= frozen["anchor_index"],
                                            frozen["slope"] * source_x + frozen["intercept"], np.nan)
                        np.testing.assert_allclose(actual["data"], expected, equal_nan=True)
                    ax = captured["axes"][0]
                    starts = [text for text in ax.texts if text.get_text() == " START"]
                    if lower >= offset:
                        self.assertEqual(starts[0].get_position()[0], lower - offset)
                    else:
                        self.assertEqual(starts, [])  # Never relabel left edge as START.
                    # Owner format 2026-09-23: the chart header stays minimal;
                    # the incomplete-impulse note is no longer shown there,
                    # even though _chart_window still reports it (asserted
                    # by the dedicated _chart_window tests below).
                    if warning and warning != "Предшествующий импульс показан не полностью":
                        self.assertIn(warning, ax.get_title())
                    elif warning:
                        self.assertNotIn(warning, ax.get_title())
                    self.assertEqual(result, original_result)
                    pd.testing.assert_frame_equal(df, original_df)


if __name__ == "__main__":
    unittest.main()
