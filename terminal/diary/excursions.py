"""Trading Diary D5 post-trade MAE/MFE and exit analytics.

This module is downstream/research-only. It consumes a closed TradeEpisode plus a
versioned market-price path that is explicitly bounded to the trade lifetime.
It never changes Scanner admission, strategy/risk decisions, order dispatch,
execution, positions, or reconciliation.

No-look-ahead rule: every supplied path bar must lie fully inside
[episode.opened_at_ms, episode.closed_at_ms]. A path that extends before entry or
after exit is rejected. Incomplete/gapped in-trade coverage remains explicit and
does not produce excursion metrics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable

from terminal.domain.models import PositionSide

from .factors import (
    DiaryFactorStore,
    FactorDefinition,
    FactorObservation,
    FactorProvenance,
    FactorSubjectKind,
    FactorTiming,
    FactorValueKind,
)
from .models import TradeEpisode


EXCURSION_SEMANTICS_V1 = "trade-lifetime-clipped-high-low-v1"
EXIT_QUALITY_SEMANTICS_V1 = "directional-exit-vs-mfe-v1"


class ExcursionReadiness(str, Enum):
    INCOMPLETE = "INCOMPLETE"
    READY = "READY"


@dataclass(frozen=True, slots=True)
class TradePathBar:
    """One market-data interval clipped to the trade lifetime."""

    start_ms: int
    end_ms: int
    high: Decimal
    low: Decimal

    def __post_init__(self) -> None:
        if self.start_ms < 0 or self.end_ms < 0:
            raise ValueError("path timestamps must not be negative")
        if self.end_ms <= self.start_ms:
            raise ValueError("path bar end must be after start")
        if not self.high.is_finite() or not self.low.is_finite():
            raise ValueError("path prices must be finite")
        if self.low <= 0 or self.high <= 0:
            raise ValueError("path prices must be positive")
        if self.high < self.low:
            raise ValueError("path high cannot be below low")


@dataclass(frozen=True, slots=True)
class PostTradePath:
    trade_episode_id: str
    bars: tuple[TradePathBar, ...]
    source_version: str
    observed_at_ms: int
    semantics_version: str = EXCURSION_SEMANTICS_V1

    def __post_init__(self) -> None:
        if not self.trade_episode_id.strip():
            raise ValueError("trade_episode_id must be non-empty")
        if not self.source_version.strip():
            raise ValueError("source_version must be non-empty")
        if not self.semantics_version.strip():
            raise ValueError("semantics_version must be non-empty")
        if self.observed_at_ms < 0:
            raise ValueError("observed_at_ms must not be negative")
        for previous, current in zip(self.bars, self.bars[1:]):
            if current.start_ms < previous.end_ms:
                raise ValueError("path bars must be ordered and non-overlapping")


@dataclass(frozen=True, slots=True)
class ExitReference:
    price: Decimal
    source_version: str

    def __post_init__(self) -> None:
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("exit reference price must be positive and finite")
        if not self.source_version.strip():
            raise ValueError("exit reference source_version must be non-empty")


@dataclass(frozen=True, slots=True)
class ExcursionMetrics:
    trade_episode_id: str
    holding_duration_ms: int
    mae_price: Decimal
    mfe_price: Decimal
    mae_pct: Decimal
    mfe_pct: Decimal
    exit_excursion_pct: Decimal
    exit_capture_ratio: Decimal | None
    exit_giveback_pct_points: Decimal
    semantics_version: str = EXCURSION_SEMANTICS_V1
    exit_quality_version: str = EXIT_QUALITY_SEMANTICS_V1


@dataclass(frozen=True, slots=True)
class ExcursionAnalysis:
    readiness: ExcursionReadiness
    metrics: ExcursionMetrics | None
    missing_reasons: tuple[str, ...]


D5_POST_TRADE_FACTOR_DEFINITIONS_V1: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        factor_key="trade.holding_duration_ms",
        version=1,
        value_kind=FactorValueKind.INTEGER,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="ms",
        description="Closed trade holding duration from episode open to authoritative close.",
    ),
    FactorDefinition(
        factor_key="trade.mae_price",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="quote_price",
        description="Maximum adverse price excursion from average entry during the clipped trade lifetime.",
    ),
    FactorDefinition(
        factor_key="trade.mfe_price",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="quote_price",
        description="Maximum favorable price excursion from average entry during the clipped trade lifetime.",
    ),
    FactorDefinition(
        factor_key="trade.mae_pct",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="percent",
        description="Maximum adverse excursion as percent of average entry.",
    ),
    FactorDefinition(
        factor_key="trade.mfe_pct",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="percent",
        description="Maximum favorable excursion as percent of average entry.",
    ),
    FactorDefinition(
        factor_key="trade.exit_excursion_pct",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="percent",
        description="Directional exit move from average entry; positive is favorable for the episode side.",
    ),
    FactorDefinition(
        factor_key="trade.exit_capture_ratio",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="ratio",
        description="Directional exit excursion divided by MFE; absent when MFE is zero.",
    ),
    FactorDefinition(
        factor_key="trade.exit_giveback_pct_points",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        timing=FactorTiming.POST_TRADE,
        unit="percentage_points",
        description="MFE percent minus directional exit excursion percent.",
    ),
)


def _coverage_reasons(episode: TradeEpisode, path: PostTradePath) -> tuple[str, ...]:
    assert episode.closed_at_ms is not None
    if path.trade_episode_id != episode.trade_episode_id.value:
        raise ValueError("post-trade path belongs to another trade episode")
    for bar in path.bars:
        if bar.start_ms < episode.opened_at_ms:
            raise ValueError("no-look-ahead path includes pre-entry market data")
        if bar.end_ms > episode.closed_at_ms:
            raise ValueError("no-look-ahead path includes post-exit market data")

    reasons: list[str] = []
    if not path.bars:
        return ("NO_PATH_BARS",)
    if path.bars[0].start_ms != episode.opened_at_ms:
        reasons.append("MISSING_ENTRY_TO_FIRST_BAR_COVERAGE")
    if path.bars[-1].end_ms != episode.closed_at_ms:
        reasons.append("MISSING_LAST_BAR_TO_EXIT_COVERAGE")
    for previous, current in zip(path.bars, path.bars[1:]):
        if current.start_ms != previous.end_ms:
            reasons.append("GAPPED_PATH_COVERAGE")
            break
    return tuple(reasons)


def analyze_post_trade_excursion(
    episode: TradeEpisode,
    path: PostTradePath,
    exit_reference: ExitReference,
) -> ExcursionAnalysis:
    """Compute D5 excursion/exit analytics only from complete in-trade coverage."""
    if not episode.is_closed:
        raise ValueError("post-trade excursion analytics require a closed episode")
    assert episode.closed_at_ms is not None
    reasons = _coverage_reasons(episode, path)
    if reasons:
        return ExcursionAnalysis(ExcursionReadiness.INCOMPLETE, None, reasons)

    entry = episode.average_entry.value
    highest = max(bar.high for bar in path.bars)
    lowest = min(bar.low for bar in path.bars)
    hundred = Decimal("100")

    if episode.side is PositionSide.LONG:
        mfe_price = max(Decimal("0"), highest - entry)
        mae_price = max(Decimal("0"), entry - lowest)
        exit_move = exit_reference.price - entry
    elif episode.side is PositionSide.SHORT:
        mfe_price = max(Decimal("0"), entry - lowest)
        mae_price = max(Decimal("0"), highest - entry)
        exit_move = entry - exit_reference.price
    else:  # defensive: TradeEpisode itself forbids FLAT
        raise ValueError("unsupported episode side")

    mfe_pct = (mfe_price / entry) * hundred
    mae_pct = (mae_price / entry) * hundred
    exit_excursion_pct = (exit_move / entry) * hundred
    exit_capture_ratio = exit_excursion_pct / mfe_pct if mfe_pct > 0 else None
    giveback = mfe_pct - exit_excursion_pct

    return ExcursionAnalysis(
        readiness=ExcursionReadiness.READY,
        metrics=ExcursionMetrics(
            trade_episode_id=episode.trade_episode_id.value,
            holding_duration_ms=episode.closed_at_ms - episode.opened_at_ms,
            mae_price=mae_price,
            mfe_price=mfe_price,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
            exit_excursion_pct=exit_excursion_pct,
            exit_capture_ratio=exit_capture_ratio,
            exit_giveback_pct_points=giveback,
            semantics_version=path.semantics_version,
        ),
        missing_reasons=(),
    )


def persist_post_trade_excursion_factors(
    *,
    analysis: ExcursionAnalysis,
    path: PostTradePath,
    exit_reference: ExitReference,
    database_path: str | Path,
) -> int:
    """Persist READY D5 metrics as append-only versioned post-trade factors.

    INCOMPLETE analyses intentionally persist no numeric factor observations; their
    missingness remains visible through ExcursionAnalysis.missing_reasons.
    """
    if analysis.readiness is not ExcursionReadiness.READY or analysis.metrics is None:
        return 0
    metrics = analysis.metrics
    values: dict[str, int | float] = {
        "trade.holding_duration_ms": metrics.holding_duration_ms,
        "trade.mae_price": float(metrics.mae_price),
        "trade.mfe_price": float(metrics.mfe_price),
        "trade.mae_pct": float(metrics.mae_pct),
        "trade.mfe_pct": float(metrics.mfe_pct),
        "trade.exit_excursion_pct": float(metrics.exit_excursion_pct),
        "trade.exit_giveback_pct_points": float(metrics.exit_giveback_pct_points),
    }
    if metrics.exit_capture_ratio is not None:
        values["trade.exit_capture_ratio"] = float(metrics.exit_capture_ratio)

    source_version = (
        f"{path.source_version}|{path.semantics_version}|"
        f"{exit_reference.source_version}|{metrics.exit_quality_version}"
    )
    definitions = {item.factor_key: item for item in D5_POST_TRADE_FACTOR_DEFINITIONS_V1}
    recorded = 0
    with DiaryFactorStore.open(database_path) as store:
        store.register_definitions(D5_POST_TRADE_FACTOR_DEFINITIONS_V1)
        for factor_key, value in sorted(values.items()):
            definition = definitions[factor_key]
            identity_material = (
                f"{metrics.trade_episode_id}|{factor_key}|{definition.version}|{source_version}"
            )
            observation_id = "fo_d5_" + hashlib.sha256(
                identity_material.encode("utf-8")
            ).hexdigest()[:24]
            existing = store.get_observation(observation_id)
            observation = FactorObservation(
                observation_id=observation_id,
                factor_key=factor_key,
                factor_version=definition.version,
                subject_kind=FactorSubjectKind.TRADE_EPISODE,
                subject_id=metrics.trade_episode_id,
                observed_at_ms=path.observed_at_ms,
                provenance=FactorProvenance.MARKET_DATA_DERIVED,
                source_version=source_version,
                value=value,
            )
            store.append_observation(observation)
            if existing is None:
                recorded += 1
    return recorded
