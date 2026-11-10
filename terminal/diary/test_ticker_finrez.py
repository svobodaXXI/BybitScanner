"""Focused first-screen Finrez ranking and Moscow-period regressions."""
from __future__ import annotations

import unittest
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from terminal.diary.ticker_finrez import aggregate_ticker_pnl, period_start_ms, project_paper_ticker_pnl
from terminal.diary.models import (
    AllocationRole, DiaryEnvironment, ExecutionAllocation, TradeEpisode, TradeEpisodeId,
)
from terminal.diary.scoped_statistics_archive import StatisticsScopeError
from terminal.diary.scoped_statistics_reporter import PaperSourceSnapshot
from terminal.domain.models import (
    Category, ExecutionDedupKey, ExecutionId, Origin, PositionKey, PositionSide,
    Price, Quantity, Symbol, TradingAccountId,
)


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




def _scoped_episode(suffix: str, symbol: str, roles_and_origins, *, closed_at=None):
    """Typed immutable episode and exact per-execution controller evidence."""
    episode_id = TradeEpisodeId(suffix)
    allocations = []
    origins = {}
    for index, (role, origin) in enumerate(roles_and_origins):
        key = ExecutionDedupKey(TradingAccountId("paper"), Category.LINEAR, ExecutionId(f"{suffix}-{index}"))
        allocations.append(ExecutionAllocation(
            execution_key=key, trade_episode_id=episode_id, role=role,
            quantity=Decimal("1"), fee=Decimal("0.1"), occurred_at_ms=_ms(9, 9) + index,
        ))
        origins[key] = origin
    episode = TradeEpisode(
        trade_episode_id=episode_id,
        position_key=PositionKey(TradingAccountId("paper"), Category.LINEAR, Symbol(symbol), 0),
        side=PositionSide.LONG, environment=DiaryEnvironment.PAPER,
        opened_at_ms=_ms(9, 9), closed_at_ms=closed_at if closed_at is not None else _ms(9, 10),
        opening_price=Price(Decimal("100")), average_entry=Price(Decimal("100")),
        open_quantity=Quantity(Decimal("0")), realized_price_pnl=Decimal("5"),
        execution_fees=Decimal("0.1") * len(allocations), allocations=tuple(allocations),
    )
    return episode, origins


class FinrezMixedControllerTests(unittest.TestCase):
    def test_robot_manual_close_is_visible_but_not_counted_as_autonomous_robot_pnl(self):
        pure, p = _scoped_episode("robot", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.ROBOT),
        ])
        assisted, a = _scoped_episode("assisted", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.REDUCE, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        manual, m = _scoped_episode("manual", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.TERMINAL_MANUAL),
            (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        snapshot = PaperSourceSnapshot(4, (pure, assisted, manual), {**p, **a, **m})
        robot = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="ROBOT", period="TODAY", now_ms=_ms(9, 12),
        )
        self.assertEqual(robot["tickers"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.8", "trade_count": 1},
        ])
        self.assertEqual(robot["manual_interventions"], [
            {"symbol": "BTCUSDT", "pnl_usdt": "4.7", "trade_count": 1},
        ])
        manual_report = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="MANUAL", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(manual_report["tickers"], [
            {"symbol": "ETHUSDT", "pnl_usdt": "4.8", "trade_count": 1},
        ])
        self.assertEqual(manual_report["manual_interventions"], [])

    def test_assisted_only_is_not_fabricated_as_zero_trades(self):
        assisted, origins = _scoped_episode("assisted", "BTCUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        snapshot = PaperSourceSnapshot(3, (assisted,), origins)
        report = project_paper_ticker_pnl(
            snapshot, account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
        )
        self.assertEqual(report["tickers"], [])
        self.assertEqual(report["manual_interventions"][0]["trade_count"], 1)

    def test_other_mixed_or_unknown_ownership_remains_blocked(self):
        cases = [
            [(AllocationRole.OPEN, Origin.TERMINAL_MANUAL), (AllocationRole.CLOSE, Origin.ROBOT)],
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.INCREASE, Origin.TERMINAL_MANUAL),
             (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL)],
            [(AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.REDUCE, Origin.TERMINAL_MANUAL),
             (AllocationRole.CLOSE, Origin.ROBOT)],
        ]
        for i, roles in enumerate(cases):
            mixed, origins = _scoped_episode(f"mixed-{i}", "BTCUSDT", roles)
            with self.subTest(case=i), self.assertRaisesRegex(StatisticsScopeError, "mixed_controller"):
                project_paper_ticker_pnl(
                    PaperSourceSnapshot(2, (mixed,), origins),
                    account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
                )
        assisted, origins = _scoped_episode("unknown", "ETHUSDT", [
            (AllocationRole.OPEN, Origin.ROBOT), (AllocationRole.CLOSE, Origin.TERMINAL_MANUAL),
        ])
        origins.pop(assisted.allocations[-1].execution_key)
        with self.assertRaisesRegex(StatisticsScopeError, "unattributed"):
            project_paper_ticker_pnl(
                PaperSourceSnapshot(2, (assisted,), origins),
                account_id="paper", owner="ROBOT", period="ALL", now_ms=_ms(9, 12),
            )

if __name__ == "__main__":
    unittest.main()
