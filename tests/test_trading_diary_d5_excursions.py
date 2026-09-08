from decimal import Decimal
from pathlib import Path

import pytest

from terminal.diary import (
    D5_POST_TRADE_FACTOR_DEFINITIONS_V1,
    DiaryEnvironment,
    DiaryFactorStore,
    ExcursionReadiness,
    ExitReference,
    PostTradePath,
    TradeEpisode,
    TradeEpisodeId,
    TradePathBar,
    analyze_post_trade_excursion,
    persist_post_trade_excursion_factors,
)
from terminal.diary.models import AllocationRole, ExecutionAllocation
from terminal.diary.factors import FactorSubjectKind, FactorTiming
from terminal.domain.models import (
    Category,
    ExecutionDedupKey,
    ExecutionId,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)


def _episode(*, side: PositionSide = PositionSide.LONG, closed: bool = True) -> TradeEpisode:
    key = PositionKey(
        trading_account_id=TradingAccountId("acct-1"),
        category=Category.LINEAR,
        symbol=Symbol("BTCUSDT"),
        position_idx=0,
    )
    allocation = ExecutionAllocation(
        execution_key=ExecutionDedupKey(
            trading_account_id=TradingAccountId("acct-1"),
            category=Category.LINEAR,
            exec_id=ExecutionId("exec-1"),
        ),
        trade_episode_id=TradeEpisodeId("te-1"),
        role=AllocationRole.CLOSE if closed else AllocationRole.OPEN,
        quantity=Decimal("1"),
        fee=Decimal("0.1"),
        occurred_at_ms=200 if closed else 100,
    )
    return TradeEpisode(
        trade_episode_id=TradeEpisodeId("te-1"),
        position_key=key,
        side=side,
        environment=DiaryEnvironment.LIVE,
        opened_at_ms=100,
        closed_at_ms=200 if closed else None,
        opening_price=Price(Decimal("100")),
        average_entry=Price(Decimal("100")),
        open_quantity=Quantity(Decimal("0") if closed else Decimal("1")),
        realized_price_pnl=Decimal("0"),
        execution_fees=Decimal("0.1"),
        allocations=(allocation,),
    )


def _complete_path() -> PostTradePath:
    return PostTradePath(
        trade_episode_id="te-1",
        bars=(
            TradePathBar(100, 150, Decimal("110"), Decimal("95")),
            TradePathBar(150, 200, Decimal("108"), Decimal("97")),
        ),
        source_version="market-bars-v1",
        observed_at_ms=250,
    )


def test_long_mae_mfe_and_exit_quality_use_only_trade_lifetime():
    result = analyze_post_trade_excursion(
        _episode(side=PositionSide.LONG),
        _complete_path(),
        ExitReference(Decimal("106"), "exit-from-executions-v1"),
    )
    assert result.readiness is ExcursionReadiness.READY
    metrics = result.metrics
    assert metrics is not None
    assert metrics.holding_duration_ms == 100
    assert metrics.mae_price == Decimal("5")
    assert metrics.mfe_price == Decimal("10")
    assert metrics.mae_pct == Decimal("5")
    assert metrics.mfe_pct == Decimal("10")
    assert metrics.exit_excursion_pct == Decimal("6")
    assert metrics.exit_capture_ratio == Decimal("0.6")
    assert metrics.exit_giveback_pct_points == Decimal("4")


def test_short_excursions_are_direction_aware():
    result = analyze_post_trade_excursion(
        _episode(side=PositionSide.SHORT),
        _complete_path(),
        ExitReference(Decimal("96"), "exit-from-executions-v1"),
    )
    metrics = result.metrics
    assert result.readiness is ExcursionReadiness.READY
    assert metrics is not None
    assert metrics.mae_price == Decimal("10")
    assert metrics.mfe_price == Decimal("5")
    assert metrics.mae_pct == Decimal("10")
    assert metrics.mfe_pct == Decimal("5")
    assert metrics.exit_excursion_pct == Decimal("4")
    assert metrics.exit_capture_ratio == Decimal("0.8")
    assert metrics.exit_giveback_pct_points == Decimal("1")


def test_gapped_path_is_incomplete_and_produces_no_metrics():
    path = PostTradePath(
        trade_episode_id="te-1",
        bars=(
            TradePathBar(100, 140, Decimal("104"), Decimal("98")),
            TradePathBar(150, 200, Decimal("106"), Decimal("99")),
        ),
        source_version="market-bars-v1",
        observed_at_ms=250,
    )
    result = analyze_post_trade_excursion(
        _episode(),
        path,
        ExitReference(Decimal("103"), "exit-v1"),
    )
    assert result.readiness is ExcursionReadiness.INCOMPLETE
    assert result.metrics is None
    assert "GAPPED_PATH_COVERAGE" in result.missing_reasons


def test_no_look_ahead_rejects_pre_entry_or_post_exit_bars():
    episode = _episode()
    pre_entry = PostTradePath(
        trade_episode_id="te-1",
        bars=(TradePathBar(90, 200, Decimal("110"), Decimal("90")),),
        source_version="bad-v1",
        observed_at_ms=250,
    )
    with pytest.raises(ValueError, match="pre-entry"):
        analyze_post_trade_excursion(episode, pre_entry, ExitReference(Decimal("100"), "exit-v1"))

    post_exit = PostTradePath(
        trade_episode_id="te-1",
        bars=(TradePathBar(100, 210, Decimal("110"), Decimal("90")),),
        source_version="bad-v1",
        observed_at_ms=250,
    )
    with pytest.raises(ValueError, match="post-exit"):
        analyze_post_trade_excursion(episode, post_exit, ExitReference(Decimal("100"), "exit-v1"))


def test_open_episode_is_not_eligible_for_post_trade_excursion():
    with pytest.raises(ValueError, match="closed episode"):
        analyze_post_trade_excursion(
            _episode(closed=False),
            _complete_path(),
            ExitReference(Decimal("100"), "exit-v1"),
        )


def test_ready_metrics_persist_as_replay_safe_post_trade_factors(tmp_path: Path):
    path = _complete_path()
    exit_ref = ExitReference(Decimal("106"), "exit-from-executions-v1")
    analysis = analyze_post_trade_excursion(_episode(), path, exit_ref)
    factor_db = tmp_path / "d5_factors.sqlite3"

    first = persist_post_trade_excursion_factors(
        analysis=analysis,
        path=path,
        exit_reference=exit_ref,
        database_path=factor_db,
    )
    second = persist_post_trade_excursion_factors(
        analysis=analysis,
        path=path,
        exit_reference=exit_ref,
        database_path=factor_db,
    )
    assert first == 8
    assert second == 0

    with DiaryFactorStore.open(factor_db) as store:
        observations = store.load_observations(
            subject_kind=FactorSubjectKind.TRADE_EPISODE,
            subject_id="te-1",
        )
        assert len(observations) == 8
        assert all(item.subject_kind is FactorSubjectKind.TRADE_EPISODE for item in observations)


def test_d5_definitions_are_post_trade_only_and_do_not_invent_r_normalization():
    assert all(
        item.timing is FactorTiming.POST_TRADE
        and item.subject_kind is FactorSubjectKind.TRADE_EPISODE
        for item in D5_POST_TRADE_FACTOR_DEFINITIONS_V1
    )
    assert all("_r" not in item.factor_key and not item.factor_key.endswith(".r") for item in D5_POST_TRADE_FACTOR_DEFINITIONS_V1)
