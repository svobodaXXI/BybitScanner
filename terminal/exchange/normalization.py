"""Pure fail-closed normalization of Bybit V5 payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from terminal.domain.models import (
    Category,
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Symbol,
    TradingAccountId,
)

from .events import (
    ExecutionEvent,
    InstrumentSnapshot,
    NormalizedOrderStatus,
    NormalizedOrderType,
    NormalizedPositionStatus,
    OrderEvent,
    PositionEvent,
)


class PayloadNormalizationError(ValueError):
    """Raw exchange evidence is missing, malformed or unsupported."""


class IncompatiblePositionMode(PayloadNormalizationError):
    """Position evidence does not satisfy Manual v1 One-Way mode."""


_MISSING = object()


def _required(payload: Mapping[str, Any], name: str) -> Any:
    value = payload.get(name, _MISSING)
    if value is _MISSING or value is None or value == "":
        raise PayloadNormalizationError(f"required field is missing: {name}")
    return value


def _text(payload: Mapping[str, Any], name: str) -> str:
    value = _required(payload, name)
    if not isinstance(value, str):
        raise PayloadNormalizationError(f"field {name} must be a string")
    return value


def _optional_text(payload: Mapping[str, Any], name: str) -> str | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise PayloadNormalizationError(f"field {name} must be a string")
    return value


def _decimal_value(value: Any, name: str) -> Decimal:
    if not isinstance(value, str):
        raise PayloadNormalizationError(f"field {name} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise PayloadNormalizationError(f"field {name} is not a Decimal") from exc
    if not result.is_finite():
        raise PayloadNormalizationError(f"field {name} must be finite")
    return result


def _decimal(payload: Mapping[str, Any], name: str) -> Decimal:
    return _decimal_value(_required(payload, name), name)


def _optional_decimal(payload: Mapping[str, Any], name: str) -> Decimal | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    return _decimal_value(value, name)


def _decimal_or_zero(payload: Mapping[str, Any], name: str) -> Decimal:
    value = payload.get(name)
    if value in (None, ""):
        return Decimal(0)
    return _decimal_value(value, name)


def _integer(payload: Mapping[str, Any], name: str) -> int:
    value = _required(payload, name)
    if isinstance(value, bool):
        raise PayloadNormalizationError(f"field {name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PayloadNormalizationError(f"field {name} must be an integer") from exc


def _optional_integer(payload: Mapping[str, Any], name: str) -> int | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise PayloadNormalizationError(f"field {name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise PayloadNormalizationError(f"field {name} must be an integer") from exc


def _boolean(payload: Mapping[str, Any], name: str) -> bool:
    value = _required(payload, name)
    if not isinstance(value, bool):
        raise PayloadNormalizationError(f"field {name} must be boolean")
    return value


def _optional_boolean(payload: Mapping[str, Any], name: str) -> bool | None:
    value = payload.get(name)
    if value in (None, ""):
        return None
    if not isinstance(value, bool):
        raise PayloadNormalizationError(f"field {name} must be boolean")
    return value


def _category(payload: Mapping[str, Any]) -> Category:
    raw = _text(payload, "category")
    if raw != Category.LINEAR.value:
        raise PayloadNormalizationError(f"unsupported category: {raw}")
    return Category.LINEAR


def _symbol(payload: Mapping[str, Any]) -> str:
    return Symbol(_text(payload, "symbol")).value


def _side(payload: Mapping[str, Any]) -> OrderSide:
    try:
        return OrderSide(_text(payload, "side"))
    except ValueError as exc:
        raise PayloadNormalizationError("unsupported order side") from exc


def _order_type(raw: str) -> NormalizedOrderType:
    return {
        "Market": NormalizedOrderType.MARKET,
        "Limit": NormalizedOrderType.LIMIT,
    }.get(raw, NormalizedOrderType.UNKNOWN)


def _order_status(raw: str) -> NormalizedOrderStatus:
    return {
        "Untriggered": NormalizedOrderStatus.PENDING_TRIGGER,
        "Triggered": NormalizedOrderStatus.OPEN,
        "New": NormalizedOrderStatus.OPEN,
        "PartiallyFilled": NormalizedOrderStatus.PARTIALLY_FILLED_OPEN,
        "Filled": NormalizedOrderStatus.FILLED,
        "Cancelled": NormalizedOrderStatus.CANCELLED,
        "PartiallyFilledCanceled": NormalizedOrderStatus.CANCELLED,
        "Rejected": NormalizedOrderStatus.REJECTED,
        "Deactivated": NormalizedOrderStatus.DEACTIVATED,
    }.get(raw, NormalizedOrderStatus.UNKNOWN)


def _position_status(raw: str) -> NormalizedPositionStatus:
    return {
        "Normal": NormalizedPositionStatus.NORMAL,
        "Liq": NormalizedPositionStatus.LIQUIDATING,
        "Adl": NormalizedPositionStatus.AUTO_DELEVERAGING,
    }.get(raw, NormalizedPositionStatus.UNKNOWN)


def normalize_order(
    payload: Mapping[str, Any], trading_account_id: TradingAccountId
) -> OrderEvent:
    raw_order_type = _text(payload, "orderType")
    raw_status = _text(payload, "orderStatus")
    return OrderEvent(
        trading_account_id=trading_account_id,
        category=_category(payload),
        symbol=_symbol(payload),
        order_id=OrderId(_text(payload, "orderId")),
        order_link_id=_optional_text(payload, "orderLinkId"),
        position_idx=_integer(payload, "positionIdx"),
        side=_side(payload),
        order_type=_order_type(raw_order_type),
        raw_order_type=raw_order_type,
        price=_optional_decimal(payload, "price"),
        quantity=_decimal(payload, "qty"),
        cumulative_filled_quantity=_decimal_or_zero(payload, "cumExecQty"),
        leaves_quantity=_decimal_or_zero(payload, "leavesQty"),
        average_price=_optional_decimal(payload, "avgPrice"),
        status=_order_status(raw_status),
        raw_status=raw_status,
        reduce_only=_boolean(payload, "reduceOnly"),
        close_on_trigger=_boolean(payload, "closeOnTrigger"),
        stop_order_type=_optional_text(payload, "stopOrderType"),
        trigger_price=_optional_decimal(payload, "triggerPrice"),
        take_profit=_optional_decimal(payload, "takeProfit"),
        stop_loss=_optional_decimal(payload, "stopLoss"),
        tpsl_mode=_optional_text(payload, "tpslMode"),
        created_at_ms=_integer(payload, "createdTime"),
        updated_at_ms=_integer(payload, "updatedTime"),
    )


def normalize_execution(
    payload: Mapping[str, Any], trading_account_id: TradingAccountId
) -> ExecutionEvent:
    return ExecutionEvent(
        trading_account_id=trading_account_id,
        category=_category(payload),
        symbol=_symbol(payload),
        exec_id=ExecutionId(_text(payload, "execId")),
        order_id=OrderId(_text(payload, "orderId")),
        order_link_id=_optional_text(payload, "orderLinkId"),
        side=_side(payload),
        execution_price=_decimal(payload, "execPrice"),
        execution_quantity=_decimal(payload, "execQty"),
        execution_fee=_decimal(payload, "execFee"),
        execution_value=_decimal(payload, "execValue"),
        is_maker=_optional_boolean(payload, "isMaker"),
        executed_at_ms=_integer(payload, "execTime"),
        sequence=_optional_integer(payload, "seq"),
    )


def normalize_position(
    payload: Mapping[str, Any], trading_account_id: TradingAccountId
) -> PositionEvent:
    category = _category(payload)
    symbol = _symbol(payload)
    position_idx = _integer(payload, "positionIdx")
    if position_idx != 0:
        raise IncompatiblePositionMode(
            f"Manual v1 requires One-Way positionIdx=0, received {position_idx}"
        )
    size = _decimal(payload, "size")
    raw_side = payload.get("side")
    if raw_side == "" and size == 0:
        side = PositionSide.FLAT
    elif raw_side == OrderSide.BUY.value and size > 0:
        side = PositionSide.LONG
    elif raw_side == OrderSide.SELL.value and size > 0:
        side = PositionSide.SHORT
    else:
        raise PayloadNormalizationError("position side and size are contradictory")
    raw_status = _text(payload, "positionStatus")
    average_entry = _optional_decimal(payload, "avgPrice")
    if average_entry is None:
        average_entry = _optional_decimal(payload, "entryPrice")
    return PositionEvent(
        position_key=PositionKey(
            trading_account_id,
            category,
            Symbol(symbol),
            position_idx,
        ),
        side=side,
        size=size,
        average_entry=average_entry,
        mark_price=_optional_decimal(payload, "markPrice"),
        position_value=_optional_decimal(payload, "positionValue"),
        unrealized_pnl=_optional_decimal(payload, "unrealisedPnl"),
        current_realized_pnl=_optional_decimal(payload, "curRealisedPnl"),
        cumulative_realized_pnl=_optional_decimal(payload, "cumRealisedPnl"),
        status=_position_status(raw_status),
        raw_status=raw_status,
        take_profit=_optional_decimal(payload, "takeProfit"),
        stop_loss=_optional_decimal(payload, "stopLoss"),
        trailing_stop=_optional_decimal(payload, "trailingStop"),
        sequence=_optional_integer(payload, "seq"),
        updated_at_ms=_integer(payload, "updatedTime"),
    )


def normalize_instrument(payload: Mapping[str, Any]) -> InstrumentSnapshot:
    category = _category(payload)
    price_filter = payload.get("priceFilter")
    lot_filter = payload.get("lotSizeFilter")
    if not isinstance(price_filter, Mapping) or not isinstance(lot_filter, Mapping):
        raise PayloadNormalizationError("instrument filters are missing")
    return InstrumentSnapshot(
        category=category,
        symbol=_symbol(payload),
        contract_type=_text(payload, "contractType"),
        status=_text(payload, "status"),
        base_coin=_text(payload, "baseCoin"),
        quote_coin=_text(payload, "quoteCoin"),
        settle_coin=_text(payload, "settleCoin"),
        min_price=_decimal(price_filter, "minPrice"),
        max_price=_decimal(price_filter, "maxPrice"),
        tick_size=_decimal(price_filter, "tickSize"),
        min_order_quantity=_decimal(lot_filter, "minOrderQty"),
        max_order_quantity=_decimal(lot_filter, "maxOrderQty"),
        max_market_order_quantity=_decimal(lot_filter, "maxMktOrderQty"),
        quantity_step=_decimal(lot_filter, "qtyStep"),
        min_notional_value=_decimal(lot_filter, "minNotionalValue"),
    )


def normalize_order_message(
    message: Mapping[str, Any], trading_account_id: TradingAccountId
) -> tuple[OrderEvent, ...]:
    return tuple(
        normalize_order(item, trading_account_id)
        for item in _message_items(message, "order")
    )


def normalize_execution_message(
    message: Mapping[str, Any], trading_account_id: TradingAccountId
) -> tuple[ExecutionEvent, ...]:
    return tuple(
        normalize_execution(item, trading_account_id)
        for item in _message_items(message, "execution")
    )


def normalize_position_message(
    message: Mapping[str, Any], trading_account_id: TradingAccountId
) -> tuple[PositionEvent, ...]:
    return tuple(
        normalize_position(item, trading_account_id)
        for item in _message_items(message, "position")
    )


def _message_items(message: Mapping[str, Any], expected_topic: str) -> list[Mapping[str, Any]]:
    topic = message.get("topic")
    if not isinstance(topic, str) or topic.split(".", 1)[0] != expected_topic:
        raise PayloadNormalizationError(f"unexpected private stream topic: {topic}")
    data = message.get("data")
    if not isinstance(data, list) or not data:
        raise PayloadNormalizationError("private stream data must be a non-empty list")
    if not all(isinstance(item, Mapping) for item in data):
        raise PayloadNormalizationError("private stream item must be an object")
    return data
