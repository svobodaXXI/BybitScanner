"""Generic persistence models for automatic factor observations and settings."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class AutomaticFactorObservationORM(Base):
    __tablename__ = "automatic_factor_observations"
    __table_args__ = (UniqueConstraint("trade_id", "factor_id", "definition_version", "calculation_version", "capture_semantics", name="uq_automatic_observations_identity"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    trade_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    factor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(64), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value_decimal: Mapped[object | None] = mapped_column(Numeric(30, 12), nullable=True)
    value_integer: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value_boolean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    capture_semantics: Mapped[str] = mapped_column(String(32), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    availability_status: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutomaticFactorSettingORM(Base):
    __tablename__ = "automatic_factor_settings"
    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True)
    factor_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
