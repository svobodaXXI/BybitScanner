"""Robot v0.1 initial retest LIMIT orchestration over shared Terminal contracts.

This module does not execute or persist orders itself. It builds one deterministic
PAPER LIMIT command for a confirmed retest and hands that command to the existing
runtime ``create_limit`` capability exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping, Protocol

from robot_state_machine import (
    DIRECTION_LONG,
    DIRECTION_SHORT,
    PHASE_RETEST_DETECTED,
    boundary_price,
)
from terminal.api.models import (
    ClientActionId,
    LimitCommandRequest,
    PaperLimitAmendRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
)
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide


class RobotEntryLimitError(RuntimeError):
    """Raised when an initial retest LIMIT cannot be built safely."""


class PaperLimitSubmitter(Protocol):
    def create_limit(self, request: LimitCommandRequest): ...
    def amend_limit(self, request: PaperLimitAmendRequest): ...


REPRICE_CANDLES = 5


@dataclass(frozen=True, slots=True)
class InitialRetestLimitPlan:
    candidate_id: str
    direction: str
    retest_index: int
    boundary_price: Decimal
    request: LimitCommandRequest


@dataclass(frozen=True, slots=True)
class RetestLimitRepricePlan:
    candidate_id: str
    geometry_index: int
    boundary_price: Decimal
    request: PaperLimitAmendRequest


def _positive_decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotEntryLimitError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotEntryLimitError(f"{field} must be finite and positive")
    return number


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotEntryLimitError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotEntryLimitError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotEntryLimitError(f"{field} must be an integer")
    return int(number)


def _stable_client_action_id(candidate_id: str, retest_index: int) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0initial-retest-limit\0{retest_index}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-retest-limit-{digest}")


def _stable_reprice_action_id(
    candidate_id: str, order_id: str, geometry_index: int,
) -> ClientActionId:
    digest = hashlib.sha256(
        (
            f"{candidate_id}\0retest-limit-reprice\0"
            f"{order_id}\0{geometry_index}"
        ).encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-retest-reprice-{digest}")


def reprice_due(*, last_limit_index: int, current_index: int) -> bool:
    previous = _required_int(last_limit_index, "last_limit_index")
    current = _required_int(current_index, "current_index")
    if current < previous:
        raise RobotEntryLimitError("current_index precedes last_limit_index")
    return current - previous >= REPRICE_CANDLES


def _entry_side_and_price(
    snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    geometry_index: int,
    tick_size: Decimal,
) -> tuple[OrderSide, Decimal]:
    direction = str(state.get("direction", "")).strip().upper()
    if direction == DIRECTION_LONG:
        side = OrderSide.BUY
        boundary_side = "upper"
        offset_sign = Decimal("1")
        expected_pattern = "Falling Wedge"
    elif direction == DIRECTION_SHORT:
        side = OrderSide.SELL
        boundary_side = "lower"
        offset_sign = Decimal("-1")
        expected_pattern = "Rising Wedge"
    else:
        raise RobotEntryLimitError("unsupported Robot direction")
    if str(snapshot.get("pattern", "")).strip() != expected_pattern:
        raise RobotEntryLimitError("state direction differs from frozen pattern")

    index = _required_int(geometry_index, "geometry_index")
    tick = _positive_decimal(tick_size, "tick_size")
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    raw_limit_price = frozen_boundary + offset_sign * tick * Decimal("2")
    if raw_limit_price <= 0:
        raise RobotEntryLimitError("aggressive LIMIT price is not positive")
    return side, normalize_limit_price(raw_limit_price, tick, side)


def build_initial_retest_limit(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    tick_size: Decimal,
) -> InitialRetestLimitPlan:
    """Build the single initial 1 WV LIMIT created after retest detection.

    The frozen Scanner boundary is evaluated at the retest candle index. The
    requested price is two ticks through that boundary in the aggressive entry
    direction, then normalized with the shared Terminal price normalizer.
    """

    if not isinstance(candidate, Mapping):
        raise RobotEntryLimitError("candidate must be a mapping")
    if not isinstance(state, Mapping):
        raise RobotEntryLimitError("state must be a mapping")
    if candidate.get("status") != "APPROVED":
        raise RobotEntryLimitError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotEntryLimitError("initial retest LIMIT requires 1m candidate")
    if state.get("phase") != PHASE_RETEST_DETECTED:
        raise RobotEntryLimitError("initial retest LIMIT requires RETEST_DETECTED")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    if not candidate_id:
        raise RobotEntryLimitError("candidate_id is required")

    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotEntryLimitError("signal snapshot is missing")
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    if not symbol:
        raise RobotEntryLimitError("signal snapshot has no symbol")

    direction = str(state.get("direction", "")).strip().upper()
    retest_index = _required_int(state.get("retest_index"), "retest_index")
    breakout_index = _required_int(state.get("breakout_index"), "breakout_index")
    if retest_index <= breakout_index:
        raise RobotEntryLimitError("retest must occur after breakout")

    side, normalized_limit_price = _entry_side_and_price(
        snapshot,
        state,
        geometry_index=retest_index,
        tick_size=tick_size,
    )
    boundary_side = "upper" if direction == DIRECTION_LONG else "lower"
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=retest_index),
        "frozen boundary price",
    )

    request = LimitCommandRequest(
        client_action_id=_stable_client_action_id(candidate_id, retest_index),
        symbol=symbol,
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=normalized_limit_price,
        limit_price=normalized_limit_price,
        time_in_force=TimeInForce.GTC,
    )
    return InitialRetestLimitPlan(
        candidate_id=candidate_id,
        direction=direction,
        retest_index=retest_index,
        boundary_price=frozen_boundary,
        request=request,
    )


def build_retest_limit_reprice(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    geometry_index: int,
    tick_size: Decimal,
    order_id: str,
) -> RetestLimitRepricePlan:
    """Amend the still-unfilled entry LIMIT to the current frozen boundary."""

    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise RobotEntryLimitError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotEntryLimitError("retest LIMIT reprice requires 1m candidate")
    if not isinstance(state, Mapping) or state.get("phase") != PHASE_RETEST_DETECTED:
        raise RobotEntryLimitError("retest LIMIT reprice requires RETEST_DETECTED")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    snapshot = candidate.get("signal_snapshot")
    normalized_order_id = str(order_id).strip()
    if not candidate_id or not isinstance(snapshot, Mapping) or not normalized_order_id:
        raise RobotEntryLimitError("candidate identity, snapshot and order_id are required")

    index = _required_int(geometry_index, "geometry_index")
    geometry = snapshot.get("geometry")
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    if not isinstance(apex, Mapping):
        raise RobotEntryLimitError("signal snapshot has no frozen apex")
    apex_index = _required_int(apex.get("index"), "apex_index")
    if index >= apex_index:
        raise RobotEntryLimitError("reprice is forbidden at or after apex")

    _side, price = _entry_side_and_price(
        snapshot,
        state,
        geometry_index=index,
        tick_size=tick_size,
    )
    boundary_side = (
        "upper"
        if str(state.get("direction", "")).strip().upper() == DIRECTION_LONG
        else "lower"
    )
    frozen_boundary = _positive_decimal(
        boundary_price(snapshot, side=boundary_side, geometry_index=index),
        "frozen boundary price",
    )
    return RetestLimitRepricePlan(
        candidate_id=candidate_id,
        geometry_index=index,
        boundary_price=frozen_boundary,
        request=PaperLimitAmendRequest(
            client_action_id=_stable_reprice_action_id(
                candidate_id, normalized_order_id, index,
            ),
            symbol=str(snapshot.get("symbol", "")).strip().upper(),
            order_id=normalized_order_id,
            limit_price=price,
        ),
    )


def submit_retest_limit_reprice(
    submitter: PaperLimitSubmitter,
    plan: RetestLimitRepricePlan,
):
    return submitter.amend_limit(plan.request)


def submit_initial_retest_limit(
    submitter: PaperLimitSubmitter,
    plan: InitialRetestLimitPlan,
):
    """Submit exactly once through the shared PAPER LIMIT capability.

    No retry or fallback is performed here. Transport ambiguity remains owned by
    the shared execution lifecycle and later Robot reconciliation slices.
    """

    return submitter.create_limit(plan.request)
