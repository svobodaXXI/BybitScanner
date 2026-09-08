"""add generic automatic data storage and per-account metric layouts"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_instruments_auto_data"
down_revision = "0002_instruments_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "automatic_factor_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factor_id", sa.String(length=128), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("calculation_version", sa.String(length=64), nullable=False),
        sa.Column("value_type", sa.String(length=16), nullable=False),
        sa.Column("value_decimal", sa.Numeric(30, 12), nullable=True),
        sa.Column("value_integer", sa.Integer(), nullable=True),
        sa.Column("value_boolean", sa.Boolean(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=64), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("provider_key", sa.String(length=128), nullable=True),
        sa.Column("capture_semantics", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("availability_status", sa.String(length=32), nullable=False),
        sa.Column("provenance", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trade_id", "factor_id", "definition_version", "calculation_version", "capture_semantics", name="uq_automatic_observations_identity"),
    )
    op.create_table(
        "automatic_factor_settings",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("factor_id", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("account_id", "factor_id"),
    )
    op.create_table(
        "statistics_layouts",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("overview_metric_ids", sa.JSON(), nullable=False),
        sa.Column("home_metric_ids", sa.JSON(), nullable=False),
        sa.Column("home_metric_period", sa.String(length=8), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("account_id"),
    )


def downgrade() -> None:
    op.drop_table("statistics_layouts")
    op.drop_table("automatic_factor_settings")
    op.drop_table("automatic_factor_observations")
