"""Persistence models for supported-history settings and reversible state."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExchangeImportSettingsORM(Base):
    __tablename__ = "exchange_import_settings"

    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(32), primary_key=True)
    history_available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tracking_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    initial_import_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW_ONLY")
    initial_import_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


class TradeJournalStateORM(Base):
    __tablename__ = "trade_journal_state"

    trade_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), primary_key=True)
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="INCLUDED")
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)


Index("ix_trade_journal_state_account_state", TradeJournalStateORM.account_id, TradeJournalStateORM.state)
