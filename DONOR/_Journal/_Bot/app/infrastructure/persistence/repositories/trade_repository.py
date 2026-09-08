"""SQLAlchemy async adapter for the current Trade repository port."""

from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.application.errors import PersistenceIntegrityError
from app.application.ports.repositories import TradeRepository
from app.core.accounts.account_id import AccountId
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeStatus
from app.core.trades.enums import TradePnLSource
from app.core.trades.trade import Trade
from app.core.trades.execution_replay import validate_execution_replay
from app.core.trades.trade_id import TradeId

from ..mappers import trade_from_orm, trade_to_orm
from ..models.trade import TradeExpenseORM, TradeORM
from ..models.execution import ExecutionORM
from ..mappers import execution_from_orm
from ..models.history_import import TradeJournalStateORM
from ._common import require_session


_TRADE_SCALARS = (
    "account_id", "instrument_id", "direction", "status", "opened_at", "closed_at",
    "entry_price", "exit_price", "quantity", "stop_price", "take_profit", "currency", "risk_amount",
    "risk_currency", "fees_amount", "fees_currency", "gross_pnl_amount", "gross_pnl_currency",
    "net_pnl_amount", "net_pnl_currency", "pnl_source", "updated_at",
)


def _expense_key(amount, currency):
    return amount, currency


class SqlAlchemyTradeRepository(TradeRepository):
    """Uses an injected session; callers own commit, rollback, and close."""

    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def get_by_id(self, trade_id: TradeId) -> Trade | None:
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        model = await self._load_model(trade_id)
        return None if model is None else await self._to_domain(model)

    async def save(self, trade: Trade) -> None:
        if not isinstance(trade, Trade):
            raise TypeError("trade must be Trade")
        existing = await self._load_model(trade.trade_id)
        if existing is None:
            self._session.add(trade_to_orm(trade))
            await self._session.flush()
            return

        # Rehydrate first so a corrupt cached PnL cannot be overwritten silently.
        await self._to_domain(existing)
        candidate = trade_to_orm(trade)
        for name in _TRADE_SCALARS:
            setattr(existing, name, getattr(candidate, name))
        self._append_expenses(existing, trade)
        await self._session.flush()

    async def list_open(
        self,
        *,
        account_id: AccountId | None = None,
        instrument_id: InstrumentId | None = None,
        include_excluded: bool = False,
    ) -> tuple[Trade, ...]:
        if account_id is not None and not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId or None")
        if instrument_id is not None and not isinstance(instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId or None")
        statement = (
            select(TradeORM)
            .options(selectinload(TradeORM.expenses))
            .where(TradeORM.status == TradeStatus.OPEN.value)
            .order_by(TradeORM.opened_at.asc(), TradeORM.id.asc())
        )
        if not include_excluded:
            statement = statement.where(~select(TradeJournalStateORM.trade_id).where(
                TradeJournalStateORM.trade_id == TradeORM.id,
                TradeJournalStateORM.state != "INCLUDED",
            ).exists())
        if account_id is not None:
            statement = statement.where(TradeORM.account_id == account_id.value)
        if instrument_id is not None:
            statement = statement.where(TradeORM.instrument_id == instrument_id.value)
        result = await self._session.execute(statement)
        return tuple([await self._to_domain(model) for model in result.scalars().all()])

    async def list_all(
        self,
        *,
        account_id: AccountId | None = None,
        instrument_id: InstrumentId | None = None,
        limit: int = 100,
        offset: int = 0,
        direction=None,
        status=None,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        include_excluded: bool = False,
    ) -> tuple[Trade, ...]:
        if account_id is not None and not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId or None")
        if instrument_id is not None and not isinstance(instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId or None")
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be an integer >= 1")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be an integer >= 0")
        statement = (
            select(TradeORM)
            .options(selectinload(TradeORM.expenses))
            .order_by(TradeORM.opened_at.desc(), TradeORM.id.desc())
            .offset(offset)
            .limit(limit)
        )
        if not include_excluded:
            statement = statement.where(~select(TradeJournalStateORM.trade_id).where(
                TradeJournalStateORM.trade_id == TradeORM.id,
                TradeJournalStateORM.state != "INCLUDED",
            ).exists())
        if account_id is not None:
            statement = statement.where(TradeORM.account_id == account_id.value)
        if instrument_id is not None:
            statement = statement.where(TradeORM.instrument_id == instrument_id.value)
        if direction is not None:
            statement = statement.where(TradeORM.direction == getattr(direction, "value", direction))
        if status is not None:
            statement = statement.where(TradeORM.status == getattr(status, "value", status))
        filter_time = func.coalesce(TradeORM.closed_at, TradeORM.opened_at)
        if from_at is not None:
            statement = statement.where(filter_time >= from_at)
        if to_at is not None:
            statement = statement.where(filter_time < to_at)
        result = await self._session.execute(statement)
        return tuple([await self._to_domain(model) for model in result.scalars().all()])

    async def _load_model(self, trade_id: TradeId):
        statement = (
            select(TradeORM)
            .options(selectinload(TradeORM.expenses))
            .where(TradeORM.id == trade_id.value)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _to_domain(self, model: TradeORM) -> Trade:
        try:
            trade = trade_from_orm(model)
            if trade.pnl_source is TradePnLSource.EXECUTION_REPLAY:
                result = await self._session.execute(
                    select(ExecutionORM)
                    .where(ExecutionORM.trade_id == model.id)
                    .order_by(ExecutionORM.executed_at.asc(), ExecutionORM.id.asc())
                )
                validate_execution_replay(
                    trade,
                    tuple(execution_from_orm(item) for item in result.scalars().all()),
                )
            return trade
        except (TypeError, ValueError) as error:
            raise PersistenceIntegrityError("persisted Trade violates Domain invariants") from error

    @staticmethod
    def _append_expenses(existing: TradeORM, trade: Trade) -> None:
        persisted = list(existing.expenses or ())
        old_counts = Counter(_expense_key(item.amount, item.currency) for item in persisted)
        new_counts = Counter(_expense_key(item.amount.amount, item.amount.currency) for item in trade.expenses)
        if any(old_counts[key] > new_counts[key] for key in old_counts):
            raise PersistenceIntegrityError("Trade expenses are append-only and cannot be removed or rewritten")
        missing = new_counts - old_counts
        for expense in trade.expenses:
            key = _expense_key(expense.amount.amount, expense.amount.currency)
            if missing[key]:
                existing.expenses.append(
                    TradeExpenseORM(
                        trade_id=trade.trade_id.value,
                        sequence=max((item.sequence for item in persisted), default=-1) + 1,
                        amount=expense.amount.amount,
                        currency=expense.amount.currency,
                        created_at=trade.opened_at,
                    )
                )
                persisted.append(existing.expenses[-1])
                missing[key] -= 1
