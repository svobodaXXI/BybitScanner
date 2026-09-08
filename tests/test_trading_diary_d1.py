from decimal import Decimal

import pytest

from terminal.diary import DiaryEnvironment, TradeEpisodeReconstructor
from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    OrderId,
    OrderSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)


def _execution(exec_id: str, side: OrderSide, qty: str, price: str, fee: str, ts: int) -> Execution:
    return Execution(
        dedup_key=ExecutionDedupKey(
            TradingAccountId("acct"), Category.LINEAR, ExecutionId(exec_id)
        ),
        order_id=OrderId(f"order-{exec_id}"),
        symbol=Symbol("BTCUSDT"),
        side=side,
        price=Price(Decimal(price)),
        quantity=Quantity(Decimal(qty)),
        fee=Decimal(fee),
        exchange_timestamp_ms=ts,
    )


def test_reconstructs_one_episode_with_increase_partial_reduce_and_close():
    executions = (
        _execution("e1", OrderSide.BUY, "2", "100", "0.2", 1),
        _execution("e2", OrderSide.BUY, "1", "110", "0.1", 2),
        _execution("e3", OrderSide.SELL, "1", "120", "0.1", 3),
        _execution("e4", OrderSide.SELL, "2", "90", "0.2", 4),
    )

    episodes = TradeEpisodeReconstructor().reconstruct(
        executions, environment=DiaryEnvironment.LIVE
    )

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.is_closed
    assert episode.open_quantity.value == Decimal("0")
    assert episode.closed_at_ms == 4
    assert [item.role.value for item in episode.allocations] == [
        "OPEN", "INCREASE", "REDUCE", "CLOSE"
    ]
    assert episode.execution_fees == Decimal("0.6")
    assert episode.realized_price_pnl.quantize(Decimal("0.00000001")) == Decimal("-10.00000000")


def test_replay_duplicate_does_not_duplicate_episode_or_allocation():
    execution = _execution("e1", OrderSide.BUY, "1", "100", "0.1", 1)
    episodes = TradeEpisodeReconstructor().reconstruct(
        (execution, execution), environment=DiaryEnvironment.PAPER
    )

    assert len(episodes) == 1
    assert len(episodes[0].allocations) == 1
    assert episodes[0].open_quantity.value == Decimal("1")


def test_conflicting_duplicate_execution_evidence_is_rejected():
    first = _execution("e1", OrderSide.BUY, "1", "100", "0.1", 1)
    conflict = _execution("e1", OrderSide.BUY, "1", "101", "0.1", 1)

    with pytest.raises(ValueError, match="conflicting immutable evidence"):
        TradeEpisodeReconstructor().reconstruct(
            (first, conflict), environment=DiaryEnvironment.LIVE
        )


def test_zero_crossing_reversal_splits_execution_without_double_counting_quantity_or_fee():
    executions = (
        _execution("e1", OrderSide.BUY, "2", "100", "0.2", 1),
        _execution("e2", OrderSide.SELL, "3", "90", "0.3", 2),
    )

    episodes = TradeEpisodeReconstructor().reconstruct(
        executions, environment=DiaryEnvironment.LIVE
    )

    assert len(episodes) == 2
    long_episode, short_episode = episodes
    assert long_episode.is_closed
    assert long_episode.open_quantity.value == Decimal("0")
    assert short_episode.open_quantity.value == Decimal("1")
    assert short_episode.side.value == "Short"
    reversal_allocations = [
        allocation
        for episode in episodes
        for allocation in episode.allocations
        if allocation.execution_key.exec_id.value == "e2"
    ]
    assert sum(item.quantity for item in reversal_allocations) == Decimal("3")
    assert sum(item.fee for item in reversal_allocations) == Decimal("0.3")
    assert [item.role.value for item in reversal_allocations] == ["CLOSE", "REVERSAL_OPEN"]


def test_episode_identity_is_stable_for_same_persisted_execution_history():
    executions = (
        _execution("e1", OrderSide.SELL, "1", "100", "0.1", 1),
        _execution("e2", OrderSide.BUY, "1", "90", "0.1", 2),
    )
    reconstructor = TradeEpisodeReconstructor()

    first = reconstructor.reconstruct(executions, environment=DiaryEnvironment.LIVE)
    second = reconstructor.reconstruct(tuple(reversed(executions)), environment=DiaryEnvironment.LIVE)

    assert first[0].trade_episode_id == second[0].trade_episode_id
    assert first == second
