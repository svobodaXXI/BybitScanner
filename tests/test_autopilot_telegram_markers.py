"""Telegram Robot markers must be identical to the chart's durable evidence."""
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from terminal.domain.models import Symbol
from terminal.runtime.paper_http_server import _robot_position_markers


def trade(trade_id="robot-trade-1"):
    return SimpleNamespace(trade_id=trade_id)


class TelegramMarkerParityTests(unittest.TestCase):
    def test_proven_open_robot_trade_uses_telegram_markers_exactly(self):
        expected = (
            SimpleNamespace(time_ms=1800000000001, price=Decimal("1.2345"), side="Buy", filled=True),
            SimpleNamespace(time_ms=1800000000010, price=Decimal("1.236"), side="Sell", filled=False),
        )
        def lookup(account, symbol):
            self.assertEqual(account.value, "paper")
            self.assertEqual(symbol.value, "BTCUSDT")
            return trade()
        store = SimpleNamespace(get_open_robot_trade_for_symbol=lookup)
        view = SimpleNamespace(
            trade=trade(), is_open=True, is_robot=True,
            quantity=Decimal("4"), markers=expected,
        )
        with patch("robot_position_view.load_position_view", return_value=view) as load:
            result = _robot_position_markers(
                SimpleNamespace(store=store), "BTCUSDT", "robot-trade-1", 1800000001000,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "robot_position_view.TradeMarker")
        self.assertEqual(result["account_id"], "paper")
        self.assertEqual(result["markers"], [
            {"time_ms": 1800000000001, "price": "1.2345", "side": "Buy", "filled": True},
            {"time_ms": 1800000000010, "price": "1.236", "side": "Sell", "filled": False},
        ])
        load.assert_called_once()

    def test_ambiguous_or_different_trade_id_never_leaks_markers(self):
        for active in (None, trade("other-trade")):
            store = SimpleNamespace(get_open_robot_trade_for_symbol=lambda *_: active)
            with patch("robot_position_view.load_position_view") as load:
                result = _robot_position_markers(
                    SimpleNamespace(store=store), "BTCUSDT", "robot-trade-1", 1800000001000,
                )
            self.assertEqual(result, {"ok": False, "error": "unproven_robot_position"})
            load.assert_not_called()

    def test_flat_unproven_position_must_not_show_even_real_trade_markers(self):
        store = SimpleNamespace(get_open_robot_trade_for_symbol=lambda *_: trade())
        view = SimpleNamespace(
            trade=trade(), is_open=True, is_robot=True,
            quantity=Decimal("0"), markers=(SimpleNamespace(time_ms=1),),
        )
        with patch("robot_position_view.load_position_view", return_value=view):
            result = _robot_position_markers(
                SimpleNamespace(store=store), "BTCUSDT", "robot-trade-1", 1800000001000,
            )
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
