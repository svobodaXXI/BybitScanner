"""Trading Diary D3 readiness, PnL provenance and read-only statistics.

This module derives research views from already reconstructed TradeEpisode values.
It is observational only: it cannot mutate orders, executions, positions or
reconciliation state.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Iterable

from .models import DiaryEnvironment, TradeEpisode, TradeEpisodeId


class DiaryReadiness(str, Enum):
    OPEN = "OPEN"
    CLOSED_INCOMPLETE = "CLOSED_INCOMPLETE"
    CLOSED_READY = "CLOSED_READY"


class PnLSource(str, Enum):
    DERIVED_FROM_EXECUTIONS = "DERIVED_FROM_EXECUTIONS"
    PAPER_SIMULATED = "PAPER_SIMULATED"
    EXCHANGE_CLOSED_PNL = "EXCHANGE_CLOSED_PNL"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"


NET_PNL_FORMULA_V1 = "realized_price_pnl-execution_fees-funding-other_exchange_costs-manual_external_costs"


@dataclass(frozen=True, slots=True)
class PnLComponents:
    """Versioned trade-level PnL/cost components; None means unknown, never zero."""

    trade_episode_id: TradeEpisodeId
    realized_price_pnl: Decimal | None
    execution_fees: Decimal | None
    funding: Decimal | None
    other_exchange_costs: Decimal | None
    manual_external_costs: Decimal | None
    source: PnLSource
    formula_version: str = NET_PNL_FORMULA_V1

    def __post_init__(self) -> None:
        for name in (
            "realized_price_pnl",
            "execution_fees",
            "funding",
            "other_exchange_costs",
            "manual_external_costs",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise ValueError(f"{name} must be a finite Decimal or None")
        if not self.formula_version.strip():
            raise ValueError("formula_version must be non-empty")

    @property
    def missing_components(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in (
                "realized_price_pnl",
                "execution_fees",
                "funding",
                "other_exchange_costs",
                "manual_external_costs",
            )
            if getattr(self, name) is None
        )

    @property
    def net_pnl(self) -> Decimal | None:
        if self.missing_components:
            return None
        assert self.realized_price_pnl is not None
        assert self.execution_fees is not None
        assert self.funding is not None
        assert self.other_exchange_costs is not None
        assert self.manual_external_costs is not None
        return (
            self.realized_price_pnl
            - self.execution_fees
            - self.funding
            - self.other_exchange_costs
            - self.manual_external_costs
        )


@dataclass(frozen=True, slots=True)
class TradeAnalyticsRecord:
    episode: TradeEpisode
    pnl: PnLComponents
    pattern: str | None = None
    setup_id: str | None = None
    entry_mode: str | None = None

    def __post_init__(self) -> None:
        if self.pnl.trade_episode_id != self.episode.trade_episode_id:
            raise ValueError("PnL components belong to another trade episode")

    @property
    def readiness(self) -> DiaryReadiness:
        if not self.episode.is_closed:
            return DiaryReadiness.OPEN
        if self.pnl.net_pnl is None:
            return DiaryReadiness.CLOSED_INCOMPLETE
        return DiaryReadiness.CLOSED_READY

    @property
    def missing_reasons(self) -> tuple[str, ...]:
        if not self.episode.is_closed:
            return ("TRADE_OPEN",)
        return tuple(f"MISSING_{name.upper()}" for name in self.pnl.missing_components)


@dataclass(frozen=True, slots=True)
class TradeStatistics:
    eligible_closed_ready: int
    excluded_open: int
    excluded_incomplete: int
    wins: int
    losses: int
    breakeven: int
    net_pnl: Decimal
    average_net_pnl: Decimal | None
    profit_factor: Decimal | None
    coverage_ratio: Decimal


class DiaryStatisticsEngine:
    """Read-only statistics over CLOSED_READY records only."""

    def summarize(
        self,
        records: Iterable[TradeAnalyticsRecord],
        *,
        pattern: str | None = None,
        setup_id: str | None = None,
        entry_mode: str | None = None,
        environment: DiaryEnvironment | None = None,
    ) -> TradeStatistics:
        selected = [
            record
            for record in records
            if (pattern is None or record.pattern == pattern)
            and (setup_id is None or record.setup_id == setup_id)
            and (entry_mode is None or record.entry_mode == entry_mode)
            and (environment is None or record.episode.environment is environment)
        ]

        open_count = sum(record.readiness is DiaryReadiness.OPEN for record in selected)
        incomplete_count = sum(
            record.readiness is DiaryReadiness.CLOSED_INCOMPLETE for record in selected
        )
        ready = [record for record in selected if record.readiness is DiaryReadiness.CLOSED_READY]
        pnls = [record.pnl.net_pnl for record in ready]
        values = [value for value in pnls if value is not None]

        wins = sum(value > 0 for value in values)
        losses = sum(value < 0 for value in values)
        breakeven = sum(value == 0 for value in values)
        net = sum(values, Decimal("0"))
        average = net / len(values) if values else None
        gross_profit = sum((value for value in values if value > 0), Decimal("0"))
        gross_loss = -sum((value for value in values if value < 0), Decimal("0"))
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (None if gross_profit == 0 else Decimal("Infinity"))
        )
        total = len(selected)
        coverage = Decimal(len(ready)) / Decimal(total) if total else Decimal("0")

        return TradeStatistics(
            eligible_closed_ready=len(ready),
            excluded_open=open_count,
            excluded_incomplete=incomplete_count,
            wins=wins,
            losses=losses,
            breakeven=breakeven,
            net_pnl=net,
            average_net_pnl=average,
            profit_factor=profit_factor,
            coverage_ratio=coverage,
        )


def pnl_from_episode(
    episode: TradeEpisode,
    *,
    funding: Decimal | None,
    other_exchange_costs: Decimal | None,
    manual_external_costs: Decimal | None,
) -> PnLComponents:
    """Build baseline PnL provenance without inventing unavailable cost values."""

    source = {
        DiaryEnvironment.LIVE: PnLSource.DERIVED_FROM_EXECUTIONS,
        DiaryEnvironment.PAPER: PnLSource.PAPER_SIMULATED,
        DiaryEnvironment.HISTORICAL_REPLAY: PnLSource.HISTORICAL_REPLAY,
    }[episode.environment]
    return PnLComponents(
        trade_episode_id=episode.trade_episode_id,
        realized_price_pnl=episode.realized_price_pnl,
        execution_fees=episode.execution_fees,
        funding=funding,
        other_exchange_costs=other_exchange_costs,
        manual_external_costs=manual_external_costs,
        source=source,
    )
