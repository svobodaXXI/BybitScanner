"""add explicit human-readable instrument catalog

Revision ID: 0002_instruments
Revises: 0001_initial
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_instruments"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_instruments"),
        sa.UniqueConstraint("symbol", "exchange", "market", name="uq_instruments_symbol_exchange_market"),
    )
    op.create_index("ix_instruments_symbol", "instruments", ["symbol"])


def downgrade() -> None:
    op.drop_index("ix_instruments_symbol", table_name="instruments")
    op.drop_table("instruments")
