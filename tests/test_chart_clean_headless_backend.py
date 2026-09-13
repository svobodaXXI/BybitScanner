import os
import sys
import tempfile
import threading
import time
import unittest

import matplotlib
import numpy as np
import pandas as pd

import chart_clean


class ChartCleanHeadlessBackendTests(unittest.TestCase):
    """Regression for the PAPER backend crash: ScannerControlRuntime renders
    scan charts on its own background thread (never the process main
    thread). matplotlib auto-selects an interactive GUI backend (TkAgg, when
    Tkinter is available) as soon as pyplot -- or mplfinance, which imports
    pyplot itself -- is first imported, unless a backend was already
    selected. TkAgg is not thread-safe: the first real scan pass crashed the
    whole PAPER backend process with a native Tcl error ("Tcl_AsyncDelete:
    async handler deleted by the wrong thread"). chart_clean.py now selects
    the non-interactive Agg backend before importing mplfinance/pyplot."""

    def _sample_candles(self, periods: int = 60) -> pd.DataFrame:
        rng = np.random.default_rng(0)
        close = 100 + np.cumsum(rng.normal(0, 0.2, periods))
        open_ = close - rng.normal(0, 0.1, periods)
        high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.1, periods))
        low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.1, periods))
        start_ms = 1_700_000_000_000
        return pd.DataFrame({
            "time": start_ms + np.arange(periods) * 60_000,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
        })

    def test_matplotlib_backend_is_headless_agg(self) -> None:
        self.assertEqual(matplotlib.get_backend().lower(), "agg")

    def test_draw_chart_renders_from_a_background_thread_without_tkinter(self) -> None:
        df = self._sample_candles()
        errors: list[BaseException] = []

        with tempfile.TemporaryDirectory() as charts_dir:
            original_charts_dir = chart_clean.CHARTS_DIR
            chart_clean.CHARTS_DIR = charts_dir

            def render() -> None:
                try:
                    chart_clean.draw_chart(df, [], [], "TESTUSDT", None)
                except BaseException as exc:  # pragma: no cover - failure path
                    errors.append(exc)

            thread = threading.Thread(target=render, name="scanner-control-runtime")
            try:
                thread.start()
                thread.join(timeout=30)
            finally:
                chart_clean.CHARTS_DIR = original_charts_dir

            self.assertFalse(thread.is_alive(), "draw_chart() did not finish in time")
            if errors:
                raise errors[0]
            self.assertTrue(
                os.path.exists(os.path.join(charts_dir, "TESTUSDT_analysis.png")),
            )

        self.assertNotIn("tkinter", sys.modules)
        self.assertNotIn("Tkinter", sys.modules)

    def test_repeated_background_thread_renders_stay_thread_safe(self) -> None:
        """Mirrors ScannerControlRuntime calling draw_chart() repeatedly
        across ticks: several sequential background-thread renders must all
        complete cleanly, not just the first one."""
        df = self._sample_candles()
        errors: list[BaseException] = []

        with tempfile.TemporaryDirectory() as charts_dir:
            original_charts_dir = chart_clean.CHARTS_DIR
            chart_clean.CHARTS_DIR = charts_dir
            try:
                for index in range(3):
                    def render(symbol: str = f"TESTUSDT{index}") -> None:
                        try:
                            chart_clean.draw_chart(df, [], [], symbol, None)
                        except BaseException as exc:  # pragma: no cover
                            errors.append(exc)

                    thread = threading.Thread(target=render, name="scanner-control-runtime")
                    thread.start()
                    thread.join(timeout=30)
                    self.assertFalse(thread.is_alive())
            finally:
                chart_clean.CHARTS_DIR = original_charts_dir

        if errors:
            raise errors[0]


if __name__ == "__main__":
    unittest.main()
