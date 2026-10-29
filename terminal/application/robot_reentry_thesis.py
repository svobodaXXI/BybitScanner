"""Conservative structural/lineage evidence for post-STOP cross-pattern retries.

No symbol-only or direction-only campaign inheritance. A previous STOP
candidate's *canonical immutable* snapshot hash and identity must be
explicitly cited by the new signal, and both independently frozen patterns
must have compatible directional price corridors. This is an admission
precondition, not a claim of profitability and not a pattern detector.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import robot_l_shape
import robot_state_machine


@dataclass(frozen=True, slots=True)
class FrozenCorridor:
    direction: str
    low: Decimal
    high: Decimal
    reference: Decimal


def _positive_number(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("unproven price")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("unproven price") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError("unproven price")
    return number


def frozen_corridor(snapshot: Mapping[str, Any]) -> FrozenCorridor | None:
    """Only immutable, strategy-recognized values, never live ticker prices."""
    if not isinstance(snapshot, Mapping):
        return None
    try:
        pattern = snapshot.get("pattern")
        if pattern in {"MIRROR", "L-shape"}:
            terms = robot_l_shape.frozen_terms(snapshot)
            return FrozenCorridor(
                terms.direction, min(terms.stop, terms.target),
                max(terms.stop, terms.target), terms.reference,
            )
        if pattern == "IKIGAI_BOX":
            identity, plan = snapshot.get("identity"), snapshot.get("plan")
            if not isinstance(identity, Mapping) or not isinstance(plan, Mapping):
                return None
            direction = identity.get("direction")
            if direction not in {"LONG", "SHORT"} or plan.get("direction") != direction:
                return None
            stop = _positive_number(plan["stop_price"])
            take = _positive_number(plan["take_price"])
            reference = _positive_number(plan["full_position"]["average_entry"])
            if not (stop < reference < take if direction == "LONG"
                    else take < reference < stop):
                return None
            return FrozenCorridor(direction, min(stop, take), max(stop, take), reference)
        if pattern in {"Falling Wedge", "Rising Wedge"}:
            geometry = snapshot.get("robot_geometry") or snapshot.get("geometry")
            if not isinstance(geometry, Mapping):
                return None
            index = geometry.get("current_index")
            if type(index) is not int or index < 0:
                return None
            # Existing canonical Robot Wedge geometry is validated by the
            # producer/Admission. Evaluate both frozen lines at one index.
            above = _positive_number(robot_state_machine.boundary_price(
                snapshot, side="upper", geometry_index=index,
            ))
            below = _positive_number(robot_state_machine.boundary_price(
                snapshot, side="lower", geometry_index=index,
            ))
            if above <= below:
                return None
            direction = "LONG" if pattern == "Falling Wedge" else "SHORT"
            return FrozenCorridor(
                direction, below, above, (below + above) / Decimal("2"),
            )
    except (
        KeyError, ValueError, TypeError, ArithmeticError,
        robot_l_shape.RobotLShapeError,
        robot_state_machine.RobotStateMachineError,
    ):
        return None
    return None


def verified_same_thesis(
    *, previous_candidate_id: str, previous_snapshot_sha256: str,
    previous_snapshot: Mapping[str, Any],
    new_snapshot: Mapping[str, Any], direction: str,
) -> bool:
    """Require explicit immutable source lineage PLUS price context overlap.

    Broad correlation is NOT proof. This narrow test deliberately rejects
    unlinked/distant continuation setups until their detectors provide
    stronger structure attribution. The stored STOP execution is verified
    separately by canonical SQLiteStore in the same admission transaction.
    """
    if not isinstance(previous_candidate_id, str) or not previous_candidate_id:
        return False
    if (not isinstance(previous_snapshot_sha256, str)
            or len(previous_snapshot_sha256) != 64):
        return False
    source = new_snapshot.get("reentry_parent") if isinstance(new_snapshot, Mapping) else None
    if (not isinstance(source, Mapping) or set(source) != {
        "candidate_id", "snapshot_sha256",
    } or source.get("candidate_id") != previous_candidate_id
            or source.get("snapshot_sha256") != previous_snapshot_sha256):
        return False
    previous = frozen_corridor(previous_snapshot)
    current = frozen_corridor(new_snapshot)
    if previous is None or current is None:
        return False
    if (direction not in {"LONG", "SHORT"}
            or previous.direction != direction
            or current.direction != direction):
        return False
    # In particular, unrelated formations in disjoint price regions may
    # share symbol/direction but are NOT the same trade thesis. Require the
    # new frozen reference within the original structural stop/target range.
    if not (previous.low <= current.reference <= previous.high):
        return False
    if current.high < previous.low or previous.high < current.low:
        return False
    return True
