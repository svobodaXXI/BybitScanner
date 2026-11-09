"""Focused first-screen Finrez ranking and Moscow-period regressions."""
from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from terminal.diary.ticker_finrez import aggregate_ticker_pnl, period_start_ms


_MSK = ZoneInfo("Europe/Moscow")


def _ms(day: int, hour: int, minute: int = 0) -> int:
    return int(datetime(2026, 11, day, hour, minute, tzinfo=_MSK).timestamp() * 1000)


def _episode(symbol: str, gross: str, fees: str, closed_at: int | None):
    return SimpleNamespace(
        position_key=SimpleNamespace(symbol=SimpleNamespace(value=symbol)),
        realized_price_pnl=Decimal(gross),
        execution_fees=Decimal(fees),
        closed_at_ms=closed_at,
    )


class FinrezRankingTests(unittest.TestCase):
    def test_today_starts_at_moscow_midnight_not_device_timezone(self):
        now = _ms(9, 12)
        self.assertEqual(period_start_ms(period="TODAY", now_ms=now), _ms(9, 0))
        start, rows = aggregate_ticker_pnl(
            [
                _episode("BTCUSDT", "100", "1", _ms(8, 23, 59)),
                _episode("BTCUSDT", "-10", "0.5", _ms(9, 0)),
                _episode("ETHUSDT", "7", "1", _ms(9, 11)),
                _episode("DOGEUSDT", "100", "0", _ms(9, 12, 1)),
                _episode("ADAUSDT", "100", "0", None),
            ], period="TODAY", now_ms=now,
        )
        self.assertEqual(start, _ms(9, 0))
        self.assertEqual(rows, [
            {"symbol": "ETHUSDT", "pnl_usdt": "6", "trade_count": 1},
            {"symbol": "BTCUSDT", "pnl_usdt": "-10.5", "trade_count": 1},
        ])

    def test_all_time_sums_each_ticker_and_subtracts_fees_once(self):
        _, rows = aggregate_ticker_pnl([
            _episode("BTCUSDT", "5", "1", _ms(8, 23)),
            _episode("ETHUSDT", "-1", "0.2", _ms(9, 0)),
            _episode("BTCUSDT", "-2", "0.5", _ms(9, 10)),
            _episode("XRPUSDT", "0", "0", _ms(9, 10)),
        ], period="ALL", now_ms=_ms(9, 11))
        self.assertEqual(rows, [
            {"symbol": "BTCUSDT", "pnl_usdt": "1.5", "trade_count": 2},
            {"symbol": "XRPUSDT", "pnl_usdt": "0", "trade_count": 1},
            {"symbol": "ETHUSDT", "pnl_usdt": "-1.2", "trade_count": 1},
        ])

    def test_rejects_unknown_period_and_negative_time(self):
        for period, now in [("WEEK", _ms(9, 12)), ("TODAY", -1)]:
            with self.assertRaises(ValueError):
                period_start_ms(period=period, now_ms=now)


if __name__ == "__main__":
    unittest.main()
