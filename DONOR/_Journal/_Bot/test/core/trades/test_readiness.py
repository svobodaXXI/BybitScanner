from dataclasses import replace
from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition, CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.trades import TradeReadinessStatus, evaluate_trade_readiness
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade


NOW = datetime(2026, 9, 4, 10, tzinfo=timezone.utc)


def make_trade(closed=False):
    trade = Trade.open(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, Price(100), Quantity(1), NOW, "USDT")
    if closed:
        trade.close(Price(100), NOW)
    return trade


def test_open_and_zero_pnl_are_distinct_from_missing_data():
    assert evaluate_trade_readiness(make_trade()).status is TradeReadinessStatus.OPEN
    assert evaluate_trade_readiness(make_trade(True)).status is TradeReadinessStatus.READY
    incomplete = replace(make_trade(True), exit_price=None, net_pnl=None, gross_pnl=None)
    result = evaluate_trade_readiness(incomplete)
    assert result.status is TradeReadinessStatus.INCOMPLETE
    assert set(result.missing) == {"EXIT_PRICE", "NET_PNL"}


def test_required_dynamic_field_gates_statistics_but_optional_field_does_not():
    trade = make_trade(True)
    required = CustomFieldDefinition.create("setup", "Setup", CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, CustomFieldPhase.POST_TRADE, required_for_statistics=True)
    optional = CustomFieldDefinition.create("comment", "Comment", CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, required_for_statistics=False)
    assert evaluate_trade_readiness(trade, required_dynamic_fields=(required,)).status is TradeReadinessStatus.INCOMPLETE
    # Optional fields are not passed as a readiness requirement.
    assert evaluate_trade_readiness(trade).status is TradeReadinessStatus.READY
    ready = evaluate_trade_readiness(trade, required_dynamic_fields=(required,), filled_dynamic_field_ids=(required.id,))
    assert ready.status is TradeReadinessStatus.READY
