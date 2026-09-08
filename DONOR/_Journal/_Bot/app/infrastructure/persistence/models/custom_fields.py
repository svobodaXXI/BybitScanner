"""SQLAlchemy catalog models for dynamic custom fields."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class CustomFieldDefinitionORM(Base):
    """One current immutable semantic definition per field identity in V1.

    V1 has no semantic version-transition operation. A future semantic successor
    uses a new field identity/code; the composite target is retained so values
    can only reference the exact persisted pair.
    """

    __tablename__ = "custom_field_definitions"
    __table_args__ = (UniqueConstraint("id", "definition_version", name="uq_custom_field_definitions_id_version"),)

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_for_statistics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    definition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomFieldOptionORM(Base):
    __tablename__ = "custom_field_options"
    __table_args__ = (
        UniqueConstraint("field_id", "code", name="uq_custom_field_options_field_code"),
        UniqueConstraint("field_id", "id", name="uq_custom_field_options_field_id_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    field_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("custom_field_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CustomFieldScopeORM(Base):
    __tablename__ = "custom_field_scopes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    field_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("custom_field_definitions.id", ondelete="RESTRICT"), nullable=False
    )
    exchange: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    setup_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
