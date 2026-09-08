"""Mappers for the factual Execution domain entity."""

from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution import Execution
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade_id import TradeId

from ..models.execution import ExecutionORM


def execution_to_orm(execution: Execution) -> ExecutionORM:
    if not isinstance(execution, Execution):
        raise TypeError("execution must be Execution")
    return ExecutionORM(
        id=execution.execution_id.value,
        trade_id=None if execution.trade_id is None else execution.trade_id.value,
        account_id=execution.account_id.value,
        instrument_id=execution.instrument_id.value,
        side=execution.side.value,
        quantity=execution.quantity.value,
        price=execution.price.value,
        fee_amount=execution.fee.amount,
        fee_currency=execution.fee.currency,
        executed_at=execution.executed_at,
        exchange=execution.exchange,
        external_execution_id=execution.external_execution_id,
        external_order_id=execution.external_order_id,
        position_id=execution.position_id,
    )


def execution_from_orm(model: ExecutionORM) -> Execution:
    if not isinstance(model, ExecutionORM):
        raise TypeError("model must be ExecutionORM")
    return Execution(
        execution_id=ExecutionId(model.id),
        account_id=AccountId(model.account_id),
        instrument_id=InstrumentId(model.instrument_id),
        side=ExecutionSide(model.side),
        quantity=Quantity(model.quantity),
        price=Price(model.price),
        fee=Money(model.fee_amount, model.fee_currency),
        executed_at=model.executed_at,
        exchange=model.exchange,
        trade_id=None if model.trade_id is None else TradeId(model.trade_id),
        external_execution_id=model.external_execution_id,
        external_order_id=model.external_order_id,
        position_id=model.position_id,
    )
