"""add optional take-profit level for Telegram Quick Working Mode"""

from alembic import op
import sqlalchemy as sa


revision = "0002_instruments_trade_take"
down_revision = "0002_instruments_auto_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("take_profit", sa.Numeric(38, 18), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "take_profit")
