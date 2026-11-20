"""Robot v0.1 restart/recovery planner.

Pure fail-closed recovery policy. It does not execute orders itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from robot_state_machine import PHASE_EXPIRED_AT_APEX, resume_without_replay
import robot_l_shape

ROBOT_STOPPED = "ROBOT_STOPPED"
ROBOT_RUNNING = "ROBOT_RUNNING"
RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
RESUME_WAITING = "RESUME_WAITING"
RESUME_OPEN_POSITION = "RESUME_OPEN_POSITION"
EXPIRED_AT_APEX = "EXPIRED_AT_APEX"
BOX_ENTRY_READY = "BOX_ENTRY_READY"


class RobotRestartError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RestartDecision:
    status: str
    candidate_id: str | None = None
    reason: str | None = None
    state: dict[str, Any] | None = None


def initial_robot_mode(durable_mode: str | None) -> str:
    """First run defaults to stopped; never autostart Robot."""
    value = str(durable_mode or "").strip().upper()
    if not value:
        return ROBOT_STOPPED
    if value not in {ROBOT_STOPPED, ROBOT_RUNNING}:
        raise RobotRestartError("invalid durable Robot mode")
    return value


def reconcile_restart(
    *,
    durable_mode: str | None,
    open_robot_positions: Sequence[Mapping[str, Any]],
    approved_candidates: Sequence[Mapping[str, Any]],
    latest_geometry_index_by_candidate: Mapping[str, int],
) -> tuple[str, tuple[RestartDecision, ...]]:
    """Build restart actions without replaying missed candles.

    OPEN Robot positions survive restart. WAITING approved candidates resume only
    from their persisted immutable snapshot and persisted Robot state. Each
    candidate gets its own latest index because two candidates on one symbol may
    have different frozen Scanner index anchors.
    """

    mode = initial_robot_mode(durable_mode)
    positions = tuple(open_robot_positions or ())
    candidates = tuple(approved_candidates or ())

    if mode == ROBOT_STOPPED and positions:
        return RECONCILIATION_REQUIRED, (
            RestartDecision(
                RECONCILIATION_REQUIRED,
                reason="surviving Robot position conflicts with durable ROBOT_STOPPED",
            ),
        )

    decisions: list[RestartDecision] = []
    for position in positions:
        candidate_id = str(position.get("candidate_id", "")).strip() or None
        symbol = str(position.get("symbol", "")).strip().upper()
        if not symbol:
            raise RobotRestartError("open Robot position has no symbol")
        decisions.append(
            RestartDecision(
                RESUME_OPEN_POSITION,
                candidate_id=candidate_id,
                reason="authoritative open Robot position survives restart",
            )
        )

    if mode == ROBOT_STOPPED:
        return ROBOT_STOPPED, tuple(decisions)

    for candidate in candidates:
        if candidate.get("status") != "APPROVED":
            continue
        candidate_id = str(candidate.get("candidate_id", "")).strip()
        snapshot = candidate.get("signal_snapshot")
        state_wrapper = candidate.get("robot_state")
        if not candidate_id or not isinstance(snapshot, Mapping) or not isinstance(state_wrapper, Mapping):
            raise RobotRestartError("approved candidate lacks durable recovery state")
        state = dict(state_wrapper)
        state.pop("revision", None)
        if (
            snapshot.get("pattern") == "IKIGAI_BOX"
            and state.get("phase") == BOX_ENTRY_READY
        ):
            decisions.append(
                RestartDecision(
                    RESUME_WAITING,
                    candidate_id=candidate_id,
                    reason=BOX_ENTRY_READY,
                    state=state,
                )
            )
            continue
        if robot_l_shape.is_l_shape_snapshot(snapshot):
            robot_l_shape.frozen_terms(snapshot)
            if state.get("phase") not in {
                robot_l_shape.PHASE_WAITING_RETEST,
                robot_l_shape.PHASE_RETEST_DETECTED,
            }:
                raise RobotRestartError("L-shape candidate has invalid durable recovery phase")
            decisions.append(
                RestartDecision(
                    RESUME_WAITING,
                    candidate_id=candidate_id,
                    reason=str(state.get("phase")),
                    state=state,
                )
            )
            continue
        if candidate_id not in latest_geometry_index_by_candidate:
            raise RobotRestartError(
                f"latest geometry index is unavailable for candidate {candidate_id}"
            )
        # An early Wedge LIMIT can be in-flight without a linked order id
        # across a crash. Reaching the apex must NOT silently terminalize
        # the owner candidate, orphan its partial fill or discard STOP recovery.
        # Full account reconciliation is required instead of a false EXPIRED.
        execution = state.get("execution") or {}
        if (isinstance(execution, Mapping)
                and execution.get("entry_mode") == "IMPULSE_EARLY_LIMIT"
                and execution.get("impulse_entry_intent") is not None
                and state.get("phase") == "WAITING_RETEST"):
            geometry = snapshot.get("robot_geometry") or snapshot.get("geometry")
            apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
            apex_index = apex.get("index") if isinstance(apex, Mapping) else None
            latest = latest_geometry_index_by_candidate.get(candidate_id)
            if (type(latest) is not int or type(apex_index) not in (int, float)
                    or isinstance(apex_index, bool) or latest >= apex_index):
                raise RobotRestartError(
                    "uncertain impulse entry at apex requires owner reconciliation"
                )
        resumed, event = resume_without_replay(
            snapshot,
            state,
            latest_geometry_index=int(latest_geometry_index_by_candidate[candidate_id]),
        )
        if resumed.get("phase") == PHASE_EXPIRED_AT_APEX:
            decisions.append(
                RestartDecision(EXPIRED_AT_APEX, candidate_id=candidate_id, reason=event, state=resumed)
            )
        else:
            decisions.append(
                RestartDecision(RESUME_WAITING, candidate_id=candidate_id, reason=event, state=resumed)
            )

    return ROBOT_RUNNING, tuple(decisions)
