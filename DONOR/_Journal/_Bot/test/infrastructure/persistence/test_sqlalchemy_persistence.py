from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, UniqueConstraint
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import postgresql

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.enums import ExecutionSide, TradeDirection
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId
from app.infrastructure.persistence.base import Base
from app.infrastructure.persistence.mappers import (
    custom_field_definition_from_orm,
    custom_field_definition_to_orm,
    custom_field_option_from_orm,
    custom_field_option_to_orm,
    custom_field_scope_from_orm,
    custom_field_scope_to_orm,
    execution_from_orm,
    execution_to_orm,
    trade_custom_value_from_orm,
    trade_custom_value_to_orm,
    trade_from_orm,
    trade_to_orm,
)
from app.infrastructure.persistence.models import (
    AccountORM,
    AccountOwnerORM,
    OwnerORM,
    TelegramViewerGrantORM,
    CustomFieldDefinitionORM,
    CustomFieldOptionORM,
    CustomFieldScopeORM,
    ExecutionORM,
    TradeCustomValueORM,
    TradeExpenseORM,
    TradeORM,
    InstrumentORM,
)


NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def make_definition(value_type=CustomFieldValueType.TEXT, source=CustomFieldSource.MANUAL, **kwargs):
    return CustomFieldDefinition.create(
        code=kwargs.pop("code", "quality"),
        name=kwargs.pop("name", "Quality"),
        value_type=value_type,
        source=source,
        phase=kwargs.pop("phase", CustomFieldPhase.ANY),
        required=kwargs.pop("required", False),
        created_at=NOW,
        **kwargs,
    )


def test_metadata_contains_only_current_phase_tables():
    assert set(Base.metadata.tables) == {
        "accounts",
        "owners",
        "account_owners",
        "telegram_viewer_grants",
        "trades",
        "trade_expenses",
        "executions",
        "custom_field_definitions",
        "custom_field_options",
        "custom_field_scopes",
        "trade_custom_values",
        "instruments",
        "reminder_settings",
        "automatic_factor_observations",
        "automatic_factor_settings",
        "statistics_layouts",
        "exchange_import_settings",
        "trade_journal_state",
    }


def test_financial_columns_are_numeric_38_18_and_timestamps_are_timezone_aware():
    financial_columns = [
        TradeORM.entry_price,
        TradeORM.quantity,
        TradeORM.fees_amount,
        TradeORM.risk_amount,
        TradeORM.gross_pnl_amount,
        TradeORM.net_pnl_amount,
        TradeORM.take_profit,
        ExecutionORM.quantity,
        ExecutionORM.price,
        ExecutionORM.fee_amount,
        TradeExpenseORM.amount,
        TradeCustomValueORM.number_value,
    ]
    for column in financial_columns:
        assert isinstance(column.property.columns[0].type, Numeric)
        assert column.property.columns[0].type.precision == 38
        assert column.property.columns[0].type.scale == 18
    for model, names in (
        (AccountORM, ("created_at",)),
        (OwnerORM, ("created_at",)),
        (AccountOwnerORM, ("created_at",)),
        (TelegramViewerGrantORM, ("created_at",)),
        (TradeORM, ("opened_at", "closed_at", "created_at", "updated_at")),
        (ExecutionORM, ("executed_at", "created_at")),
        (CustomFieldDefinitionORM, ("created_at",)),
        (TradeCustomValueORM, ("recorded_at",)),
        (InstrumentORM, ("created_at",)),
    ):
        for name in names:
            column = getattr(model, name).property.columns[0]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True


def test_execution_partial_unique_index_compiles_for_postgresql():
    index = next(index for index in ExecutionORM.__table__.indexes if index.name == "uq_executions_exchange_account_external_id")
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "UNIQUE" in ddl
    assert "exchange" in ddl
    assert "account_id" in ddl
    assert "external_execution_id" in ddl
    assert "WHERE external_execution_id IS NOT NULL" in ddl


def test_trade_custom_value_unique_key_and_typed_value_check_compile():
    table = TradeCustomValueORM.__table__
    unique = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_trade_custom_values_trade_field_version"
    )
    assert [column.name for column in unique.columns] == ["trade_id", "field_id", "definition_version"]
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "exactly_one_typed_value" in ddl
    assert "NUMERIC(38, 18)" in ddl


def test_historical_foreign_keys_do_not_cascade_delete():
    for table in (TradeExpenseORM.__table__, ExecutionORM.__table__, CustomFieldOptionORM.__table__, CustomFieldScopeORM.__table__, TradeCustomValueORM.__table__):
        for foreign_key in table.foreign_keys:
            if foreign_key.target_fullname.startswith(("trades.", "custom_field_definitions.", "custom_field_options.")):
                assert foreign_key.ondelete in (None, "RESTRICT")


def test_execution_round_trip_preserves_domain_values():
    execution = Execution(
        execution_id=ExecutionId.generate(),
        account_id=AccountId.generate(),
        instrument_id=InstrumentId.generate(),
        side=ExecutionSide.BUY,
        quantity=Quantity(Decimal("1.25")),
        price=Price(Decimal("100.10")),
        fee=Money(Decimal("0.10"), "USDT"),
        executed_at=NOW,
        exchange="bybit",
        external_execution_id="exec-1",
    )
    restored = execution_from_orm(execution_to_orm(execution))
    assert restored == execution


def test_trade_round_trip_rehydrates_through_public_lifecycle():
    trade = Trade.open(
        account_id=AccountId.generate(),
        instrument_id=InstrumentId.generate(),
        direction=TradeDirection.LONG,
        entry_price=Price(100),
        quantity=Quantity(2),
        opened_at=NOW,
        currency="USDT",
        take_profit=Price(120),
        fees=Money(Decimal("1"), "USDT"),
        risk=Risk(Money(Decimal("10"), "USDT")),
        expenses=(Expense(Money(Decimal("-0.5"), "USDT")),),
    )
    trade.close(Price(110), datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc))
    restored = trade_from_orm(trade_to_orm(trade))
    assert restored.trade_id == trade.trade_id
    assert restored.fees == trade.fees
    assert restored.expenses == trade.expenses
    assert restored.gross_pnl == trade.gross_pnl
    assert restored.net_pnl == trade.net_pnl
    assert restored.take_profit == trade.take_profit


def test_statistics_mappers_round_trip_and_choice_uses_option_id():
    definition = make_definition(CustomFieldValueType.CHOICE, code="setup_quality")
    option = CustomFieldOption.create(definition.id, "good", "Good")
    scope = CustomFieldScope.create(definition.id, exchange="BYBIT", setup_code="BREAKOUT")
    value = TradeCustomValue.create(TradeId.generate(), definition, option.id, NOW, option=option)

    assert custom_field_definition_from_orm(custom_field_definition_to_orm(definition)) == definition
    assert custom_field_option_from_orm(custom_field_option_to_orm(option)) == option
    assert custom_field_scope_from_orm(custom_field_scope_to_orm(scope)) == scope
    orm_value = trade_custom_value_to_orm(value, definition)
    assert orm_value.option_id == option.id.value
    assert orm_value.text_value is None
    assert trade_custom_value_from_orm(orm_value).value == option.id


def test_engine_factory_is_async_postgresql_oriented_without_connecting():
    from app.infrastructure.persistence.database import create_async_engine, create_session_factory

    engine = create_async_engine("postgresql+asyncpg://user:password@localhost:5432/trading_journal")
    assert engine.url.drivername == "postgresql+asyncpg"
    assert create_session_factory(engine).kw["expire_on_commit"] is False


def test_execution_persistence_timestamp_has_utc_orm_default_and_is_not_domain_data():
    execution = Execution(
        execution_id=ExecutionId.generate(),
        account_id=AccountId.generate(),
        instrument_id=InstrumentId.generate(),
        side=ExecutionSide.BUY,
        quantity=Quantity("0.01"),
        price=Price("1019.55"),
        fee=Money("0.00367038", "USDT"),
        executed_at=NOW.replace(year=2026),
        exchange="BYBIT",
        external_execution_id="exec-utc-default",
    )
    model = execution_to_orm(execution)
    default = ExecutionORM.__table__.c.created_at.default
    assert default is not None and callable(default.arg)
    created_at = default.arg(None)
    assert created_at.tzinfo is not None
    assert created_at.utcoffset().total_seconds() == 0
    assert model.executed_at == execution.executed_at
    assert execution_from_orm(model) == execution
    assert not hasattr(execution, "created_at")
