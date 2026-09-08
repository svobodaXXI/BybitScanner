"""add manual read-only Telegram viewer grants"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0011_telegram_viewer_grants"
down_revision = "0010_account_owner_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "telegram_viewer_grants",
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("telegram_user_id"),
    )
    op.create_index(
        "ix_telegram_viewer_grants_owner_id",
        "telegram_viewer_grants",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telegram_viewer_grants_owner_id", table_name="telegram_viewer_grants")
    op.drop_table("telegram_viewer_grants")
