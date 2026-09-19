import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

import robot_position_chart as chart
from robot_position_chart import PositionChartError, render_position_chart
from robot_position_view import (
    CAPTION_LIMIT, ENTRY_BEFORE_CHART_LINE, NOT_ROBOT_LINE, PositionView, TradeMarker,
    chart_candle_limit, format_position_card, load_position_view, signal_chart_candle_minutes,
    with_last_price,
)
from terminal.domain.models import OrderSide, PositionSide, Symbol

START_MS = 1_789_760_640_000  # aligned to a minute


def _trade(**overrides):
    values = dict(
        trade_id="robot-trade-1", candidate_id="cand-1", symbol=Symbol("SAGAUSDT"),
        direction="LONG", pattern="Falling Wedge", entry_path="LIMIT",
        entry_time_ms=START_MS + 120 * 60_000, average_entry=Decimal("0.0254"),
        stop_price=Decimal("0.0249"), take_price=Decimal("0.0284"),
        entry_quantity=Decimal("100"), exit_time_ms=None, exit_price=None,
        exit_reason=None, realized_pnl_usdt=None, realized_pnl_pct=None, fees_costs_usdt=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _snapshot():
    return {
        "pattern": "Falling Wedge",
        "scanner_geometry_cursor": {
            "version": "1.0", "timeframe": "1", "geometry_index": 199,
            "source_candle_time_ms": START_MS + 100 * 60_000,
        },
        "robot_geometry": {
            "current_index": 199, "scanner_source_timeframe": "1",
            "upper_line": {"slope": -0.00001, "intercept": 0.0280, "anchor_index": 120},
            "lower_line": {"slope": -0.000002, "intercept": 0.0247, "anchor_index": 125},
            "apex": {"index": 390.0},
        },
    }


def _view(**overrides):
    values = dict(
        symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("100"),
        average_entry=Decimal("0.0254"), stop_price=Decimal("0.0249"),
        take_price=Decimal("0.0284"), pattern="Falling Wedge", trade=_trade(),
        signal_snapshot=_snapshot(),
    )
    values.update(overrides)
    return PositionView(**values)


FIVE_MIN_MS = 5 * 60_000
CANDLES_START_MS = START_MS - START_MS % FIVE_MIN_MS  # 5m candles open on a 5-minute boundary


def _candles(count=300):
    times = [CANDLES_START_MS + index * FIVE_MIN_MS for index in range(count)]
    close = [0.0255 + 0.0002 * ((index % 20) - 10) / 10 for index in range(count)]
    return pd.DataFrame({
        "time": times,
        "open": close,
        "high": [value + 0.0001 for value in close],
        "low": [value - 0.0001 for value in close],
        "close": close,
        "volume": [1.0] * count,
    })


class FormatPositionCardTests(unittest.TestCase):
    def test_open_robot_long_card(self):
        card = format_position_card(with_last_price(_view(), "0.0260"))
        self.assertTrue(card.startswith("SAGAUSDT · LONG"))
        self.assertIn("Статус: открыта", card)
        self.assertIn("Размер: 100", card)
        self.assertIn("Средний вход: 0.0254", card)
        self.assertIn("PnL: ≈ +0.06 USDT (+2.36%)", card)
        self.assertIn("STOP: 0.0249", card)
        self.assertIn("TAKE: 0.0284", card)
        self.assertIn("Паттерн: Falling Wedge", card)
        self.assertNotIn(NOT_ROBOT_LINE, card)

    def test_short_pnl_sign_and_missing_price(self):
        short = _view(direction="SHORT")
        # U+2212 minus, two decimals, no "~".
        self.assertIn("PnL: ≈ −0.06 USDT (−2.36%)", format_position_card(with_last_price(short, "0.0260")))
        self.assertIn("PnL: —", format_position_card(short))

    def test_pnl_always_two_decimals_and_zero_is_plus(self):
        card = format_position_card(with_last_price(_view(quantity=Decimal("10000")), "0.02573"))
        self.assertIn("PnL: ≈ +3.30 USDT (+1.30%)", card)
        flat = format_position_card(with_last_price(_view(), "0.0254"))
        self.assertIn("PnL: ≈ +0.00 USDT (+0.00%)", flat)
        self.assertNotIn("~", card)

    def test_entry_before_chart_line(self):
        self.assertNotIn(ENTRY_BEFORE_CHART_LINE, format_position_card(_view()))
        self.assertIn(ENTRY_BEFORE_CHART_LINE, format_position_card(_view(entry_before_chart=True)))

    def test_manual_position_card_has_no_chart_line(self):
        card = format_position_card(_view(
            symbol="CELOUSDT", trade=None, signal_snapshot=None, pattern=None,
            stop_price=None, take_price=None,
        ))
        self.assertIn("STOP: —", card)
        self.assertIn("Паттерн: —", card)
        self.assertTrue(card.endswith(NOT_ROBOT_LINE))

    def test_closed_trade_card(self):
        trade = _trade(
            exit_time_ms=START_MS + 200 * 60_000, exit_price=Decimal("0.0249"),
            exit_reason="STOP", realized_pnl_usdt=Decimal("-0.05"),
            realized_pnl_pct=Decimal("-2.02"), fees_costs_usdt=Decimal("0.0013"),
        )
        card = format_position_card(_view(is_open=False, trade=trade, fees_usdt=Decimal("0.0026")))
        self.assertIn("Статус: закрыта", card)
        self.assertIn("Выход: 0.0249 (по стопу)", card)
        # Before fees, then entry + exit fees and (-0.05 - 0.0026) / (100 * 0.0254) * 100.
        self.assertIn(
            "Итог: -0.05 USDT (до комиссий), комиссии 0.0026 USDT (вход + выход), "
            "-2.07% (после комиссий)",
            card,
        )
        self.assertNotIn("PnL:", card)

    def test_caption_fits_telegram_limit(self):
        card = format_position_card(_view(pattern="X" * 2000))
        self.assertLessEqual(len(card), CAPTION_LIMIT)


class ChartCandleLimitTests(unittest.TestCase):
    NOW = START_MS + 2_000 * 60_000

    def _minutes_ago(self, minutes):
        return self.NOW - minutes * 60_000

    def test_short_position_uses_minimum_window(self):
        self.assertEqual(chart_candle_limit(self._minutes_ago(30), self.NOW), (120, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(6 * 60), self.NOW), (120, False))
        self.assertEqual(chart_candle_limit(None, self.NOW), (120, False))

    def test_longer_position_covers_entry_plus_margin(self):
        # ceil(minutes / 5) + 24
        self.assertEqual(chart_candle_limit(self._minutes_ago(12 * 60), self.NOW), (168, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(12 * 60 + 1), self.NOW), (169, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(24 * 60), self.NOW), (312, False))

    def test_window_is_capped_and_old_entry_is_flagged(self):
        self.assertEqual(chart_candle_limit(self._minutes_ago(81 * 60), self.NOW), (996, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(82 * 60), self.NOW), (1000, False))
        # The entry candle is still the oldest of the 1000 / already outside them.
        self.assertEqual(chart_candle_limit(self._minutes_ago(4_999), self.NOW), (1000, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(5_000), self.NOW), (1000, True))
        self.assertEqual(chart_candle_limit(self._minutes_ago(90 * 60), self.NOW), (1000, True))


class ChartTimeframeTests(unittest.TestCase):
    NOW = START_MS + 2_000 * 60_000

    def test_signal_timeframe_source_and_fallbacks(self):
        for snapshot, expected in (
            ({"scanner_source_timeframe": "5"}, 5),
            ({"scanner_source_timeframe": "1"}, 1),
            ({"scanner_source_timeframe": 15}, 15),
            ({"robot_geometry": {"scanner_source_timeframe": "1"}}, 1),
            ({"scanner_source_timeframe": "junk", "robot_geometry": {"scanner_source_timeframe": "1"}}, 1),
            ({"scanner_source_timeframe": "7"}, 5),
            ({"scanner_source_timeframe": "junk"}, 5),
            ({"scanner_source_timeframe": None, "robot_geometry": "junk"}, 5),
            ({}, 5),
            (None, 5),
        ):
            with self.subTest(snapshot=snapshot):
                self.assertEqual(signal_chart_candle_minutes(snapshot), expected)

    def _minutes_ago(self, minutes):
        return self.NOW - minutes * 60_000

    def test_one_minute_limit(self):
        self.assertEqual(chart_candle_limit(self._minutes_ago(30), self.NOW, 1), (300, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(6 * 60), self.NOW, 1), (384, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(999), self.NOW, 1), (1000, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(1000), self.NOW, 1), (1000, True))
        self.assertEqual(chart_candle_limit(self._minutes_ago(17 * 60), self.NOW, 1), (1000, True))
        self.assertEqual(chart_candle_limit(None, self.NOW, 1), (300, False))

    def test_other_timeframes_use_120_minimum(self):
        self.assertEqual(chart_candle_limit(self._minutes_ago(30), self.NOW, 15), (120, False))
        self.assertEqual(chart_candle_limit(self._minutes_ago(60 * 60), self.NOW, 15), (264, False))


class LoadPositionViewTests(unittest.TestCase):
    def _store(self, *, trade, protection=None, limit_status="filled"):
        execution = lambda order_id, ts, side: SimpleNamespace(
            order_id=order_id, exchange_timestamp_ms=ts, side=side,
            price=SimpleNamespace(value=Decimal("0.0254")), fee=Decimal("0.001"),
        )
        entry = execution("limit-1", trade.entry_time_ms, OrderSide.BUY)
        other = execution("other", trade.entry_time_ms + 1_000, OrderSide.BUY)
        stale = execution("old", trade.entry_time_ms - 60_000, OrderSide.SELL)
        return SimpleNamespace(
            get_position_projection=lambda key: SimpleNamespace(
                side=PositionSide.LONG, quantity=SimpleNamespace(value=Decimal("100")),
                average_entry=SimpleNamespace(value=Decimal("0.0255")),
                sync_state="synced",
            ),
            get_open_robot_trade_for_symbol=lambda account, symbol: trade,
            get_robot_trade=lambda trade_id: trade,
            get_protection_projection=lambda key: protection,
            get_robot_candidate=lambda candidate_id: SimpleNamespace(
                signal_snapshot=_snapshot(),
                robot_state={"execution": {"limit_order_id": "limit-1"}},
            ),
            load_executions_for_order=lambda account, order_id: (
                (entry,) if order_id.value == "limit-1" else ()
            ),
            load_executions_for_symbol=lambda account, symbol: (stale, entry, other),
            get_paper_limit=lambda order_id, account: SimpleNamespace(
                status=limit_status, price=Decimal("0.0250"), side=OrderSide.BUY,
                created_at_ms=START_MS,
            ),
        )

    def test_limit_entry_uses_order_executions_and_protection_levels(self):
        protection = SimpleNamespace(stop_loss=Decimal("0.0248"), take_profit=None)
        view = load_position_view(self._store(trade=_trade(), protection=protection), "sagausdt")
        self.assertEqual(view.average_entry, Decimal("0.0255"))
        self.assertEqual(view.stop_price, Decimal("0.0248"))
        self.assertEqual(view.take_price, Decimal("0.0284"))
        self.assertEqual([m.filled for m in view.markers], [True])
        # The frozen snapshot is a 1m signal (robot_geometry.scanner_source_timeframe).
        self.assertEqual(view.chart_candle_minutes, 1)

    def test_only_open_paper_limit_from_robot_state_becomes_hollow_marker(self):
        # Resting (open / partially_filled) -> hollow; the filled part stays a filled triangle.
        for status, expected in (
            ("open", [("Buy", True), ("Buy", False)]),
            ("partially_filled", [("Buy", True), ("Buy", False)]),
            ("filled", [("Buy", True)]),
            ("cancelled", [("Buy", True)]),
        ):
            with self.subTest(status=status):
                view = load_position_view(self._store(trade=_trade(), limit_status=status), "SAGAUSDT")
                self.assertEqual([(m.side, m.filled) for m in view.markers], expected)
                if not view.markers[-1].filled:
                    self.assertEqual(
                        (view.markers[-1].price, view.markers[-1].time_ms),
                        (Decimal("0.0250"), START_MS),
                    )

    def test_market_entry_uses_time_window_and_open_limit_is_hollow(self):
        store = self._store(trade=_trade(entry_path="MARKET"), limit_status="open")
        view = load_position_view(store, "SAGAUSDT", now_ms=_trade().entry_time_ms + 2_000)
        self.assertEqual([(m.side, m.filled) for m in view.markers],
                         [("Buy", True), ("Buy", True), ("Buy", False)])

    def test_closed_trade_fees_sum_entry_and_exit_executions(self):
        exit_ms = _trade().entry_time_ms + 60 * 60_000
        trade = _trade(
            exit_time_ms=exit_ms, exit_price=Decimal("0.0249"), exit_reason="STOP",
            realized_pnl_usdt=Decimal("-0.05"), realized_pnl_pct=Decimal("-2.02"),
            fees_costs_usdt=Decimal("0.0013"),  # closing leg only; not what the card shows
        )
        fill = lambda order_id, ts, side, price, fee: SimpleNamespace(
            order_id=order_id, exchange_timestamp_ms=ts, side=side,
            price=SimpleNamespace(value=Decimal(price)), fee=Decimal(fee),
        )
        # Two partial fills of the entry limit, then the closing fill.
        partials = (
            fill("limit-1", trade.entry_time_ms, OrderSide.BUY, "0.0254", "0.0005"),
            fill("limit-1", trade.entry_time_ms + 30_000, OrderSide.BUY, "0.0254", "0.0008"),
        )
        closing = fill("stop-1", exit_ms, OrderSide.SELL, "0.0249", "0.0013")
        unrelated = (
            fill("next-entry", exit_ms + 1_000, OrderSide.BUY, "0.0249", "0.5"),
            fill("old", trade.entry_time_ms - 60_000, OrderSide.SELL, "0.0260", "0.5"),
        )
        for entry_path in ("LIMIT", "MARKET"):
            with self.subTest(entry_path=entry_path):
                store = self._store(trade=_trade(**{**vars(trade), "entry_path": entry_path}))
                store.load_executions_for_order = lambda account, order_id: (
                    partials if order_id.value == "limit-1" else ()
                )
                symbol_fills = (unrelated[1], *partials, closing)
                if entry_path == "LIMIT":
                    symbol_fills += (unrelated[0],)  # excluded by side at exit time
                store.load_executions_for_symbol = lambda account, symbol, f=symbol_fills: f
                view = load_position_view(store, "SAGAUSDT", trade_id="robot-trade-1")

                self.assertEqual(view.fees_usdt, Decimal("0.0026"))
                self.assertEqual([(m.side, m.filled) for m in view.markers],
                                 [("Buy", True), ("Buy", True), ("Sell", True)])
                self.assertIn(
                    "комиссии 0.0026 USDT (вход + выход), -2.07% (после комиссий)",
                    format_position_card(view),
                )


class RenderPositionChartTests(unittest.TestCase):
    def test_renders_non_empty_png_with_lines_levels_and_markers(self):
        markers = (
            TradeMarker(START_MS + 120 * 60_000 + 500, Decimal("0.0254"), "Buy", True),
            TradeMarker(START_MS + 250 * 60_000, Decimal("0.0250"), "Buy", False),
        )
        trade = _trade(exit_time_ms=START_MS + 280 * 60_000, exit_price=Decimal("0.0249"))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "robot" / "SAGAUSDT_position.png"
            with patch("robot_position_chart._draw_marker", wraps=chart._draw_marker) as draw:
                result = render_position_chart(
                    _view(markers=markers, trade=trade, is_open=False), _candles(), out,
                )
            self.assertEqual(result, out)
            self.assertGreater(out.stat().st_size, 0)
            self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        # Entry fill, hollow resting limit, and the robot_trades exit (no matching execution).
        self.assertEqual(
            [(c.args[3], c.kwargs["filled"]) for c in draw.call_args_list],
            [("Buy", True), ("Buy", False), ("Sell", True)],
        )

    def test_renders_wide_window_of_max_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "wide.png"
            render_position_chart(_view(), _candles(1000), out)
            self.assertEqual(out.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_market_exit_execution_is_drawn_once(self):
        exit_ms = START_MS + 200 * 60_000
        markers = (
            TradeMarker(START_MS + 150 * 60_000, Decimal("0.0254"), "Sell", True),
            TradeMarker(exit_ms + 1_500, Decimal("0.0258"), "Buy", True),
        )
        trade = _trade(
            direction="SHORT", entry_path="MARKET", exit_time_ms=exit_ms,
            exit_price=Decimal("0.0258"),
        )
        view = _view(direction="SHORT", markers=markers, trade=trade, is_open=False)
        with tempfile.TemporaryDirectory() as directory, \
                patch("robot_position_chart._draw_marker", wraps=chart._draw_marker) as draw:
            render_position_chart(view, _candles(), Path(directory) / "x.png")
        self.assertEqual(
            [(c.args[3], c.kwargs["filled"]) for c in draw.call_args_list],
            [("Sell", True), ("Buy", True)],
        )

    def test_candle_position_covers_every_minute_of_a_5m_candle(self):
        times = np.array([CANDLES_START_MS + i * FIVE_MIN_MS for i in range(3)], dtype="int64")
        for minute, second, expected in (
            (0, 0, 0), (1, 0, 0), (4, 0, 0), (4, 59, 0), (5, 0, 1), (9, 0, 1), (10, 0, 2),
        ):
            with self.subTest(minute=minute, second=second):
                time_ms = CANDLES_START_MS + minute * 60_000 + second * 1_000
                self.assertEqual(chart._candle_position(times, time_ms, FIVE_MIN_MS), expected)
        self.assertIsNone(chart._candle_position(times, CANDLES_START_MS - 1, FIVE_MIN_MS))
        self.assertIsNone(chart._candle_position(times, CANDLES_START_MS + 15 * 60_000, FIVE_MIN_MS))

    def test_1m_signal_chart_uses_1m_candles_and_title(self):
        candles = _candles(300)
        candles["time"] = [START_MS + index * 60_000 for index in range(300)]
        base = START_MS + 40 * 60_000
        markers = (
            TradeMarker(base + 700, Decimal("0.0254"), "Buy", True),
            TradeMarker(base + 60_000 + 700, Decimal("0.0254"), "Buy", True),
        )
        with tempfile.TemporaryDirectory() as directory, \
                patch("robot_position_chart._draw_marker", wraps=chart._draw_marker) as draw, \
                patch("robot_position_chart.mpf.plot", wraps=chart.mpf.plot) as plot:
            render_position_chart(
                _view(markers=markers, chart_candle_minutes=1), candles, Path(directory) / "x.png",
            )
        self.assertEqual([c.args[1] for c in draw.call_args_list], [40, 41])
        self.assertTrue(plot.call_args.kwargs["title"].endswith("| LONG | 1m"))

    def test_fills_inside_one_5m_candle_share_it_and_title_says_5m(self):
        candle = CANDLES_START_MS + 40 * FIVE_MIN_MS
        markers = tuple(
            TradeMarker(candle + minute * 60_000 + 700, Decimal("0.0254"), "Buy", True)
            for minute in (0, 1, 4, 5)
        )
        with tempfile.TemporaryDirectory() as directory, \
                patch("robot_position_chart._draw_marker", wraps=chart._draw_marker) as draw, \
                patch("robot_position_chart.mpf.plot", wraps=chart.mpf.plot) as plot:
            render_position_chart(_view(markers=markers), _candles(), Path(directory) / "x.png")
        self.assertEqual([c.args[1] for c in draw.call_args_list], [40, 40, 40, 41])
        self.assertTrue(plot.call_args.kwargs["title"].endswith("| LONG | 5m"))

    def test_hollow_marker_has_outline_only(self):
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            chart._draw_marker(ax, 0, 1.0, "Buy", filled=False)
            chart._draw_marker(ax, 1, 1.0, "Buy", filled=True)
            hollow, filled = ax.collections
            self.assertEqual(len(hollow.get_facecolor()), 0)
            self.assertEqual(len(hollow.get_edgecolor()), 1)
            self.assertEqual(len(filled.get_facecolor()), 1)
        finally:
            plt.close(fig)

    def test_renders_without_frozen_geometry(self):
        with tempfile.TemporaryDirectory() as directory:
            out = render_position_chart(
                _view(signal_snapshot={}), _candles(50), Path(directory) / "x.png",
            )
            self.assertGreater(out.stat().st_size, 0)

    def test_empty_candles_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PositionChartError):
                render_position_chart(_view(), pd.DataFrame(), Path(directory) / "x.png")


if __name__ == "__main__":
    unittest.main()
