"""Deterministic shared-Market plan for Robot v0.1 late admission.

This module builds and restores command identity/request data only. It performs
no persistence, no market-data fetch, and no order submission.
RobotBreakoutMonitor owns durable intent ordering; TerminalCommandApi owns
normalization/execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import uuid
from typing import Any, Mapping

import robot_state_machine
from terminal.api.models import (
    ClientActionId,
    MarketCommandRequest,
    VolumeRequest,
    VolumeUnit,
)
from terminal.application.command_identity import (
    CommandIdentityCandidate,
    CommandIdentityFactory,
)
from terminal.application.robot_admission_catchup import LATE_ADMISSION_MARKET
from terminal.domain.models import CommandId, OrderSide, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook


LATE_ADMISSION_MARKET_WV = Decimal("1")
LATE_ADMISSION_SLIPPAGE_TYPE = "Percent"
LATE_ADMISSION_SLIPPAGE_PERCENT = Decimal("0.5")


class RobotLateAdmissionMarketError(RuntimeError):
    """Raised when a deterministic late-admission Market plan is invalid."""


@dataclass(frozen=True, slots=True)
class LateAdmissionMarketPlan:
    candidate_id: str
    direction: str
    best_price: Decimal
    request: MarketCommandRequest
    identity: CommandIdentityCandidate


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotLateAdmissionMarketError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotLateAdmissionMarketError(f"{field} must be finite and positive")
    return number


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotLateAdmissionMarketError(f"{field} must be a non-negative integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotLateAdmissionMarketError(f"{field} must be a non-negative integer") from exc
    if not number.is_finite() or number < 0 or number != number.to_integral_value():
        raise RobotLateAdmissionMarketError(f"{field} must be a non-negative integer")
    return int(number)


def _stable_digest(candidate_id: str) -> str:
    return hashlib.sha256(
        f"{candidate_id}\0late-admission-market".encode("utf-8")
    ).hexdigest()[:32]


def _stable_action_id(candidate_id: str) -> ClientActionId:
    return ClientActionId(f"robot-late-market-{_stable_digest(candidate_id)}")


def _stable_command_identity(candidate_id: str) -> CommandIdentityCandidate:
    deterministic_uuid = uuid.UUID(hex=_stable_digest(candidate_id))
    return CommandIdentityFactory(lambda: deterministic_uuid).create()


def build_late_admission_market_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    book: NormalizedOrderBook,
) -> LateAdmissionMarketPlan:
    """Build the single 1-WV MARKET intent for a replay-discovered retest.

    The sizing reference is the current executable best price on the same side
    that the shared PAPER Market path will consume. Canonical quantity remains
    owned by TerminalCommandApi.market_preflight(); this builder never duplicates
    instrument normalization.
    """

    if not isinstance(candidate, Mapping) or not isinstance(state, Mapping):
        raise RobotLateAdmissionMarketError("candidate and state must be mappings")
    if candidate.get("status") != "APPROVED":
        raise RobotLateAdmissionMarketError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotLateAdmissionMarketError("late admission requires 1m candidate")
    if state.get("phase") != robot_state_machine.PHASE_RETEST_DETECTED:
        raise RobotLateAdmissionMarketError("late admission requires RETEST_DETECTED")

    execution = state.get("execution")
    if not isinstance(execution, Mapping) or execution.get("entry_mode") != LATE_ADMISSION_MARKET:
        raise RobotLateAdmissionMarketError("late admission marker is missing")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    snapshot = candidate.get("signal_snapshot")
    if not candidate_id or not isinstance(snapshot, Mapping):
        raise RobotLateAdmissionMarketError("candidate identity and snapshot are required")
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not symbol:
        raise RobotLateAdmissionMarketError("signal snapshot symbol is missing")

    direction = str(state.get("direction", "")).strip().upper()
    if direction == robot_state_machine.DIRECTION_LONG:
        side = OrderSide.BUY
        levels = book.asks
    elif direction == robot_state_machine.DIRECTION_SHORT:
        side = OrderSide.SELL
        levels = book.bids
    else:
        raise RobotLateAdmissionMarketError("unsupported Robot direction")

    if book.symbol != Symbol(symbol) or book.health is not BookHealth.READY:
        raise RobotLateAdmissionMarketError("normalized book is not READY for candidate symbol")
    if not levels:
        raise RobotLateAdmissionMarketError("executable book side is empty")

    best_price = levels[0].price.value
    if not isinstance(best_price, Decimal) or not best_price.is_finite() or best_price <= 0:
        raise RobotLateAdmissionMarketError("best executable price is invalid")

    request = MarketCommandRequest(
        client_action_id=_stable_action_id(candidate_id),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, LATE_ADMISSION_MARKET_WV),
        sizing_reference_price=best_price,
        slippage_type=LATE_ADMISSION_SLIPPAGE_TYPE,
        slippage_value=LATE_ADMISSION_SLIPPAGE_PERCENT,
    )
    return LateAdmissionMarketPlan(
        candidate_id=candidate_id,
        direction=direction,
        best_price=best_price,
        request=request,
        identity=_stable_command_identity(candidate_id),
    )


def durable_late_admission_market_intent(
    plan: LateAdmissionMarketPlan,
    *,
    normalized_quantity: Decimal,
    current_geometry_index: int,
    projected_vwap: Decimal,
    stop_price: Decimal,
    take_price: Decimal,
    expected_reward: Decimal,
    rr: Decimal,
    adverse_slippage: Decimal,
    persisted_at_ms: int,
) -> dict[str, object]:
    """Serialize the exact approved Market request/identity before mutation."""

    quantity = _decimal(normalized_quantity, "normalized_quantity")
    geometry_index = _non_negative_int(current_geometry_index, "current_geometry_index")
    persisted = _non_negative_int(persisted_at_ms, "persisted_at_ms")
    metrics = {
        "projected_vwap": _decimal(projected_vwap, "projected_vwap"),
        "stop_price": _decimal(stop_price, "stop_price"),
        "take_price": _decimal(take_price, "take_price"),
        "expected_reward": _decimal(expected_reward, "expected_reward"),
        "rr": _decimal(rr, "rr"),
    }
    slippage = adverse_slippage if isinstance(adverse_slippage, Decimal) else Decimal(str(adverse_slippage))
    if not slippage.is_finite() or slippage < 0:
        raise RobotLateAdmissionMarketError("adverse_slippage must be finite and non-negative")

    request = plan.request
    return {
        "candidate_id": plan.candidate_id,
        "direction": plan.direction,
        "client_action_id": request.client_action_id.value,
        "command_id": plan.identity.command_id.value,
        "order_link_id": plan.identity.order_link_id,
        "symbol": request.symbol,
        "side": request.side.value,
        "volume_unit": request.volume.unit.value,
        "volume_amount": str(request.volume.amount),
        "sizing_reference_price": str(request.sizing_reference_price),
        "slippage_type": request.slippage_type,
        "slippage_value": str(request.slippage_value),
        "best_price": str(plan.best_price),
        "normalized_quantity": str(quantity),
        "geometry_index": geometry_index,
        "projected_vwap": str(metrics["projected_vwap"]),
        "stop_price": str(metrics["stop_price"]),
        "take_price": str(metrics["take_price"]),
        "expected_reward": str(metrics["expected_reward"]),
        "rr": str(metrics["rr"]),
        "adverse_slippage": str(slippage),
        "persisted_at_ms": persisted,
    }


def restore_late_admission_market_plan(
    intent: Mapping[str, Any],
) -> LateAdmissionMarketPlan:
    """Restore exactly the previously persisted request for crash/restart replay."""

    if not isinstance(intent, Mapping):
        raise RobotLateAdmissionMarketError("durable late Market intent must be a mapping")
    candidate_id = str(intent.get("candidate_id", "")).strip()
    direction = str(intent.get("direction", "")).strip().upper()
    symbol = str(intent.get("symbol", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotLateAdmissionMarketError("durable late Market identity is incomplete")
    if direction not in {robot_state_machine.DIRECTION_LONG, robot_state_machine.DIRECTION_SHORT}:
        raise RobotLateAdmissionMarketError("durable late Market direction is invalid")

    expected_action = _stable_action_id(candidate_id)
    expected_identity = _stable_command_identity(candidate_id)
    if str(intent.get("client_action_id", "")) != expected_action.value:
        raise RobotLateAdmissionMarketError("durable late Market client_action_id changed")
    if str(intent.get("command_id", "")) != expected_identity.command_id.value:
        raise RobotLateAdmissionMarketError("durable late Market command_id changed")
    if str(intent.get("order_link_id", "")) != expected_identity.order_link_id:
        raise RobotLateAdmissionMarketError("durable late Market order_link_id changed")

    try:
        side = OrderSide(str(intent.get("side", "")))
        volume_unit = VolumeUnit(str(intent.get("volume_unit", "")))
    except ValueError as exc:
        raise RobotLateAdmissionMarketError("durable late Market enum value is invalid") from exc
    if volume_unit is not VolumeUnit.WORKING_VOLUME:
        raise RobotLateAdmissionMarketError("durable late Market volume must use working volume")

    volume_amount = _decimal(intent.get("volume_amount"), "volume_amount")
    if volume_amount != LATE_ADMISSION_MARKET_WV:
        raise RobotLateAdmissionMarketError("durable late Market volume changed")
    sizing_reference_price = _decimal(
        intent.get("sizing_reference_price"), "sizing_reference_price"
    )
    best_price = _decimal(intent.get("best_price"), "best_price")
    if sizing_reference_price != best_price:
        raise RobotLateAdmissionMarketError("durable late Market sizing reference changed")
    slippage_type = str(intent.get("slippage_type", ""))
    slippage_value = _decimal(intent.get("slippage_value"), "slippage_value")
    if (
        slippage_type != LATE_ADMISSION_SLIPPAGE_TYPE
        or slippage_value != LATE_ADMISSION_SLIPPAGE_PERCENT
    ):
        raise RobotLateAdmissionMarketError("durable late Market slippage changed")

    request = MarketCommandRequest(
        client_action_id=expected_action,
        symbol=symbol,
        side=side,
        volume=VolumeRequest(volume_unit, volume_amount),
        sizing_reference_price=sizing_reference_price,
        slippage_type=slippage_type,
        slippage_value=slippage_value,
    )
    return LateAdmissionMarketPlan(
        candidate_id=candidate_id,
        direction=direction,
        best_price=best_price,
        request=request,
        identity=CommandIdentityCandidate(
            command_id=CommandId(expected_identity.command_id.value),
            order_link_id=expected_identity.order_link_id,
        ),
    )
