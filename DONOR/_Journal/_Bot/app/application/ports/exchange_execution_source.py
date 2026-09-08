"""Small exchange-neutral source boundary for future adapters."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.core.trades.execution_fact import ExecutionFact


@runtime_checkable
class ExchangeExecutionSource(Protocol):
    """Fetch already-normalized execution facts; transport stays outside inward."""

    async def fetch_executions(
        self,
        *,
        cursor: str | None = None,
        since: datetime | None = None,
        end_at: datetime | None = None,
        include_inactive: bool = False,
    ) -> tuple[ExecutionFact, ...]:
        """Return facts after an adapter-owned cursor/time boundary."""
        ...
