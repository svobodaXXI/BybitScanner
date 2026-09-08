"""Typed-column persistence model for historical dynamic values."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from .trade import NUMERIC_TYPE


class TradeCustomValueORM(Base):
    __tablename__ = "trade_custom_values"
    __table_args__ = (
        UniqueConstraint("trade_id", "field_id", "definition_version", name="uq_trade_custom_values_trade_field_version"),
        ForeignKeyConstraint(
            ["field_id", "definition_version"],
            ["custom_field_definitions.id", "custom_field_definitions.definition_version"],
            name="fk_trade_custom_values_field_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["field_id", "option_id"],
            ["custom_field_options.field_id", "custom_field_options.id"],
            name="fk_trade_custom_values_field_option",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(value_type = 'TEXT' AND text_value IS NOT NULL AND number_value IS NULL AND bool_value IS NULL AND option_id IS NULL) "
            "OR (value_type = 'NUMBER' AND text_value IS NULL AND number_value IS NOT NULL AND bool_value IS NULL AND option_id IS NULL) "
            "OR (value_type = 'YES_NO' AND text_value IS NULL AND number_value IS NULL AND bool_value IS NOT NULL AND option_id IS NULL) "
            "OR (value_type = 'CHOICE' AND text_value IS NULL AND number_value IS NULL AND bool_value IS NULL AND option_id IS NOT NULL)",
            name="exactly_one_typed_value",
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    trade_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("trades.id", ondelete="RESTRICT"), nullable=False
    )
    field_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text_value: Mapped[str | None] = mapped_column(String, nullable=True)
    number_value: Mapped[Decimal | None] = mapped_column(NUMERIC_TYPE, nullable=True)
    bool_value: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    option_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
