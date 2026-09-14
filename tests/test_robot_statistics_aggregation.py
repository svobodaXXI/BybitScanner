from __future__ import annotations

import unittest
from decimal import Decimal

from terminal.statistics.aggregation import (
    build_cumulative_pnl,
    summarize_robot_trades,
)
from terminal.statistics.models import (
    PnlBasis,
    RobotStatisticsTrade,
)


def _trade(
    *,
    trade_id: str,
    pnl: str,
    fee: str | None = "0",
    entry_quantity: str | None = "5",
    average_entry: str = "10",
    entry_time_ms: int = 1000,
    exit_time_ms: int = 2000,
) -> RobotStatisticsTrade:
    return RobotStatisticsTrade(
        trade_id=trade_id,
        trading_account_id="account-a",
        candidate_id=f"candidate-{trade_id}",
        symbol="BTCUSDT",
        direction="LONG",
        pattern="FALLING_WEDGE",
        source_timeframe="1",
        signal_time_ms=500,
        entry_time_ms=entry_time_ms,
        entry_path="LIMIT",
        actual_wv=Decimal("0.1"),
        average_entry=Decimal(average_entry),
        entry_quantity=(
            Decimal(entry_quantity)
            if entry_quantity is not None
            else None
        ),
        entry_position_version=1,
        stop_price=Decimal("9"),
        take_price=Decimal("12"),
        exit_time_ms=exit_time_ms,
        exit_price=Decimal("11"),
        exit_reason="TAKE",
        realized_pnl_usdt=Decimal(pnl),
        realized_pnl_pct=Decimal("1"),
        fees_costs_usdt=(
            Decimal(fee)
            if fee is not None
            else None
        ),
    )


class RobotStatisticsAggregationTests(unittest.TestCase):
    def test_gross_summary_classifies_profit_loss_and_breakeven(self) -> None:
        trades = (
            _trade(trade_id="t1", pnl="10"),
            _trade(trade_id="t2", pnl="-4"),
            _trade(trade_id="t3", pnl="0"),
        )

        summary = summarize_robot_trades(
            trades,
            basis=PnlBasis.GROSS,
        )

        self.assertEqual(summary.total_pnl_usdt, Decimal("6"))
        self.assertEqual(summary.completed_trades, 3)
        self.assertEqual(summary.profitable_trades, 1)
        self.assertEqual(summary.losing_trades, 1)
        self.assertEqual(summary.breakeven_trades, 1)
        self.assertEqual(
            summary.win_rate_pct,
            Decimal("1") / Decimal("3") * Decimal("100"),
        )
        self.assertEqual(
            summary.profitable_to_losing_ratio,
            Decimal("1"),
        )
        self.assertEqual(
            summary.average_pnl_usdt,
            Decimal("2"),
        )

    def test_known_cost_adjusted_basis_excludes_trade_with_unknown_cost(self) -> None:
        trades = (
            _trade(
                trade_id="known",
                pnl="10",
                fee="2",
            ),
            _trade(
                trade_id="unknown",
                pnl="20",
                fee=None,
            ),
        )

        summary = summarize_robot_trades(
            trades,
            basis=PnlBasis.KNOWN_COST_ADJUSTED,
        )

        self.assertEqual(summary.total_pnl_usdt, Decimal("8"))
        self.assertEqual(summary.profitable_trades, 1)
        self.assertEqual(summary.coverage.completed_trades, 2)
        self.assertEqual(summary.coverage.pnl_available_trades, 1)
        self.assertEqual(summary.coverage.cost_complete_trades, 1)

    def test_return_on_traded_notional_uses_same_eligible_subset(self) -> None:
        trades = (
            _trade(
                trade_id="eligible",
                pnl="10",
                entry_quantity="5",
                average_entry="10",
            ),
            _trade(
                trade_id="missing-notional",
                pnl="100",
                entry_quantity=None,
                average_entry="10",
            ),
        )

        summary = summarize_robot_trades(
            trades,
            basis=PnlBasis.GROSS,
        )

        # Only "eligible" contributes:
        # 10 / (5 * 10) * 100 = 20%
        self.assertEqual(
            summary.return_on_traded_notional_pct,
            Decimal("20"),
        )
        self.assertEqual(
            summary.coverage.return_notional_eligible_trades,
            1,
        )
        self.assertEqual(
            summary.coverage.excluded_return_notional_trades,
            1,
        )

    def test_nonpositive_entry_notional_is_excluded_from_period_return(self) -> None:
        trades = (
            _trade(
                trade_id="zero",
                pnl="10",
                entry_quantity="0",
            ),
        )

        summary = summarize_robot_trades(
            trades,
            basis=PnlBasis.GROSS,
        )

        self.assertIsNone(
            summary.return_on_traded_notional_pct
        )
        self.assertEqual(
            summary.coverage.return_notional_eligible_trades,
            0,
        )
        self.assertEqual(
            summary.coverage.excluded_return_notional_trades,
            1,
        )

    def test_average_holding_time_uses_selected_trade_set(self) -> None:
        trades = (
            _trade(
                trade_id="a",
                pnl="1",
                entry_time_ms=1000,
                exit_time_ms=3000,
            ),
            _trade(
                trade_id="b",
                pnl="1",
                entry_time_ms=2000,
                exit_time_ms=6000,
            ),
        )

        summary = summarize_robot_trades(
            trades,
            basis=PnlBasis.GROSS,
        )

        self.assertEqual(
            summary.average_holding_ms,
            Decimal("3000"),
        )

    def test_zero_losing_trades_keeps_profit_to_loss_ratio_unavailable(self) -> None:
        summary = summarize_robot_trades(
            (
                _trade(trade_id="a", pnl="5"),
                _trade(trade_id="b", pnl="0"),
            ),
            basis=PnlBasis.GROSS,
        )

        self.assertIsNone(
            summary.profitable_to_losing_ratio
        )

    def test_empty_trade_set_returns_explicit_empty_summary(self) -> None:
        summary = summarize_robot_trades(
            (),
            basis=PnlBasis.GROSS,
        )

        self.assertEqual(summary.total_pnl_usdt, Decimal("0"))
        self.assertEqual(summary.completed_trades, 0)
        self.assertIsNone(summary.average_pnl_usdt)
        self.assertIsNone(summary.average_holding_ms)
        self.assertIsNone(summary.win_rate_pct)
        self.assertIsNone(
            summary.return_on_traded_notional_pct
        )

    def test_cumulative_pnl_orders_by_exit_time_then_trade_id(self) -> None:
        trades = (
            _trade(
                trade_id="trade-b",
                pnl="3",
                exit_time_ms=5000,
            ),
            _trade(
                trade_id="trade-a",
                pnl="2",
                exit_time_ms=5000,
            ),
            _trade(
                trade_id="trade-c",
                pnl="-1",
                exit_time_ms=6000,
            ),
        )

        points = build_cumulative_pnl(
            trades,
            basis=PnlBasis.GROSS,
        )

        self.assertEqual(
            [point.trade_id for point in points],
            ["trade-a", "trade-b", "trade-c"],
        )
        self.assertEqual(
            [point.cumulative_pnl_usdt for point in points],
            [
                Decimal("2"),
                Decimal("5"),
                Decimal("4"),
            ],
        )

    def test_adjusted_cumulative_curve_skips_unknown_cost_trade(self) -> None:
        trades = (
            _trade(
                trade_id="known",
                pnl="10",
                fee="2",
                exit_time_ms=1000,
            ),
            _trade(
                trade_id="unknown",
                pnl="20",
                fee=None,
                exit_time_ms=2000,
            ),
        )

        points = build_cumulative_pnl(
            trades,
            basis=PnlBasis.KNOWN_COST_ADJUSTED,
        )

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0].trade_id, "known")
        self.assertEqual(
            points[0].trade_pnl_usdt,
            Decimal("8"),
        )
        self.assertEqual(
            points[0].cumulative_pnl_usdt,
            Decimal("8"),
        )


if __name__ == "__main__":
    unittest.main()