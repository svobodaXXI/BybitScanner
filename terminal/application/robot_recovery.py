"""Durable Robot v0.1 restart recovery coordinator.

This application layer binds Terminal SQLite state to the existing pure
``robot_restart_recovery`` policy. Recovery is read/reconcile/persist only: it
never submits, retries, amends, cancels, or closes an exchange order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping

from robot_restart_recovery import (
    EXPIRED_AT_APEX,
    RECONCILIATION_REQUIRED,
    RESUME_WAITING,
    ROBOT_RUNNING,
    ROBOT_STOPPED,
    RestartDecision,
    reconcile_restart,
)
from scanner_geometry_cursor import default_scanner_geometry_cursor_provider
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    PersistenceError,
    RobotRuntimeStateRecord,
    SQLiteStore,
)

RECONCILING = "RECONCILING"
READY = "READY"
PAUSED = "PAUSED"


class RobotRecoveryError(RuntimeError):
    """Raised when durable Robot recovery cannot safely complete."""


@dataclass(frozen=True, slots=True)
class RobotRecoveryResult:
    runtime_state: RobotRuntimeStateRecord
    decisions: tuple[RestartDecision, ...]

    @property
    def admission_ready(self) -> bool:
        return (
            self.runtime_state.mode == ROBOT_RUNNING
            and self.runtime_state.recovery_status == READY
        )


class RobotRecoveryCoordinator:
    """Single durable owner of Robot restart recovery admission."""

    def __init__(
        self,
        store: SQLiteStore,
        trading_account_id: TradingAccountId,
        *,
        latest_geometry_index_provider: Callable[[str, Mapping[str, object]], int] | None = None,
        clock_ms: Callable[[], int],
    ) -> None:
        self._store = store
        self._account_id = trading_account_id
        self._latest_geometry_index_provider = (
            latest_geometry_index_provider or default_scanner_geometry_cursor_provider()
        )
        self._clock_ms = clock_ms

    def recover(self) -> RobotRecoveryResult:
        now_ms = self._now_ms()
        runtime = self._store.initialize_robot_runtime_state(
            self._account_id, updated_at_ms=now_ms,
        )
        _candidates, open_positions, approved = self._load_candidate_sets()

        if runtime.mode == ROBOT_STOPPED:
            status, decisions = reconcile_restart(
                durable_mode=runtime.mode,
                open_robot_positions=open_positions,
                approved_candidates=(),
                latest_geometry_index_by_candidate={},
            )
            if status == RECONCILIATION_REQUIRED:
                runtime = self._set_runtime(
                    runtime,
                    mode=ROBOT_STOPPED,
                    recovery_status=RECONCILIATION_REQUIRED,
                    reason=decisions[0].reason if decisions else "restart reconciliation required",
                )
            return RobotRecoveryResult(runtime, decisions)

        was_paused = runtime.recovery_status == PAUSED
        return self._reconcile_running(runtime, open_positions, approved, was_paused=was_paused)

    def start(self) -> RobotRecoveryResult:
        """Explicit operator start from durable ``ROBOT_STOPPED``.

        This is the ``Запустить робота`` action, distinct from ``recover()``:
        ``recover()`` never lifts ``ROBOT_STOPPED`` on its own (it must survive
        process/PC restart per
        AUTOPILOT_ROBOT_V0_1_RESTART_FROM_STOPPED_DECISION.md), while ``start()``
        is the one path that actively reconciles into ``ROBOT_RUNNING``. Callers
        (``terminal.application.robot_control.start_robot``) are responsible for
        rejecting the call outright when durable mode is not already
        ``ROBOT_STOPPED``; this method assumes that precondition already holds.
        Per that same decision, previously stopped/terminal candidates are never
        revived here: only candidates still ``APPROVED`` are reconciled, exactly
        as an ordinary running-mode restart would.
        """
        now_ms = self._now_ms()
        runtime = self._store.initialize_robot_runtime_state(
            self._account_id, updated_at_ms=now_ms,
        )
        _candidates, open_positions, approved = self._load_candidate_sets()
        return self._reconcile_running(runtime, open_positions, approved, was_paused=False)

    def _load_candidate_sets(self):
        candidates = self._store.load_robot_candidates(self._account_id)
        open_positions = tuple(
            {"candidate_id": item.candidate_id, "symbol": item.symbol.value}
            for item in candidates
            if item.status == "OPEN"
        )
        approved = tuple(item for item in candidates if item.status == "APPROVED")
        return candidates, open_positions, approved

    def _reconcile_running(
        self,
        runtime: RobotRuntimeStateRecord,
        open_positions: tuple[dict[str, object], ...],
        approved: tuple,
        *,
        was_paused: bool,
    ) -> RobotRecoveryResult:
        runtime = self._set_runtime(
            runtime,
            mode=ROBOT_RUNNING,
            recovery_status=RECONCILING,
            reason="restart recovery in progress",
        )
        try:
            geometry_indices = self._latest_geometry_indices(approved)
            status, decisions = reconcile_restart(
                durable_mode=ROBOT_RUNNING,
                open_robot_positions=open_positions,
                approved_candidates=tuple(self._candidate_payload(item) for item in approved),
                latest_geometry_index_by_candidate=geometry_indices,
            )
            if status != ROBOT_RUNNING:
                raise RobotRecoveryError(f"unexpected restart status: {status}")
            by_candidate = {item.candidate_id: item for item in approved}
            for decision in decisions:
                if decision.status not in {RESUME_WAITING, EXPIRED_AT_APEX}:
                    continue
                if decision.candidate_id not in by_candidate or decision.state is None:
                    raise RobotRecoveryError("restart decision lacks durable candidate state")
                candidate = by_candidate[decision.candidate_id]
                self._store.save_robot_candidate_state(
                    candidate.candidate_id,
                    status="EXPIRED" if decision.status == EXPIRED_AT_APEX else "APPROVED",
                    robot_state=dict(decision.state),
                    expected_revision=candidate.state_revision,
                    updated_at_ms=self._now_ms(),
                )
            # An operator's pause is a durable admission decision (see
            # AUTOPILOT_ROBOT_V0_1_ROBOT_CONTROL_DECISION.md Section 2/6): a
            # restart must not silently resume admission on its own, so a
            # reconciliation that started PAUSED lands back on PAUSED, not READY.
            runtime = self._set_runtime(
                runtime,
                mode=ROBOT_RUNNING,
                recovery_status=PAUSED if was_paused else READY,
                reason=None,
            )
            return RobotRecoveryResult(runtime, decisions)
        except Exception as exc:
            runtime = self._mark_reconciliation_required(runtime, exc)
            return RobotRecoveryResult(runtime, ())

    def admission_ready(self) -> bool:
        runtime = self._store.get_robot_runtime_state(self._account_id)
        return bool(
            runtime is not None
            and runtime.mode == ROBOT_RUNNING
            and runtime.recovery_status == READY
        )

    def _latest_geometry_indices(self, approved) -> dict[str, int]:
        if not approved:
            return {}
        provider = self._latest_geometry_index_provider
        result: dict[str, int] = {}
        for candidate in approved:
            value = provider(candidate.symbol.value, candidate.signal_snapshot)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RobotRecoveryError(
                    f"invalid latest geometry index for candidate {candidate.candidate_id}"
                )
            result[candidate.candidate_id] = value
        return result

    @staticmethod
    def _candidate_payload(candidate) -> dict[str, object]:
        return {
            "candidate_id": candidate.candidate_id,
            "symbol": candidate.symbol.value,
            "status": candidate.status,
            "signal_snapshot": dict(candidate.signal_snapshot),
            "robot_state": dict(candidate.robot_state) if candidate.robot_state is not None else None,
        }

    def _mark_reconciliation_required(
        self, runtime: RobotRuntimeStateRecord, exc: Exception,
    ) -> RobotRuntimeStateRecord:
        reason = str(exc).strip() or type(exc).__name__
        try:
            return self._set_runtime(
                runtime,
                mode=ROBOT_RUNNING,
                recovery_status=RECONCILIATION_REQUIRED,
                reason=reason,
            )
        except (ConcurrentUpdate, PersistenceError) as mark_exc:
            raise RobotRecoveryError(
                "Robot recovery failed and durable fail-closed status could not be published"
            ) from mark_exc

    def _set_runtime(
        self,
        runtime: RobotRuntimeStateRecord,
        *,
        mode: str,
        recovery_status: str,
        reason: str | None,
    ) -> RobotRuntimeStateRecord:
        return self._store.update_robot_runtime_state(
            self._account_id,
            mode=mode,
            recovery_status=recovery_status,
            reason=reason,
            expected_version=runtime.version,
            updated_at_ms=self._now_ms(),
        )

    def _now_ms(self) -> int:
        value = self._clock_ms()
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RobotRecoveryError("Robot recovery clock returned invalid timestamp")
        return value
