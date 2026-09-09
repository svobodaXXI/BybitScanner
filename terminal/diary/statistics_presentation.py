"""Read-only Trading Diary D6.4 statistics presentation.

The projection consumes existing D3 TradeAnalyticsRecord values and optional D4/D5
factor observations. It never invents missing data and never mutates trading state.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .analytics import DiaryReadiness, DiaryStatisticsEngine, TradeAnalyticsRecord
from .factors import FactorObservation, FactorSubjectKind


POST_TRADE_FACTOR_KEYS = (
    "trade.mae_pct",
    "trade.mfe_pct",
    "trade.exit_capture_ratio",
)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value.is_infinite():
        return "Infinity" if value > 0 else "-Infinity"
    return str(value)


def _average(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / len(values) if values else None


def project_trade_statistics(
    records: Iterable[TradeAnalyticsRecord],
    *,
    factor_observations: Iterable[FactorObservation] = (),
) -> dict[str, object]:
    """Project D6.4 statistics without coercing unavailable metrics to zero."""
    materialized = list(records)
    summary = DiaryStatisticsEngine().summarize(materialized)
    ready = [
        record
        for record in materialized
        if record.readiness is DiaryReadiness.CLOSED_READY
    ]
    ready_pnls = [
        value
        for record in ready
        if (value := record.pnl.net_pnl) is not None
    ]
    wins = [value for value in ready_pnls if value > 0]
    losses = [value for value in ready_pnls if value < 0]
    average_win = _average(wins)
    average_loss = _average(losses)
    payoff_ratio = (
        average_win / abs(average_loss)
        if average_win is not None and average_loss is not None and average_loss != 0
        else None
    )
    win_rate = (
        Decimal(summary.wins) / Decimal(len(ready_pnls))
        if ready_pnls else None
    )
    holding_values = [
        Decimal(record.episode.closed_at_ms - record.episode.opened_at_ms)
        for record in ready
        if record.episode.closed_at_ms is not None
    ]

    closed_subject_ids = {
        record.episode.trade_episode_id.value
        for record in materialized
        if record.episode.is_closed
    }
    observations_by_key: dict[str, set[str]] = {
        key: set() for key in POST_TRADE_FACTOR_KEYS
    }
    for observation in factor_observations:
        if (
            observation.subject_kind is FactorSubjectKind.TRADE_EPISODE
            and observation.factor_key in observations_by_key
            and observation.subject_id in closed_subject_ids
        ):
            observations_by_key[observation.factor_key].add(observation.subject_id)

    closed_count = len(closed_subject_ids)
    factor_coverage = {}
    for key in POST_TRADE_FACTOR_KEYS:
        observed = len(observations_by_key[key])
        ratio = (
            Decimal(observed) / Decimal(closed_count)
            if closed_count else Decimal("0")
        )
        factor_coverage[key] = {
            "eligible_closed": closed_count,
            "observed": observed,
            "coverage_ratio": str(ratio),
        }

    return {
        "sample": {
            "total": len(materialized),
            "eligible_closed_ready": summary.eligible_closed_ready,
            "excluded_open": summary.excluded_open,
            "excluded_incomplete": summary.excluded_incomplete,
        },
        "pnl": {
            "net_pnl": _decimal_text(summary.net_pnl) if ready_pnls else None,
            "average_net_pnl": _decimal_text(summary.average_net_pnl),
            "wins": summary.wins,
            "losses": summary.losses,
            "breakeven": summary.breakeven,
            "win_rate": _decimal_text(win_rate),
            "average_win": _decimal_text(average_win),
            "average_loss": _decimal_text(average_loss),
            "payoff_ratio": _decimal_text(payoff_ratio),
            "profit_factor": _decimal_text(summary.profit_factor),
        },
        "holding": {
            "average_duration_ms": _decimal_text(_average(holding_values)),
        },
        "coverage": {
            "pnl_ready_ratio": str(summary.coverage_ratio),
            "post_trade_factors": factor_coverage,
        },
    }
