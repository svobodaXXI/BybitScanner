"""Read-only Robot Statistics v1 domain models."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class PnlBasis(str, Enum):
    GROSS = "GROSS"
    KNOWN_COST_ADJUSTED = "KNOWN_COST_ADJUSTED"


@dataclass(frozen=True, slots=True)
class RobotStatisticsTrade:
    trade_id: str
    trading_account_id: str
    candidate_id: str
    symbol: str
    direction: str
    pattern: str
    source_timeframe: str
    signal_time_ms: int
    entry_time_ms: int
    entry_path: str
    actual_wv: Decimal
    average_entry: Decimal
    entry_quantity: Decimal | None
    entry_position_version: int | None
    stop_price: Decimal
    take_price: Decimal
    exit_time_ms: int
    exit_price: Decimal
    exit_reason: str
    realized_pnl_usdt: Decimal
    realized_pnl_pct: Decimal
    fees_costs_usdt: Decimal | None

    @property
    def entry_notional_usdt(self) -> Decimal | None:
        if self.entry_quantity is None:
            return None
        return self.entry_quantity * self.average_entry

    def pnl_usdt(self, basis: PnlBasis) -> Decimal | None:
        if basis is PnlBasis.GROSS:
            return self.realized_pnl_usdt
        if self.fees_costs_usdt is None:
            return None
        return self.realized_pnl_usdt - self.fees_costs_usdt


@dataclass(frozen=True, slots=True)
class RobotStatisticsCoverage:
    completed_trades: int
    pnl_available_trades: int
    cost_complete_trades: int
    return_notional_eligible_trades: int
    excluded_return_notional_trades: int


@dataclass(frozen=True, slots=True)
class CumulativePnlPoint:
    trade_id: str
    symbol: str
    exit_time_ms: int
    trade_pnl_usdt: Decimal
    cumulative_pnl_usdt: Decimal


@dataclass(frozen=True, slots=True)
class DailyTickerPnl:
    symbol: str
    selected_pnl_usdt: Decimal
    trade_count: int


@dataclass(frozen=True, slots=True)
class TickerRankingRow:
    symbol: str
    selected_pnl_usdt: Decimal
    trade_count: int


@dataclass(frozen=True, slots=True)
class DailyPnlResult:
    day: str
    selected_pnl_usdt: Decimal
    completed_trade_count: int
    selected_trade_count: int
    tickers: tuple[DailyTickerPnl, ...]


@dataclass(frozen=True, slots=True)
class RobotStatisticsSummary:
    pnl_basis: PnlBasis
    total_pnl_usdt: Decimal
    return_on_traded_notional_pct: Decimal | None
    completed_trades: int
    profitable_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: Decimal | None
    profitable_to_losing_ratio: Decimal | None
    average_pnl_usdt: Decimal | None
    average_holding_ms: Decimal | None
    coverage: RobotStatisticsCoverage
