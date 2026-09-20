"""Narrow offline tests for the Ikigai Box trade overlay (presentation only).

No Scanner, Telegram, Robot, orders or candidate creation are involved: the
overlay only computes PLANNED levels for the chart/card.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from matplotlib.collections import LineCollection

from geometry.ikigai_box import detect_ikigai_box, detect_ikigai_box_watches
from geometry.ikigai_box_chart import _stage_caption, render_ikigai_box_chart
from geometry.ikigai_box_overlay import (
    FALLBACK_STOP_FRACTION,
    GRID_ORDERS,
    build_entry_grid,
    build_trade_overlay,
)
from tests.test_ikigai_box_detector import (
    _terminal_wick_two_impulses,
    _two_impulses,
)


def _confirmed(direction, second_steps):
    candles, _, _ = _two_impulses(direction, second_steps=second_steps)
    candles["time"] = [
        1_790_000_000_000 + 300_000 * n for n in range(len(candles))
    ]
    setup = detect_ikigai_box(candles)
    assert setup is not None
    return candles, setup


def _with_last_bar(candles, **bar):
    changed = candles.copy(deep=True)
    for column, value in bar.items():
        changed.loc[changed.index[-1], column] = value
    return changed


class IkigaiBoxOverlayTests(unittest.TestCase):
    def test_watch_before_1_618_is_observation_without_entry_zone(self):
        frame, _ = _terminal_wick_two_impulses(second=False)
        frame["time"] = [
            1_790_000_000_000 + 3_600_000 * i for i in range(len(frame))
        ]
        watch = next(
            w for w in detect_ikigai_box_watches(frame)
            if w.anchor_identity == ("SHORT", 20, 23)
        )
        overlay = build_trade_overlay(frame, watch)

        self.assertEqual(overlay.stage, "BOX_READY")
        self.assertFalse(overlay.level_1_618_reached)
        self.assertFalse(overlay.entry_zone_active)
        self.assertIsNone(overlay.grid)
        self.assertIsNone(overlay.stop)
        self.assertEqual(overlay.target_price, watch.fibonacci_1_0)
        self.assertIn("НЕ достигнут", _stage_caption(overlay))

    def test_reached_1_618_builds_four_quarter_limits_beyond_the_level(self):
        for direction, side, sign in ((1, "SHORT", 1), (-1, "LONG", -1)):
            with self.subTest(side=side):
                candles, setup = _confirmed(direction, 6)
                overlay = build_trade_overlay(candles, setup)

                self.assertEqual(setup.direction, side)
                self.assertTrue(overlay.level_1_618_reached)
                self.assertTrue(overlay.entry_zone_active)
                grid = overlay.grid
                self.assertEqual(len(grid.prices), GRID_ORDERS)
                self.assertAlmostEqual(
                    grid.size_fraction_each * len(grid.prices), 1.0
                )
                self.assertEqual(grid.anchor_price, setup.fibonacci_1_618)
                # Ordered nearest -> furthest in the leg-two direction.
                self.assertEqual(
                    list(grid.prices), sorted(grid.prices)[::sign]
                )
                gaps = [
                    abs(b - a) for a, b in zip(grid.prices, grid.prices[1:])
                ]
                for gap in gaps:
                    self.assertAlmostEqual(gap, gaps[0])
                # 1.618 sits inside the zone and the FURTHEST limit is past it.
                self.assertLessEqual(min(grid.prices), grid.anchor_price)
                self.assertGreaterEqual(max(grid.prices), grid.anchor_price)
                self.assertGreater(
                    (grid.prices[-1] - grid.anchor_price) * sign, 0
                )
                self.assertTrue(grid.furthest_beyond_anchor)
                # Most of the grid fills BEFORE price reaches 1.618: three on
                # the approach side, only the furthest one beyond the level.
                approach = [
                    p for p in grid.prices
                    if (p - grid.anchor_price) * sign < 0
                ]
                beyond = [
                    p for p in grid.prices
                    if (p - grid.anchor_price) * sign > 0
                ]
                self.assertEqual((len(approach), len(beyond)), (3, 1))
                self.assertEqual(beyond, [grid.prices[-1]])
                # The secondary 2.618 area is not swallowed by the first grid.
                self.assertLess(
                    (grid.prices[-1] - setup.fibonacci_2_618) * sign, 0
                )
                self.assertIn("ДОСТИГНУТ", _stage_caption(overlay))
                self.assertIn("НЕ сигнал входа", _stage_caption(overlay))

    def test_grid_structure_is_reusable_for_the_2_618_zone_later(self):
        _, setup = _confirmed(-1, 6)
        grid = build_entry_grid(setup, anchor_level=2.618)

        self.assertEqual(grid.anchor_price, setup.fibonacci_2_618)
        self.assertTrue(grid.furthest_beyond_anchor)
        self.assertLess(grid.prices[-1], setup.fibonacci_2_618)  # LONG: below
        self.assertTrue(grid.spacing_is_placeholder)

    def test_fallback_stop_is_minus_1_5_percent_from_planned_entry(self):
        for direction, sign in ((1, 1), (-1, -1)):
            with self.subTest(direction=direction):
                candles, setup = _confirmed(direction, 6)
                overlay = build_trade_overlay(candles, setup)
                stop = overlay.stop
                reference = sum(overlay.grid.prices) / GRID_ORDERS

                self.assertEqual(stop.basis, "FALLBACK_-1.5%")
                self.assertIsNone(stop.anchor_index)
                self.assertAlmostEqual(stop.reference_entry, reference)
                self.assertAlmostEqual(
                    stop.price, reference * (1 + sign * FALLBACK_STOP_FRACTION)
                )
                # LONG stop below entry, SHORT stop above entry.
                self.assertGreater((stop.price - reference) * sign, 0)

    def test_reversal_candle_extreme_becomes_the_stop(self):
        candles, setup = _confirmed(1, 6)          # SHORT
        star = _with_last_bar(
            candles, open=113.3, close=113.2, high=114.4, low=113.15,
        )
        short = build_trade_overlay(star, setup).stop
        self.assertEqual(short.basis, "REVERSAL_CANDLE")
        self.assertEqual(short.anchor_kind, "SHOOTING_STAR")
        self.assertEqual(short.price, 114.4)
        self.assertEqual(short.anchor_index, setup.as_of_index)

        candles, setup = _confirmed(-1, 6)         # LONG
        hammer = _with_last_bar(
            candles, open=186.7, close=186.8, high=186.85, low=185.6,
        )
        long_ = build_trade_overlay(hammer, setup).stop
        self.assertEqual(long_.basis, "REVERSAL_CANDLE")
        self.assertEqual(long_.anchor_kind, "HAMMER")
        self.assertEqual(long_.price, 185.6)

    def test_reversal_extreme_that_does_not_protect_falls_back(self):
        candles, setup = _confirmed(1, 6)
        # F(1.618) is touched one bar earlier; the last bar is a pin bar whose
        # high stays below the planned average entry, so it cannot protect it.
        touch = candles.copy(deep=True)
        touch.loc[touch.index[-2], "high"] = 113.40
        weak = _with_last_bar(
            touch, open=112.75, close=112.73, high=112.80, low=112.72,
        )
        stop = build_trade_overlay(weak, setup).stop

        self.assertEqual(stop.basis, "FALLBACK_-1.5%")
        self.assertGreater(stop.price, stop.reference_entry)

    def test_overlay_never_reads_candles_after_as_of(self):
        candles, setup = _confirmed(-1, 6)
        future = pd.concat([candles, pd.DataFrame([{
            "time": int(candles["time"].iloc[-1]) + 300_000,
            "open": 1.0, "high": 1.0, "low": 0.5, "close": 1.0,
        }])], ignore_index=True)

        self.assertEqual(
            build_trade_overlay(candles, setup),
            build_trade_overlay(future, setup),
        )
        # A malformed future candle must not even be converted to float:
        # as_of is a hard provenance boundary, not just a comparison bound.
        for column in ("open", "high", "low", "close"):
            # pandas 3 rejects assigning a string into a float64 column.
            # Cast explicitly so the intentionally malformed FUTURE row
            # tests our as_of boundary, not pandas assignment semantics.
            future[column] = future[column].astype(object)
            future.loc[future.index[-1], column] = "NOT_YET_KNOWN"
        self.assertEqual(
            build_trade_overlay(candles, setup),
            build_trade_overlay(future, setup),
        )


class IkigaiBoxOverlayChartTests(unittest.TestCase):
    def _segments(self, sample, watch=None):
        import mplfinance as mpf
        actual_plot = mpf.plot
        observed = {}

        def observe(frame, **options):
            observed["figure"], observed["axes"] = actual_plot(frame, **options)
            return observed["figure"], observed["axes"]

        candles, setup = sample
        with tempfile.TemporaryDirectory() as directory:
            with patch("geometry.ikigai_box_chart.mpf.plot", side_effect=observe):
                path = render_ikigai_box_chart(
                    candles, setup, Path(directory) / "overlay.png",
                    symbol="TESTUSDT", timeframe="5",
                )
            self.assertGreater(path.stat().st_size, 10_000)
        axes = observed["axes"][0]
        if build_trade_overlay(candles, setup).grid is not None:
            labels = [
                item for item in axes.texts
                if item.get_text().startswith("Схема сетки")
            ]
            self.assertEqual(len(labels), 1)
            # The four-order illustration must be outside the candle plot,
            # not obscuring the latest post-1.618 bars.
            self.assertGreater(labels[0].get_position()[0], 1.0)
            self.assertIs(labels[0].get_transform(), axes.get_yaxis_transform())
        return [
            segment
            for collection in axes.collections
            if isinstance(collection, LineCollection)
            for segment in collection.get_segments()
        ]

    def _has_line(self, segments, price):
        return any(
            abs(a[1] - price) < 1e-8 and abs(b[1] - price) < 1e-8
            for a, b in segments
        )

    def test_reached_chart_draws_grid_stop_and_target_lines(self):
        for direction in (1, -1):
            with self.subTest(direction=direction):
                candles, setup = _confirmed(direction, 6)
                overlay = build_trade_overlay(candles, setup)
                segments = self._segments((candles, setup))

                for price in overlay.grid.prices:
                    self.assertTrue(self._has_line(segments, price), price)
                self.assertTrue(self._has_line(segments, overlay.stop.price))
                self.assertTrue(self._has_line(segments, overlay.target_price))

    def test_observation_chart_has_no_grid_or_stop_lines(self):
        candles, setup = _confirmed(-1, 3)
        overlay = build_trade_overlay(candles, setup)
        self.assertFalse(overlay.level_1_618_reached)

        segments = self._segments((candles, setup))
        # A grid built for comparison must NOT be drawn while only observing.
        # (F(1.618) itself is always drawn as a Fibonacci line, so skip it.)
        grid = build_entry_grid(setup)
        for price in grid.prices:
            if abs(price - grid.anchor_price) > 1e-9:
                self.assertFalse(self._has_line(segments, price), price)
        self.assertTrue(self._has_line(segments, overlay.target_price))


if __name__ == "__main__":
    unittest.main()
