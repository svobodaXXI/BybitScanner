"""Transport-neutral, frontend-safe Terminal API data contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from terminal.domain.models import OrderSide


PROTOCOL_VERSION = "1"


class CommandResultStatus(str, Enum):
    ACCEPTED_PENDING = "accepted_pending"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    UNKNOWN = "unknown"
    VALIDATION_ERROR = "validation_error"
    UNAVAILABLE = "unavailable"
    PERSISTENCE_FAILURE = "persistence_failure"


class VolumeUnit(str, Enum):
    WORKING_VOLUME = "working_volume"
    USDT = "usdt"


class TimeInForce(str, Enum):
    GTC = "GTC"


class ServiceHealth(str, Enum):
    HEALTHY = "healthy"
    UNAVAILABLE = "unavailable"


class TradingReadiness(str, Enum):
    READY = "ready"
    DEGRADED = "degraded"
    RECONCILING = "reconciling"
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    DISABLED = "disabled"


class EventType(str, Enum):
    SNAPSHOT_REPLACED = "snapshot_replaced"
    POSITION_CHANGED = "position_changed"
    ORDER_ADDED = "order_added"
    ORDER_UPDATED = "order_updated"
    ORDER_REMOVED = "order_removed"
    EXECUTION_RECORDED = "execution_recorded"
    CONNECTIVITY_CHANGED = "connectivity_changed"
    TRUST_CHANGED = "trust_changed"
    CLEANUP_CHANGED = "cleanup_changed"
    PROTECTION_CHANGED = "protection_changed"
    WARNING_CHANGED = "warning_changed"
    HEARTBEAT = "heartbeat"


class PresentationChannel(str, Enum):
    POSITION = "position"
    ORDERS = "orders"
    EXECUTIONS = "executions"
    PROTECTION = "protection"
    CLEANUP = "cleanup"
    CONNECTIVITY = "connectivity"
    WARNINGS = "warnings"


class SubscriptionOperation(str, Enum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    UNSUBSCRIBE_ALL = "unsubscribe_all"
    PING = "ping"
    PONG = "pong"


@dataclass(frozen=True, slots=True)
class ClientActionId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value or len(self.value) > 128:
            raise ValueError("client_action_id must be a non-empty opaque string up to 128 characters")
        if any(ord(character) < 32 for character in self.value):
            raise ValueError("client_action_id cannot contain control characters")


@dataclass(frozen=True, slots=True)
class VolumeRequest:
    unit: VolumeUnit
    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite() or self.amount <= 0:
            raise ValueError("volume amount must be a positive finite Decimal")


@dataclass(frozen=True, slots=True)
class MarketCommandRequest:
    client_action_id: ClientActionId
    symbol: str
    side: OrderSide
    volume: VolumeRequest
    sizing_reference_price: Decimal
    slippage_type: str
    slippage_value: Decimal


@dataclass(frozen=True, slots=True)
class FullCloseCommandRequest:
    client_action_id: ClientActionId
    symbol: str


@dataclass(frozen=True, slots=True)
class CloseAllCommandRequest:
    client_action_id: ClientActionId


@dataclass(frozen=True, slots=True)
class PaperOpenPositionProjection:
    symbol: str
    position_side: str
    position_quantity: Decimal
    average_entry: Decimal | None
    engaged_notional_usdt: Decimal
    engaged_wv: Decimal
    current_price: Decimal | None
    unrealized_pnl: Decimal | None
    tick_size: Decimal


@dataclass(frozen=True, slots=True)
class PaperOpenPositionsResponse:
    account_id: str
    positions: tuple[PaperOpenPositionProjection, ...]


@dataclass(frozen=True, slots=True)
class CloseAllCommandResponse:
    client_action_id: str
    results: tuple[CommandResult, ...]
    positions: tuple[PaperOpenPositionProjection, ...]


@dataclass(frozen=True, slots=True)
class LimitCommandRequest:
    client_action_id: ClientActionId
    symbol: str
    side: OrderSide
    volume: VolumeRequest
    sizing_reference_price: Decimal
    limit_price: Decimal
    time_in_force: TimeInForce = TimeInForce.GTC


@dataclass(frozen=True, slots=True)
class PaperLimitCancelRequest:
    client_action_id: ClientActionId
    symbol: str
    order_id: str


@dataclass(frozen=True, slots=True)
class PaperLimitAmendRequest:
    client_action_id: ClientActionId
    symbol: str
    order_id: str
    limit_price: Decimal


@dataclass(frozen=True, slots=True)
class PaperLimitOrderProjection:
    order_id: str
    order_link_id: str
    symbol: str
    side: OrderSide
    price: str
    quantity: str
    time_in_force: TimeInForce


@dataclass(frozen=True, slots=True)
class PaperLimitMutationResult:
    client_action_id: str
    status: CommandResultStatus
    reason_code: str
    order_id: str | None


@dataclass(frozen=True, slots=True)
class AmendCommandRequest:
    client_action_id: ClientActionId
    symbol: str
    order_id: str | None = None
    order_link_id: str | None = None
    resulting_total_quantity: Decimal | None = None
    changed_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CancelCommandRequest:
    client_action_id: ClientActionId
    symbol: str
    order_id: str | None = None
    order_link_id: str | None = None


@dataclass(frozen=True, slots=True)
class ProtectionCommandRequest:
    client_action_id: ClientActionId
    symbol: str
    take_profit: Decimal | None
    stop_loss: Decimal | None
    tp_trigger_by: str = "LastPrice"
    sl_trigger_by: str = "LastPrice"


@dataclass(frozen=True, slots=True)
class CommandResult:
    client_action_id: str
    status: CommandResultStatus
    reason_code: str
    message: str
    command_id: str | None = None
    reconciliation_required: bool = False


@dataclass(frozen=True, slots=True)
class SubscriptionRequest:
    operation: SubscriptionOperation
    symbol: str | None = None
    channels: tuple[PresentationChannel, ...] = ()
    nonce: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionResult:
    operation: SubscriptionOperation
    accepted: bool
    symbol: str | None
    channels: tuple[PresentationChannel, ...]
    fresh_snapshot_required: bool = False
    nonce: str | None = None


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    protocol_version: str
    stream_id: str
    snapshot_id: str
    event_sequence: int
    reconciliation_generation: int
    entity_id: str
    entity_version: int
    exchange_sequence: int | None
    event_type: EventType
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.event_sequence < 1 or self.entity_version < 0:
            raise ValueError("event and entity versions must be non-negative ordered values")


def to_primitive(value: Any) -> Any:
    """Convert approved DTO values to JSON-ready primitives without float conversion."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ClientActionId):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {key: to_primitive(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): to_primitive(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_primitive(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported API serialization type: {type(value).__name__}")

