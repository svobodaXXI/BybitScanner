"""Persist one normalized external execution with durable idempotency."""

from dataclasses import dataclass
from enum import StrEnum

from app.application.errors import (
    AccountNotFoundError,
    DuplicateExecutionError,
    ExecutionFactConflictError,
    InstrumentMappingNotFoundError,
    InvalidExecutionFactError,
)
from app.application.ports.repositories import AccountRepository, ExecutionRepository, InstrumentRepository
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.accounts.account_id import AccountId
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.execution_id import ExecutionId


class ExecutionProcessingStatus(StrEnum):
    PROCESSED = "PROCESSED"
    ALREADY_PROCESSED = "ALREADY_PROCESSED"


@dataclass(frozen=True, slots=True)
class ProcessExecutionFactResult:
    status: ExecutionProcessingStatus
    execution_id: ExecutionId
    account_id: AccountId
    instrument_id: InstrumentId
    exchange: str
    external_execution_id: str


class ProcessExecutionFact:
    """Application boundary from normalized facts to existing Execution persistence.

    Trade lifecycle/aggregation is intentionally not invoked here: the current
    aggregation service is instance-scoped and durable Trade updates need a
    later transaction/UoW decision before exchange ingestion is enabled.
    """

    def __init__(
        self,
        execution_repository: ExecutionRepository,
        account_repository: AccountRepository,
        instrument_repository: InstrumentRepository,
    ) -> None:
        self._executions = execution_repository
        self._accounts = account_repository
        self._instruments = instrument_repository

    async def execute(self, fact: ExecutionFact) -> ProcessExecutionFactResult:
        candidate, existing = await self.prepare(fact)
        if existing is not None:
            return self.replay_result(existing, candidate)
        try:
            await self._executions.save(candidate)
        except DuplicateExecutionError:
            existing = await self._executions.get_by_external_id(
                exchange=fact.exchange,
                account_id=fact.account_id,
                external_execution_id=candidate.external_execution_id,
            )
            if existing is None:
                raise
            return self.replay_result(existing, candidate)
        return ProcessExecutionFactResult(
            ExecutionProcessingStatus.PROCESSED,
            candidate.execution_id,
            candidate.account_id,
            candidate.instrument_id,
            candidate.exchange,
            candidate.external_execution_id,
        )

    async def prepare(self, fact: ExecutionFact) -> tuple[Execution, Execution | None]:
        """Validate and load the durable identity without mutating repositories."""
        if not isinstance(fact, ExecutionFact):
            raise TypeError("fact must be ExecutionFact")
        external_id = fact.external_execution_id
        if not isinstance(external_id, str) or not external_id.strip():
            raise InvalidExecutionFactError("external_execution_id is required for exchange ingestion")
        if not await self._accounts.exists(fact.account_id):
            raise AccountNotFoundError(f"external account is not a Journal account: {fact.account_id}")
        if await self._instruments.get_by_id(fact.instrument_id) is None:
            raise InstrumentMappingNotFoundError(f"instrument mapping not found: {fact.instrument_id}")

        candidate = Execution.from_fact(fact)
        existing = await self._executions.get_by_external_id(
            exchange=fact.exchange,
            account_id=fact.account_id,
            external_execution_id=external_id.strip(),
        )
        return candidate, existing

    @staticmethod
    def replay_result(existing: Execution, candidate: Execution) -> ProcessExecutionFactResult:
        if not _same_external_facts(existing, candidate) and not _same_confirmed_reversal_replay(existing, candidate):
            raise ExecutionFactConflictError(
                f"external execution identity conflicts with stored facts: {candidate.exchange}/{candidate.external_execution_id}"
            )
        return ProcessExecutionFactResult(
            ExecutionProcessingStatus.ALREADY_PROCESSED,
            existing.execution_id,
            existing.account_id,
            existing.instrument_id,
            existing.exchange,
            existing.external_execution_id,
        )


def _same_external_facts(left: Execution, right: Execution) -> bool:
    return all(
        getattr(left, name) == getattr(right, name)
        for name in (
            "account_id",
            "instrument_id",
            "side",
            "quantity",
            "price",
            "fee",
            "executed_at",
            "exchange",
            "external_execution_id",
            "external_order_id",
            "position_id",
        )
    )


def _same_confirmed_reversal_replay(existing: Execution, candidate: Execution) -> bool:
    """Recognize the residual leg of a previously split confirmed Bybit fill."""
    if existing.exchange != "BYBIT" or not existing.external_order_id:
        return False
    if not existing.external_order_id.endswith("::reversal-residual"):
        return False
    return all(
        getattr(existing, name) == getattr(candidate, name)
        for name in (
            "account_id", "instrument_id", "side", "price", "executed_at",
            "exchange", "external_execution_id", "position_id",
        )
    ) and existing.quantity.value < candidate.quantity.value and existing.fee.amount <= candidate.fee.amount
