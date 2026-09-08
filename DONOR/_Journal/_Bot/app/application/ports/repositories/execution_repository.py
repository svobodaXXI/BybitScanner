"""Repository port for factual executions."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade_id import TradeId


@runtime_checkable
class ExecutionRepository(Protocol):
    """Async contract including durable external-id lookup for idempotency."""

    async def save(self, execution: Execution) -> None:
        """Persist an execution by its internal execution_id."""
        ...

    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        ...

    async def get_by_external_id(
        self,
        *,
        exchange: str,
        account_id: AccountId,
        external_execution_id: str,
    ) -> Execution | None:
        """Find a real, non-empty external execution identity."""
        ...

    async def list_by_trade(self, trade_id: TradeId) -> tuple[Execution, ...]:
        """Return executions ordered by executed_at, then execution_id."""
        ...
