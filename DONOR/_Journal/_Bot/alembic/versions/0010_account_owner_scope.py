"""add internal owner scope for trading accounts"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0010_account_owner_scope"
down_revision = "0009_reminder_delivery_state"
branch_labels = None
depends_on = None


LEGACY_SINGLE_OWNER_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "account_owners",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("account_id"),
    )
    op.create_index("ix_account_owners_owner_id", "account_owners", ["owner_id"], unique=False)

    op.execute(
        sa.text(
            "INSERT INTO owners (id, created_at) "
            f"VALUES ('{LEGACY_SINGLE_OWNER_ID}'::uuid, CURRENT_TIMESTAMP)"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO account_owners (account_id, owner_id, created_at) "
            f"SELECT id, '{LEGACY_SINGLE_OWNER_ID}'::uuid, CURRENT_TIMESTAMP FROM accounts"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_account_owners_owner_id", table_name="account_owners")
    op.drop_table("account_owners")
    op.drop_table("owners")
