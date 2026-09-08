from datetime import datetime, timezone
from decimal import Decimal
import asyncio

import pytest

from app.application import (
    AddExpense,
    AddExpenseCommand,
    AddFee,
    AddFeeCommand,
    AddManualCustomValue,
    AddManualCustomValueCommand,
    CloseManualTrade,
    CloseManualTradeCommand,
    CreateManualTrade,
    CreateManualTradeCommand,
    EnrichTrade,
    EnrichTradeCommand,
    GetTradeDetails,
    GetTradeDetailsCommand,
    ListOpenTrades,
    ListOpenTradesCommand,
    ListAllTrades,
    ListAllTradesCommand,
    UpdateTradeProtection,
    UpdateTradeProtectionCommand,
)
from app.application.errors import (
    AccountNotFoundError,
    CustomFieldNotApplicableError,
    CustomFieldNotManualError,
    DuplicateTradeCustomValueError,
    InvalidCustomFieldValueError,
    TradeAlreadyClosedError,
    TradeNotFoundError,
)
from app.application.statistics import TradeEnrichmentService
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
    CustomFieldResolutionContext,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.statistics.ids import TradeCustomValueId
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


def run(coroutine):
    return asyncio.run(coroutine)


class AccountFake:
    def __init__(self, existing=()):
        self.existing = set(existing)

    async def exists(self, account_id):
        return account_id in self.existing


class TradeFake:
    def __init__(self, trades=()):
        self.trades = {trade.trade_id: trade for trade in trades}
        self.saved = []

    async def get_by_id(self, trade_id):
        return self.trades.get(trade_id)

    async def save(self, trade):
        self.trades[trade.trade_id] = trade
        self.saved.append(trade)

    async def list_open(self, *, account_id=None, instrument_id=None):
        return tuple(
            trade for trade in self.trades.values()
            if trade.status is TradeStatus.OPEN
            and (account_id is None or trade.account_id == account_id)
            and (instrument_id is None or trade.instrument_id == instrument_id)
        )

    async def list_all(self, *, account_id=None, instrument_id=None, limit=100, offset=0):
        values = [
            trade for trade in self.trades.values()
            if (account_id is None or trade.account_id == account_id)
            and (instrument_id is None or trade.instrument_id == instrument_id)
        ]
        return tuple(values[offset:offset + limit])


class FieldFake:
    def __init__(self, definitions=(), options=(), scopes=()):
        self.definitions = {item.id: item for item in definitions}
        self.options = tuple(options)
        self.scopes = tuple(scopes)

    async def get_definition(self, field_id):
        return self.definitions.get(field_id)

    async def list_definitions(self, *, include_inactive=False):
        values = tuple(self.definitions.values())
        return tuple(item for item in values if include_inactive or item.is_active)

    async def list_options(self, field_id, *, include_inactive=False):
        return tuple(item for item in self.options if item.field_id == field_id and (include_inactive or item.active))

    async def list_scopes(self, field_id=None):
        return tuple(item for item in self.scopes if field_id is None or item.field_id == field_id)


class ValueFake:
    def __init__(self, values=()):
        self.values = list(values)
        self.added = []

    async def add(self, value):
        if await self.get_for_field(trade_id=value.trade_id, field_id=value.field_id, definition_version=value.definition_version):
            raise DuplicateTradeCustomValueError("duplicate")
        self.values.append(value)
        self.added.append(value)

    async def list_by_trade(self, trade_id):
        return tuple(value for value in self.values if value.trade_id == trade_id)

    async def get_for_field(self, *, trade_id, field_id, definition_version):
        return next((value for value in self.values if value.trade_id == trade_id and value.field_id == field_id and value.definition_version == definition_version), None)

    async def upsert(self, value):
        existing = await self.get_for_field(
            trade_id=value.trade_id, field_id=value.field_id, definition_version=value.definition_version
        )
        if existing is None:
            self.values.append(value)
        else:
            self.values[self.values.index(existing)] = value


def make_trade(*, account_id=None, instrument_id=None, opened_at=NOW, closed=False):
    trade = Trade.open(
        account_id=account_id or AccountId.generate(),
        instrument_id=instrument_id or InstrumentId.generate(),
        direction=TradeDirection.LONG,
        entry_price=Price(100),
        quantity=Quantity(2),
        opened_at=opened_at,
        currency="USDT",
        trade_id=TradeId.generate(),
    )
    if closed:
        trade.close(Price(110), datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc))
    return trade


def field(code, *, source=CustomFieldSource.MANUAL, value_type=CustomFieldValueType.TEXT, phase=CustomFieldPhase.ANY, required=False, inactive=False):
    definition = CustomFieldDefinition.create(code, code, value_type, source, phase=phase, required=required, created_at=NOW)
    return definition.deactivate() if inactive else definition


def test_create_manual_trade_checks_account_and_allows_multiple_open_trades():
    account = AccountId.generate()
    accounts = AccountFake([account])
    repository = TradeFake()
    use_case = CreateManualTrade(accounts, repository)
    first = run(use_case.execute(CreateManualTradeCommand(account, InstrumentId.generate(), TradeDirection.LONG, 100, 1, NOW, "usdt")))
    second = run(use_case.execute(CreateManualTradeCommand(account, InstrumentId.generate(), TradeDirection.SHORT, 200, 2, NOW, "usdt")))
    assert first.status is TradeStatus.OPEN
    assert second.status is TradeStatus.OPEN
    assert len(repository.saved) == 2

    missing = CreateManualTradeCommand(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, 1, 1, NOW, "USDT")
    with pytest.raises(AccountNotFoundError):
        run(use_case.execute(missing))


def test_create_and_edit_trade_protection_keeps_take_profit_in_trade_view():
    account = AccountId.generate()
    trade_repository = TradeFake()
    result = run(CreateManualTrade(AccountFake([account]), trade_repository).execute(
        CreateManualTradeCommand(
            account,
            InstrumentId.generate(),
            TradeDirection.LONG,
            100,
            1,
            NOW,
            "USDT",
            stop_price=95,
            take_profit=125,
        )
    ))
    assert result.trade.stop_price.value == Decimal("95")
    assert result.trade.take_profit.value == Decimal("125")

    updated = run(UpdateTradeProtection(trade_repository).execute(
        UpdateTradeProtectionCommand(result.trade_id, stop_price=97, take_profit=130)
    ))
    assert updated.trade.stop_price.value == Decimal("97")
    assert updated.trade.take_profit.value == Decimal("130")


def test_imported_closed_trade_protection_can_be_updated_for_planned_rr():
    trade = make_trade()
    trade.close(Price(110), NOW.replace(hour=11))
    repository = TradeFake([trade])

    updated = run(UpdateTradeProtection(repository).execute(
        UpdateTradeProtectionCommand(trade.trade_id, stop_price=95, take_profit=120)
    ))

    assert updated.trade.status is TradeStatus.CLOSED
    assert updated.trade.stop_price.value == Decimal("95")
    assert updated.trade.take_profit.value == Decimal("120")


def test_close_manual_trade_uses_domain_pnl_and_rejects_repeat():
    trade = make_trade()
    repository = TradeFake([trade])
    result = run(CloseManualTrade(repository).execute(CloseManualTradeCommand(trade.trade_id, 110, NOW.replace(hour=11))))
    assert result.trade.status is TradeStatus.CLOSED
    assert result.trade.gross_pnl.amount == Decimal("20")
    assert result.trade.net_pnl.amount == Decimal("20")
    with pytest.raises(TradeAlreadyClosedError):
        run(CloseManualTrade(repository).execute(CloseManualTradeCommand(trade.trade_id, 111, NOW.replace(hour=12))))
    with pytest.raises(TradeNotFoundError):
        run(CloseManualTrade(TradeFake()).execute(CloseManualTradeCommand(TradeId.generate(), 1, NOW)))


def test_add_fee_and_signed_expenses_persist_through_trade():
    trade = make_trade()
    repository = TradeFake([trade])
    run(AddFee(repository).execute(AddFeeCommand(trade.trade_id, Money(Decimal("3"), "USDT"))))
    run(AddExpense(repository).execute(AddExpenseCommand(trade.trade_id, Money(Decimal("5"), "USDT"))))
    run(AddExpense(repository).execute(AddExpenseCommand(trade.trade_id, Expense(Money(Decimal("-2"), "USDT")))))
    updated = repository.trades[trade.trade_id]
    assert updated.fees.amount == Decimal("3")
    assert [item.amount.amount for item in updated.expenses] == [Decimal("5"), Decimal("-2")]
    updated.close(Price(110), NOW.replace(hour=11))
    assert updated.net_pnl.amount == Decimal("20")


def test_add_manual_custom_value_supports_all_types_and_rejects_invalid_scope_source_and_duplicates():
    trade = make_trade()
    trade_repo = TradeFake([trade])
    text = field("journal_note")
    number = field("confidence", value_type=CustomFieldValueType.NUMBER)
    invalid_number = field("invalid_confidence", value_type=CustomFieldValueType.NUMBER)
    yes_no = field("followed_plan", value_type=CustomFieldValueType.YES_NO)
    choice = field("quality", value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(choice.id, "good", "Good")
    auto = field("exchange_fee", source=CustomFieldSource.EXCHANGE)
    scoped = field("scoped")
    fields = FieldFake([text, number, invalid_number, yes_no, choice, auto, scoped], [option], [CustomFieldScope.create(scoped.id, exchange="OTHER")])
    values = ValueFake()
    use_case = AddManualCustomValue(trade_repo, fields, values)
    context = CustomFieldResolutionContext(phase=CustomFieldPhase.OPEN, exchange="BYBIT")
    run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, text.id, "note", context)))
    number_result = run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, number.id, Decimal("1.25"), context)))
    run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, yes_no.id, True, context)))
    choice_result = run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, choice.id, option.id, context)))
    assert number_result.value.value == Decimal("1.25")
    assert choice_result.value.value == option.id
    with pytest.raises(InvalidCustomFieldValueError):
        run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, invalid_number.id, 1.25, context)))
    with pytest.raises(CustomFieldNotManualError):
        run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, auto.id, "x", context)))
    with pytest.raises(CustomFieldNotApplicableError):
        run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, scoped.id, "x", context)))
    with pytest.raises(DuplicateTradeCustomValueError):
        run(use_case.execute(AddManualCustomValueCommand(trade.trade_id, text.id, "new", context)))


def test_manual_custom_value_edit_upserts_the_current_value_without_duplicates():
    trade = make_trade(closed=True)
    definition = field("comment", phase=CustomFieldPhase.POST_TRADE)
    values = ValueFake()
    use_case = AddManualCustomValue(TradeFake([trade]), FieldFake([definition]), values, allow_update=True)
    command = AddManualCustomValueCommand(
        trade.trade_id, definition.id, "first", CustomFieldResolutionContext(CustomFieldPhase.POST_TRADE)
    )
    first = run(use_case.execute(command))
    second = run(use_case.execute(AddManualCustomValueCommand(
        trade.trade_id, definition.id, "second", CustomFieldResolutionContext(CustomFieldPhase.POST_TRADE)
    )))

    assert len(values.values) == 1
    assert values.values[0].value == "second"
    assert second.value.id == first.value.id


def test_enrich_trade_persists_derived_and_keeps_missing_inputs_missing():
    trade = make_trade()
    derived = field("position_value", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    missing = field("stop_distance", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    fields = FieldFake([derived, missing])
    values = ValueFake()
    result = run(EnrichTrade(TradeFake([trade]), fields, values, TradeEnrichmentService()).execute(
        EnrichTradeCommand(trade.trade_id, CustomFieldResolutionContext(CustomFieldPhase.OPEN))
    ))
    assert result.generated_values[0].value == Decimal("200")
    assert len(values.added) == 1
    assert values.added[0].field_id == derived.id
    assert result.unavailable_auto_fields[0].field.id == missing.id


def test_list_open_and_details_include_filters_pnl_and_inactive_history():
    account = AccountId.generate()
    instrument = InstrumentId.generate()
    first = make_trade(account_id=account, instrument_id=instrument, opened_at=NOW.replace(minute=2))
    second = make_trade(account_id=account, instrument_id=instrument, opened_at=NOW.replace(minute=1))
    closed = make_trade(account_id=account, instrument_id=instrument, closed=True)
    trades = TradeFake([first, second, closed])
    listed = run(ListOpenTrades(trades).execute(ListOpenTradesCommand(account, instrument)))
    assert [item.trade_id for item in listed.trades] == [second.trade_id, first.trade_id]
    assert closed.trade_id not in [item.trade_id for item in listed.trades]
    assert len(run(ListOpenTrades(trades).execute()).trades) == 2

    definition = field("old_note", inactive=True)
    historical = TradeCustomValue(
        id=TradeCustomValueId.generate(),
        trade_id=closed.trade_id,
        field_id=definition.id,
        value="kept",
        recorded_at=NOW,
        source=CustomFieldSource.MANUAL,
        definition_version=definition.definition_version,
    )
    details = run(GetTradeDetails(trades, FieldFake([definition]), ValueFake([historical])).execute(GetTradeDetailsCommand(closed.trade_id)))
    assert details.net_pnl.amount == Decimal("20")
    assert details.custom_values[0].value.value == "kept"
    assert details.custom_values[0].definition is definition


def test_list_all_trades_includes_open_and_closed_with_page_limit():
    open_trade = make_trade()
    closed_trade = make_trade(closed=True)
    repository = TradeFake([open_trade, closed_trade])
    result = run(ListAllTrades(repository).execute(ListAllTradesCommand(limit=1)))
    assert len(result.trades) == 1
    result = run(ListAllTrades(repository).execute(ListAllTradesCommand(limit=10)))
    assert {item.status for item in result.trades} == {TradeStatus.OPEN, TradeStatus.CLOSED}
