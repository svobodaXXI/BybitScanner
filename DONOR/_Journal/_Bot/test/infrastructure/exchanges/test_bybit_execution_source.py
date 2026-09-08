import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import replace

import pytest

from app.application import ProcessExecutionFact
from app.application.errors import ExecutionFactConflictError
from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.instruments import Instrument, InstrumentId
from app.core.trades.execution import Execution
from app.infrastructure.exchanges.bybit.config import BybitSettings
from app.infrastructure.exchanges.bybit.errors import (
    BybitAuthenticationError,
    BybitInstrumentMappingError,
    BybitPayloadError,
    BybitRequestError,
)
from app.infrastructure.exchanges.bybit.execution_source import BybitExecutionSource


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, path, params):
        self.calls.append((path, dict(params)))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeInstruments:
    def __init__(self, *matches):
        self.matches = matches
        self.calls = []

    async def get_by_exchange_symbol(self, exchange, symbol, *, active_only=True):
        self.calls.append((exchange, symbol, active_only))
        return tuple(item for item in self.matches if item.symbol == symbol)

    async def get_by_id(self, instrument_id):
        return next((item for item in self.matches if item.instrument_id == instrument_id), None)


class FakeAccounts:
    def __init__(self, account_id):
        self.account_id = account_id

    async def exists(self, account_id):
        return account_id == self.account_id


class FakeExecutionRepository:
    def __init__(self):
        self.items = []

    async def get_by_external_id(self, *, exchange, account_id, external_execution_id):
        return next((item for item in self.items if (item.exchange, item.account_id, item.external_execution_id) == (exchange, account_id, external_execution_id)), None)

    async def save(self, execution):
        self.items.append(execution)


def settings(account_id, **changes):
    values = dict(api_key="key", api_secret="secret", account_id=account_id, max_retries=0)
    values.update(changes)
    return BybitSettings(**values)


def instrument(symbol="BTCUSDT"):
    return Instrument(InstrumentId.generate(), symbol, f"{symbol} asset", "BYBIT", "LINEAR")


def item(*, exec_id="fill-1", symbol="BTCUSDT", side="Buy", price="100.10", quantity="1.25", fee="0.10", time_ms="1725364800000", order_id="order-1", position_id="position-1"):
    return {
        "execId": exec_id,
        "symbol": symbol,
        "side": side,
        "execPrice": price,
        "execQty": quantity,
        "execFee": fee,
        "feeCurrency": "USDT",
        "execTime": time_ms,
        "orderId": order_id,
        "positionId": position_id,
        "execType": "Trade",
    }


def page(items, cursor=None, ret_code=0):
    return {"retCode": ret_code, "retMsg": "OK", "result": {"list": items, "nextPageCursor": cursor}}


def source_for(client, *matches, **setting_changes):
    account_id = AccountId.generate()
    return BybitExecutionSource(settings(account_id, **setting_changes), FakeInstruments(*matches), client), account_id


def test_bybit_normalizes_buy_and_sell_fills_with_decimal_and_utc_values():
    first = instrument()
    second = instrument("ETHUSDT")
    client = FakeClient(page([item(exec_id="b", symbol="BTCUSDT", side="Buy", time_ms="1725364800000"), item(exec_id="s", symbol="ETHUSDT", side="Sell", time_ms="1725364801000")]))
    source, account_id = source_for(client, first, second)
    facts = asyncio.run(source.fetch_executions())
    assert [fact.external_execution_id for fact in facts] == ["b", "s"]
    assert facts[0].account_id == account_id
    assert facts[0].quantity.value == Decimal("1.25")
    assert facts[0].price.value == Decimal("100.10")
    assert facts[0].executed_at.tzinfo is not None
    assert facts[0].executed_at == datetime(2024, 9, 3, 12, tzinfo=timezone.utc)
    assert facts[0].external_order_id == "order-1"
    assert facts[0].position_id == "position-1"
    assert facts[1].side.value == "SELL"
    assert all(call[1]["execType"] == "Trade" for call in client.calls)
    assert all(call[1]["settleCoin"] == "USDT" and call[1]["category"] == "linear" for call in client.calls)


def test_bybit_missing_or_non_usdt_fee_currency_uses_usdt_settlement_scope():
    for value in (None, "BTC"):
        row = {key: item_value for key, item_value in item().items() if key != "feeCurrency"}
        if value is not None:
            row["feeCurrency"] = value
        source, _ = source_for(FakeClient(page([row])), instrument())
        facts = asyncio.run(source.fetch_executions())
        assert facts[0].fee.currency == "USDT"
        assert facts[0].fee.amount == Decimal("0.10")


def test_bybit_10001_preserves_sanitized_retmsg_without_secrets():
    payload = page([], ret_code=10001)
    payload["retMsg"] = "invalid request\nrange is too large"
    source, _ = source_for(FakeClient(payload), instrument())
    with pytest.raises(BybitRequestError) as error:
        asyncio.run(source.fetch_executions())
    message = str(error.value)
    assert "Bybit API request failed:" in message
    assert "retCode=10001" in message
    assert "retMsg=invalid request range is too large" in message


def test_raw_history_windows_are_strictly_bounded_and_reset_cursor():
    client = FakeClient(
        page([], "cursor-in-window"),
        page([], None),
        page([], None),
        page([], None),
    )
    source, _ = source_for(client, instrument())
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=15)
    asyncio.run(source.fetch_raw_historical_executions(start_at=start, end_at=end))
    assert len(client.calls) == 4
    for _, params in client.calls:
        assert int(params["startTime"]) < int(params["endTime"])
        assert 0 < int(params["endTime"]) - int(params["startTime"]) <= 7 * 86_400_000
        assert params["category"] == "linear"
        assert params["settleCoin"] == "USDT"
        assert params["execType"] == "Trade"
    assert "cursor" not in client.calls[0][1]
    assert client.calls[1][1]["cursor"] == "cursor-in-window"
    assert "cursor" not in client.calls[2][1]
    assert "cursor" not in client.calls[3][1]
    assert int(client.calls[3][1]["endTime"]) - int(client.calls[3][1]["startTime"]) == 86_400_000


def test_raw_history_rejects_equal_boundaries():
    source, _ = source_for(FakeClient(page([])), instrument())
    value = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="less than"):
        asyncio.run(source.fetch_raw_historical_executions(start_at=value, end_at=value))


def test_bybit_fetches_all_pages_propagates_cursor_and_orders_chronologically():
    item_old = item(exec_id="old", time_ms="1725364800000")
    item_new = item(exec_id="new", time_ms="1725364802000")
    client = FakeClient(page([item_new], "next-token"), page([item_old]))
    source, _ = source_for(client, instrument())
    facts = asyncio.run(source.fetch_executions(cursor="start-token", since=datetime(2024, 9, 3, 11, tzinfo=timezone.utc)))
    assert [fact.external_execution_id for fact in facts] == ["old", "new"]
    assert client.calls[0][1]["cursor"] == "start-token"
    assert client.calls[1][1]["cursor"] == "next-token"
    assert client.calls[0][1]["startTime"] == "1725361200000"


def test_bybit_deduplicates_exact_duplicate_execution_ids():
    client = FakeClient(page([item(), item()]))
    source, _ = source_for(client, instrument())
    assert len(asyncio.run(source.fetch_executions())) == 1


@pytest.mark.parametrize(
    "payload",
    [
        page([item(exec_id="",)]),
        page([item(side="Unknown")]),
        page([item(price="not-a-number")]),
        page([item(time_ms="not-a-time")]),
        page([{**item(), "symbol": ""}]),
        page([{**item(), "execFee": "-0.1", "execType": "Trade"}]),
    ],
)
def test_bybit_rejects_invalid_or_unsafe_payload(payload):
    source, _ = source_for(FakeClient(payload), instrument())
    with pytest.raises(BybitPayloadError):
        asyncio.run(source.fetch_executions())


def test_bybit_rejects_unknown_and_ambiguous_instrument_mapping():
    source, _ = source_for(FakeClient(page([item()])))
    with pytest.raises(BybitInstrumentMappingError):
        asyncio.run(source.fetch_executions())


def test_bybit_funding_rows_are_defensively_ignored_even_with_negative_fee():
    funding = {**item(exec_id="funding-1", fee="-0.1"), "execType": "Funding"}
    client = FakeClient(page([funding, item(exec_id="trade-1")]))
    source, _ = source_for(client, instrument())
    facts = asyncio.run(source.fetch_executions())
    assert [fact.external_execution_id for fact in facts] == ["trade-1"]
    source, _ = source_for(FakeClient(page([item()])), instrument(), instrument())
    with pytest.raises(BybitInstrumentMappingError):
        asyncio.run(source.fetch_executions())


def test_bybit_translates_authentication_failure_without_retry():
    source, _ = source_for(FakeClient(page([], ret_code=10003)), instrument(), max_retries=2)
    with pytest.raises(BybitAuthenticationError):
        asyncio.run(source.fetch_executions())


def test_bybit_retries_one_rate_limit_then_succeeds():
    client = FakeClient(page([], ret_code=10006), page([item()]))
    source, _ = source_for(client, instrument(), max_retries=1)
    assert len(asyncio.run(source.fetch_executions())) == 1
    assert len(client.calls) == 2


def test_bybit_payload_conflict_with_same_execution_id_is_not_hidden():
    client = FakeClient(page([item(price="100"), item(price="101")]))
    source, _ = source_for(client, instrument())
    with pytest.raises(BybitPayloadError):
        asyncio.run(source.fetch_executions())


def test_bybit_historical_fetch_uses_seven_day_windows_and_global_ordering():
    first = item(exec_id="first", time_ms="1725364800000")
    second = item(exec_id="second", time_ms="1725969600000")
    client = FakeClient(page([first]), page([second]))
    source, _ = source_for(client, instrument())
    start = datetime(2024, 9, 1, tzinfo=timezone.utc)
    end = datetime(2024, 9, 12, tzinfo=timezone.utc)
    facts = asyncio.run(source.fetch_historical_executions(start_at=start, end_at=end))
    assert [fact.external_execution_id for fact in facts] == ["first", "second"]
    assert len(client.calls) == 2
    assert client.calls[0][1]["execType"] == "Trade"
    assert client.calls[0][1]["endTime"] == "1725753599999"
    assert client.calls[1][1]["startTime"] == "1725753600000"
    assert client.calls[1][1]["endTime"] == "1726099200000"


def test_historical_worker_pool_is_bounded_and_windows_overlap():
    class ConcurrentClient:
        def __init__(self):
            self.active = 0
            self.maximum = 0
            self.calls = []

        async def get(self, path, params):
            self.calls.append(dict(params))
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0.02)
            self.active -= 1
            return page([])

    client = ConcurrentClient()
    source, _ = source_for(client, instrument(), history_concurrency=2)
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    asyncio.run(source.fetch_raw_historical_executions(start_at=start, end_at=start + timedelta(days=20)))
    assert client.maximum == 2
    assert client.maximum <= 2


def test_sequential_and_concurrent_historical_results_are_identical():
    class RangeClient:
        def __init__(self):
            self.calls = []

        async def get(self, path, params):
            self.calls.append(dict(params))
            at = int(params["startTime"]) + 1
            return page([item(exec_id=f"fill-{params['startTime']}", time_ms=str(at))])

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    first_client = RangeClient()
    account_id = AccountId.generate()
    journal_instrument = instrument()
    first = BybitExecutionSource(settings(account_id, history_concurrency=1), FakeInstruments(journal_instrument), first_client)
    second_client = RangeClient()
    second = BybitExecutionSource(settings(account_id, history_concurrency=4), FakeInstruments(journal_instrument), second_client)
    sequential = asyncio.run(first.fetch_historical_executions(start_at=start, end_at=start + timedelta(days=20)))
    concurrent = asyncio.run(second.fetch_historical_executions(start_at=start, end_at=start + timedelta(days=20)))
    assert [(item.executed_at, item.external_execution_id) for item in sequential] == [(item.executed_at, item.external_execution_id) for item in concurrent]


def test_bybit_payload_flows_into_process_execution_fact_and_replay_policy():
    account_id = AccountId.generate()
    journal_instrument = instrument()
    client = FakeClient(page([item()]))
    source = BybitExecutionSource(settings(account_id), FakeInstruments(journal_instrument), client)
    repository = FakeExecutionRepository()
    processor = ProcessExecutionFact(repository, FakeAccounts(account_id), FakeInstruments(journal_instrument))
    fact = asyncio.run(source.fetch_executions())[0]
    first = asyncio.run(processor.execute(fact))
    replay = asyncio.run(processor.execute(fact))
    assert first.status.value == "PROCESSED"
    assert replay.status.value == "ALREADY_PROCESSED"
    assert len(repository.items) == 1
    with pytest.raises(ExecutionFactConflictError):
        asyncio.run(processor.execute(replace(fact, price=Price("999"))))
