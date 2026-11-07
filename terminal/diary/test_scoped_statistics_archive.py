from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from terminal.diary.models import (
    AllocationRole, DiaryEnvironment, ExecutionAllocation, TradeEpisode, TradeEpisodeId,
)
from terminal.diary.scoped_statistics_archive import ScopedStatisticsArchive, StatisticsScopeError
from terminal.domain.models import (
    Category, ExecutionDedupKey, ExecutionId, Origin, PositionKey, PositionSide,
    Price, Quantity, Symbol, TradingAccountId,
)


def episode(account_id: str, suffix: str) -> TradeEpisode:
    key = ExecutionDedupKey(TradingAccountId(account_id), Category.LINEAR, ExecutionId(suffix))
    return TradeEpisode(
        trade_episode_id=TradeEpisodeId(f"{account_id}-{suffix}"),
        position_key=PositionKey(TradingAccountId(account_id), Category.LINEAR, Symbol("BTCUSDT"), 0),
        side=PositionSide.LONG, environment=DiaryEnvironment.PAPER,
        opened_at_ms=100, closed_at_ms=None, opening_price=Price(Decimal("100")),
        average_entry=Price(Decimal("100")), open_quantity=Quantity(Decimal("1")),
        realized_price_pnl=Decimal("0"), execution_fees=Decimal("1"),
        allocations=(ExecutionAllocation(
            execution_key=key, trade_episode_id=TradeEpisodeId(f"{account_id}-{suffix}"),
            role=AllocationRole.OPEN, quantity=Decimal("1"), fee=Decimal("1"),
            occurred_at_ms=100,
        ),),
    )


def test_archive_persists_separate_account_and_owner_statistics_without_paper_db(tmp_path: Path):
    archive_path = tmp_path / "scoped_diary_statistics.sqlite3"
    paper_db = tmp_path / "paper_runtime.sqlite3"
    factor_store = tmp_path / "missing_factors.sqlite3"
    manual = episode("paper", "manual-1")
    robot = episode("paper", "robot-1")
    other = episode("bybit-main-1", "live-1")
    evidence = {
        manual.allocations[0].execution_key: Origin.TERMINAL_MANUAL,
        robot.allocations[0].execution_key: Origin.ROBOT,
        other.allocations[0].execution_key: Origin.TERMINAL_MANUAL,
    }
    store = ScopedStatisticsArchive(archive_path)
    try:
        manual_report = store.publish(
            account_id="paper", owner="MANUAL", source_revision=1,
            episodes=(manual, robot), origin_evidence=evidence, factor_store_path=factor_store,
        )
        robot_report = store.publish(
            account_id="paper", owner="ROBOT", source_revision=1,
            episodes=(manual, robot), origin_evidence=evidence, factor_store_path=factor_store,
        )
        main_report = store.publish(
            account_id="bybit-main-1", owner="MANUAL", source_revision=1,
            episodes=(other,), origin_evidence=evidence, factor_store_path=factor_store,
        )
        assert manual_report["statistics"]["sample"]["total"] == 1
        assert robot_report["statistics"]["sample"]["total"] == 1
        assert main_report["statistics"]["sample"]["total"] == 1
        assert store.latest(account_id="paper", owner="MANUAL") == manual_report
        assert store.latest(account_id="paper", owner="ROBOT") == robot_report
        assert store.latest(account_id="bybit-main-1", owner="MANUAL") == main_report
        assert store.latest(account_id="bybit-main-1", owner="ROBOT") is None
        assert not paper_db.exists()
        assert not factor_store.exists()
    finally:
        store.close()

    reopened = ScopedStatisticsArchive(archive_path)
    try:
        assert reopened.latest(account_id="paper", owner="ROBOT") == robot_report
    finally:
        reopened.close()


def test_unknown_origin_or_mixed_episode_blocks_publication_not_pnl_estimate(tmp_path: Path):
    store = ScopedStatisticsArchive(tmp_path / "scoped_diary_statistics.sqlite3")
    one = episode("paper", "unknown")
    key = one.allocations[0].execution_key
    try:
        with pytest.raises(StatisticsScopeError, match="unattributed"):
            store.publish(account_id="paper", owner="MANUAL", source_revision=1,
                          episodes=(one,), origin_evidence={}, factor_store_path=tmp_path / "none")
        with pytest.raises(StatisticsScopeError, match="unattributed"):
            store.publish(account_id="paper", owner="ROBOT", source_revision=1,
                          episodes=(one,), origin_evidence={key: Origin.EXTERNAL},
                          factor_store_path=tmp_path / "none")
        assert store.latest(account_id="paper", owner="MANUAL") is None
        assert store.latest(account_id="paper", owner="ROBOT") is None
    finally:
        store.close()


def test_mixed_manual_robot_episode_does_not_enter_either_account_report(tmp_path: Path):
    store = ScopedStatisticsArchive(tmp_path / "scoped_diary_statistics.sqlite3")
    manual = episode("paper", "manual")
    robot = episode("paper", "robot")
    # A single economic position episode may contain allocations from two
    # different controllers. It is NOT legal to split PnL by execution origin.
    mixed = replace(manual, allocations=(
        manual.allocations[0],
        replace(robot.allocations[0], trade_episode_id=manual.trade_episode_id),
    ))
    origins = {
        manual.allocations[0].execution_key: Origin.TERMINAL_MANUAL,
        robot.allocations[0].execution_key: Origin.ROBOT,
    }
    try:
        for owner in ("MANUAL", "ROBOT"):
            with pytest.raises(StatisticsScopeError, match="mixed_controller"):
                store.publish(
                    account_id="paper", owner=owner, source_revision=1,
                    episodes=(mixed,), origin_evidence=origins,
                    factor_store_path=tmp_path / "missing",
                )
            assert store.latest(account_id="paper", owner=owner) is None
    finally:
        store.close()


def test_cross_account_replay_and_invalid_scope_fail_closed(tmp_path: Path):
    store = ScopedStatisticsArchive(tmp_path / "scoped_diary_statistics.sqlite3")
    one = episode("paper", "one")
    key = one.allocations[0].execution_key
    evidence = {key: Origin.ROBOT}
    try:
        with pytest.raises(StatisticsScopeError, match="cross_account"):
            store.publish(account_id="bybit-main", owner="ROBOT", source_revision=1,
                          episodes=(one,), origin_evidence=evidence, factor_store_path=tmp_path / "none")
        with pytest.raises(StatisticsScopeError, match="owner_required"):
            store.publish(account_id="paper", owner="ALL", source_revision=1,
                          episodes=(one,), origin_evidence=evidence, factor_store_path=tmp_path / "none")
        report = store.publish(account_id="paper", owner="ROBOT", source_revision=2,
                               episodes=(one,), origin_evidence=evidence, factor_store_path=tmp_path / "none")
        assert store.publish(account_id="paper", owner="ROBOT", source_revision=2,
                             episodes=(one,), origin_evidence=evidence, factor_store_path=tmp_path / "none") == report
        with pytest.raises(StatisticsScopeError, match="stale"):
            store.publish(account_id="paper", owner="ROBOT", source_revision=1,
                          episodes=(one,), origin_evidence=evidence, factor_store_path=tmp_path / "none")
        with pytest.raises(StatisticsScopeError, match="conflicting"):
            store.publish(account_id="paper", owner="ROBOT", source_revision=2,
                          episodes=(), origin_evidence=evidence, factor_store_path=tmp_path / "none")
    finally:
        store.close()


def test_archive_cannot_be_mistaken_for_live_paper_database(tmp_path: Path):
    with pytest.raises(StatisticsScopeError, match="independent"):
        ScopedStatisticsArchive(tmp_path / "paper_runtime.sqlite3")
    assert not (tmp_path / "paper_runtime.sqlite3").exists()
