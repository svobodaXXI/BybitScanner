"""SQLAlchemy persistence model for user reminder settings."""

from datetime import date, time, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class ReminderSettingsORM(Base):
    __tablename__ = "reminder_settings"

    account_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True
    )
    incomplete_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    open_threshold_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_digest_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    daily_digest_time: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_reminder_local_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
