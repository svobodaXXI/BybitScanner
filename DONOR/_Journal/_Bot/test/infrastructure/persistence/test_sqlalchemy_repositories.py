import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.errors import (
    CustomFieldSemanticMutationError,
    DuplicateTradeCustomValueError,
    PersistenceIntegrityError,
)
from app.application.ports.repositories import (
    AccountRepository,
    CustomFieldRepository,
    ExecutionRepository,
    TradeCustomValueRepository,
    TradeRepository,
)
from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.instruments.instrument import Instrument
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.enums import ExecutionSide, TradeDirection, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId
from app.infrastructure.persistence.mappers import (
    execution_to_orm,
    trade_custom_value_to_orm,
    trade_to_orm,
)
from app.infrastructure.persistence.models import (
    CustomFieldDefinitionORM,
    CustomFieldOptionORM,
    CustomFieldScopeORM,
    ExecutionORM,
    TradeCustomValueORM,
    TradeORM,
    InstrumentORM,
)
from app.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyCustomFieldRepository,
    SqlAlchemyExecutionRepository,
    SqlAlchemyTradeCustomValueRepository,
    SqlAlchemyTradeRepository,
    SqlAlchemyInstrumentRepository,
)


NOW = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


class ScalarResult:
    def __init__(self, *items):
        self.items = list(items)

    def scalar_one_or_none(self):
        return self.items[0] if self.items else None

    def scalars(self):
        return self

    def all(self):
        return list(self.items)


class FakeAsyncSession:
    def __init__(self, *results, scalar_values=()):
        self.results = list(results)
        self.scalar_values = list(scalar_values)
        self.added = []
        self.flush_count = 0
        self.commit_called = False
        self.rollback_called = False

    async def execute(self, statement):
        return self.results.pop(0) if self.results else ScalarResult()

    async def scalar(self, statement):
        return self.scalar_values.pop(0)

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flush_count += 1


def make_trade(*, account_id=None, instrument_id=None, expenses=(), closed=False):
    trade = Trade.open(
        account_id=account_id or AccountId.generate(),
        instrument_id=instrument_id or InstrumentId.generate(),
        direction=TradeDirection.LONG,
        entry_price=Price(100),
        quantity=Quantity(2),
        opened_at=NOW,
        currency="USDT",
        fees=Money(Decimal("1"), "USDT"),
        expenses=expenses,
        trade_id=TradeId.generate(),
    )
    if closed:
        trade.close(Price(110), datetime(2026, 8, 1, 13, 0, tzinfo=timezone.utc))
    return trade


def make_execution(*, execution_id=None, external_id=None):
    return Execution(
        execution_id=execution_id or ExecutionId.generate(),
        account_id=AccountId.generate(),
        instrument_id=InstrumentId.generate(),
        side=ExecutionSide.BUY,
        quantity=Quantity(1),
        price=Price(100),
        fee=Money(Decimal("0.1"), "USDT"),
        executed_at=NOW,
        exchange="bybit",
        external_execution_id=external_id,
    )


def make_definition(*, code="quality", source=CustomFieldSource.MANUAL, value_type=CustomFieldValueType.TEXT, status=None):
    definition = CustomFieldDefinition.create(
        code=code,
        name="Quality",
        value_type=value_type,
        source=source,
        phase=CustomFieldPhase.ANY,
        created_at=NOW,
    )
    return definition.deactivate() if status == "INACTIVE" else definition


def run(coro):
    return asyncio.run(coro)


def test_trade_repository_save_new_and_session_ownership():
    trade = make_trade()
    session = FakeAsyncSession(ScalarResult())
    repository = SqlAlchemyTradeRepository(session)
    run(repository.save(trade))

    assert isinstance(session.added[0], TradeORM)
    assert session.flush_count == 1
    assert not session.commit_called
    assert not session.rollback_called
    assert isinstance(repository, TradeRepository)


def test_trade_save_unchanged_twice_does_not_duplicate_expenses():
    trade = make_trade(expenses=(Expense(Money(Decimal("2"), "USDT")),))
    existing = trade_to_orm(trade)
    first_session = FakeAsyncSession(ScalarResult(existing))
    run(SqlAlchemyTradeRepository(first_session).save(trade))
    assert len(existing.expenses) == 1

    second_session = FakeAsyncSession(ScalarResult(existing))
    run(SqlAlchemyTradeRepository(second_session).save(trade))
    assert len(existing.expenses) == 1
    assert second_session.flush_count == 1


def test_trade_save_appends_new_expense_but_rejects_removal():
    old = Expense(Money(Decimal("2"), "USDT"))
    trade_old = make_trade(expenses=(old,))
    trade_new = make_trade(expenses=(old, Expense(Money(Decimal("-1"), "USDT"))))
    trade_new = Trade(
        trade_id=trade_old.trade_id,
        account_id=trade_old.account_id,
        instrument_id=trade_old.instrument_id,
        direction=trade_old.direction,
        status=trade_old.status,
        opened_at=trade_old.opened_at,
        closed_at=trade_old.closed_at,
        entry_price=trade_old.entry_price,
        exit_price=trade_old.exit_price,
        quantity=trade_old.quantity,
        stop_price=trade_old.stop_price,
        risk=trade_old.risk,
        fees=trade_old.fees,
        expenses=trade_new.expenses,
        gross_pnl=trade_old.gross_pnl,
        net_pnl=trade_old.net_pnl,
    )
    existing = trade_to_orm(trade_old)
    session = FakeAsyncSession(ScalarResult(existing))
    run(SqlAlchemyTradeRepository(session).save(trade_new))
    assert len(existing.expenses) == 2

    removed = make_trade()
    removed = Trade(
        trade_id=trade_old.trade_id,
        account_id=trade_old.account_id,
        instrument_id=trade_old.instrument_id,
        direction=trade_old.direction,
        status=trade_old.status,
        opened_at=trade_old.opened_at,
        closed_at=trade_old.closed_at,
        entry_price=trade_old.entry_price,
        exit_price=trade_old.exit_price,
        quantity=trade_old.quantity,
        stop_price=trade_old.stop_price,
        risk=trade_old.risk,
        fees=trade_old.fees,
        expenses=(),
        gross_pnl=trade_old.gross_pnl,
        net_pnl=trade_old.net_pnl,
    )
    with pytest.raises(PersistenceIntegrityError):
        run(SqlAlchemyTradeRepository(FakeAsyncSession(ScalarResult(existing))).save(removed))


def test_trade_list_open_filters_and_ordering_statement():
    first = make_trade()
    second = make_trade(account_id=first.account_id, instrument_id=first.instrument_id)
    session = FakeAsyncSession(ScalarResult(trade_to_orm(first), trade_to_orm(second)))
    result = run(SqlAlchemyTradeRepository(session).list_open(account_id=first.account_id, instrument_id=first.instrument_id))
    assert tuple(item.trade_id for item in result) == (first.trade_id, second.trade_id)


def test_trade_list_all_is_bounded_and_includes_closed_trades():
    first = make_trade()
    second = make_trade(closed=True)
    session = FakeAsyncSession(ScalarResult(trade_to_orm(first), trade_to_orm(second)))
    result = run(SqlAlchemyTradeRepository(session).list_all(limit=2, offset=0))
    assert tuple(item.trade_id for item in result) == (first.trade_id, second.trade_id)


def test_trade_pnl_mismatch_on_load_is_persistence_integrity_error():
    trade = make_trade(closed=True)
    model = trade_to_orm(trade)
    model.net_pnl_amount += Decimal("1")
    with pytest.raises(PersistenceIntegrityError):
        run(SqlAlchemyTradeRepository(FakeAsyncSession(ScalarResult(model))).get_by_id(trade.trade_id))


def test_execution_repository_save_get_ordering_and_duplicate_internal_id():
    execution = make_execution(external_id="ext-1")
    new_session = FakeAsyncSession(ScalarResult(), ScalarResult())
    repository = SqlAlchemyExecutionRepository(new_session)
    run(repository.save(execution))
    assert isinstance(new_session.added[0], ExecutionORM)
    assert isinstance(repository, ExecutionRepository)

    existing = execution_to_orm(execution)
    same = FakeAsyncSession(ScalarResult(existing), ScalarResult(existing))
    run(SqlAlchemyExecutionRepository(same).save(execution))
    assert not same.added

    different = make_execution(execution_id=execution.execution_id)
    with pytest.raises(PersistenceIntegrityError):
        run(SqlAlchemyExecutionRepository(FakeAsyncSession(ScalarResult(existing))).save(different))


def test_execution_external_lookup_validates_identity_and_normalizes_exchange():
    execution = make_execution(external_id="ext-1")
    session = FakeAsyncSession(ScalarResult(execution_to_orm(execution)))
    found = run(
        SqlAlchemyExecutionRepository(session).get_by_external_id(
            exchange=" BYBIT ", account_id=execution.account_id, external_execution_id="ext-1"
        )
    )
    assert found == execution
    with pytest.raises(ValueError):
        run(SqlAlchemyExecutionRepository(FakeAsyncSession()).get_by_external_id(exchange="BYBIT", account_id=execution.account_id, external_execution_id=" "))
    with pytest.raises(ValueError):
        run(SqlAlchemyExecutionRepository(FakeAsyncSession()).get_by_external_id(exchange="BYBIT", account_id=execution.account_id, external_execution_id=None))


def test_custom_field_repository_status_mutation_is_allowed_semantic_mutation_rejected():
    definition = make_definition()
    existing = CustomFieldDefinitionORM(
        id=definition.id.value, code=str(definition.code), name=definition.name,
        value_type=definition.value_type.value, source=definition.source.value,
        status="ACTIVE", phase=definition.phase.value, required=definition.required,
        definition_version=definition.definition_version, created_at=definition.created_at,
    )
    inactive = definition.deactivate()
    session = FakeAsyncSession(ScalarResult(existing))
    run(SqlAlchemyCustomFieldRepository(session).save_definition(inactive))
    assert existing.status == "INACTIVE"

    changed = make_definition(code="other")
    with pytest.raises(CustomFieldSemanticMutationError):
        run(SqlAlchemyCustomFieldRepository(FakeAsyncSession(ScalarResult(existing))).save_definition(changed))
    assert isinstance(SqlAlchemyCustomFieldRepository(FakeAsyncSession()), CustomFieldRepository)


def test_custom_field_option_mutation_and_scope_idempotency():
    definition = make_definition(value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(definition.id, "good", "Good")
    existing_option = CustomFieldOptionORM(
        id=option.id.value, field_id=option.field_id.value, code=option.code,
        label=option.label, sort_order=option.sort_order, active=True,
    )
    updated = option.deactivate()
    run(SqlAlchemyCustomFieldRepository(FakeAsyncSession(ScalarResult(existing_option))).save_option(updated))
    assert existing_option.active is False

    reassigned = CustomFieldOption.create(CustomFieldDefinition.create("other", "Other", CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, created_at=NOW).id, option.code, option.label, option_id=option.id)
    with pytest.raises(CustomFieldSemanticMutationError):
        run(SqlAlchemyCustomFieldRepository(FakeAsyncSession(ScalarResult(existing_option))).save_option(reassigned))

    scope = CustomFieldScope.create(definition.id, exchange="BYBIT")
    existing_scope = CustomFieldScopeORM(field_id=scope.field_id.value, exchange="BYBIT")
    duplicate_session = FakeAsyncSession(ScalarResult(existing_scope))
    run(SqlAlchemyCustomFieldRepository(duplicate_session).save_scope(scope))
    assert not duplicate_session.added


def test_trade_custom_value_repository_is_append_only_and_loads_history():
    definition = make_definition()
    trade_id = TradeId.generate()
    value = TradeCustomValue.create(trade_id, definition, "good", NOW)
    session = FakeAsyncSession(ScalarResult())
    repository = SqlAlchemyTradeCustomValueRepository(session)
    run(repository.add(value))
    assert isinstance(session.added[0], TradeCustomValueORM)
    assert isinstance(repository, TradeCustomValueRepository)

    existing = trade_custom_value_to_orm(value, definition)
    with pytest.raises(DuplicateTradeCustomValueError):
        run(SqlAlchemyTradeCustomValueRepository(FakeAsyncSession(ScalarResult(existing))).add(value))

    loaded = run(SqlAlchemyTradeCustomValueRepository(FakeAsyncSession(ScalarResult(existing))).get_for_field(
        trade_id=trade_id, field_id=definition.id, definition_version=1
    ))
    assert loaded == value


def test_account_repository_exists_and_all_concrete_adapters_are_protocols():
    account_id = AccountId.generate()
    assert run(SqlAlchemyAccountRepository(FakeAsyncSession(scalar_values=[True])).exists(account_id)) is True
    assert run(SqlAlchemyAccountRepository(FakeAsyncSession(scalar_values=[False])).exists(account_id)) is False
    assert isinstance(SqlAlchemyAccountRepository(FakeAsyncSession()), AccountRepository)


def test_instrument_catalog_upsert_uses_natural_key_and_preserves_existing_id():
    existing_id = InstrumentId.generate()
    incoming = Instrument(InstrumentId.generate(), "BTCUSDT", "BTC/USDT", "BYBIT", "LINEAR", True)
    existing = InstrumentORM(
        id=existing_id.value,
        symbol="BTCUSDT",
        name="Old BTC/USDT",
        exchange="BYBIT",
        market="LINEAR",
        active=True,
        created_at=NOW,
    )
    session = FakeAsyncSession(scalar_values=[None, existing])
    run(SqlAlchemyInstrumentRepository(session).save(incoming))
    assert session.added == []
    assert existing.id == existing_id.value
    assert existing.name == "BTC/USDT"
