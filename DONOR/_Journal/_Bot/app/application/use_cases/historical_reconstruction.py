"""Historical-only execution reconstruction helpers.

Historical exchange fills can contain a one-way position reversal: one SELL
fill may close the remaining LONG and open a new SHORT with its residual
quantity (and vice versa).  The manual Trade Core deliberately keeps its
strict over-close invariant.  This adapter is therefore isolated to preview /
historical reconstruction and never changes manual aggregation semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.core.common.quantity import Quantity
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.trade_aggregate import TradeAggregate
from app.core.trades.trade_aggregation_service import TradeAggregationService


@dataclass(frozen=True, slots=True)
class HistoricalAggregationApplication:
    """Aggregates affected by one source fill.

    A normal fill affects one aggregate.  A reversal affects the closed old
    aggregate and the newly opened opposite aggregate.  ``source_execution``
    remains the original exchange identity in both cases; the internal split
    identity is never exposed as an exchange fact.
    """

    current: TradeAggregate
    aggregates: tuple[TradeAggregate, ...]
    reversal: bool = False
    prior_position_qty: object | None = None
    residual_qty: object | None = None


class HistoricalTradeAggregationAdapter:
    """Reconstruct exchange position continuity without weakening Trade Core."""

    def __init__(self) -> None:
        self._service = TradeAggregationService()

    def get(self, account_id, instrument_id):
        return self._service.get(account_id, instrument_id)

    def all(self):
        return self._service.all()

    def apply_fact(self, fact: ExecutionFact) -> HistoricalAggregationApplication:
        if not isinstance(fact, ExecutionFact):
            raise TypeError("fact must be ExecutionFact")
        execution = Execution.from_fact(fact)
        if self._service.is_duplicate(execution):
            aggregate = self._service.apply(execution)
            return HistoricalAggregationApplication(aggregate, (aggregate,))

        current = self._service.get(fact.account_id, fact.instrument_id)
        if current is None or current.status.value == "CLOSED":
            aggregate = self._service.apply(execution)
            return HistoricalAggregationApplication(aggregate, (aggregate,))

        prior_position_qty = current.open_quantity.value

        opening_side = (
            execution.side.value == "BUY"
            if current.direction.value == "LONG"
            else execution.side.value == "SELL"
        )
        if opening_side or execution.quantity.value <= prior_position_qty:
            aggregate = self._service.apply(execution)
            return HistoricalAggregationApplication(aggregate, (aggregate,))

        close_quantity = Quantity(prior_position_qty)
        residual_quantity = Quantity(execution.quantity.value - close_quantity.value)
        close_ratio = close_quantity.value / execution.quantity.value
        close_fee = execution.fee * close_ratio
        residual_fee = execution.fee - close_fee
        external_id = execution.external_execution_id or "execution"
        close_execution = replace(
            execution,
            quantity=close_quantity,
            fee=close_fee,
            external_execution_id=f"{external_id}:historical-close",
        )
        residual_execution = replace(
            execution,
            quantity=residual_quantity,
            fee=residual_fee,
        )
        closed = self._service.apply(close_execution)
        opened = self._service.apply(residual_execution)
        return HistoricalAggregationApplication(
            opened, (closed, opened), reversal=True,
            prior_position_qty=prior_position_qty, residual_qty=residual_quantity.value,
        )
