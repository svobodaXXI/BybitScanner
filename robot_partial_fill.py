"""Robot v0.1 partial-fill completion and top-up policy.

This module owns strategy decisions only. It never retries exchange mutations and
never increases exposure while order state is ambiguous. Limit/Market execution
remains owned by shared Terminal capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping

from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT, boundary_price
from terminal.api.models import ClientActionId, LimitCommandRequest, TimeInForce, VolumeRequest, VolumeUnit
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide

TARGET_WV = Decimal("1")
PARTIAL_COMPLETION_WAIT_MS = 10_000
MAX_ADVERSE_MOVE = Decimal("0.005")
REPRICE_CANDLES = 5
MIN_RR = Decimal("1")

DECISION_WAIT = "WAIT"
DECISION_MARKET_COMPLETE = "MARKET_COMPLETE"
DECISION_KEEP_PARTIAL = "KEEP_PARTIAL"
DECISION_BLOCKED_AMBIGUOUS = "BLOCKED_AMBIGUOUS"
DECISION_BLOCKED_POOR_RR = "BLOCKED_POOR_RR"
DECISION_APEX_REACHED = "APEX_REACHED"
DECISION_FULL = "FULL"


class RobotPartialFillError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PartialFillSnapshot:
    direction: str
    filled_wv: Decimal
    first_partial_at_ms: int
    first_partial_price: Decimal
    order_authoritatively_inactive: bool


@dataclass(frozen=True, slots=True)
class PartialFillDecision:
    action: str
    missing_wv: Decimal
    adverse_move: Decimal


@dataclass(frozen=True, slots=True)
class TopUpLimitPlan:
    candidate_id: str
    geometry_index: int
    missing_wv: Decimal
    boundary_price: Decimal
    request: LimitCommandRequest


def _decimal(value: Any, field: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotPartialFillError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise RobotPartialFillError(f"{field} must be finite and {'non-negative' if allow_zero else 'positive'}")
    return number


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotPartialFillError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotPartialFillError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotPartialFillError(f"{field} must be an integer")
    return int(number)


def missing_wv(filled_wv: Decimal) -> Decimal:
    filled = _decimal(filled_wv, "filled_wv", allow_zero=True)
    if filled > TARGET_WV:
        raise RobotPartialFillError("filled_wv exceeds 1 WV invariant")
    return TARGET_WV - filled


def adverse_move_ratio(direction: str, *, reference_price: Decimal, current_price: Decimal) -> Decimal:
    reference = _decimal(reference_price, "reference_price")
    current = _decimal(current_price, "current_price")
    normalized_direction = direction.strip().upper()
    if normalized_direction == DIRECTION_LONG:
        return max(Decimal("0"), (current - reference) / reference)
    if normalized_direction == DIRECTION_SHORT:
        return max(Decimal("0"), (reference - current) / reference)
    raise RobotPartialFillError("unsupported Robot direction")


def evaluate_partial_completion(
    snapshot: PartialFillSnapshot,
    *,
    now_ms: int,
    current_price: Decimal,
    rr: Decimal,
    before_apex: bool,
) -> PartialFillDecision:
    """Decide whether the remainder may be completed by Market after a partial fill."""

    filled = _decimal(snapshot.filled_wv, "filled_wv", allow_zero=True)
    remainder = missing_wv(filled)
    adverse = adverse_move_ratio(
        snapshot.direction,
        reference_price=snapshot.first_partial_price,
        current_price=current_price,
    )
    if remainder == 0:
        return PartialFillDecision(DECISION_FULL, remainder, adverse)
    if not before_apex:
        return PartialFillDecision(DECISION_APEX_REACHED, remainder, adverse)
    if not snapshot.order_authoritatively_inactive:
        return PartialFillDecision(DECISION_BLOCKED_AMBIGUOUS, remainder, adverse)
    if _decimal(rr, "rr", allow_zero=True) < MIN_RR:
        return PartialFillDecision(DECISION_BLOCKED_POOR_RR, remainder, adverse)
    elapsed = _integer(now_ms, "now_ms") - _integer(snapshot.first_partial_at_ms, "first_partial_at_ms")
    if elapsed < 0:
        raise RobotPartialFillError("now_ms precedes first partial fill")
    if elapsed < PARTIAL_COMPLETION_WAIT_MS:
        return PartialFillDecision(DECISION_WAIT, remainder, adverse)
    if adverse > MAX_ADVERSE_MOVE:
        return PartialFillDecision(DECISION_KEEP_PARTIAL, remainder, adverse)
    return PartialFillDecision(DECISION_MARKET_COMPLETE, remainder, adverse)


def topup_due(*, last_limit_index: int, current_index: int) -> bool:
    previous = _integer(last_limit_index, "last_limit_index")
    current = _integer(current_index, "current_index")
    if current < previous:
        raise RobotPartialFillError("current_index precedes last_limit_index")
    return current - previous >= REPRICE_CANDLES


def _topup_action_id(candidate_id: str, geometry_index: int, missing: Decimal) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0topup-limit\0{geometry_index}\0{missing.normalize()}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-topup-limit-{digest}")


def build_topup_limit(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    geometry_index: int,
    filled_wv: Decimal,
    tick_size: Decimal,
    rr: Decimal,
) -> TopUpLimitPlan:
    """Build one missing-volume top-up LIMIT at frozen boundary +/- two ticks."""

    if candidate.get("status") != "APPROVED":
        raise RobotPartialFillError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotPartialFillError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotPartialFillError("candidate identity and symbol are required")

    index = _integer(geometry_index, "geometry_index")
    apex_index = _integer(state.get("apex_index"), "apex_index")
    if index >= apex_index:
        raise RobotPartialFillError("top-up is forbidden at or after apex")
    if _decimal(rr, "rr", allow_zero=True) < MIN_RR:
        raise RobotPartialFillError("top-up requires whole-position RR >= 1")
    remainder = missing_wv(filled_wv)
    if remainder <= 0:
        raise RobotPartialFillError("no top-up volume remains")

    direction = str(state.get("direction", "")).strip().upper()
    tick = _decimal(tick_size, "tick_size")
    if direction == DIRECTION_LONG:
        side = OrderSide.BUY
        boundary_side = "upper"
        sign = Decimal("1")
    elif direction == DIRECTION_SHORT:
        side = OrderSide.SELL
        boundary_side = "lower"
        sign = Decimal("-1")
    else:
        raise RobotPartialFillError("unsupported Robot direction")

    frozen_boundary = _decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    raw_price = frozen_boundary + sign * tick * Decimal("2")
    if raw_price <= 0:
        raise RobotPartialFillError("top-up LIMIT price is not positive")
    price = normalize_limit_price(raw_price, tick, side)
    request = LimitCommandRequest(
        client_action_id=_topup_action_id(candidate_id, index, remainder),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, remainder),
        sizing_reference_price=price,
        limit_price=price,
        time_in_force=TimeInForce.GTC,
    )
    return TopUpLimitPlan(candidate_id, index, remainder, frozen_boundary, request)
