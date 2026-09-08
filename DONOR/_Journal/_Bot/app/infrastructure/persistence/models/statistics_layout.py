"""Per-account Statistics Overview and Home metric layout."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class StatisticsLayoutORM(Base):
    __tablename__ = "statistics_layouts"

    account_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"), primary_key=True)
    overview_metric_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    home_metric_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    home_metric_period: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
