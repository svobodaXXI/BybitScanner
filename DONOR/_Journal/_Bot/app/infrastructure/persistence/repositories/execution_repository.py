"""SQLAlchemy async adapter for append-only Execution facts."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.application.errors import DuplicateExecutionError, PersistenceIntegrityError
from app.application.ports.repositories import ExecutionRepository
from app.core.accounts.account_id import AccountId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade_id import TradeId

from ..mappers import execution_from_orm, execution_to_orm
from ..models.execution import ExecutionORM
from ._common import is_named_constraint, require_session


def _normal_exchange(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("exchange must be a non-empty string")
    return value.strip().upper()


def _external_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("external_execution_id must be a non-empty string")
    return value.strip()


class SqlAlchemyExecutionRepository(ExecutionRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def save(self, execution: Execution) -> None:
        if not isinstance(execution, Execution):
            raise TypeError("execution must be Execution")
        if execution.external_execution_id is not None:
            external_id = _external_id(execution.external_execution_id)
            duplicate = await self.get_by_external_id(
                exchange=execution.exchange,
                account_id=execution.account_id,
                external_execution_id=external_id,
            )
            if duplicate is not None and duplicate.execution_id != execution.execution_id:
                raise DuplicateExecutionError("external execution identity already exists")
        existing = await self._load(execution.execution_id)
        if existing is not None:
            current = self._to_domain(existing)
            if current == execution:
                return
            raise PersistenceIntegrityError("execution_id already contains different factual data")
        self._session.add(execution_to_orm(execution))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if is_named_constraint(error, "uq_executions_exchange_account_external_id"):
                raise DuplicateExecutionError("external execution identity already exists") from error
            raise PersistenceIntegrityError("execution could not be persisted") from error

    async def get_by_id(self, execution_id: ExecutionId) -> Execution | None:
        if not isinstance(execution_id, ExecutionId):
            raise TypeError("execution_id must be ExecutionId")
        model = await self._load(execution_id)
        return None if model is None else self._to_domain(model)

    async def get_by_external_id(
        self,
        *,
        exchange: str,
        account_id: AccountId,
        external_execution_id: str,
    ) -> Execution | None:
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        statement = select(ExecutionORM).where(
            ExecutionORM.exchange == _normal_exchange(exchange),
            ExecutionORM.account_id == account_id.value,
            ExecutionORM.external_execution_id == _external_id(external_execution_id),
        )
        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()
        return None if model is None else self._to_domain(model)

    async def list_by_trade(self, trade_id: TradeId) -> tuple[Execution, ...]:
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        result = await self._session.execute(
            select(ExecutionORM)
            .where(ExecutionORM.trade_id == trade_id.value)
            .order_by(ExecutionORM.executed_at.asc(), ExecutionORM.id.asc())
        )
        return tuple(self._to_domain(model) for model in result.scalars().all())

    async def _load(self, execution_id: ExecutionId):
        result = await self._session.execute(select(ExecutionORM).where(ExecutionORM.id == execution_id.value))
        return result.scalar_one_or_none()

    @staticmethod
    def _to_domain(model: ExecutionORM) -> Execution:
        try:
            return execution_from_orm(model)
        except (TypeError, ValueError) as error:
            raise PersistenceIntegrityError("persisted Execution violates Domain invariants") from error
