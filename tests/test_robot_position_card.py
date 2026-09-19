import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import robot_position_chart as chart
from robot_position_chart import PositionChartError, render_position_chart
from robot_position_view import (
    CAPTION_LIMIT, NOT_ROBOT_LINE, PositionView, TradeMarker, format_position_card,
    load_position_view, with_last_price,
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
        exit_reason=None, realized_pnl_usdt=None, realized_pnl_pct=None,
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


def _candles(count=300):
    times = [START_MS + index * 60_000 for index in range(count)]
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
        self.assertIn("PnL: ~+0.06 USDT (+2.36%)", card)
        self.assertIn("STOP: 0.0249", card)
        self.assertIn("TAKE: 0.0284", card)
        self.assertIn("Паттерн: Falling Wedge", card)
        self.assertNotIn(NOT_ROBOT_LINE, card)

    def test_short_pnl_sign_and_missing_price(self):
        short = _view(direction="SHORT")
        self.assertIn("PnL: ~-0.06 USDT (-2.36%)", format_position_card(with_last_price(short, "0.0260")))
        self.assertIn("PnL: —", format_position_card(short))

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
            exit_reason="STOP", realized_pnl_usdt=Decimal("-5.17"),
            realized_pnl_pct=Decimal("-2.13"),
        )
        card = format_position_card(_view(is_open=False, trade=trade))
        self.assertIn("Статус: закрыта", card)
        self.assertIn("Выход: 0.0249 (STOP)", card)
        self.assertIn("PnL: -5.17 USDT (-2.13%)", card)

    def test_caption_fits_telegram_limit(self):
        card = format_position_card(_view(pattern="X" * 2000))
        self.assertLessEqual(len(card), CAPTION_LIMIT)


class LoadPositionViewTests(unittest.TestCase):
    def _store(self, *, trade, protection=None, limit_status="filled"):
        execution = lambda order_id, ts, side: SimpleNamespace(
            order_id=order_id, exchange_timestamp_ms=ts, side=side,
            price=SimpleNamespace(value=Decimal("0.0254")),
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
