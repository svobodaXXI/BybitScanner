"""SQLAlchemy persistence models for Trade and signed trade expenses."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base


NUMERIC_TYPE = Numeric(38, 18)


class TradeORM(Base):
    __tablename__ = "trades"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False
    )
    instrument_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_price: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    stop_price: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    risk_amount: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    risk_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fees_amount: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    fees_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    gross_pnl_amount: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    gross_pnl_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    net_pnl_amount: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    net_pnl_currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pnl_source: Mapped[str] = mapped_column(String(32), nullable=False, default="SNAPSHOT", server_default="SNAPSHOT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    expenses: Mapped[list["TradeExpenseORM"]] = relationship(
        back_populates="trade",
        cascade="save-update, merge",
        passive_deletes=True,
        order_by="TradeExpenseORM.sequence, TradeExpenseORM.id",
    )


class TradeExpenseORM(Base):
    __tablename__ = "trade_expenses"
    __table_args__ = (
        UniqueConstraint("trade_id", "sequence", name="uq_trade_expenses_trade_sequence"),
        CheckConstraint("sequence >= 0", name="sequence_non_negative"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[Decimal] = mapped_column(NUMERIC_TYPE, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    trade: Mapped[TradeORM] = relationship(back_populates="expenses")


Index("ix_trades_account_status", TradeORM.account_id, TradeORM.status)
