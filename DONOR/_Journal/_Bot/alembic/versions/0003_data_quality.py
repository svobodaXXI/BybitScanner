"""add statistics readiness flag to dynamic field definitions"""

from alembic import op
import sqlalchemy as sa


revision = "0002_instruments_data_quality"
down_revision = "0002_instruments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "custom_field_definitions",
        sa.Column("required_for_statistics", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("custom_field_definitions", "required_for_statistics")
