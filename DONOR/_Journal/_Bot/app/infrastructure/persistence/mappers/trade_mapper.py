"""Trade mapper using public Trade lifecycle operations for rehydration."""

from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection, TradePnLSource, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId

from ..models.trade import TradeExpenseORM, TradeORM


def _money(amount, currency):
    return Money(amount, currency)


def trade_to_orm(trade: Trade) -> TradeORM:
    if not isinstance(trade, Trade):
        raise TypeError("trade must be Trade")
    risk_amount = None if trade.risk is None else trade.risk.amount.amount
    risk_currency = None if trade.risk is None else trade.risk.amount.currency
    return TradeORM(
        id=trade.trade_id.value,
        account_id=trade.account_id.value,
        instrument_id=trade.instrument_id.value,
        direction=trade.direction.value,
        status=trade.status.value,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
        entry_price=trade.entry_price.value,
        exit_price=None if trade.exit_price is None else trade.exit_price.value,
        quantity=trade.quantity.value,
        stop_price=None if trade.stop_price is None else trade.stop_price.value,
        take_profit=None if trade.take_profit is None else trade.take_profit.value,
        currency=trade.fees.currency,
        risk_amount=risk_amount,
        risk_currency=risk_currency,
        fees_amount=trade.fees.amount,
        fees_currency=trade.fees.currency,
        gross_pnl_amount=None if trade.gross_pnl is None else trade.gross_pnl.amount,
        gross_pnl_currency=None if trade.gross_pnl is None else trade.gross_pnl.currency,
        net_pnl_amount=None if trade.net_pnl is None else trade.net_pnl.amount,
        net_pnl_currency=None if trade.net_pnl is None else trade.net_pnl.currency,
        pnl_source=trade.pnl_source.value,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        expenses=[
            TradeExpenseORM(
                trade_id=trade.trade_id.value,
                sequence=sequence,
                amount=expense.amount.amount,
                currency=expense.amount.currency,
                created_at=trade.opened_at,
            )
            for sequence, expense in enumerate(trade.expenses)
        ],
    )


def trade_from_orm(model: TradeORM) -> Trade:
    if not isinstance(model, TradeORM):
        raise TypeError("model must be TradeORM")
    if model.status not in (TradeStatus.OPEN.value, TradeStatus.CLOSED.value):
        raise ValueError(f"unsupported persisted Trade status: {model.status!r}")
    try:
        pnl_source = TradePnLSource(model.pnl_source or TradePnLSource.SNAPSHOT.value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"unsupported persisted PnL source: {model.pnl_source!r}") from error
    expenses = tuple(Expense(_money(item.amount, item.currency)) for item in (model.expenses or ()))
    risk = None
    if model.risk_amount is not None:
        risk = Risk(_money(model.risk_amount, model.risk_currency or model.currency))
    trade = Trade.open(
        account_id=AccountId(model.account_id),
        instrument_id=InstrumentId(model.instrument_id),
        direction=TradeDirection(model.direction),
        entry_price=Price(model.entry_price),
        quantity=Quantity(model.quantity),
        opened_at=model.opened_at,
        currency=model.currency,
        trade_id=TradeId(model.id),
        stop_price=None if model.stop_price is None else Price(model.stop_price),
        take_profit=None if model.take_profit is None else Price(model.take_profit),
        risk=risk,
        fees=_money(model.fees_amount, model.fees_currency),
        expenses=expenses,
        pnl_source=pnl_source,
    )
    if model.status == TradeStatus.CLOSED.value:
        if model.closed_at is None:
            raise ValueError("persisted CLOSED Trade lacks closed_at")
        if model.exit_price is not None and model.gross_pnl_amount is not None and model.net_pnl_amount is not None:
            trade.close(Price(model.exit_price), model.closed_at)
            persisted_gross = _money(model.gross_pnl_amount, model.gross_pnl_currency)
            persisted_net = _money(model.net_pnl_amount, model.net_pnl_currency)
            if pnl_source is TradePnLSource.SNAPSHOT:
                if trade.gross_pnl != persisted_gross:
                    raise ValueError("persisted gross PnL does not match Trade facts")
                if trade.net_pnl != persisted_net:
                    raise ValueError("persisted net PnL does not match Trade facts")
            else:
                trade.gross_pnl = persisted_gross
                trade.net_pnl = persisted_net
        else:
            trade = Trade(
                trade_id=trade.trade_id,
                account_id=trade.account_id,
                instrument_id=trade.instrument_id,
                direction=trade.direction,
                status=TradeStatus.CLOSED,
                opened_at=trade.opened_at,
                closed_at=model.closed_at,
                entry_price=trade.entry_price,
                exit_price=None if model.exit_price is None else Price(model.exit_price),
                quantity=trade.quantity,
                stop_price=trade.stop_price,
                take_profit=trade.take_profit,
                risk=trade.risk,
                fees=trade.fees,
                expenses=trade.expenses,
                gross_pnl=None if model.gross_pnl_amount is None else _money(model.gross_pnl_amount, model.gross_pnl_currency),
                net_pnl=None if model.net_pnl_amount is None else _money(model.net_pnl_amount, model.net_pnl_currency),
                pnl_source=pnl_source,
            )
    return trade
