"""Focused renderer acceptance; no Telegram messages or Robot effects."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from matplotlib.collections import LineCollection

from geometry.ikigai_box import detect_ikigai_box
from geometry.ikigai_box_chart import (
    fibonacci_chart_levels,
    render_ikigai_box_chart,
)
from tests.test_ikigai_box_detector import _two_impulses


def _sample(direction=1):
    candles, _, _ = _two_impulses(direction)
    candles["time"] = [
        1_790_000_000_000 + 300_000 * n for n in range(len(candles))
    ]
    setup = detect_ikigai_box(candles)
    assert setup is not None
    return candles, setup


class IkigaiBoxChartTests(unittest.TestCase):
    def test_mirror_levels_are_the_first_impulse_and_outer_extension(self):
        for direction, side in ((1, "SHORT"), (-1, "LONG")):
            with self.subTest(side=side):
                _, setup = _sample(direction)
                self.assertEqual(setup.direction, side)
                levels = fibonacci_chart_levels(setup)
                self.assertEqual([label for label, _ in levels],
                                 [0.0, 1.0, 1.618, 2.618])
                self.assertEqual(levels[0][1], setup.anchor_start_price)
                self.assertEqual(levels[1][1], setup.anchor_end_price)
                for label, price in levels:
                    self.assertAlmostEqual(
                        price, setup.fibonacci_price(label)
                    )
                self.assertEqual(
                    sorted(price for _, price in levels),
                    [price for _, price in levels][::direction],
                )

    def test_render_png_uses_exact_frozen_levels_and_shows_origin(self):
        candles, setup = _sample()
        original = candles.copy(deep=True)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "ikigai" / "BTC-5m-abc.png"
            with patch(
                "geometry.ikigai_box_chart.mpf.plot",
                wraps=__import__("mplfinance").plot,
            ) as plot:
                rendered = render_ikigai_box_chart(
                    candles, setup, target, symbol="BTCUSDT",
                    timeframe="5", context_bars=7,
                )
            self.assertEqual(rendered, target)
            self.assertGreater(target.stat().st_size, 10_000)
            with target.open("rb") as stream:
                self.assertEqual(stream.read(8), b"\x89PNG\r\n\x1a\n")
            window = plot.call_args.args[0]
            self.assertEqual(
                len(window),
                setup.as_of_index
                - max(0, setup.impulse_start_index - 7) + 1,
            )
            figure, axes = plot.return_value
            chart_lines = [
                collection for collection in axes[0].collections
                if isinstance(collection, LineCollection)
            ]
            for _, price in fibonacci_chart_levels(setup):
                self.assertTrue(
                    any(
                        abs(segment[0][1] - price) < 1e-8
                        and abs(segment[1][1] - price) < 1e-8
                        for collection in chart_lines
                        for segment in collection.get_segments()
                    ),
                    f"Missing Fibonacci price line at {price}",
                )
        pd.testing.assert_frame_equal(candles, original)

    def test_prefix_does_not_draw_future_candles(self):
        candles, setup = _sample(-1)
        future = pd.concat([
            candles,
            pd.DataFrame([
                dict(time=candles["time"].iloc[-1] + 300_000,
                     open=100_000, high=100_001,
                     low=99_999, close=100_000),
            ]),
        ], ignore_index=True)
        with tempfile.TemporaryDirectory() as directory:
            with patch(
                "geometry.ikigai_box_chart.mpf.plot",
                wraps=__import__("mplfinance").plot,
            ) as plot:
                render_ikigai_box_chart(
                    future, setup, Path(directory) / "only-past.png",
                    symbol="TESTUSDT", timeframe="5",
                )
            plotted = plot.call_args.args[0]
            self.assertEqual(
                len(plotted),
                setup.as_of_index
                - max(0, setup.impulse_start_index - 10) + 1,
            )
            self.assertLess(float(plotted["high"].max()), 100_000)

    def test_invalid_as_of_or_anchor_fails_before_output(self):
        from dataclasses import replace

        candles, setup = _sample()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "no-image.png"
            with self.assertRaises(ValueError):
                render_ikigai_box_chart(
                    candles, replace(setup, as_of_index=len(candles)),
                    target, symbol="TESTUSDT", timeframe="5",
                )
            with self.assertRaises(ValueError):
                render_ikigai_box_chart(
                    candles, replace(setup, fibonacci_1_618=10_000),
                    target, symbol="TESTUSDT", timeframe="5",
                )
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
