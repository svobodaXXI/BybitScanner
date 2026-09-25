"""L-shape Robot policy adapter over the shared PAPER execution lifecycle.

The L-shape detector has no Wedge apex or pair of sloping boundaries.  This
module therefore owns only the pattern-specific frozen contract, horizontal
retest transition and initial 1-WV LIMIT construction.  Order execution,
fill/position ownership proof, protection submission, durable trades and
recovery remain owned by the existing shared Robot components.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping

from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT, PHASE_RETEST_DETECTED
from terminal.api.models import (
    ClientActionId,
    LimitCommandRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
)
from terminal.application.normalization import normalize_limit_price
from terminal.domain.models import OrderSide


PATTERN = "L-shape"
STATE_VERSION = "1.0"
PHASE_WAITING_RETEST = "L_SHAPE_WAITING_RETEST"
PHASE_INVALIDATED = "L_SHAPE_INVALIDATED"

EVENT_INITIALIZED = "L_SHAPE_INITIALIZED"
EVENT_NO_TRANSITION = "L_SHAPE_NO_TRANSITION"
EVENT_RETEST = "L_SHAPE_RETEST"
EVENT_INVALIDATED_TARGET = "L_SHAPE_TARGET_REACHED_BEFORE_ENTRY"
EVENT_INVALIDATED_STOP = "L_SHAPE_STOP_REACHED_BEFORE_ENTRY"
EVENT_INVALIDATED_BOTH = "L_SHAPE_STOP_AND_TARGET_REACHED_BEFORE_ENTRY"
EVENT_IGNORED_STALE = "L_SHAPE_IGNORED_STALE_CANDLE"
EVENT_TERMINAL = "L_SHAPE_TERMINAL_STATE"

MIN_POTENTIAL_PERCENT = Decimal("0.8")
MIN_REWARD_RISK = Decimal("2")


class RobotLShapeError(RuntimeError):
    """Raised when frozen L-shape Robot inputs cannot be trusted."""


@dataclass(frozen=True, slots=True)
class FrozenLShapeTerms:
    direction: str
    source_timeframe: str
    breakout_time_ms: int
    reference: Decimal
    target: Decimal
    stop: Decimal
    structural_stop: Decimal
    stop_kind: str
    potential_percent: Decimal
    reward_risk: Decimal


@dataclass(frozen=True, slots=True)
class LShapeEntryPlan:
    candidate_id: str
    direction: str
    retest_time_ms: int
    boundary_price: Decimal
    request: LimitCommandRequest


def is_l_shape_snapshot(snapshot: Mapping[str, Any] | None) -> bool:
    return isinstance(snapshot, Mapping) and str(snapshot.get("pattern", "")).strip() == PATTERN


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotLShapeError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotLShapeError(f"{field} must be finite and positive")
    return number


def _timestamp(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotLShapeError(f"{field} must be a non-negative integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotLShapeError(f"{field} must be a non-negative integer") from exc
    if (
        not number.is_finite()
        or number != number.to_integral_value()
        or number < 0
    ):
        raise RobotLShapeError(f"{field} must be a non-negative integer")
    return int(number)


def frozen_terms(snapshot: Mapping[str, Any]) -> FrozenLShapeTerms:
    if not is_l_shape_snapshot(snapshot):
        raise RobotLShapeError("snapshot is not L-shape")
    terms = snapshot.get("l_shape")
    if not isinstance(terms, Mapping):
        raise RobotLShapeError("L-shape frozen terms are missing")

    direction = str(terms.get("direction", "")).strip().upper()
    if direction not in {DIRECTION_LONG, DIRECTION_SHORT}:
        raise RobotLShapeError("L-shape direction is invalid")
    source_timeframe = str(terms.get("source_timeframe", "")).strip()
    if not source_timeframe.isdecimal() or int(source_timeframe) <= 0:
        raise RobotLShapeError("L-shape source timeframe is invalid")

    reference = _decimal(terms.get("reference"), "L-shape reference")
    target = _decimal(terms.get("target"), "L-shape target")
    stop = _decimal(terms.get("stop"), "L-shape stop")
    structural_stop = _decimal(
        terms.get("structural_stop"), "L-shape structural_stop"
    )
    potential = _decimal(
        terms.get("potential_percent"), "L-shape potential_percent"
    )
    reward_risk = _decimal(terms.get("reward_risk"), "L-shape reward_risk")
    stop_kind = str(terms.get("stop_kind", "")).strip()
    if not stop_kind:
        raise RobotLShapeError("L-shape stop_kind is missing")

    if direction == DIRECTION_LONG:
        if not (stop < reference < target):
            raise RobotLShapeError("LONG L-shape frozen price geometry is invalid")
    elif not (target < reference < stop):
        raise RobotLShapeError("SHORT L-shape frozen price geometry is invalid")

    if potential < MIN_POTENTIAL_PERCENT:
        raise RobotLShapeError("L-shape potential is below 0.8%")
    if reward_risk < MIN_REWARD_RISK:
        raise RobotLShapeError("L-shape frozen reward/risk is below 2:1")

    return FrozenLShapeTerms(
        direction=direction,
        source_timeframe=source_timeframe,
        breakout_time_ms=_timestamp(
            terms.get("breakout_time_ms"), "L-shape breakout_time_ms"
        ),
        reference=reference,
        target=target,
        stop=stop,
        structural_stop=structural_stop,
        stop_kind=stop_kind,
        potential_percent=potential,
        reward_risk=reward_risk,
    )


def initialize_state(candidate: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise RobotLShapeError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotLShapeError("signal snapshot is missing")
    terms = frozen_terms(snapshot)
    return {
        "state_version": STATE_VERSION,
        "phase": PHASE_WAITING_RETEST,
        "pattern": PATTERN,
        "direction": terms.direction,
        "last_candle_time_ms": terms.breakout_time_ms,
        "breakout_time_ms": terms.breakout_time_ms,
        "retest_time_ms": None,
        "last_event": EVENT_INITIALIZED,
    }, EVENT_INITIALIZED


def _validate_state(snapshot: Mapping[str, Any], state: Mapping[str, Any]) -> FrozenLShapeTerms:
    if not isinstance(state, Mapping):
        raise RobotLShapeError("L-shape Robot state must be a mapping")
    if state.get("state_version") != STATE_VERSION:
        raise RobotLShapeError("unsupported L-shape Robot state version")
    terms = frozen_terms(snapshot)
    if state.get("pattern") != PATTERN or state.get("direction") != terms.direction:
        raise RobotLShapeError("L-shape state differs from frozen snapshot")
    if state.get("phase") not in {
        PHASE_WAITING_RETEST,
        PHASE_RETEST_DETECTED,
        PHASE_INVALIDATED,
    }:
        raise RobotLShapeError("invalid L-shape Robot phase")
    _timestamp(state.get("last_candle_time_ms"), "state.last_candle_time_ms")
    return terms


def invalidation_event(
    snapshot: Mapping[str, Any], candle: Mapping[str, Any],
) -> str | None:
    terms = frozen_terms(snapshot)
    if not isinstance(candle, Mapping):
        raise RobotLShapeError("closed candle must be a mapping")
    high = _decimal(candle.get("high"), "candle.high")
    low = _decimal(candle.get("low"), "candle.low")
    if low > high:
        raise RobotLShapeError("candle low exceeds high")

    target_hit = (
        high >= terms.target
        if terms.direction == DIRECTION_LONG
        else low <= terms.target
    )
    stop_hit = (
        low <= terms.stop
        if terms.direction == DIRECTION_LONG
        else high >= terms.stop
    )
    if target_hit and stop_hit:
        return EVENT_INVALIDATED_BOTH
    if target_hit:
        return EVENT_INVALIDATED_TARGET
    if stop_hit:
        return EVENT_INVALIDATED_STOP
    return None


def process_closed_candle(
    snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    candle: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    terms = _validate_state(snapshot, state)
    new_state = deepcopy(dict(state))
    if new_state["phase"] in {PHASE_RETEST_DETECTED, PHASE_INVALIDATED}:
        return new_state, EVENT_TERMINAL
    if not isinstance(candle, Mapping):
        raise RobotLShapeError("closed candle must be a mapping")

    time_ms = _timestamp(candle.get("time_ms"), "candle.time_ms")
    cursor = _timestamp(
        new_state.get("last_candle_time_ms"), "state.last_candle_time_ms"
    )
    if time_ms <= cursor:
        return new_state, EVENT_IGNORED_STALE

    high = _decimal(candle.get("high"), "candle.high")
    low = _decimal(candle.get("low"), "candle.low")
    if low > high:
        raise RobotLShapeError("candle low exceeds high")
    new_state["last_candle_time_ms"] = time_ms

    invalidated = invalidation_event(snapshot, candle)
    if invalidated is not None:
        new_state["phase"] = PHASE_INVALIDATED
        new_state["last_event"] = invalidated
        return new_state, invalidated

    touched = (
        low <= terms.reference
        if terms.direction == DIRECTION_LONG
        else high >= terms.reference
    )
    if touched:
        new_state["phase"] = PHASE_RETEST_DETECTED
        new_state["retest_time_ms"] = time_ms
        new_state["last_event"] = EVENT_RETEST
        return new_state, EVENT_RETEST

    new_state["last_event"] = EVENT_NO_TRANSITION
    return new_state, EVENT_NO_TRANSITION


def _stable_entry_action_id(candidate_id: str, retest_time_ms: int) -> ClientActionId:
    digest = hashlib.sha256(
        f"{candidate_id}\0l-shape-retest-limit\0{retest_time_ms}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-lshape-limit-{digest}")


def build_initial_retest_limit(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    tick_size: Decimal,
) -> LShapeEntryPlan:
    if not isinstance(candidate, Mapping) or candidate.get("status") != "APPROVED":
        raise RobotLShapeError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotLShapeError("signal snapshot is missing")
    terms = _validate_state(snapshot, state)
    if state.get("phase") != PHASE_RETEST_DETECTED:
        raise RobotLShapeError("L-shape entry requires RETEST_DETECTED")

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    if not candidate_id:
        raise RobotLShapeError("candidate_id is required")
    retest_time_ms = _timestamp(state.get("retest_time_ms"), "state.retest_time_ms")
    tick = _decimal(tick_size, "tick_size")

    if terms.direction == DIRECTION_LONG:
        side = OrderSide.BUY
        raw_price = terms.reference + tick * Decimal("2")
    else:
        side = OrderSide.SELL
        raw_price = terms.reference - tick * Decimal("2")
    if raw_price <= 0:
        raise RobotLShapeError("L-shape LIMIT price is not positive")
    limit_price = normalize_limit_price(raw_price, tick, side)

    request = LimitCommandRequest(
        client_action_id=_stable_entry_action_id(candidate_id, retest_time_ms),
        symbol=str(snapshot.get("symbol", "")).strip().upper(),
        side=side,
        volume=VolumeRequest(VolumeUnit.WORKING_VOLUME, Decimal("1")),
        sizing_reference_price=limit_price,
        limit_price=limit_price,
        time_in_force=TimeInForce.GTC,
    )
    if not request.symbol:
        raise RobotLShapeError("L-shape signal snapshot has no symbol")
    return LShapeEntryPlan(
        candidate_id=candidate_id,
        direction=terms.direction,
        retest_time_ms=retest_time_ms,
        boundary_price=terms.reference,
        request=request,
    )
