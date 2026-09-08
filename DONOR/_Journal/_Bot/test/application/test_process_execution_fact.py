import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.errors import AccountNotFoundError, ExecutionFactConflictError, InstrumentMappingNotFoundError, InvalidExecutionFactError
from app.application.use_cases.process_execution_fact import ExecutionProcessingStatus, ProcessExecutionFact
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import Instrument, InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution_fact import ExecutionFact


class FakeAccounts:
    def __init__(self, *account_ids):
        self.account_ids = set(account_ids)

    async def exists(self, account_id):
        return account_id in self.account_ids


class FakeInstruments:
    def __init__(self, instrument):
        self.instrument = instrument

    async def get_by_id(self, instrument_id):
        return self.instrument if instrument_id == self.instrument.instrument_id else None


class FakeExecutions:
    def __init__(self):
        self.items = []
        self.saved = []

    async def get_by_external_id(self, *, exchange, account_id, external_execution_id):
        return next((item for item in self.items if (item.exchange, item.account_id, item.external_execution_id) == (exchange, account_id, external_execution_id)), None)

    async def save(self, execution):
        self.items.append(execution)
        self.saved.append(execution)


def make_fact(account_id, instrument_id, **changes):
    values = dict(
        exchange="bybit",
        account_id=account_id,
        instrument_id=instrument_id,
        side=ExecutionSide.BUY,
        quantity=Quantity(Decimal("1.25")),
        price=Price(Decimal("100.10")),
        fee=Money(Decimal("0.10"), "USDT"),
        executed_at=datetime(2026, 9, 3, 12, tzinfo=timezone.utc),
        external_execution_id="fill-1",
    )
    values.update(changes)
    return ExecutionFact(**values)


def make_processor():
    account_id = AccountId.generate()
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin / Tether", "BYBIT", "SPOT")
    executions = FakeExecutions()
    processor = ProcessExecutionFact(executions, FakeAccounts(account_id), FakeInstruments(instrument))
    return processor, executions, account_id, instrument.instrument_id


def test_process_execution_fact_first_and_exact_replay_are_idempotent():
    processor, executions, account_id, instrument_id = make_processor()
    first = asyncio.run(processor.execute(make_fact(account_id, instrument_id)))
    replay = asyncio.run(processor.execute(make_fact(account_id, instrument_id)))
    assert first.status is ExecutionProcessingStatus.PROCESSED
    assert replay.status is ExecutionProcessingStatus.ALREADY_PROCESSED
    assert replay.execution_id == first.execution_id
    assert len(executions.saved) == 1


def test_process_execution_fact_conflicting_replay_is_explicit():
    processor, _, account_id, instrument_id = make_processor()
    asyncio.run(processor.execute(make_fact(account_id, instrument_id)))
    with pytest.raises(ExecutionFactConflictError):
        asyncio.run(processor.execute(make_fact(account_id, instrument_id, price=Price(101))))


def test_process_execution_fact_requires_existing_account_and_instrument():
    processor, _, account_id, instrument_id = make_processor()
    with pytest.raises(AccountNotFoundError):
        asyncio.run(processor.execute(make_fact(AccountId.generate(), instrument_id)))
    with pytest.raises(InstrumentMappingNotFoundError):
        asyncio.run(processor.execute(make_fact(account_id, InstrumentId.generate())))
    with pytest.raises(InvalidExecutionFactError):
        asyncio.run(processor.execute(make_fact(account_id, instrument_id, external_execution_id=None)))


def test_process_execution_fact_allows_same_external_identity_on_different_exchange_and_account():
    processor, executions, account_id, instrument_id = make_processor()
    asyncio.run(processor.execute(make_fact(account_id, instrument_id)))
    asyncio.run(processor.execute(make_fact(account_id, instrument_id, exchange="MOEX")))
    other_account = AccountId.generate()
    other_instrument = Instrument(instrument_id, "BTCUSDT", "Bitcoin / Tether")
    processor = ProcessExecutionFact(executions, FakeAccounts(account_id, other_account), FakeInstruments(other_instrument))
    asyncio.run(processor.execute(make_fact(other_account, instrument_id)))
    asyncio.run(processor.execute(make_fact(account_id, instrument_id, external_execution_id="fill-2")))
    assert len(executions.saved) == 4
