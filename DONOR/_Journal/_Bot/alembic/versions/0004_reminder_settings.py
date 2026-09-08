"""persist per-account Attention reminder settings"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_instruments_reminders"
down_revision = "0002_instruments_data_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reminder_settings",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incomplete_delay_seconds", sa.Integer(), nullable=False),
        sa.Column("open_threshold_seconds", sa.Integer(), nullable=False),
        sa.Column("daily_digest_enabled", sa.Boolean(), nullable=False),
        sa.Column("daily_digest_time", sa.Time(), nullable=False),
        sa.Column("timezone_name", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_reminder_settings_account_id_accounts", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("account_id", name="pk_reminder_settings"),
    )


def downgrade() -> None:
    op.drop_table("reminder_settings")
