from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import InstrumentId
from app.core.accounts.account_id import AccountId
from app.core.trades.enums import ExecutionSide, TradeDirection, TradePnLSource, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.execution_replay import replay_executions, validate_execution_replay
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


def fills(*rows):
    account = AccountId.generate()
    instrument = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Execution(
            execution_id=ExecutionId.generate(),
            account_id=account,
            instrument_id=instrument,
            side=side,
            quantity=Quantity(quantity),
            price=Price(price),
            fee=Money(fee, "USDT"),
            executed_at=base + timedelta(minutes=index),
            exchange="BYBIT",
            external_execution_id=external_id,
        )
        for index, (side, quantity, price, fee, external_id) in enumerate(rows)
    )


def replay_trade(executions, *, direction, status, quantity, gross, fees):
    first = executions[0]
    return Trade(
        trade_id=TradeId.generate(),
        account_id=first.account_id,
        instrument_id=first.instrument_id,
        direction=direction,
        status=status,
        opened_at=first.executed_at,
        closed_at=executions[-1].executed_at if status is TradeStatus.CLOSED else None,
        entry_price=Price("100"),
        exit_price=Price("90") if status is TradeStatus.CLOSED else None,
        quantity=Quantity(quantity),
        stop_price=None,
        risk=None,
        fees=Money(fees, "USDT"),
        gross_pnl=Money(gross, "USDT") if status is TradeStatus.CLOSED else None,
        net_pnl=Money(Decimal(gross) - Decimal(fees), "USDT") if status is TradeStatus.CLOSED else None,
        pnl_source=TradePnLSource.EXECUTION_REPLAY,
    )


def test_scale_in_replay_accepts_snapshot_rounding_delta():
    executions = fills(
        (ExecutionSide.BUY, "3", "100", "0.1", "open-1"),
        (ExecutionSide.BUY, "2", "101", "0.2", "open-2"),
        (ExecutionSide.SELL, "5", "102", "0.3", "close"),
    )
    result = replay_executions(executions)
    trade = replay_trade(
        executions,
        direction=TradeDirection.LONG,
        status=TradeStatus.CLOSED,
        quantity="5",
        gross=str(result.gross_pnl.amount),
        fees="0.6",
    )
    trade.entry_price = Price("100.4")
    validate_execution_replay(trade, executions)


@pytest.mark.parametrize(
    "rows",
    [
        (
            (ExecutionSide.BUY, "10", "100", "0.1", "open"),
            (ExecutionSide.SELL, "4", "110", "0.1", "partial"),
            (ExecutionSide.SELL, "6", "105", "0.1", "close"),
        ),
        (
            (ExecutionSide.SELL, "2", "100", "0.1", "open"),
            (ExecutionSide.BUY, "1", "90", "0.1", "partial"),
            (ExecutionSide.BUY, "1", "95", "0.1", "close"),
        ),
        (
            (ExecutionSide.BUY, "1", "100", "0.1", "open"),
            (ExecutionSide.SELL, "2", "110", "0.2", "reverse"),
            (ExecutionSide.BUY, "1", "90", "0.1", "close-residual"),
        ),
    ],
)
def test_replay_supports_partial_multiple_exit_and_residual_reversal(rows):
    executions = fills(*rows)
    result = replay_executions(executions)
    assert result.fees.amount == sum((Decimal(row[3]) for row in rows), Decimal(0))
    assert result.status is TradeStatus.CLOSED
    assert result.gross_pnl.amount.is_finite()


def test_wrong_replay_gross_fee_or_net_is_rejected():
    executions = fills(
        (ExecutionSide.BUY, "1", "100", "0.1", "open"),
        (ExecutionSide.SELL, "1", "110", "0.2", "close"),
    )
    result = replay_executions(executions)
    for gross, fees in (("9", "0.3"), (str(result.gross_pnl.amount), "0.4")):
        trade = replay_trade(executions, direction=TradeDirection.LONG, status=TradeStatus.CLOSED, quantity="1", gross=gross, fees=fees)
        with pytest.raises(ValueError):
            validate_execution_replay(trade, executions)
    trade = replay_trade(executions, direction=TradeDirection.LONG, status=TradeStatus.CLOSED, quantity="1", gross=str(result.gross_pnl.amount), fees="0.3")
    trade.net_pnl = Money("999", "USDT")
    with pytest.raises(ValueError):
        validate_execution_replay(trade, executions)
