from __future__ import annotations

import unittest
from decimal import Decimal

from terminal.statistics.aggregation import (
    aggregate_daily_pnl,
    aggregate_ticker_ranking,
    build_cumulative_pnl,
    summarize_robot_trades,
)
from terminal.statistics.models import (
    PnlBasis,
    RobotStatisticsTrade,
    TickerRankingRow,
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
    symbol: str = "BTCUSDT",
) -> RobotStatisticsTrade:
    return RobotStatisticsTrade(
        trade_id=trade_id,
        trading_account_id="account-a",
        candidate_id=f"candidate-{trade_id}",
        symbol=symbol,
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
    def test_ticker_ranking_aggregates_symbols(self) -> None:
        rows = aggregate_ticker_ranking(
            iter((
                _trade(trade_id="b1", pnl="1.1", symbol="BTCUSDT"),
                _trade(trade_id="e1", pnl="2.2", symbol="ETHUSDT"),
                _trade(trade_id="b2", pnl="3.3", symbol="BTCUSDT"),
            )),
            basis=PnlBasis.GROSS,
        )
        self.assertEqual(rows, (
            TickerRankingRow("BTCUSDT", Decimal("4.4"), 2),
            TickerRankingRow("ETHUSDT", Decimal("2.2"), 1),
        ))

    def test_ticker_ranking_orders_pnl_descending(self) -> None:
        rows = aggregate_ticker_ranking(
            (
                _trade(trade_id="loss", pnl="-2", symbol="AUSDT"),
                _trade(trade_id="zero", pnl="0", symbol="BUSDT"),
                _trade(trade_id="profit", pnl="3", symbol="ZUSDT"),
                _trade(trade_id="larger-loss", pnl="-10", symbol="CUSDT"),
            ),
            basis=PnlBasis.GROSS,
        )
        self.assertEqual(
            [row.symbol for row in rows], ["ZUSDT", "BUSDT", "AUSDT", "CUSDT"],
        )

    def test_ticker_ranking_pnl_tie_orders_trade_count_descending(self) -> None:
        rows = aggregate_ticker_ranking(
            (
                _trade(trade_id="a", pnl="2", symbol="AUSDT"),
                _trade(trade_id="z1", pnl="1", symbol="ZUSDT"),
                _trade(trade_id="z2", pnl="1", symbol="ZUSDT"),
            ),
            basis=PnlBasis.GROSS,
        )
        self.assertEqual([row.symbol for row in rows], ["ZUSDT", "AUSDT"])

    def test_ticker_ranking_full_tie_orders_symbol_ascending(self) -> None:
        trades = (
            _trade(trade_id="z", pnl="2", symbol="ZUSDT"),
            _trade(trade_id="a", pnl="2", symbol="AUSDT"),
            _trade(trade_id="b", pnl="2", symbol="BUSDT"),
        )
        for source in (trades, tuple(reversed(trades))):
            with self.subTest(source=source):
                rows = aggregate_ticker_ranking(source, basis=PnlBasis.GROSS)
                self.assertEqual(
                    [row.symbol for row in rows], ["AUSDT", "BUSDT", "ZUSDT"],
                )

    def test_ticker_ranking_adjusted_excludes_unknown_costs(self) -> None:
        trades = (
            _trade(trade_id="known", pnl="10", fee="3", symbol="BTCUSDT"),
            _trade(trade_id="unknown", pnl="100", fee=None, symbol="BTCUSDT"),
            _trade(trade_id="only-unknown", pnl="200", fee=None, symbol="ETHUSDT"),
            _trade(trade_id="other", pnl="8", fee="0", symbol="SOLUSDT"),
        )
        self.assertEqual(
            aggregate_ticker_ranking(trades, basis=PnlBasis.KNOWN_COST_ADJUSTED),
            (
                TickerRankingRow("SOLUSDT", Decimal("8"), 1),
                TickerRankingRow("BTCUSDT", Decimal("7"), 1),
            ),
        )
        self.assertEqual(
            aggregate_ticker_ranking(trades, basis=PnlBasis.GROSS),
            (
                TickerRankingRow("ETHUSDT", Decimal("200"), 1),
                TickerRankingRow("BTCUSDT", Decimal("110"), 2),
                TickerRankingRow("SOLUSDT", Decimal("8"), 1),
            ),
        )
        self.assertEqual(
            aggregate_ticker_ranking(
                (trades[2],), basis=PnlBasis.KNOWN_COST_ADJUSTED,
            ),
            (),
        )

    def test_ticker_ranking_preserves_decimal_math(self) -> None:
        for basis, expected in (
            (PnlBasis.GROSS, Decimal("0.3000000000000000003")),
            (PnlBasis.KNOWN_COST_ADJUSTED, Decimal("0.2700000000000000003")),
        ):
            with self.subTest(basis=basis):
                rows = aggregate_ticker_ranking(
                    (
                        _trade(trade_id="a", pnl="0.1000000000000000001", fee="0.01"),
                        _trade(trade_id="b", pnl="0.2000000000000000002", fee="0.02"),
                    ),
                    basis=basis,
                )
                self.assertIsInstance(rows[0].selected_pnl_usdt, Decimal)
                self.assertEqual(rows[0].selected_pnl_usdt, expected)

    def test_ticker_ranking_empty_input_returns_empty_tuple(self) -> None:
        for basis in PnlBasis:
            with self.subTest(basis=basis):
                self.assertEqual(aggregate_ticker_ranking((), basis=basis), ())

    def test_daily_pnl_groups_two_days_by_msk_close_date(self) -> None:
        trades = (
            _trade(trade_id="day-1", pnl="1.25", exit_time_ms=0),
            _trade(trade_id="day-2", pnl="2.75", exit_time_ms=75_600_000),
        )

        results = aggregate_daily_pnl(trades, basis=PnlBasis.GROSS)

        self.assertEqual([item.day for item in results], ["1970-01-01", "1970-01-02"])
        self.assertEqual(
            [item.selected_pnl_usdt for item in results],
            [Decimal("1.25"), Decimal("2.75")],
        )

    def test_daily_pnl_uses_msk_day_for_utc_timestamp(self) -> None:
        results = aggregate_daily_pnl(
            (_trade(trade_id="utc-next-msk-day", pnl="3", exit_time_ms=75_600_000),),
            basis=PnlBasis.GROSS,
        )

        self.assertEqual(results[0].day, "1970-01-02")

    def test_daily_pnl_aggregates_multiple_tickers(self) -> None:
        results = aggregate_daily_pnl(
            (
                _trade(trade_id="btc-1", pnl="1.1", symbol="BTCUSDT"),
                _trade(trade_id="eth", pnl="2.2", symbol="ETHUSDT"),
                _trade(trade_id="btc-2", pnl="3.3", symbol="BTCUSDT"),
            ),
            basis=PnlBasis.GROSS,
        )

        day = results[0]
        self.assertEqual(day.selected_pnl_usdt, Decimal("6.6"))
        self.assertEqual(day.completed_trade_count, 3)
        self.assertEqual(day.selected_trade_count, 3)
        self.assertEqual(
            [(ticker.symbol, ticker.selected_pnl_usdt, ticker.trade_count) for ticker in day.tickers],
            [
                ("BTCUSDT", Decimal("4.4"), 2),
                ("ETHUSDT", Decimal("2.2"), 1),
            ],
        )

    def test_daily_pnl_orders_days_and_tickers_deterministically(self) -> None:
        results = aggregate_daily_pnl(
            (
                _trade(
                    trade_id="later-z",
                    pnl="1",
                    symbol="ZUSDT",
                    exit_time_ms=75_600_000,
                ),
                _trade(trade_id="earlier-b", pnl="1", symbol="BUSDT", exit_time_ms=0),
                _trade(trade_id="earlier-a", pnl="1", symbol="AUSDT", exit_time_ms=0),
            ),
            basis=PnlBasis.GROSS,
        )

        self.assertEqual([item.day for item in results], ["1970-01-01", "1970-01-02"])
        self.assertEqual([ticker.symbol for ticker in results[0].tickers], ["AUSDT", "BUSDT"])

    def test_daily_adjusted_pnl_skips_unknown_cost_trade(self) -> None:
        results = aggregate_daily_pnl(
            (
                _trade(trade_id="known", pnl="10.5", fee="0.4", symbol="BTCUSDT"),
                _trade(trade_id="unknown", pnl="20", fee=None, symbol="ETHUSDT"),
            ),
            basis=PnlBasis.KNOWN_COST_ADJUSTED,
        )

        day = results[0]
        self.assertEqual(day.selected_pnl_usdt, Decimal("10.1"))
        self.assertEqual(day.completed_trade_count, 2)
        self.assertEqual(day.selected_trade_count, 1)
        self.assertEqual([ticker.symbol for ticker in day.tickers], ["BTCUSDT"])

    def test_daily_pnl_preserves_decimal_arithmetic(self) -> None:
        result = aggregate_daily_pnl(
            (
                _trade(trade_id="a", pnl="0.1"),
                _trade(trade_id="b", pnl="0.2"),
            ),
            basis=PnlBasis.GROSS,
        )[0]

        self.assertIsInstance(result.selected_pnl_usdt, Decimal)
        self.assertEqual(result.selected_pnl_usdt, Decimal("0.3"))

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
