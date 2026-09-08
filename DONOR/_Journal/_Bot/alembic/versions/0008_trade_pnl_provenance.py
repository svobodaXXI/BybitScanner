"""persist authoritative PnL provenance for Trade snapshots"""

from alembic import op
import sqlalchemy as sa


revision = "0008_trade_pnl_provenance"
down_revision = "0002_instruments_history_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("pnl_source", sa.String(length=32), nullable=False, server_default="SNAPSHOT"),
    )
    op.execute(
        sa.text(
            """
            UPDATE trades
               SET pnl_source = 'EXECUTION_REPLAY'
             WHERE EXISTS (
                 SELECT 1
                   FROM executions
                  WHERE executions.trade_id = trades.id
             )
            """
        )
    )
    op.alter_column("trades", "pnl_source", server_default=None)


def downgrade() -> None:
    op.drop_column("trades", "pnl_source")
