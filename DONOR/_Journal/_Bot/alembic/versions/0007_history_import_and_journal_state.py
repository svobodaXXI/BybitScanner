"""add account-scoped history import settings and reversible journal state"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_instruments_history_import"
down_revision = "0002_instruments_trade_take"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_import_settings",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("history_available_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tracking_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initial_import_mode", sa.String(length=32), nullable=False, server_default="NEW_ONLY"),
        sa.Column("initial_import_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("account_id", "exchange"),
    )
    op.create_table(
        "trade_journal_state",
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="INCLUDED"),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("excluded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("trade_id"),
    )
    op.create_index("ix_trade_journal_state_account_state", "trade_journal_state", ["account_id", "state"])


def downgrade() -> None:
    op.drop_index("ix_trade_journal_state_account_state", table_name="trade_journal_state")
    op.drop_table("trade_journal_state")
    op.drop_table("exchange_import_settings")
