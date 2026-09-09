from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from terminal.diary.analytics import PnLComponents, PnLSource, TradeAnalyticsRecord
from terminal.diary.factors import (
    FactorObservation,
    FactorProvenance,
    FactorSubjectKind,
)
from terminal.diary.models import DiaryEnvironment, TradeEpisodeId
from terminal.diary.statistics_presentation import project_trade_statistics


def _episode(episode_id: str, *, closed: bool, opened: int = 1_000, closed_at: int = 2_000):
    return SimpleNamespace(
        trade_episode_id=TradeEpisodeId(episode_id),
        environment=DiaryEnvironment.PAPER,
        opened_at_ms=opened,
        closed_at_ms=closed_at if closed else None,
        is_closed=closed,
    )


def _record(
    episode_id: str,
    *,
    net: Decimal | None,
    closed: bool = True,
    opened: int = 1_000,
    closed_at: int = 2_000,
) -> TradeAnalyticsRecord:
    episode = _episode(
        episode_id,
        closed=closed,
        opened=opened,
        closed_at=closed_at,
    )
    if net is None:
        pnl = PnLComponents(
            trade_episode_id=episode.trade_episode_id,
            realized_price_pnl=Decimal("5") if closed else Decimal("0"),
            execution_fees=Decimal("1") if closed else Decimal("0"),
            funding=None,
            other_exchange_costs=Decimal("0") if closed else None,
            manual_external_costs=Decimal("0") if closed else None,
            source=PnLSource.PAPER_SIMULATED,
        )
    else:
        pnl = PnLComponents(
            trade_episode_id=episode.trade_episode_id,
            realized_price_pnl=net,
            execution_fees=Decimal("0"),
            funding=Decimal("0"),
            other_exchange_costs=Decimal("0"),
            manual_external_costs=Decimal("0"),
            source=PnLSource.PAPER_SIMULATED,
        )
    return TradeAnalyticsRecord(episode=episode, pnl=pnl)


def _factor(subject_id: str, key: str, observation_id: str) -> FactorObservation:
    return FactorObservation(
        observation_id=observation_id,
        factor_key=key,
        factor_version=1,
        subject_kind=FactorSubjectKind.TRADE_EPISODE,
        subject_id=subject_id,
        observed_at_ms=3_000,
        provenance=FactorProvenance.MARKET_DATA_DERIVED,
        source_version="test-v1",
        value=1.25,
    )


def test_projects_ready_pnl_metrics_without_recomputing_trade_semantics():
    result = project_trade_statistics([
        _record("win", net=Decimal("12"), opened=1_000, closed_at=4_000),
        _record("loss", net=Decimal("-4"), opened=2_000, closed_at=4_000),
        _record("flat", net=Decimal("0"), opened=3_000, closed_at=4_000),
    ])

    assert result["sample"] == {
        "total": 3,
        "eligible_closed_ready": 3,
        "excluded_open": 0,
        "excluded_incomplete": 0,
    }
    assert result["pnl"]["net_pnl"] == "8"
    assert result["pnl"]["average_net_pnl"] == str(Decimal("8") / Decimal("3"))
    assert result["pnl"]["wins"] == 1
    assert result["pnl"]["losses"] == 1
    assert result["pnl"]["breakeven"] == 1
    assert result["pnl"]["win_rate"] == str(Decimal("1") / Decimal("3"))
    assert result["pnl"]["average_win"] == "12"
    assert result["pnl"]["average_loss"] == "-4"
    assert result["pnl"]["payoff_ratio"] == "3"
    assert result["pnl"]["profit_factor"] == "3"
    assert result["holding"]["average_duration_ms"] == "2000"
    assert result["coverage"]["pnl_ready_ratio"] == "1"


def test_keeps_net_metrics_missing_when_closed_trade_lacks_cost_evidence():
    result = project_trade_statistics([
        _record("incomplete", net=None),
        _record("open", net=None, closed=False),
    ])

    assert result["sample"] == {
        "total": 2,
        "eligible_closed_ready": 0,
        "excluded_open": 1,
        "excluded_incomplete": 1,
    }
    assert result["pnl"]["net_pnl"] is None
    assert result["pnl"]["average_net_pnl"] is None
    assert result["pnl"]["win_rate"] is None
    assert result["pnl"]["profit_factor"] is None
    assert result["holding"]["average_duration_ms"] is None
    assert result["coverage"]["pnl_ready_ratio"] == "0"


def test_factor_coverage_counts_distinct_closed_trade_observations_only():
    records = [
        _record("one", net=None),
        _record("two", net=None),
        _record("open", net=None, closed=False),
    ]
    factors = [
        _factor("one", "trade.mae_pct", "mae-one"),
        _factor("one", "trade.mae_pct", "mae-one-duplicate-versioned-observation"),
        _factor("one", "trade.mfe_pct", "mfe-one"),
        _factor("open", "trade.mae_pct", "mae-open"),
    ]

    result = project_trade_statistics(records, factor_observations=factors)
    coverage = result["coverage"]["post_trade_factors"]

    assert coverage["trade.mae_pct"] == {
        "eligible_closed": 2,
        "observed": 1,
        "coverage_ratio": "0.5",
    }
    assert coverage["trade.mfe_pct"] == {
        "eligible_closed": 2,
        "observed": 1,
        "coverage_ratio": "0.5",
    }
    assert coverage["trade.exit_capture_ratio"] == {
        "eligible_closed": 2,
        "observed": 0,
        "coverage_ratio": "0",
    }
