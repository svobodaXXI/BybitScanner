"""Robot v0.1 STOP/TAKE planning and protection-recovery policy.

Strategy policy lives here; exchange mutations remain owned by the shared PAPER
runtime. No mutation is blindly retried. STOP safety always has priority over
TAKE recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Any, Mapping, Protocol

from robot_state_machine import DIRECTION_LONG, DIRECTION_SHORT
from terminal.api.models import (
    ClientActionId,
    FullCloseCommandRequest,
    PaperStopMutationRequest,
)

MAX_STOP_DISTANCE = Decimal("0.02")
TAKE_REALIZATION = Decimal("0.90")
PROTECTION_DEADLINE_MS = 5_000

RECOVERY_PROTECTED = "PROTECTED"
RECOVERY_TAKE_ONLY = "TAKE_RECOVERY"
RECOVERY_WAIT = "WAIT_PROTECTION"
RECOVERY_EMERGENCY_CLOSE = "EMERGENCY_CLOSE"
RECOVERY_EMERGENCY_CLOSE_PENDING = "EMERGENCY_CLOSE_PENDING"
RECOVERY_CLOSED = "CLOSED_EMERGENCY_PROTECTION_FAILURE"


class RobotProtectionError(RuntimeError):
    pass


class ProtectionSubmitter(Protocol):
    def create_stop(self, request: PaperStopMutationRequest): ...
    def amend_stop(self, request: PaperStopMutationRequest): ...
    def create_take(self, request: PaperStopMutationRequest): ...
    def amend_take(self, request: PaperStopMutationRequest): ...
    def full_close(self, request: FullCloseCommandRequest): ...


@dataclass(frozen=True, slots=True)
class ProtectionPlan:
    candidate_id: str
    symbol: str
    direction: str
    stop_price: Decimal
    take_price: Decimal
    stop_request: PaperStopMutationRequest
    take_request: PaperStopMutationRequest


@dataclass(frozen=True, slots=True)
class ProtectionRecoveryDecision:
    action: str
    deadline_at_ms: int | None
    emergency_close_request: FullCloseCommandRequest | None = None


def _decimal(value: Any, field: str) -> Decimal:
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:
        raise RobotProtectionError(f"{field} must be decimal-compatible") from exc
    if not number.is_finite() or number <= 0:
        raise RobotProtectionError(f"{field} must be finite and positive")
    return number


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise RobotProtectionError(f"{field} must be an integer")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise RobotProtectionError(f"{field} must be an integer") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise RobotProtectionError(f"{field} must be an integer")
    return int(number)


def _action_id(candidate_id: str, leg: str, price: Decimal | None = None) -> ClientActionId:
    suffix = "" if price is None else f"\0{price.normalize()}"
    digest = hashlib.sha256(
        f"{candidate_id}\0{leg}{suffix}".encode("utf-8")
    ).hexdigest()[:32]
    return ClientActionId(f"robot-{leg}-{digest}")


def structural_stop(
    direction: str,
    *,
    average_entry: Decimal,
    structural_extreme: Decimal,
    tick_size: Decimal,
) -> Decimal:
    """Return structural STOP with a hard 2% distance fallback.

    LONG structural stop is one tick below the relevant low. SHORT is one tick
    above the relevant high. If that stop is farther than 2% from authoritative
    average entry, use exactly the 2% fallback instead.
    """

    entry = _decimal(average_entry, "average_entry")
    extreme = _decimal(structural_extreme, "structural_extreme")
    tick = _decimal(tick_size, "tick_size")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        candidate = extreme - tick
        if candidate <= 0 or candidate >= entry:
            raise RobotProtectionError("LONG structural STOP must be below entry")
        distance = (entry - candidate) / entry
        return entry * (Decimal("1") - MAX_STOP_DISTANCE) if distance > MAX_STOP_DISTANCE else candidate
    if normalized_direction == DIRECTION_SHORT:
        candidate = extreme + tick
        if candidate <= entry:
            raise RobotProtectionError("SHORT structural STOP must be above entry")
        distance = (candidate - entry) / entry
        return entry * (Decimal("1") + MAX_STOP_DISTANCE) if distance > MAX_STOP_DISTANCE else candidate
    raise RobotProtectionError("unsupported Robot direction")


def tighten_stop(direction: str, *, existing_stop: Decimal | None, proposed_stop: Decimal) -> Decimal:
    """Never widen STOP after averaging or top-up."""

    proposed = _decimal(proposed_stop, "proposed_stop")
    if existing_stop is None:
        return proposed
    existing = _decimal(existing_stop, "existing_stop")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        return max(existing, proposed)
    if normalized_direction == DIRECTION_SHORT:
        return min(existing, proposed)
    raise RobotProtectionError("unsupported Robot direction")


def frozen_take_90(
    direction: str,
    *,
    frozen_signal_reference_price: Decimal,
    frozen_scanner_target_price: Decimal,
) -> Decimal:
    """Freeze TAKE at 90% realization of Scanner's immutable signal potential."""

    reference = _decimal(frozen_signal_reference_price, "frozen_signal_reference_price")
    target = _decimal(frozen_scanner_target_price, "frozen_scanner_target_price")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        if target <= reference:
            raise RobotProtectionError("LONG Scanner target must be above signal reference")
        return reference + (target - reference) * TAKE_REALIZATION
    if normalized_direction == DIRECTION_SHORT:
        if target >= reference:
            raise RobotProtectionError("SHORT Scanner target must be below signal reference")
        return reference - (reference - target) * TAKE_REALIZATION
    raise RobotProtectionError("unsupported Robot direction")


def build_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    structural_extreme: Decimal,
    tick_size: Decimal,
    frozen_signal_reference_price: Decimal,
    frozen_scanner_target_price: Decimal,
    existing_stop: Decimal | None = None,
) -> ProtectionPlan:
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")

    proposed_stop = structural_stop(
        direction,
        average_entry=average_entry,
        structural_extreme=structural_extreme,
        tick_size=tick_size,
    )
    stop = tighten_stop(direction, existing_stop=existing_stop, proposed_stop=proposed_stop)
    take = frozen_take_90(
        direction,
        frozen_signal_reference_price=frozen_signal_reference_price,
        frozen_scanner_target_price=frozen_scanner_target_price,
    )
    entry = _decimal(average_entry, "average_entry")
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("LONG protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("SHORT protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop,
        take_price=take,
        stop_request=PaperStopMutationRequest(_action_id(candidate_id, "stop", stop), symbol, stop),
        take_request=PaperStopMutationRequest(_action_id(candidate_id, "take", take), symbol, take),
    )


def protection_recovery(
    candidate_id: str,
    symbol: str,
    *,
    position_open: bool,
    stop_proven: bool,
    take_proven: bool,
    protection_started_at_ms: int,
    now_ms: int,
    market_data_authoritative: bool,
    intended_stop_crossed: bool,
    emergency_close_in_flight: bool = False,
    authoritative_flat: bool = False,
) -> ProtectionRecoveryDecision:
    """Fail closed while a filled Robot position lacks proven STOP protection."""

    started = _integer(protection_started_at_ms, "protection_started_at_ms")
    now = _integer(now_ms, "now_ms")
    if now < started:
        raise RobotProtectionError("now_ms precedes protection start")
    deadline = started + PROTECTION_DEADLINE_MS

    if authoritative_flat:
        return ProtectionRecoveryDecision(RECOVERY_CLOSED, None)
    if not position_open:
        raise RobotProtectionError("non-flat recovery state requires open position")
    if stop_proven:
        return ProtectionRecoveryDecision(
            RECOVERY_PROTECTED if take_proven else RECOVERY_TAKE_ONLY,
            None,
        )
    if emergency_close_in_flight:
        return ProtectionRecoveryDecision(RECOVERY_EMERGENCY_CLOSE_PENDING, deadline)

    must_close = (
        not market_data_authoritative
        or intended_stop_crossed
        or now >= deadline
    )
    if must_close:
        request = FullCloseCommandRequest(
            _action_id(candidate_id, "emergency-protection-close"),
            symbol.strip().upper(),
        )
        return ProtectionRecoveryDecision(RECOVERY_EMERGENCY_CLOSE, deadline, request)
    return ProtectionRecoveryDecision(RECOVERY_WAIT, deadline)


def submit_initial_protection(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    """Submit STOP first, then TAKE once each; caller reconciles ambiguous results."""

    stop_result = submitter.create_stop(plan.stop_request)
    take_result = submitter.create_take(plan.take_request)
    return stop_result, take_result


def submit_stop_amend(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    return submitter.amend_stop(plan.stop_request)


def submit_take_amend(submitter: ProtectionSubmitter, plan: ProtectionPlan):
    return submitter.amend_take(plan.take_request)


def submit_emergency_close(submitter: ProtectionSubmitter, decision: ProtectionRecoveryDecision):
    if decision.action != RECOVERY_EMERGENCY_CLOSE or decision.emergency_close_request is None:
        raise RobotProtectionError("decision does not authorize emergency close")
    return submitter.full_close(decision.emergency_close_request)
