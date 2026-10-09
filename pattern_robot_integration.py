"""Shared Scanner -> durable Robot candidate handoff boundary.

Pattern-specific strategy modules decide what facts belong in the immutable
signal snapshot. This module owns the common executable-capability decision and
candidate persistence step used before Telegram exposes the Robot admission
action. It does not approve candidates, execute orders, or alter protection.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping

from robot_candidate_store import create_signal_snapshot
from robot_failure_diagnostics import record_robot_incident
from robot_state_machine import is_supported_pattern


# Optional observer of persisted Robot candidates (Autopilot SHADOW, issue #446).
# Bound only for the duration of one in-process Scanner pass, on that pass's own
# thread: a ContextVar keeps concurrent passes on other threads isolated and
# restores the outer observer for a nested pass. It can never affect delivery
# or the handoff result.
_candidate_observer: ContextVar[Callable[[str], None] | None] = ContextVar(
    "robot_candidate_observer", default=None,
)


@contextmanager
def robot_candidate_observer(observer: Callable[[str], None] | None) -> Iterator[None]:
    token = _candidate_observer.set(observer)
    try:
        yield
    finally:
        _candidate_observer.reset(token)


def _notify_candidate_observer(candidate_id: str) -> None:
    observer = _candidate_observer.get()
    if observer is None:
        return
    try:
        observer(candidate_id)
    except Exception as error:
        print(
            "[AUTOPILOT SHADOW OBSERVER ERROR] "
            f"candidate_id={candidate_id} error_class={type(error).__name__}"
        )


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
        record_robot_incident(
            incident_type="ROBOT_CANDIDATE_FAILURE",
            stage="candidate_persistence",
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
        record_robot_incident(
            incident_type="ROBOT_CANDIDATE_FAILURE",
            stage="candidate_persistence",
            reason_code="CANDIDATE_ID_MISSING_AFTER_PERSIST",
            symbol=symbol or None,
            timeframe=str(timeframe).strip() or None,
            pattern=pattern or None,
        )
        print(
            "[ROBOT CANDIDATE ERROR] "
            "persisted candidate has no candidate_id"
        )
        return RobotHandoffResult(
            executable=True,
            persistence_failed=True,
        )

    _notify_candidate_observer(candidate_id)
    return RobotHandoffResult(
        executable=True,
        candidate_id=candidate_id,
    )
