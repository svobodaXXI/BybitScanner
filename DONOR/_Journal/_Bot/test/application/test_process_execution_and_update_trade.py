import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.errors import AmbiguousOpenTradeError, ExecutionFactConflictError, UnsupportedPositionReversalError
from app.application.use_cases.process_execution_and_update_trade import ProcessExecutionAndUpdateTrade, TradeAction
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import Instrument, InstrumentId
from app.core.trades.enums import ExecutionSide, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


class State:
    def __init__(self):
        self.trades = []
        self.executions = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_trade_save = False


class Trades:
    def __init__(self, state):
        self.state = state

    async def list_open(self, *, account_id=None, instrument_id=None):
        return tuple(item for item in self.state.trades if item.status is TradeStatus.OPEN and item.account_id == account_id and item.instrument_id == instrument_id)

    async def save(self, trade):
        existing = next((index for index, item in enumerate(self.state.trades) if item.trade_id == trade.trade_id), None)
        if existing is None:
            self.state.trades.append(trade)
        else:
            self.state.trades[existing] = trade
        if self.state.fail_trade_save:
            raise RuntimeError("forced trade persistence failure")


class Executions:
    def __init__(self, state):
        self.state = state

    async def get_by_external_id(self, *, exchange, account_id, external_execution_id):
        return next((item for item in self.state.executions if (item.exchange, item.account_id, item.external_execution_id) == (exchange, account_id, external_execution_id)), None)

    async def list_by_trade(self, trade_id):
        return tuple(item for item in self.state.executions if item.trade_id == trade_id)

    async def save(self, execution):
        self.state.executions.append(execution)


class Accounts:
    def __init__(self, account_id):
        self.account_id = account_id

    async def exists(self, account_id):
        return account_id == self.account_id


class Instruments:
    def __init__(self, instrument):
        self.instrument = instrument

    async def get_by_id(self, instrument_id):
        return self.instrument if instrument_id == self.instrument.instrument_id else None


class Uow:
    def __init__(self, state, account_id, instrument):
        self.state = state
        self.trades = Trades(state)
        self.executions = Executions(state)
        self.accounts = Accounts(account_id)
        self.instruments = Instruments(instrument)
        self._snapshot = None
        self.committed = False

    async def __aenter__(self):
        self._snapshot = (deepcopy(self.state.trades), deepcopy(self.state.executions))
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None or not self.committed:
            await self.rollback()

    async def commit(self):
        self.committed = True
        self.state.commits += 1

    async def rollback(self):
        self.state.trades, self.state.executions = deepcopy(self._snapshot)
        self.state.rollbacks += 1


def make_context():
    account_id = AccountId.generate()
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin / Tether")
    state = State()
    def factory():
        return Uow(state, account_id, instrument)
    return account_id, instrument, state, factory


def fact(account_id, instrument_id, side, quantity, price, external_id, position_id="P", at=0, fee="1"):
    return ExecutionFact(
        exchange="TEST",
        account_id=account_id,
        instrument_id=instrument_id,
        side=side,
        quantity=Quantity(quantity),
        price=Price(price),
        fee=Money(fee, "USDT"),
        executed_at=datetime(2026, 1, 1, 10, tzinfo=timezone.utc) + timedelta(minutes=at),
        external_execution_id=external_id,
        position_id=position_id,
    )


def test_atomic_orchestration_creates_updates_partially_closes_and_closes_trade():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    result = asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "2", "100", "1")))
    assert result.trade_action is TradeAction.CREATED
    result = asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "110", "2", at=1)))
    assert result.trade_action is TradeAction.UPDATED
    assert state.trades[0].quantity == Quantity("3")
    assert state.trades[0].entry_price == Price("103.3333333333333333333333333")
    result = asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.SELL, "0.5", "120", "3", at=2)))
    assert result.trade_action is TradeAction.UPDATED
    assert state.trades[0].status is TradeStatus.OPEN
    assert state.trades[0].quantity == Quantity("2.5")
    result = asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.SELL, "2.5", "120", "4", at=3)))
    assert result.trade_action is TradeAction.CLOSED
    assert state.trades[0].status is TradeStatus.CLOSED
    assert state.commits == 4


def test_exact_replay_does_not_reaggregate_and_conflict_does_not_mutate():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    original = fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "100", "same")
    first = asyncio.run(use_case.execute(original))
    replay = asyncio.run(use_case.execute(original))
    assert replay.execution_status.value == "ALREADY_PROCESSED"
    assert replay.trade_action is TradeAction.NONE
    assert len(state.executions) == 1
    with pytest.raises(ExecutionFactConflictError):
        asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "2", "100", "same")))
    assert len(state.executions) == 1
    assert state.trades[0].trade_id == first.trade_id


def test_parallel_position_references_match_separate_open_trades_and_missing_reference_is_ambiguous():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "100", "p1", "P1")))
    second = asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "101", "p2", "P2")))
    assert second.trade_action is TradeAction.CREATED
    assert len(state.trades) == 2
    with pytest.raises(AmbiguousOpenTradeError):
        asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "102", "no-position", None)))


def test_reversal_and_trade_persistence_failure_roll_back_execution_and_trade():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "100", "open")))
    before = deepcopy(state.trades[0])
    with pytest.raises(UnsupportedPositionReversalError):
        asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.SELL, "2", "110", "reverse")))
    assert len(state.executions) == 1
    assert state.trades[0] == before
    state.fail_trade_save = True
    with pytest.raises(RuntimeError):
        asyncio.run(use_case.execute(fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "101", "fails", at=1)))
    assert len(state.executions) == 1
    assert state.trades[0] == before
    assert state.rollbacks >= 2


def test_scale_in_short_then_full_close_keeps_one_trade_and_weighted_entry():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    prices = ("100", "101", "102", "103", "104")
    for index, price in enumerate(prices):
        result = asyncio.run(use_case.execute(
            fact(account_id, instrument.instrument_id, ExecutionSide.SELL, "14", price, f"sell-{index}", at=index)
        ))
        assert result.trade_action is (TradeAction.CREATED if index == 0 else TradeAction.UPDATED)
    result = asyncio.run(use_case.execute(
        fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "70", "90", "buy-close", at=6)
    ))
    assert result.trade_action is TradeAction.CLOSED
    assert state.trades[0].direction.value == "SHORT"
    assert state.trades[0].quantity.value == 70
    assert state.trades[0].entry_price == Price("102")
    assert state.trades[0].status is TradeStatus.CLOSED
    assert len(state.executions) == 6
    assert {item.trade_id for item in state.executions} == {state.trades[0].trade_id}


def test_realistic_zec_long_cycle_calculates_domain_gross_and_net_pnl():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    asyncio.run(use_case.execute(fact(
        account_id, instrument.instrument_id, ExecutionSide.BUY, "0.01", "1019.55", "zec-buy",
        fee="0.00367038",
    )))
    result = asyncio.run(use_case.execute(fact(
        account_id, instrument.instrument_id, ExecutionSide.SELL, "0.01", "1009.28", "zec-sell",
        fee="0.0100928", at=1,
    )))
    trade = state.trades[0]
    assert result.trade_action is TradeAction.CLOSED
    assert trade.status is TradeStatus.CLOSED
    assert trade.gross_pnl.amount == Decimal("-0.1027")
    assert trade.fees.amount == Decimal("0.01376318")
    assert trade.net_pnl.amount == Decimal("-0.11646318")
    assert len({item.trade_id for item in state.executions}) == 1


def test_confirmed_bybit_residual_reversal_closes_old_and_opens_new_trade():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    opening = replace(
        fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "100", "open", position_id="P"),
        exchange="BYBIT",
    )
    reversal = replace(
        fact(account_id, instrument.instrument_id, ExecutionSide.SELL, "2", "110", "reverse", position_id="P", at=1),
        exchange="BYBIT",
    )

    first = asyncio.run(use_case.execute(opening))
    result = asyncio.run(use_case.execute(reversal))

    assert result.trade_action is TradeAction.REVERSED
    assert len(state.trades) == 2
    old, new = state.trades
    assert old.trade_id == first.trade_id
    assert old.status is TradeStatus.CLOSED
    assert old.quantity == Quantity("1")
    assert new.status is TradeStatus.OPEN
    assert new.direction.value == "SHORT"
    assert new.quantity == Quantity("1")
    assert new.trade_id != old.trade_id
    assert len(state.executions) == 3
    assert {item.trade_id for item in state.executions if item.trade_id == old.trade_id} == {old.trade_id}
    assert state.executions[-1].external_execution_id == "reverse"
    replay = asyncio.run(use_case.execute(reversal))
    assert replay.trade_action is TradeAction.NONE
    assert len(state.trades) == 2
    assert len(state.executions) == 3


def test_older_historical_fill_with_reused_position_id_cannot_mutate_live_open_trade():
    account_id, instrument, state, factory = make_context()
    use_case = ProcessExecutionAndUpdateTrade(factory)
    live_fact = replace(
        fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "3", "200", "live", position_id="P", at=10),
        exchange="BYBIT",
    )
    historical_fact = replace(
        fact(account_id, instrument.instrument_id, ExecutionSide.BUY, "1", "100", "old", position_id="P"),
        exchange="BYBIT",
    )

    live_result = asyncio.run(use_case.execute(live_fact))
    live_before = deepcopy(state.trades[0])
    asyncio.run(use_case.execute(historical_fact))

    assert len(state.trades) == 2
    assert state.trades[0] == live_before
    assert live_result.trade_id == state.trades[0].trade_id
    assert {item.external_execution_id for item in state.executions if item.trade_id == live_result.trade_id} == {"live"}
