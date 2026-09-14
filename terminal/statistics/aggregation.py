"""Pure aggregation for Robot Statistics v1."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .models import (
    CumulativePnlPoint,
    PnlBasis,
    RobotStatisticsCoverage,
    RobotStatisticsSummary,
    RobotStatisticsTrade,
)


_HUNDRED = Decimal("100")
_ZERO = Decimal("0")


def _selected_trade_pnl(
    trade: RobotStatisticsTrade,
    *,
    basis: PnlBasis,
) -> Decimal | None:
    return trade.pnl_usdt(basis)


def build_cumulative_pnl(
    trades: Iterable[RobotStatisticsTrade],
    *,
    basis: PnlBasis,
) -> tuple[CumulativePnlPoint, ...]:
    ordered = sorted(
        trades,
        key=lambda trade: (trade.exit_time_ms, trade.trade_id),
    )

    cumulative = _ZERO
    points: list[CumulativePnlPoint] = []

    for trade in ordered:
        pnl = _selected_trade_pnl(trade, basis=basis)
        if pnl is None:
            continue

        cumulative += pnl
        points.append(
            CumulativePnlPoint(
                trade_id=trade.trade_id,
                symbol=trade.symbol,
                exit_time_ms=trade.exit_time_ms,
                trade_pnl_usdt=pnl,
                cumulative_pnl_usdt=cumulative,
            )
        )

    return tuple(points)


def summarize_robot_trades(
    trades: Iterable[RobotStatisticsTrade],
    *,
    basis: PnlBasis,
) -> RobotStatisticsSummary:
    materialized = tuple(trades)

    selected: list[tuple[RobotStatisticsTrade, Decimal]] = []
    for trade in materialized:
        pnl = _selected_trade_pnl(trade, basis=basis)
        if pnl is not None:
            selected.append((trade, pnl))

    pnl_values = tuple(pnl for _, pnl in selected)

    profitable = sum(1 for pnl in pnl_values if pnl > 0)
    losing = sum(1 for pnl in pnl_values if pnl < 0)
    breakeven = sum(1 for pnl in pnl_values if pnl == 0)

    total_pnl = sum(pnl_values, _ZERO)

    average_pnl = (
        total_pnl / Decimal(len(pnl_values))
        if pnl_values
        else None
    )

    classified_count = profitable + losing + breakeven
    win_rate = (
        Decimal(profitable) / Decimal(classified_count) * _HUNDRED
        if classified_count
        else None
    )

    profitable_to_losing_ratio = (
        Decimal(profitable) / Decimal(losing)
        if losing
        else None
    )

    holding_values = tuple(
        Decimal(trade.exit_time_ms - trade.entry_time_ms)
        for trade, _ in selected
    )
    average_holding_ms = (
        sum(holding_values, _ZERO) / Decimal(len(holding_values))
        if holding_values
        else None
    )

    return_eligible: list[tuple[Decimal, Decimal]] = []
    for trade, pnl in selected:
        notional = trade.entry_notional_usdt
        if notional is None or notional <= 0:
            continue
        return_eligible.append((pnl, notional))

    eligible_pnl = sum(
        (pnl for pnl, _ in return_eligible),
        _ZERO,
    )
    eligible_notional = sum(
        (notional for _, notional in return_eligible),
        _ZERO,
    )

    return_on_traded_notional_pct = (
        eligible_pnl / eligible_notional * _HUNDRED
        if return_eligible and eligible_notional > 0
        else None
    )

    coverage = RobotStatisticsCoverage(
        completed_trades=len(materialized),
        pnl_available_trades=len(selected),
        cost_complete_trades=sum(
            1
            for trade in materialized
            if trade.fees_costs_usdt is not None
        ),
        return_notional_eligible_trades=len(return_eligible),
        excluded_return_notional_trades=(
            len(selected) - len(return_eligible)
        ),
    )

    return RobotStatisticsSummary(
        pnl_basis=basis,
        total_pnl_usdt=total_pnl,
        return_on_traded_notional_pct=return_on_traded_notional_pct,
        completed_trades=len(materialized),
        profitable_trades=profitable,
        losing_trades=losing,
        breakeven_trades=breakeven,
        win_rate_pct=win_rate,
        profitable_to_losing_ratio=profitable_to_losing_ratio,
        average_pnl_usdt=average_pnl,
        average_holding_ms=average_holding_ms,
        coverage=coverage,
    )