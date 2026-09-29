"""Shared Scanner -> durable Robot candidate handoff boundary.

Pattern-specific strategy modules decide what facts belong in the immutable
signal snapshot. This module owns the common executable-capability decision and
candidate persistence step used before Telegram exposes the Robot admission
action. It does not approve candidates, execute orders, or alter protection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from robot_candidate_store import create_signal_snapshot
import robot_incident_store
from robot_state_machine import is_supported_pattern


L_SHAPE_PATTERN = "L-shape"
L_SHAPE_SOURCE_TIMEFRAMES = frozenset({"1", "5"})


@dataclass(frozen=True, slots=True)
class RobotHandoffResult:
    """Outcome of the common pre-admission candidate handoff."""

    executable: bool
    candidate_id: str | None = None
    persistence_failed: bool = False


def is_robot_executable_signal(
    signal_snapshot: Mapping[str, Any] | None,
    *,
    timeframe: str,
) -> bool:
    """Return whether this exact Scanner snapshot may expose Robot admission.

    This is intentionally only a capability boundary. Pattern-specific trading
    terms stay in their strategy adapters and authoritative admission remains in
    terminal.application.robot_admission.
    """

    if not isinstance(signal_snapshot, Mapping):
        return False
    if signal_snapshot.get("scanner_observational_only", False):
        return False

    normalized_timeframe = str(timeframe).strip()
    pattern = str(signal_snapshot.get("pattern", "")).strip()

    if pattern == L_SHAPE_PATTERN:
        return (
            normalized_timeframe in L_SHAPE_SOURCE_TIMEFRAMES
            and signal_snapshot.get("robot_handoff_ready") is True
        )

    if not is_supported_pattern(pattern):
        return False

    return (
        normalized_timeframe == "1"
        or signal_snapshot.get("robot_handoff_ready") is True
    )


def prepare_robot_handoff(
    signal_snapshot: Mapping[str, Any] | None,
    *,
    timeframe: str,
    enabled: bool,
) -> RobotHandoffResult:
    """Persist one executable signal snapshot for later common admission.

    Persistence failure is fail-closed: no candidate id is returned, so the
    caller cannot render an admission button. Ordinary Scanner delivery remains
    the caller's responsibility and is not failed by this helper.
    """

    executable = is_robot_executable_signal(
        signal_snapshot,
        timeframe=timeframe,
    )
    if not enabled or not executable:
        return RobotHandoffResult(executable=executable)

    try:
        candidate = create_signal_snapshot(
            signal_snapshot,
            timeframe=str(timeframe).strip(),
        )
    except Exception as error:
        symbol = (
            str(signal_snapshot.get("symbol", "")).strip()
            if isinstance(signal_snapshot, Mapping)
            else ""
        )
        pattern = (
            str(signal_snapshot.get("pattern", "")).strip()
            if isinstance(signal_snapshot, Mapping)
            else ""
        )
        robot_incident_store.try_record_robot_incident(
            lifecycle_stage="CANDIDATE_PERSISTENCE",
            reason_code="CANDIDATE_PERSISTENCE_EXCEPTION",
            symbol=symbol or None,
            timeframe=str(timeframe).strip() or None,
            pattern=pattern or None,
            error=error,
        )
        print(
            "[ROBOT CANDIDATE ERROR] "
            f"symbol={symbol or 'UNKNOWN'} pattern={pattern or 'UNKNOWN'} "
            f"error_class={type(error).__name__}"
        )
        return RobotHandoffResult(
            executable=True,
            persistence_failed=True,
        )

    candidate_id = str(candidate.get("candidate_id", "")).strip()
    if not candidate_id:
        symbol = (
            str(signal_snapshot.get("symbol", "")).strip()
            if isinstance(signal_snapshot, Mapping)
            else ""
        )
        pattern = (
            str(signal_snapshot.get("pattern", "")).strip()
            if isinstance(signal_snapshot, Mapping)
            else ""
        )
        robot_incident_store.try_record_robot_incident(
            lifecycle_stage="CANDIDATE_PERSISTENCE",
            reason_code="CANDIDATE_ID_MISSING",
            symbol=symbol or None,
            timeframe=str(timeframe).strip() or None,
            pattern=pattern or None,
        )
        print(
            "[ROBOT CANDIDATE ERROR] "
            "reason_code=CANDIDATE_ID_MISSING"
        )
        return RobotHandoffResult(
            executable=True,
            persistence_failed=True,
        )

    return RobotHandoffResult(
        executable=True,
        candidate_id=candidate_id,
    )
