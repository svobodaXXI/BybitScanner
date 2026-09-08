"""Replay-safe reconstruction of Trading Diary trade episodes.

The reconstructor consumes immutable Terminal executions already persisted by the
existing execution/reconciliation path. It is observational: no order or
position mutation is performed here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from terminal.domain.models import Execution, OrderSide, PositionKey, PositionSide, Price, Quantity

from .models import (
    AllocationRole,
    DiaryEnvironment,
    ExecutionAllocation,
    TradeEpisode,
    TradeEpisodeId,
    position_key_for_execution,
    signed_quantity,
)


@dataclass(slots=True)
class _EpisodeBuilder:
    episode_id: TradeEpisodeId
    position_key: PositionKey
    side: PositionSide
    environment: DiaryEnvironment
    opened_at_ms: int
    opening_price: Decimal
    average_entry: Decimal
    signed_position: Decimal
    realized_price_pnl: Decimal = Decimal("0")
    execution_fees: Decimal = Decimal("0")
    closed_at_ms: int | None = None
    allocations: list[ExecutionAllocation] = field(default_factory=list)

    @property
    def abs_quantity(self) -> Decimal:
        return abs(self.signed_position)

    def freeze(self) -> TradeEpisode:
        return TradeEpisode(
            trade_episode_id=self.episode_id,
            position_key=self.position_key,
            side=self.side,
            environment=self.environment,
            opened_at_ms=self.opened_at_ms,
            closed_at_ms=self.closed_at_ms,
            opening_price=Price(self.opening_price),
            average_entry=Price(self.average_entry),
            open_quantity=Quantity(self.abs_quantity),
            realized_price_pnl=self.realized_price_pnl,
            execution_fees=self.execution_fees,
            allocations=tuple(self.allocations),
        )


class TradeEpisodeReconstructor:
    """Deterministically reconstruct episodes from persisted immutable executions."""

    def reconstruct(
        self,
        executions: tuple[Execution, ...] | list[Execution],
        *,
        environment: DiaryEnvironment,
    ) -> tuple[TradeEpisode, ...]:
        if not isinstance(environment, DiaryEnvironment):
            environment = DiaryEnvironment(environment)

        ordered = sorted(
            tuple(executions),
            key=lambda item: (
                item.exchange_timestamp_ms,
                item.dedup_key.trading_account_id.value,
                item.dedup_key.category.value,
                item.symbol.value,
                item.dedup_key.exec_id.value,
            ),
        )
        seen = set()
        active: dict[PositionKey, _EpisodeBuilder] = {}
        history: list[_EpisodeBuilder] = []

        for execution in ordered:
            if not isinstance(execution, Execution):
                raise TypeError("executions must contain terminal.domain.models.Execution values")
            key = execution.dedup_key
            if key in seen:
                continue
            seen.add(key)
            position_key = position_key_for_execution(execution)
            current = active.get(position_key)
            if current is None:
                opened = self._open_episode(execution, position_key, environment, reversal=False)
                active[position_key] = opened
                history.append(opened)
                continue

            delta = signed_quantity(execution.side, execution.quantity.value)
            current_sign = Decimal("1") if current.signed_position > 0 else Decimal("-1")
            delta_sign = Decimal("1") if delta > 0 else Decimal("-1")

            if current_sign == delta_sign:
                self._increase(current, execution)
                continue

            current_qty = current.abs_quantity
            execution_qty = execution.quantity.value
            close_qty = min(current_qty, execution_qty)
            residual = execution_qty - close_qty
            close_fee = execution.fee if residual == 0 else execution.fee * close_qty / execution_qty
            open_fee = execution.fee - close_fee
            role = AllocationRole.CLOSE if close_qty == current_qty else AllocationRole.REDUCE
            self._reduce(current, execution, close_qty, close_fee, role)

            if current.signed_position == 0:
                current.closed_at_ms = execution.exchange_timestamp_ms
                active.pop(position_key, None)

            if residual > 0:
                residual_execution = Execution(
                    dedup_key=execution.dedup_key,
                    order_id=execution.order_id,
                    symbol=execution.symbol,
                    side=execution.side,
                    price=execution.price,
                    quantity=Quantity(residual),
                    fee=open_fee,
                    exchange_timestamp_ms=execution.exchange_timestamp_ms,
                )
                opened = self._open_episode(
                    residual_execution,
                    position_key,
                    environment,
                    reversal=True,
                    original_execution=execution,
                )
                active[position_key] = opened
                history.append(opened)

        return tuple(item.freeze() for item in history)

    @staticmethod
    def _episode_id(execution: Execution, position_key: PositionKey, *, reversal: bool) -> TradeEpisodeId:
        payload = "|".join(
            (
                position_key.trading_account_id.value,
                position_key.category.value,
                position_key.symbol.value,
                str(position_key.position_idx),
                execution.dedup_key.exec_id.value,
                "reversal" if reversal else "open",
            )
        )
        return TradeEpisodeId("te_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24])

    def _open_episode(
        self,
        execution: Execution,
        position_key: PositionKey,
        environment: DiaryEnvironment,
        *,
        reversal: bool,
        original_execution: Execution | None = None,
    ) -> _EpisodeBuilder:
        signed = signed_quantity(execution.side, execution.quantity.value)
        side = PositionSide.LONG if signed > 0 else PositionSide.SHORT
        source_execution = original_execution or execution
        builder = _EpisodeBuilder(
            episode_id=self._episode_id(source_execution, position_key, reversal=reversal),
            position_key=position_key,
            side=side,
            environment=environment,
            opened_at_ms=execution.exchange_timestamp_ms,
            opening_price=execution.price.value,
            average_entry=execution.price.value,
            signed_position=signed,
            execution_fees=execution.fee,
        )
        builder.allocations.append(
            ExecutionAllocation(
                execution_key=source_execution.dedup_key,
                trade_episode_id=builder.episode_id,
                role=AllocationRole.REVERSAL_OPEN if reversal else AllocationRole.OPEN,
                quantity=execution.quantity.value,
                fee=execution.fee,
                occurred_at_ms=execution.exchange_timestamp_ms,
            )
        )
        return builder

    @staticmethod
    def _increase(current: _EpisodeBuilder, execution: Execution) -> None:
        previous_qty = current.abs_quantity
        added_qty = execution.quantity.value
        total = previous_qty + added_qty
        current.average_entry = (
            (current.average_entry * previous_qty) + (execution.price.value * added_qty)
        ) / total
        current.signed_position += signed_quantity(execution.side, added_qty)
        current.execution_fees += execution.fee
        current.allocations.append(
            ExecutionAllocation(
                execution_key=execution.dedup_key,
                trade_episode_id=current.episode_id,
                role=AllocationRole.INCREASE,
                quantity=added_qty,
                fee=execution.fee,
                occurred_at_ms=execution.exchange_timestamp_ms,
            )
        )

    @staticmethod
    def _reduce(
        current: _EpisodeBuilder,
        execution: Execution,
        quantity: Decimal,
        fee: Decimal,
        role: AllocationRole,
    ) -> None:
        if current.side is PositionSide.LONG:
            pnl = (execution.price.value - current.average_entry) * quantity
            current.signed_position -= quantity
        else:
            pnl = (current.average_entry - execution.price.value) * quantity
            current.signed_position += quantity
        current.realized_price_pnl += pnl
        current.execution_fees += fee
        current.allocations.append(
            ExecutionAllocation(
                execution_key=execution.dedup_key,
                trade_episode_id=current.episode_id,
                role=role,
                quantity=quantity,
                fee=fee,
                occurred_at_ms=execution.exchange_timestamp_ms,
            )
        )
