"""Pure Robot v0.1 breakout/retest lifecycle over frozen Scanner geometry.

This module consumes already-approved immutable Scanner snapshots and closed 1m
candles expressed in the frozen geometry index space. It never refits geometry
and performs no order execution, sizing, STOP/TAKE, or market-data transport.
"""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any, Mapping


STATE_VERSION = "1.0"
PHASE_WAITING_BREAKOUT = "WAITING_BREAKOUT"
PHASE_WAITING_RETEST = "WAITING_RETEST"
PHASE_RETEST_DETECTED = "RETEST_DETECTED"
PHASE_EXPIRED_AT_APEX = "EXPIRED_AT_APEX"

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"

EVENT_INITIALIZED = "INITIALIZED"
EVENT_NO_TRANSITION = "NO_TRANSITION"
EVENT_BREAKOUT = "BREAKOUT"
EVENT_RETEST = "RETEST"
EVENT_EXPIRED_AT_APEX = "EXPIRED_AT_APEX"
EVENT_IGNORED_STALE = "IGNORED_STALE_CANDLE"
EVENT_RESUMED_WITHOUT_REPLAY = "RESUMED_WITHOUT_REPLAY"
EVENT_TERMINAL = "TERMINAL_STATE"

_PATTERN_DIRECTION = {
    "Falling Wedge": DIRECTION_LONG,
    "Rising Wedge": DIRECTION_SHORT,
}
_TERMINAL_PHASES = {
    PHASE_RETEST_DETECTED,
    PHASE_EXPIRED_AT_APEX,
}


class RobotStateMachineError(RuntimeError):
    """Raised when lifecycle input cannot be trusted."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise RobotStateMachineError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RobotStateMachineError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise RobotStateMachineError(f"{field} must be finite")
    return number


def _geometry_index(value: Any, field: str = "geometry_index") -> int:
    number = _finite_number(value, field)
    if not number.is_integer():
        raise RobotStateMachineError(f"{field} must be an integer index")
    return int(number)


def _snapshot_geometry(signal_snapshot: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(signal_snapshot, Mapping):
        raise RobotStateMachineError("signal snapshot must be a mapping")

    pattern = str(signal_snapshot.get("pattern", "")).strip()
    if pattern not in _PATTERN_DIRECTION:
        raise RobotStateMachineError(f"unsupported Robot v0.1 pattern: {pattern!r}")

    geometry = signal_snapshot.get("geometry")
    if not isinstance(geometry, Mapping):
        raise RobotStateMachineError("signal snapshot has no frozen geometry")

    upper = geometry.get("upper_line")
    lower = geometry.get("lower_line")
    apex = geometry.get("apex")
    if not isinstance(upper, Mapping) or not isinstance(lower, Mapping):
        raise RobotStateMachineError("frozen boundary lines are missing")
    if not isinstance(apex, Mapping):
        raise RobotStateMachineError("frozen apex is missing")

    if apex.get("valid_intersection") is False:
        raise RobotStateMachineError("frozen apex is not a valid intersection")

    return {
        "pattern": pattern,
        "direction": _PATTERN_DIRECTION[pattern],
        "upper_slope": _finite_number(upper.get("slope"), "upper_line.slope"),
        "upper_intercept": _finite_number(
            upper.get("intercept"), "upper_line.intercept"
        ),
        "lower_slope": _finite_number(lower.get("slope"), "lower_line.slope"),
        "lower_intercept": _finite_number(
            lower.get("intercept"), "lower_line.intercept"
        ),
        "apex_index": _finite_number(apex.get("index"), "apex.index"),
        "current_index": _geometry_index(
            geometry.get("current_index"), "geometry.current_index"
        ),
    }


def boundary_price(
    signal_snapshot: Mapping[str, Any],
    *,
    side: str,
    geometry_index: int,
) -> float:
    """Evaluate one frozen Scanner line at a future geometry index."""

    frozen = _snapshot_geometry(signal_snapshot)
    index = _geometry_index(geometry_index)
    if side == "upper":
        return frozen["upper_slope"] * index + frozen["upper_intercept"]
    if side == "lower":
        return frozen["lower_slope"] * index + frozen["lower_intercept"]
    raise RobotStateMachineError(f"unknown boundary side: {side!r}")


def initialize_state(
    candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Create lifecycle state for one approved immutable candidate."""

    if not isinstance(candidate, Mapping):
        raise RobotStateMachineError("candidate must be a mapping")
    if candidate.get("status") != "APPROVED":
        raise RobotStateMachineError("candidate must be APPROVED")
    if str(candidate.get("timeframe", "")).strip() != "1":
        raise RobotStateMachineError("Robot v0.1 breakout lifecycle requires 1m signal")

    snapshot = candidate.get("signal_snapshot")
    frozen = _snapshot_geometry(snapshot)
    current_index = frozen["current_index"]

    phase = PHASE_WAITING_BREAKOUT
    last_event = EVENT_INITIALIZED
    if current_index >= frozen["apex_index"]:
        phase = PHASE_EXPIRED_AT_APEX
        last_event = EVENT_EXPIRED_AT_APEX

    return {
        "state_version": STATE_VERSION,
        "phase": phase,
        "pattern": frozen["pattern"],
        "direction": frozen["direction"],
        "geometry_cursor": current_index,
        "breakout_index": None,
        "retest_index": None,
        "last_event": last_event,
    }, last_event


def _validate_state(signal_snapshot: Mapping[str, Any], state: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(state, Mapping):
        raise RobotStateMachineError("state must be a mapping")
    if state.get("state_version") != STATE_VERSION:
        raise RobotStateMachineError("unsupported Robot state version")

    frozen = _snapshot_geometry(signal_snapshot)
    if state.get("pattern") != frozen["pattern"]:
        raise RobotStateMachineError("state pattern differs from frozen snapshot")
    if state.get("direction") != frozen["direction"]:
        raise RobotStateMachineError("state direction differs from frozen snapshot")

    phase = state.get("phase")
    if phase not in {
        PHASE_WAITING_BREAKOUT,
        PHASE_WAITING_RETEST,
        PHASE_RETEST_DETECTED,
        PHASE_EXPIRED_AT_APEX,
    }:
        raise RobotStateMachineError("invalid Robot lifecycle phase")

    _geometry_index(state.get("geometry_cursor"), "state.geometry_cursor")
    return frozen


def process_closed_candle(
    signal_snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    candle: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Advance the lifecycle by exactly one authoritative closed 1m candle.

    ``geometry_index`` must be expressed in the same index space as the frozen
    Scanner GeometryModel. Older/replayed candles are ignored idempotently.
    """

    frozen = _validate_state(signal_snapshot, state)
    if not isinstance(candle, Mapping):
        raise RobotStateMachineError("candle must be a mapping")
    if candle.get("closed") is not True:
        raise RobotStateMachineError("only authoritative closed candles are accepted")
    if str(candle.get("timeframe", "")).strip() != "1":
        raise RobotStateMachineError("only 1m candles are accepted")

    new_state = deepcopy(dict(state))
    if new_state["phase"] in _TERMINAL_PHASES:
        return new_state, EVENT_TERMINAL

    index = _geometry_index(candle.get("geometry_index"))
    cursor = _geometry_index(new_state.get("geometry_cursor"), "state.geometry_cursor")
    if index <= cursor:
        return new_state, EVENT_IGNORED_STALE

    high = _finite_number(candle.get("high"), "candle.high")
    low = _finite_number(candle.get("low"), "candle.low")
    close = _finite_number(candle.get("close"), "candle.close")
    if low > high:
        raise RobotStateMachineError("candle low exceeds high")

    new_state["geometry_cursor"] = index

    if index >= frozen["apex_index"]:
        new_state["phase"] = PHASE_EXPIRED_AT_APEX
        new_state["last_event"] = EVENT_EXPIRED_AT_APEX
        return new_state, EVENT_EXPIRED_AT_APEX

    if new_state["phase"] == PHASE_WAITING_BREAKOUT:
        boundary_side = "upper" if frozen["direction"] == DIRECTION_LONG else "lower"
        boundary = boundary_price(
            signal_snapshot,
            side=boundary_side,
            geometry_index=index,
        )
        broke_out = (
            close > boundary
            if frozen["direction"] == DIRECTION_LONG
            else close < boundary
        )
        if broke_out:
            new_state["phase"] = PHASE_WAITING_RETEST
            new_state["breakout_index"] = index
            new_state["last_event"] = EVENT_BREAKOUT
            return new_state, EVENT_BREAKOUT

        new_state["last_event"] = EVENT_NO_TRANSITION
        return new_state, EVENT_NO_TRANSITION

    if new_state["phase"] == PHASE_WAITING_RETEST:
        boundary_side = "upper" if frozen["direction"] == DIRECTION_LONG else "lower"
        boundary = boundary_price(
            signal_snapshot,
            side=boundary_side,
            geometry_index=index,
        )
        touched = (
            low <= boundary
            if frozen["direction"] == DIRECTION_LONG
            else high >= boundary
        )
        if touched:
            new_state["phase"] = PHASE_RETEST_DETECTED
            new_state["retest_index"] = index
            new_state["last_event"] = EVENT_RETEST
            return new_state, EVENT_RETEST

        new_state["last_event"] = EVENT_NO_TRANSITION
        return new_state, EVENT_NO_TRANSITION

    raise RobotStateMachineError("unreachable Robot lifecycle phase")


def resume_without_replay(
    signal_snapshot: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    latest_geometry_index: int,
) -> tuple[dict[str, Any], str]:
    """Advance the cursor after downtime without evaluating missed candles."""

    frozen = _validate_state(signal_snapshot, state)
    new_state = deepcopy(dict(state))
    if new_state["phase"] in _TERMINAL_PHASES:
        return new_state, EVENT_TERMINAL

    latest = _geometry_index(latest_geometry_index, "latest_geometry_index")
    cursor = _geometry_index(new_state["geometry_cursor"], "state.geometry_cursor")
    if latest < cursor:
        raise RobotStateMachineError("resume cursor cannot move backwards")
    if latest == cursor:
        return new_state, EVENT_IGNORED_STALE

    new_state["geometry_cursor"] = latest
    if latest >= frozen["apex_index"]:
        new_state["phase"] = PHASE_EXPIRED_AT_APEX
        new_state["last_event"] = EVENT_EXPIRED_AT_APEX
        return new_state, EVENT_EXPIRED_AT_APEX

    new_state["last_event"] = EVENT_RESUMED_WITHOUT_REPLAY
    return new_state, EVENT_RESUMED_WITHOUT_REPLAY
