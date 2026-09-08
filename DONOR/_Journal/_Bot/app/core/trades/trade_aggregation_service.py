"""Instance-scoped aggregation of executions into logical trades."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.instruments.instrument_id import InstrumentId

from .execution import Execution
from .execution_fact import ExecutionFact
from .trade_aggregate import TradeAggregate
from .trade_id import TradeId


AggregationKey = tuple[AccountId, InstrumentId]
ExternalExecutionKey = tuple[str, AccountId, str]


@dataclass(slots=True)
class TradeAggregationService:
    """Apply executions to one net-position aggregate per account/instrument.

    The one-net-position policy is local to this service instance. It is an MVP
    aggregation policy and does not constrain the broader Trade domain.
    """

    _current: dict[AggregationKey, TradeAggregate] = field(default_factory=dict)
    _history: list[TradeAggregate] = field(default_factory=list)
    _seen_external: dict[ExternalExecutionKey, TradeId] = field(default_factory=dict)

    def apply_fact(self, fact: ExecutionFact) -> TradeAggregate:
        """Convert a fact to an Execution and apply it."""
        if not isinstance(fact, ExecutionFact):
            raise TypeError("fact must be ExecutionFact")
        return self.apply(Execution.from_fact(fact))

    def apply(self, execution: Execution) -> TradeAggregate:
        """Apply an execution, ignoring a replayed external execution."""
        if not isinstance(execution, Execution):
            raise TypeError("execution must be Execution")
        key = (execution.account_id, execution.instrument_id)
        duplicate_key = self._external_key(execution)
        if duplicate_key is not None and duplicate_key in self._seen_external:
            trade_id = self._seen_external[duplicate_key]
            return self._aggregate_by_trade_id(trade_id)

        aggregate = self._current.get(key)
        if aggregate is None or aggregate.status.value == "CLOSED":
            aggregate = TradeAggregate.open_from_execution(execution)
            self._current[key] = aggregate
            self._history.append(aggregate)
        else:
            aggregate.apply(execution)

        if duplicate_key is not None:
            self._seen_external[duplicate_key] = aggregate.trade_id
        return aggregate

    def is_duplicate(self, execution: Execution) -> bool:
        """Return whether an external execution has already been applied."""
        if not isinstance(execution, Execution):
            raise TypeError("execution must be Execution")
        duplicate_key = self._external_key(execution)
        return duplicate_key is not None and duplicate_key in self._seen_external

    def get(self, account_id: AccountId, instrument_id: InstrumentId) -> TradeAggregate | None:
        """Return the current/latest aggregate for an account and instrument."""
        return self._current.get((account_id, instrument_id))

    def all(self) -> list[TradeAggregate]:
        """Return all aggregates created by this service instance."""
        return list(self._history)

    def add_expense(
        self,
        account_id: AccountId,
        instrument_id: InstrumentId,
        expense: Expense,
    ) -> TradeAggregate:
        """Add a signed expense to the current aggregate."""
        aggregate = self.get(account_id, instrument_id)
        if aggregate is None:
            raise ValueError("no aggregate exists for account and instrument")
        aggregate.add_expense(expense)
        return aggregate

    def reset(self) -> None:
        """Reset this in-memory aggregation context."""
        self._current.clear()
        self._history.clear()
        self._seen_external.clear()

    @staticmethod
    def _external_key(execution: Execution) -> ExternalExecutionKey | None:
        if execution.external_execution_id is None:
            return None
        return (
            execution.exchange,
            execution.account_id,
            execution.external_execution_id,
        )

    def _aggregate_by_trade_id(self, trade_id: TradeId) -> TradeAggregate:
        for aggregate in self._history:
            if aggregate.trade_id == trade_id:
                return aggregate
        raise RuntimeError("idempotency index points to a missing aggregate")
