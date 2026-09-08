"""Persistence models for internal owner/account scope and manual viewer grants."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class OwnerORM(Base):
    __tablename__ = "owners"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AccountOwnerORM(Base):
    """One current owner per trading account; one owner may have many accounts."""

    __tablename__ = "account_owners"

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_account_owners_owner_id", "owner_id"),)


class TelegramViewerGrantORM(Base):
    """Manual read-only Telegram access to one internal owner scope."""

    __tablename__ = "telegram_viewer_grants"

    telegram_user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("owners.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_telegram_viewer_grants_owner_id", "owner_id"),)
