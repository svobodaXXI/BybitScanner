"""Focused renderer acceptance; no Telegram messages or Robot effects."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from matplotlib.collections import LineCollection

from geometry.ikigai_box import detect_ikigai_box, detect_ikigai_box_watches
from geometry.ikigai_box_chart import (
    TERMINAL_BAND_RGB,
    TERMINAL_FIBONACCI_LEVELS,
    fibonacci_band_ranges,
    fibonacci_chart_levels,
    terminal_fibonacci_levels,
    render_ikigai_box_chart,
)
from tests.test_ikigai_box_detector import _two_impulses, _terminal_wick_two_impulses


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
            import mplfinance as mpf
            actual_plot = mpf.plot
            observed = {}

            def observe_plot(frame, **options):
                observed["frame"] = frame
                observed["figure"], observed["axes"] = actual_plot(frame, **options)
                return observed["figure"], observed["axes"]

            with patch(
                "geometry.ikigai_box_chart.mpf.plot",
                side_effect=observe_plot,
            ):
                rendered = render_ikigai_box_chart(
                    candles, setup, target, symbol="BTCUSDT",
                    timeframe="5", context_bars=7,
                )
            self.assertEqual(rendered, target)
            self.assertGreater(target.stat().st_size, 10_000)
            with target.open("rb") as stream:
                self.assertEqual(stream.read(8), b"\x89PNG\r\n\x1a\n")
            window = observed["frame"]
            self.assertEqual(
                len(window),
                setup.as_of_index
                - max(0, setup.impulse_start_index - 7) + 1,
            )
            axes = observed["axes"]
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

    def test_minimal_card_and_candles_are_forty_percent_narrower(self):
        import mplfinance as mpf
        from matplotlib.collections import PolyCollection
        import matplotlib.pyplot as plt

        for direction, arrow in ((-1, "↓"), (1, "↑")):
            with self.subTest(direction=direction):
                candles, setup = _sample(direction)
                actual_plot = mpf.plot
                observed = {}

                def capture(frame, **options):
                    fig, axes = actual_plot(frame, **options)
                    old_options = dict(options, figsize=(12, 7))
                    old_fig, old_axes = actual_plot(frame, **old_options)
                    observed.update(fig=fig, axis=axes[0], old_fig=old_fig,
                                    old_axis=old_axes[0])
                    return fig, axes

                with tempfile.TemporaryDirectory() as directory:
                    with patch("geometry.ikigai_box_chart.mpf.plot", side_effect=capture):
                        render_ikigai_box_chart(
                            candles, setup, Path(directory) / "minimal.png",
                            symbol="TESTUSDT", timeframe="5",
                        )
                ax, old_ax = observed["axis"], observed["old_axis"]
                sign = "+" if direction == 1 else "-"
                potential = abs(
                    setup.fibonacci_1_618 - setup.fibonacci_1_0
                ) / setup.fibonacci_1_0 * 100
                self.assertEqual(
                    ax.get_title(),
                    f"TESTUSDT · 5м · {arrow} Коробка Икигаи ({sign}{potential:.2f}%)",
                )
                self.assertEqual(list(ax.texts), [])
                # Compare actual rendered candle polygons, not just plot options.
                old_ax.set_xlim(ax.get_xlim())
                old_ax.set_ylim(ax.get_ylim())
                def body_width(axis):
                    body = next(c for c in axis.collections if isinstance(c, PolyCollection))
                    vertices = axis.transData.transform(body.get_paths()[0].vertices)
                    return vertices[:, 0].max() - vertices[:, 0].min()
                self.assertAlmostEqual(body_width(ax) / body_width(old_ax), 0.6)
                self.assertEqual(tuple(observed["fig"].get_size_inches()), (7.2, 7.0))
                plt.close(observed["old_fig"])

    def test_fibonacci_bands_mirror_the_terminal_tool(self):
        """Levels, prices, adjacent bands and palette follow drawingModel.ts."""
        from matplotlib.colors import to_rgba
        from matplotlib.patches import Rectangle

        self.assertEqual(
            TERMINAL_FIBONACCI_LEVELS,
            (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236),
        )
        for direction, side in ((1, "SHORT"), (-1, "LONG")):
            with self.subTest(side=side):
                candles, setup = _sample(direction)
                levels = terminal_fibonacci_levels(setup)
                # fibonacciPrices: first + (second - first) * level
                for level, price in levels:
                    self.assertAlmostEqual(
                        price,
                        setup.anchor_start_price
                        + (setup.anchor_end_price - setup.anchor_start_price)
                        * level,
                    )
                bands = fibonacci_band_ranges(levels)
                self.assertEqual(len(bands), len(levels) - 1)
                self.assertEqual(bands[0][:2], (0, 0.236))
                self.assertEqual(bands[6][:2], (1, 1.618))
                self.assertEqual(bands[7][:2], (1.618, 2.618))

                import mplfinance as mpf
                actual_plot = mpf.plot
                observed = {}

                def observe(frame, **options):
                    observed["figure"], observed["axes"] = actual_plot(
                        frame, **options)
                    return observed["figure"], observed["axes"]

                with tempfile.TemporaryDirectory() as directory:
                    with patch("geometry.ikigai_box_chart.mpf.plot",
                               side_effect=observe):
                        render_ikigai_box_chart(
                            candles, setup, Path(directory) / "bands.png",
                            symbol="TESTUSDT", timeframe="5",
                        )
                shaded = [
                    p for p in observed["axes"][0].patches
                    if isinstance(p, Rectangle) and p.get_zorder() == 0.5
                ]
                self.assertEqual(len(shaded), len(bands))
                for number, (_, _, low, high) in enumerate(bands):
                    rect = shaded[number]
                    self.assertAlmostEqual(rect.get_y(), low)
                    self.assertAlmostEqual(rect.get_height(), high - low)
                    red, green, blue = TERMINAL_BAND_RGB[
                        number % len(TERMINAL_BAND_RGB)]
                    self.assertEqual(
                        to_rgba(rect.get_facecolor())[:3],
                        (red / 255, green / 255, blue / 255),
                    )

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
            import mplfinance as mpf
            actual_plot = mpf.plot
            observed = {}

            def observe_plot(frame, **options):
                observed["frame"] = frame
                return actual_plot(frame, **options)

            with patch(
                "geometry.ikigai_box_chart.mpf.plot",
                side_effect=observe_plot,
            ):
                render_ikigai_box_chart(
                    future, setup, Path(directory) / "only-past.png",
                    symbol="TESTUSDT", timeframe="5",
                )
            plotted = observed["frame"]
            self.assertEqual(
                len(plotted),
                setup.as_of_index
                - max(0, setup.impulse_start_index - 10) + 1,
            )
            self.assertLess(float(plotted["high"].max()), 100_000)

    def test_render_early_watch_ready_before_second_impulse(self):
        frame, box_end = _terminal_wick_two_impulses(second=False)
        frame["time"] = [
            1_790_000_000_000 + 3_600_000 * i
            for i in range(len(frame))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frame)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        self.assertEqual(watch.phase, "BOX_READY")
        self.assertEqual(watch.as_of_index, box_end)
        self.assertIsNone(watch.first_box_exit_index)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "watch-ready.png"
            result = render_ikigai_box_chart(
                frame, watch, path, symbol="HEIUSDT", timeframe="60",
            )
            self.assertEqual(path, result)
            self.assertGreater(path.stat().st_size, 10_000)
            with path.open("rb") as image:
                self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
            # The future OHLC candle is not required to chart BOX_READY.
            extra = pd.concat([frame, pd.DataFrame([{
                "time": int(frame.iloc[-1]["time"]) + 3_600_000,
                "open": 1000, "high": 1001, "low": 999, "close": 1000,
            }])], ignore_index=True)
            path2 = Path(directory) / "watch-no-future.png"
            render_ikigai_box_chart(
                extra, watch, path2, symbol="HEIUSDT", timeframe="60",
            )
            self.assertGreater(path2.stat().st_size, 10_000)

    def test_render_break_watch_keeps_original_box_and_marks_break(self):
        from dataclasses import replace

        frame, box_end = _terminal_wick_two_impulses(second=False)
        frame["time"] = [
            1_790_000_000_000 + 3_600_000 * i
            for i in range(len(frame))
        ]
        prior = detect_ikigai_box_watches(frame)
        first = next(w for w in prior if w.anchor_identity == ("SHORT", 20, 23))
        candle = {
            "time": int(frame.iloc[-1]["time"]) + 3_600_000,
            "open": 0.1400, "high": 0.1456,
            "low": 0.1398, "close": 0.14412,
        }
        frame = pd.concat([frame, pd.DataFrame([candle])], ignore_index=True)
        watches = detect_ikigai_box_watches(
            frame, previous_watches=prior,
        )
        watch = next(w for w in watches if w.anchor_identity == first.anchor_identity)
        self.assertEqual(watch.phase, "BOX_BREAK_OBSERVED")
        self.assertEqual(watch.box_end_index, box_end)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "watch-break.png"
            render_ikigai_box_chart(
                frame, watch, target, symbol="HEIUSDT", timeframe="60",
            )
            self.assertGreater(target.stat().st_size, 10_000)
            with self.assertRaises(ValueError):
                render_ikigai_box_chart(
                    frame, replace(watch, first_box_exit_index=None),
                    Path(directory) / "invalid.png",
                    symbol="HEIUSDT", timeframe="60",
                )

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
