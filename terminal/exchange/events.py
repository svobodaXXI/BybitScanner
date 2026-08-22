"""Immutable normalized Bybit read and private-stream evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from terminal.domain.models import (
    Category,
    ExecutionDedupKey,
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    TradingAccountId,
)


class NormalizedOrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    UNKNOWN = "unknown"


class NormalizedOrderStatus(str, Enum):
    PENDING_TRIGGER = "pending_trigger"
    OPEN = "open"
    PARTIALLY_FILLED_OPEN = "partially_filled_open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    DEACTIVATED = "deactivated"
    UNKNOWN = "unknown"


class NormalizedPositionStatus(str, Enum):
    NORMAL = "normal"
    LIQUIDATING = "liquidating"
    AUTO_DELEVERAGING = "auto_deleveraging"
    UNKNOWN = "unknown"


class StreamLifecycleKind(str, Enum):
    BUFFERING = "buffering"
    CONNECTED_UNTRUSTED = "connected_untrusted"
    DISCONNECTED = "disconnected"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class OrderEvent:
    trading_account_id: TradingAccountId
    category: Category
    symbol: str
    order_id: OrderId
    order_link_id: str | None
    position_idx: int
    side: OrderSide
    order_type: NormalizedOrderType
    raw_order_type: str
    price: Decimal | None
    quantity: Decimal
    cumulative_filled_quantity: Decimal
    leaves_quantity: Decimal
    average_price: Decimal | None
    status: NormalizedOrderStatus
    raw_status: str
    reduce_only: bool
    close_on_trigger: bool
    stop_order_type: str | None
    trigger_price: Decimal | None
    take_profit: Decimal | None
    stop_loss: Decimal | None
    tpsl_mode: str | None
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    trading_account_id: TradingAccountId
    category: Category
    symbol: str
    exec_id: ExecutionId
    order_id: OrderId
    order_link_id: str | None
    side: OrderSide
    execution_price: Decimal
    execution_quantity: Decimal
    execution_fee: Decimal
    execution_value: Decimal
    is_maker: bool | None
    executed_at_ms: int
    sequence: int | None

    @property
    def dedup_identity(self) -> ExecutionDedupKey:
        return ExecutionDedupKey(
            self.trading_account_id,
            self.category,
            self.exec_id,
        )


@dataclass(frozen=True, slots=True)
class PositionEvent:
    position_key: PositionKey
    side: PositionSide
    size: Decimal
    average_entry: Decimal | None
    mark_price: Decimal | None
    position_value: Decimal | None
    unrealized_pnl: Decimal | None
    current_realized_pnl: Decimal | None
    cumulative_realized_pnl: Decimal | None
    status: NormalizedPositionStatus
    raw_status: str
    take_profit: Decimal | None
    stop_loss: Decimal | None
    trailing_stop: Decimal | None
    sequence: int | None
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class InstrumentSnapshot:
    category: Category
    symbol: str
    contract_type: str
    status: str
    base_coin: str
    quote_coin: str
    settle_coin: str
    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal
    min_order_quantity: Decimal
    max_order_quantity: Decimal
    max_market_order_quantity: Decimal
    quantity_step: Decimal
    min_notional_value: Decimal


@dataclass(frozen=True, slots=True)
class StreamLifecycleEvent:
    trading_account_id: TradingAccountId
    kind: StreamLifecycleKind
    reason: str
