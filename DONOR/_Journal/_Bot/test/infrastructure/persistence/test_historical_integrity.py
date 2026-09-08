from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import UniqueConstraint
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.enums import TradeDirection, TradePnLSource, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId
from app.infrastructure.persistence.mappers import (
    trade_custom_value_from_orm,
    trade_custom_value_to_orm,
    trade_from_orm,
    trade_to_orm,
)
from app.infrastructure.persistence.models import (
    CustomFieldDefinitionORM,
    CustomFieldOptionORM,
    TradeCustomValueORM,
)


NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def make_definition(*, value_type=CustomFieldValueType.TEXT, code="quality", version=1):
    return CustomFieldDefinition.create(
        code=code,
        name="Quality",
        value_type=value_type,
        source=CustomFieldSource.MANUAL,
        phase=CustomFieldPhase.ANY,
        definition_version=version,
        created_at=NOW,
    )


def test_v1_policy_has_no_semantic_version_transition_api():
    field = make_definition(version=1)
    toggled = field.deactivate().activate()
    assert toggled.id == field.id
    assert toggled.definition_version == 1
    assert not hasattr(field, "bump_version")

    # A semantic successor is a new catalog identity in the current V1 policy.
    successor = make_definition(code="quality_v2", version=2)
    assert successor.id != field.id


def test_definition_version_composite_fk_and_option_composite_fk_exist():
    value_table = TradeCustomValueORM.__table__
    definition_fk = next(
        fk for fk in value_table.foreign_key_constraints if fk.name == "fk_trade_custom_values_field_version"
    )
    option_fk = next(
        fk for fk in value_table.foreign_key_constraints if fk.name == "fk_trade_custom_values_field_option"
    )
    assert [column.name for column in definition_fk.columns] == ["field_id", "definition_version"]
    assert [column.target_fullname for column in definition_fk.elements] == [
        "custom_field_definitions.id",
        "custom_field_definitions.definition_version",
    ]
    assert [column.name for column in option_fk.columns] == ["field_id", "option_id"]
    assert [column.target_fullname for column in option_fk.elements] == [
        "custom_field_options.field_id",
        "custom_field_options.id",
    ]
    assert any(
        isinstance(item, UniqueConstraint)
        and item.name == "uq_custom_field_definitions_id_version"
        for item in CustomFieldDefinitionORM.__table__.constraints
    )
    assert any(
        isinstance(item, UniqueConstraint)
        and item.name == "uq_custom_field_options_field_id_id"
        for item in CustomFieldOptionORM.__table__.constraints
    )


def test_composite_fk_constraints_are_present_in_postgresql_ddl():
    ddl = str(CreateTable(TradeCustomValueORM.__table__).compile(dialect=postgresql.dialect()))
    assert "FOREIGN KEY(field_id, definition_version)" in ddl
    assert "FOREIGN KEY(field_id, option_id)" in ddl
    assert "REFERENCES custom_field_definitions (id, definition_version)" in ddl
    assert "REFERENCES custom_field_options (field_id, id)" in ddl


def test_inactive_option_keeps_choice_identity_for_historical_value_mapper():
    field = make_definition(value_type=CustomFieldValueType.CHOICE, code="setup_quality")
    option = CustomFieldOption.create(field.id, "good", "Good").deactivate()
    historical = TradeCustomValue(
        id=TradeCustomValue.create(TradeId.generate(), field, CustomFieldOption.create(field.id, "tmp", "Tmp").id, NOW).id,
        trade_id=TradeId.generate(),
        field_id=field.id,
        value=option.id,
        recorded_at=NOW,
        source=CustomFieldSource.MANUAL,
        definition_version=field.definition_version,
    )
    # The mapper does not use label, code, active, or sort_order as identity.
    orm = trade_custom_value_to_orm(historical, field)
    assert orm.option_id == option.id.value
    assert trade_custom_value_from_orm(orm).value == option.id


def test_trade_full_lifecycle_round_trip_preserves_pnl_and_signed_multiple_expenses():
    account_id = AccountId.generate()
    instrument_id = InstrumentId.generate()
    trade = Trade.open(
        account_id=account_id,
        instrument_id=instrument_id,
        direction=TradeDirection.LONG,
        entry_price=Price(Decimal("100.123456789012345678")),
        quantity=Quantity(Decimal("0.000000123456789012")),
        opened_at=NOW,
        currency="USDT",
        fees=Money(Decimal("0.000000000000000001"), "USDT"),
        expenses=(
            Expense(Money(Decimal("25.125"), "USDT")),
            Expense(Money(Decimal("-10.125"), "USDT")),
        ),
    )
    trade.close(Price(Decimal("100.223456789012345678")), datetime(2026, 7, 2, 13, 30, tzinfo=timezone.utc))
    restored = trade_from_orm(trade_to_orm(trade))

    assert restored.trade_id == trade.trade_id
    assert restored.account_id == account_id
    assert restored.instrument_id == instrument_id
    assert restored.direction == trade.direction
    assert restored.status == trade.status
    assert restored.opened_at == trade.opened_at
    assert restored.closed_at == trade.closed_at
    assert restored.entry_price == trade.entry_price
    assert restored.exit_price == trade.exit_price
    assert restored.quantity == trade.quantity
    assert restored.fees == trade.fees
    assert restored.expenses == trade.expenses
    assert restored.gross_pnl == trade.gross_pnl
    assert restored.net_pnl == trade.net_pnl
    assert restored.gross_pnl == Money(trade.gross_pnl.amount, "USDT")
    assert restored.net_pnl == Money(trade.gross_pnl.amount - trade.fees.amount + Decimal("15"), "USDT")


def test_execution_replay_provenance_round_trip_does_not_require_snapshot_pnl_equality():
    trade = Trade(
        trade_id=TradeId.generate(),
        account_id=AccountId.generate(),
        instrument_id=InstrumentId.generate(),
        direction=TradeDirection.LONG,
        status=TradeStatus.CLOSED,
        opened_at=NOW,
        closed_at=NOW,
        entry_price=Price("0.798109090909090909"),
        exit_price=Price("0.8126"),
        quantity=Quantity("132"),
        stop_price=None,
        risk=None,
        fees=Money("0.14518939", "USDT"),
        gross_pnl=Money("-1.9128", "USDT"),
        net_pnl=Money("-2.05798939", "USDT"),
        pnl_source=TradePnLSource.EXECUTION_REPLAY,
    )
    restored = trade_from_orm(trade_to_orm(trade))
    assert restored.pnl_source is TradePnLSource.EXECUTION_REPLAY
    assert restored.gross_pnl == trade.gross_pnl
    assert restored.net_pnl == trade.net_pnl
