"""Robot v0.1 STOP/TAKE planning and protection-recovery policy.

Strategy policy lives here; exchange mutations remain owned by the shared PAPER
runtime. No mutation is blindly retried. STOP safety always has priority over
TAKE recovery.
"""

from __future__ import annotations

import robot_l_shape

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import os
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
# Minimum planned take/stop ratio for a new entry (retest LIMIT and late Market entry).
MIN_ENTRY_RR = Decimal("1.5")
MIN_ENTRY_RR_ENV = "ROBOT_MIN_ENTRY_RR"
MIN_ENTRY_RR_BOUNDS = (Decimal("0"), Decimal("10"))

RECOVERY_PROTECTED = "PROTECTED"
RECOVERY_TAKE_ONLY = "TAKE_RECOVERY"
RECOVERY_WAIT = "WAIT_PROTECTION"
RECOVERY_EMERGENCY_CLOSE = "EMERGENCY_CLOSE"
RECOVERY_EMERGENCY_CLOSE_PENDING = "EMERGENCY_CLOSE_PENDING"
RECOVERY_CLOSED = "CLOSED_EMERGENCY_PROTECTION_FAILURE"


class RobotProtectionError(RuntimeError):
    pass


def min_entry_rr() -> Decimal:
    """Retest-LIMIT entry threshold: ``ROBOT_MIN_ENTRY_RR`` when a valid Decimal in 0..10, else the default."""

    raw = os.environ.get(MIN_ENTRY_RR_ENV)
    if raw is None or not raw.strip():
        return MIN_ENTRY_RR
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return MIN_ENTRY_RR
    low, high = MIN_ENTRY_RR_BOUNDS
    return value if value.is_finite() and low <= value <= high else MIN_ENTRY_RR


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

    A filled Robot position must never end up with no STOP at all. The
    structural candidate is derived from the frozen signal geometry, but
    ``average_entry`` is the authoritative fill price read after entry --
    intervening price action (partial fills, top-ups, retest slippage) can
    leave the structural extreme on the wrong side of, or equal to, the
    actual entry. Rather than fail closed and leave a filled position with no
    protection at all (CR-PAPER-PROTECTION-LIFECYCLE-001 post-BATUSDT-defect
    fix), an invalid structural candidate falls back to the same 2% distance
    already used for a too-far structural stop, always on the safe side of
    entry.
    """

    entry = _decimal(average_entry, "average_entry")
    extreme = _decimal(structural_extreme, "structural_extreme")
    tick = _decimal(tick_size, "tick_size")
    normalized_direction = str(direction).strip().upper()
    if normalized_direction == DIRECTION_LONG:
        candidate = extreme - tick
        if candidate <= 0 or candidate >= entry:
            return entry * (Decimal("1") - MAX_STOP_DISTANCE)
        distance = (entry - candidate) / entry
        return entry * (Decimal("1") - MAX_STOP_DISTANCE) if distance > MAX_STOP_DISTANCE else candidate
    if normalized_direction == DIRECTION_SHORT:
        candidate = extreme + tick
        if candidate <= entry:
            return entry * (Decimal("1") + MAX_STOP_DISTANCE)
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


@dataclass(frozen=True, slots=True)
class BoxStopTerms:
    """Pure terms only; not an order, a fill proof, or execution approval."""

    price: Decimal
    quantity: Decimal


def prepare_box_stop_terms(
    snapshot: Mapping[str, Any], *,
    confirmed_position_quantity: Decimal,
    confirmed_average_entry: Decimal,
) -> BoxStopTerms:
    """Read the frozen Box STOP and size it to externally confirmed exposure.

    The caller must independently prove fill, position ownership and protection
    authorization. This function cannot submit orders or promote BOX_PLAN_ONLY.
    """
    if (snapshot.get("pattern") != "IKIGAI_BOX"
            or snapshot.get("environment") != "PAPER"
            or snapshot.get("execution_authorized") is not False
            or snapshot.get("attempt") != 1):
        raise RobotProtectionError("a non-executable first-attempt PAPER Box snapshot is required")
    plan = snapshot.get("plan")
    if not isinstance(plan, Mapping):
        raise RobotProtectionError("Box plan is missing")
    direction = plan.get("direction")
    if direction not in (DIRECTION_LONG, DIRECTION_SHORT):
        raise RobotProtectionError("Box direction is invalid")
    prices = plan.get("limit_prices")
    quantities = plan.get("limit_quantities")
    if (not isinstance(prices, (tuple, list)) or len(prices) != 4
            or not isinstance(quantities, (tuple, list)) or len(quantities) != 4):
        raise RobotProtectionError("Box grid must contain four entries")
    levels = tuple(_decimal(price, "Box LIMIT price") for price in prices)
    sizes = tuple(_decimal(qty, "Box LIMIT quantity") for qty in quantities)
    if any(size != sizes[0] for size in sizes):
        raise RobotProtectionError("Box entry quantities must be equal")
    stop = _decimal(plan.get("stop_price"), "frozen Box STOP")
    quantity = _decimal(confirmed_position_quantity, "confirmed position quantity")
    entry = _decimal(confirmed_average_entry, "confirmed average entry")
    if quantity > sum(sizes):
        raise RobotProtectionError("confirmed exposure exceeds the approved Box grid")
    if direction == DIRECTION_LONG:
        if not (stop < levels[3] < levels[2] < levels[1] < levels[0] and stop < entry):
            raise RobotProtectionError("LONG Box STOP is not beyond P4 and actual entry")
    elif not (stop > levels[3] > levels[2] > levels[1] > levels[0] and stop > entry):
        raise RobotProtectionError("SHORT Box STOP is not beyond P4 and actual entry")
    return BoxStopTerms(stop, quantity)


def build_box_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
    confirmed_position_quantity: Decimal,
) -> ProtectionPlan:
    """Build shared Robot protection requests from immutable Box terms."""
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("identity", {}).get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")
    if direction != str(snapshot.get("plan", {}).get("direction", "")).strip().upper():
        raise RobotProtectionError("Box direction conflicts with frozen plan")

    stop_terms = prepare_box_stop_terms(
        snapshot,
        confirmed_position_quantity=confirmed_position_quantity,
        confirmed_average_entry=average_entry,
    )
    take = _decimal(snapshot["plan"].get("take_price"), "frozen Box TAKE")
    entry = _decimal(average_entry, "average_entry")
    if direction == DIRECTION_LONG and not (stop_terms.price < entry < take):
        raise RobotProtectionError("LONG Box protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop_terms.price):
        raise RobotProtectionError("SHORT Box protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop_terms.price,
        take_price=take,
        stop_request=PaperStopMutationRequest(
            _action_id(candidate_id, "stop", stop_terms.price), symbol, stop_terms.price,
        ),
        take_request=PaperStopMutationRequest(
            _action_id(candidate_id, "take", take), symbol, take,
        ),
    )



def build_l_shape_protection_plan(
    candidate: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    average_entry: Decimal,
) -> ProtectionPlan:
    """Build shared protection requests from immutable L-shape STOP/target terms."""
    if candidate.get("status") != "APPROVED":
        raise RobotProtectionError("candidate must be APPROVED")
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, Mapping):
        raise RobotProtectionError("signal snapshot is missing")
    try:
        terms = robot_l_shape.frozen_terms(snapshot)
    except robot_l_shape.RobotLShapeError as exc:
        raise RobotProtectionError(str(exc)) from exc

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    symbol = str(snapshot.get("symbol", "")).strip().upper()
    direction = str(state.get("direction", "")).strip().upper()
    if not candidate_id or not symbol:
        raise RobotProtectionError("candidate identity and symbol are required")
    if direction != terms.direction:
        raise RobotProtectionError("L-shape direction conflicts with frozen terms")

    entry = _decimal(average_entry, "average_entry")
    stop = terms.stop
    take = terms.target
    if direction == DIRECTION_LONG and not (stop < entry < take):
        raise RobotProtectionError("LONG L-shape protection geometry is invalid")
    if direction == DIRECTION_SHORT and not (take < entry < stop):
        raise RobotProtectionError("SHORT L-shape protection geometry is invalid")

    return ProtectionPlan(
        candidate_id=candidate_id,
        symbol=symbol,
        direction=direction,
        stop_price=stop,
        take_price=take,
        stop_request=PaperStopMutationRequest(
            _action_id(candidate_id, "stop", stop), symbol, stop,
        ),
        take_request=PaperStopMutationRequest(
            _action_id(candidate_id, "take", take), symbol, take,
        ),
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


def emergency_close_request(candidate_id: str, symbol: str) -> FullCloseCommandRequest:
    """Build the emergency full-close request for a filled Robot position whose
    initial protection could not be built, validated, or submitted.

    Uses the exact same deterministic action-id scheme as
    ``protection_recovery()``'s own emergency close, so a later recovery-path
    close attempt for the same candidate is idempotent with this one rather
    than a distinct action.
    """

    return FullCloseCommandRequest(
        _action_id(candidate_id, "emergency-protection-close"), symbol.strip().upper(),
    )
