import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.models import (
    AccountOwnerORM,
    OwnerORM,
    TelegramViewerGrantORM,
    TradeExpenseORM,
    TradeCustomValueORM,
)
from app.infrastructure.persistence.models import CustomFieldDefinitionORM


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_alembic_head_and_initial_revision_are_available():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "0011_telegram_viewer_grants" in result.stdout
    migration = PROJECT_ROOT / "alembic" / "versions" / "0001_initial_trading_journal.py"
    source = migration.read_text(encoding="utf-8")
    assert "def upgrade()" in source
    assert "def downgrade()" in source
    assert "revision = \"0001_initial\"" in source
    migration = PROJECT_ROOT / "alembic" / "versions" / "0002_instruments.py"
    source = migration.read_text(encoding="utf-8")
    assert "down_revision = \"0001_initial\"" in source


def test_current_metadata_registers_all_tables_and_sequence_constraints():
    assert "trade_expenses" in Base.metadata.tables
    assert "owners" in Base.metadata.tables
    assert "account_owners" in Base.metadata.tables
    assert "telegram_viewer_grants" in Base.metadata.tables
    assert OwnerORM.__table__.c.id.primary_key is True
    assert AccountOwnerORM.__table__.c.account_id.primary_key is True
    assert AccountOwnerORM.__table__.c.owner_id.nullable is False
    assert TelegramViewerGrantORM.__table__.c.telegram_user_id.primary_key is True
    assert TelegramViewerGrantORM.__table__.c.owner_id.nullable is False
    table = TradeExpenseORM.__table__
    assert table.c.sequence.nullable is False
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_trade_expenses_trade_sequence"
        for constraint in table.constraints
    )
    assert CustomFieldDefinitionORM.__table__.c.required_for_statistics.server_default is not None
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_trade_expenses_sequence_non_negative"
        for constraint in table.constraints
    )
    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "ck_trade_custom_values_exactly_one_typed_value"
        for constraint in TradeCustomValueORM.__table__.constraints
    )


def test_offline_migration_sql_contains_approved_hardening_rules():
    task_environment = os.environ.copy()
    task_environment["DATABASE_URL"] = "postgresql+asyncpg://user:password@localhost:5432/trading_journal"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=PROJECT_ROOT,
        env=task_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    sql = result.stdout
    assert "CONSTRAINT ck_trade_expenses_sequence_non_negative CHECK (sequence >= 0)" in sql
    assert "CONSTRAINT uq_trade_expenses_trade_sequence UNIQUE (trade_id, sequence)" in sql
    assert "WHERE external_execution_id IS NOT NULL" in sql
    assert "FOREIGN KEY(field_id, definition_version)" in sql
    assert "FOREIGN KEY(field_id, option_id)" in sql
    assert "CONSTRAINT uq_trade_custom_values_trade_field_version UNIQUE (trade_id, field_id, definition_version)" in sql
    assert "required_for_statistics BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ADD COLUMN pnl_source VARCHAR(32) DEFAULT 'SNAPSHOT' NOT NULL" in sql
    assert "EXECUTION_REPLAY" in sql
    assert "CREATE TABLE owners" in sql
    assert "CREATE TABLE account_owners" in sql
    assert "CREATE TABLE telegram_viewer_grants" in sql
    assert "00000000-0000-0000-0000-000000000001" in sql
    assert "SELECT id, '00000000-0000-0000-0000-000000000001'::uuid" in sql


def test_initial_migration_downgrade_compiles_from_head_to_base():
    task_environment = os.environ.copy()
    task_environment["DATABASE_URL"] = "postgresql+asyncpg://user:password@localhost:5432/trading_journal"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0001_initial:base", "--sql"],
        cwd=PROJECT_ROOT,
        env=task_environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "DROP TABLE trade_custom_values" in result.stdout
    assert "DROP TABLE accounts" in result.stdout
