"""SQLAlchemy persistence model for factual executions and idempotency."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .trade import NUMERIC_TYPE


def _utcnow() -> datetime:
    """Persistence timestamp; exchange facts keep their own executed_at."""
    return datetime.now(timezone.utc)


class ExecutionORM(Base):
    __tablename__ = "executions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), nullable=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    price: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    fee_amount: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    fee_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exchange: Mapped[str] = mapped_column(String(64), nullable=False)
    external_execution_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


Index(
    "uq_executions_exchange_account_external_id",
    ExecutionORM.exchange,
    ExecutionORM.account_id,
    ExecutionORM.external_execution_id,
    unique=True,
    postgresql_where=ExecutionORM.external_execution_id.is_not(None),
)
Index("ix_executions_trade_executed_at", ExecutionORM.trade_id, ExecutionORM.executed_at)
Index(
    "ix_executions_account_instrument_executed_at",
    ExecutionORM.account_id,
    ExecutionORM.instrument_id,
    ExecutionORM.executed_at,
)
