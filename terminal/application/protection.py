"""Manual full-position protection contracts and pure validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from terminal.application.models import ProtectionState
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide, PositionKey, PositionSide
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import InstrumentSnapshot, PositionEvent
from terminal.persistence.sqlite_store import ProtectionProjectionRecord


@dataclass(frozen=True, slots=True)
class ManualProtectionIntent:
    position_key: PositionKey
    side: OrderSide
    position: PositionEvent
    instrument: InstrumentSnapshot
    take_profit: Decimal | None
    stop_loss: Decimal | None
    tp_trigger_by: str = "LastPrice"
    sl_trigger_by: str = "LastPrice"
    connectivity: ConnectivityState = ConnectivityState.OFFLINE


@dataclass(frozen=True, slots=True)
class ProtectionApplicationResult:
    command_id: str
    state: ProtectionState
    projection: ProtectionProjectionRecord


def validate_manual_protection(intent: ManualProtectionIntent) -> None:
    if intent.position.position_key != intent.position_key:
        raise ValueError("protection Position scope does not match")
    if intent.instrument.category is not intent.position_key.category:
        raise ValueError("protection instrument category does not match")
    if intent.instrument.symbol != intent.position_key.symbol.value:
        raise ValueError("protection instrument symbol does not match")
    if intent.connectivity is not ConnectivityState.ONLINE:
        raise ValueError("manual protection mutation requires ONLINE state")
    allowed = {"LastPrice", "MarkPrice", "IndexPrice"}
    if intent.tp_trigger_by not in allowed or intent.sl_trigger_by not in allowed:
        raise ValueError("unsupported protection trigger type")
    for name, value in (("take profit", intent.take_profit), ("stop loss", intent.stop_loss)):
        if value is None:
            continue
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise ValueError(f"{name} must be a positive Decimal or None")
        if value % intent.instrument.tick_size != 0:
            raise ValueError(f"{name} must already be normalized to tick size")
        if not (intent.instrument.min_price <= value <= intent.instrument.max_price):
            raise ValueError(f"{name} is outside instrument limits")


def normalize_paper_protection_trigger(
    position: PositionEvent,
    instrument: InstrumentSnapshot,
    requested_trigger: Decimal,
    leg: str,
) -> Decimal:
    """Normalize and validate one full-position protection trigger."""

    if position.side is PositionSide.FLAT or position.size <= 0:
        raise ValueError("PAPER protection requires an authoritative open position")
    if position.average_entry is None or position.average_entry <= 0:
        raise ValueError("PAPER protection requires authoritative average entry")
    if leg not in {"stop", "take"}:
        raise ValueError("unsupported PAPER protection leg")
    closing_side = (
        OrderSide.SELL if position.side is PositionSide.LONG else OrderSide.BUY
    )
    normalized = normalize_limit_price(
        requested_trigger, instrument.tick_size, closing_side,
    )
    if not (instrument.min_price <= normalized <= instrument.max_price):
        raise ValueError("protection trigger is outside instrument limits")
    if leg == "take":
        expects_below = position.side is PositionSide.SHORT
        if expects_below and normalized >= position.average_entry:
            raise ValueError("TAKE must be below authoritative average entry")
        if not expects_below and normalized <= position.average_entry:
            raise ValueError("TAKE must be above authoritative average entry")
    return normalized


def normalize_paper_stop_trigger(
    position: PositionEvent,
    instrument: InstrumentSnapshot,
    requested_trigger: Decimal,
) -> Decimal:
    return normalize_paper_protection_trigger(position, instrument, requested_trigger, "stop")
