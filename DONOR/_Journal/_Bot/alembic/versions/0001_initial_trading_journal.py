"""initial trading journal persistence schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

NUMERIC = sa.Numeric(38, 18)
TZ = sa.TIMESTAMP(timezone=True)
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )
    op.create_table(
        "trades",
        sa.Column("id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("instrument_id", UUID, nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("opened_at", TZ, nullable=False),
        sa.Column("closed_at", TZ, nullable=True),
        sa.Column("entry_price", NUMERIC, nullable=False),
        sa.Column("exit_price", NUMERIC, nullable=True),
        sa.Column("quantity", NUMERIC, nullable=False),
        sa.Column("stop_price", NUMERIC, nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("risk_amount", NUMERIC, nullable=True),
        sa.Column("risk_currency", sa.String(length=16), nullable=True),
        sa.Column("fees_amount", NUMERIC, nullable=False),
        sa.Column("fees_currency", sa.String(length=16), nullable=False),
        sa.Column("gross_pnl_amount", NUMERIC, nullable=True),
        sa.Column("gross_pnl_currency", sa.String(length=16), nullable=True),
        sa.Column("net_pnl_amount", NUMERIC, nullable=True),
        sa.Column("net_pnl_currency", sa.String(length=16), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_trades_account_id_accounts", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_trades"),
    )
    op.create_table(
        "trade_expenses",
        sa.Column("id", UUID, nullable=False),
        sa.Column("trade_id", UUID, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("amount", NUMERIC, nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.CheckConstraint("sequence >= 0", name="sequence_non_negative"),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], name="fk_trade_expenses_trade_id_trades", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_trade_expenses"),
        sa.UniqueConstraint("trade_id", "sequence", name="uq_trade_expenses_trade_sequence"),
    )
    op.create_table(
        "executions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("trade_id", UUID, nullable=True),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("instrument_id", UUID, nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("quantity", NUMERIC, nullable=False),
        sa.Column("price", NUMERIC, nullable=False),
        sa.Column("fee_amount", NUMERIC, nullable=False),
        sa.Column("fee_currency", sa.String(length=16), nullable=False),
        sa.Column("executed_at", TZ, nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("external_execution_id", sa.String(length=255), nullable=True),
        sa.Column("external_order_id", sa.String(length=255), nullable=True),
        sa.Column("position_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", TZ, nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], name="fk_executions_account_id_accounts", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], name="fk_executions_trade_id_trades", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_executions"),
    )
    op.create_index(
        "uq_executions_exchange_account_external_id",
        "executions",
        ["exchange", "account_id", "external_execution_id"],
        unique=True,
        postgresql_where=sa.text("external_execution_id IS NOT NULL"),
    )
    op.create_index("ix_executions_trade_executed_at", "executions", ["trade_id", "executed_at"])
    op.create_index(
        "ix_executions_account_instrument_executed_at",
        "executions",
        ["account_id", "instrument_id", "executed_at"],
    )
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_custom_field_definitions"),
        sa.UniqueConstraint("code", name="uq_custom_field_definitions_code"),
        sa.UniqueConstraint("id", "definition_version", name="uq_custom_field_definitions_id_version"),
    )
    op.create_table(
        "custom_field_options",
        sa.Column("id", UUID, nullable=False),
        sa.Column("field_id", UUID, nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["field_id"], ["custom_field_definitions.id"], name="fk_custom_field_options_field_id_custom_field_definitions", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_custom_field_options"),
        sa.UniqueConstraint("field_id", "code", name="uq_custom_field_options_field_code"),
        sa.UniqueConstraint("field_id", "id", name="uq_custom_field_options_field_id_id"),
    )
    op.create_table(
        "custom_field_scopes",
        sa.Column("id", UUID, nullable=False),
        sa.Column("field_id", UUID, nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=True),
        sa.Column("market", sa.String(length=64), nullable=True),
        sa.Column("strategy_code", sa.String(length=128), nullable=True),
        sa.Column("setup_code", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["field_id"], ["custom_field_definitions.id"], name="fk_custom_field_scopes_field_id_custom_field_definitions", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id", name="pk_custom_field_scopes"),
    )
    op.create_table(
        "trade_custom_values",
        sa.Column("id", UUID, nullable=False),
        sa.Column("trade_id", UUID, nullable=False),
        sa.Column("field_id", UUID, nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", TZ, nullable=False),
        sa.Column("text_value", sa.String(), nullable=True),
        sa.Column("number_value", NUMERIC, nullable=True),
        sa.Column("bool_value", sa.Boolean(), nullable=True),
        sa.Column("option_id", UUID, nullable=True),
        sa.CheckConstraint(
            "(value_type = 'TEXT' AND text_value IS NOT NULL AND number_value IS NULL AND bool_value IS NULL AND option_id IS NULL) "
            "OR (value_type = 'NUMBER' AND text_value IS NULL AND number_value IS NOT NULL AND bool_value IS NULL AND option_id IS NULL) "
            "OR (value_type = 'YES_NO' AND text_value IS NULL AND number_value IS NULL AND bool_value IS NOT NULL AND option_id IS NULL) "
            "OR (value_type = 'CHOICE' AND text_value IS NULL AND number_value IS NULL AND bool_value IS NULL AND option_id IS NOT NULL)",
            name="ck_trade_custom_values_exactly_one_typed_value",
        ),
        sa.ForeignKeyConstraint(["trade_id"], ["trades.id"], name="fk_trade_custom_values_trade_id_trades", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["field_id", "definition_version"],
            ["custom_field_definitions.id", "custom_field_definitions.definition_version"],
            name="fk_trade_custom_values_field_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["field_id", "option_id"],
            ["custom_field_options.field_id", "custom_field_options.id"],
            name="fk_trade_custom_values_field_option",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_trade_custom_values"),
        sa.UniqueConstraint("trade_id", "field_id", "definition_version", name="uq_trade_custom_values_trade_field_version"),
    )


def downgrade() -> None:
    op.drop_table("trade_custom_values")
    op.drop_table("custom_field_scopes")
    op.drop_table("custom_field_options")
    op.drop_table("custom_field_definitions")
    op.drop_index("ix_executions_account_instrument_executed_at", table_name="executions")
    op.drop_index("ix_executions_trade_executed_at", table_name="executions")
    op.drop_index("uq_executions_exchange_account_external_id", table_name="executions")
    op.drop_table("executions")
    op.drop_table("trade_expenses")
    op.drop_table("trades")
    op.drop_table("accounts")
