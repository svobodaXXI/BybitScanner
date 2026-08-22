"""Explicit command, order and connectivity state machines."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType


class InvalidStateTransition(ValueError):
    """Raised when evidence attempts an invalid or regressive transition."""


class CommandState(str, Enum):
    LOCAL_INTENT = "local_intent"
    ADMITTED = "admitted"
    SUBMITTING = "submitting"
    ACKNOWLEDGED = "acknowledged"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    AMENDED = "amended"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"
    RECONCILING = "reconciling"


class OrderState(str, Enum):
    UNKNOWN_RECONCILING = "unknown_reconciling"
    PENDING_CONFIRMATION = "pending_confirmation"
    OPEN = "open"
    PARTIALLY_FILLED_OPEN = "partially_filled_open"
    CANCEL_PENDING = "cancel_pending"
    AMEND_PENDING = "amend_pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING_TRIGGER = "pending_trigger"


class ConnectivityState(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    UNKNOWN_EXECUTION = "unknown_execution"
    RECONCILING = "reconciling"
    OFFLINE = "offline"


_COMMAND_TRANSITIONS = {
    CommandState.LOCAL_INTENT: frozenset({CommandState.ADMITTED, CommandState.FAILED}),
    CommandState.ADMITTED: frozenset({CommandState.SUBMITTING, CommandState.FAILED}),
    CommandState.SUBMITTING: frozenset({
        CommandState.ACKNOWLEDGED,
        CommandState.REJECTED,
        CommandState.FAILED,
        CommandState.UNKNOWN,
        CommandState.RECONCILING,
    }),
    CommandState.ACKNOWLEDGED: frozenset({
        CommandState.AMENDED,
        CommandState.OPEN,
        CommandState.PARTIALLY_FILLED,
        CommandState.FILLED,
        CommandState.CANCEL_PENDING,
        CommandState.UNKNOWN,
        CommandState.RECONCILING,
    }),
    CommandState.OPEN: frozenset({
        CommandState.PARTIALLY_FILLED,
        CommandState.FILLED,
        CommandState.CANCEL_PENDING,
        CommandState.RECONCILING,
    }),
    CommandState.PARTIALLY_FILLED: frozenset({
        CommandState.FILLED,
        CommandState.CANCEL_PENDING,
        CommandState.CANCELLED,
        CommandState.RECONCILING,
    }),
    CommandState.CANCEL_PENDING: frozenset({
        CommandState.CANCELLED,
        CommandState.FILLED,
        CommandState.UNKNOWN,
        CommandState.RECONCILING,
    }),
    CommandState.UNKNOWN: frozenset({CommandState.RECONCILING}),
    CommandState.RECONCILING: frozenset({
        CommandState.AMENDED,
        CommandState.ACKNOWLEDGED,
        CommandState.OPEN,
        CommandState.PARTIALLY_FILLED,
        CommandState.FILLED,
        CommandState.CANCEL_PENDING,
        CommandState.CANCELLED,
        CommandState.REJECTED,
        CommandState.FAILED,
        CommandState.UNKNOWN,
    }),
    CommandState.FILLED: frozenset(),
    CommandState.CANCELLED: frozenset(),
    CommandState.AMENDED: frozenset(),
    CommandState.REJECTED: frozenset(),
    CommandState.FAILED: frozenset(),
}

COMMAND_TRANSITIONS = MappingProxyType(_COMMAND_TRANSITIONS)

_ORDER_TRANSITIONS = {
    OrderState.PENDING_CONFIRMATION: frozenset({
        OrderState.OPEN,
        OrderState.PARTIALLY_FILLED_OPEN,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.PENDING_TRIGGER,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.PENDING_TRIGGER: frozenset({
        OrderState.OPEN,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.OPEN: frozenset({
        OrderState.PARTIALLY_FILLED_OPEN,
        OrderState.CANCEL_PENDING,
        OrderState.AMEND_PENDING,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.PARTIALLY_FILLED_OPEN: frozenset({
        OrderState.CANCEL_PENDING,
        OrderState.AMEND_PENDING,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.CANCEL_PENDING: frozenset({
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.AMEND_PENDING: frozenset({
        OrderState.OPEN,
        OrderState.PARTIALLY_FILLED_OPEN,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.UNKNOWN_RECONCILING,
    }),
    OrderState.UNKNOWN_RECONCILING: frozenset({
        OrderState.PENDING_CONFIRMATION,
        OrderState.PENDING_TRIGGER,
        OrderState.OPEN,
        OrderState.PARTIALLY_FILLED_OPEN,
        OrderState.CANCEL_PENDING,
        OrderState.AMEND_PENDING,
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    }),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
}

ORDER_TRANSITIONS = MappingProxyType(_ORDER_TRANSITIONS)


def transition_command(current: CommandState, requested: CommandState) -> CommandState:
    if requested not in COMMAND_TRANSITIONS[current]:
        raise InvalidStateTransition(f"command transition {current.value} -> {requested.value} is invalid")
    return requested


def transition_order(current: OrderState, requested: OrderState) -> OrderState:
    if requested not in ORDER_TRANSITIONS[current]:
        raise InvalidStateTransition(f"order transition {current.value} -> {requested.value} is invalid")
    return requested
