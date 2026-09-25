"""Durable Robot v0.1 restart recovery coordinator.

This application layer binds Terminal SQLite state to the existing pure
``robot_restart_recovery`` policy. Recovery is read/reconcile/persist only: it
never submits, retries, amends, cancels, or closes an exchange order.
"""

from __future__ import annotations

import robot_l_shape

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
from terminal.domain.models import Category, PositionKey, PositionSide, TradingAccountId
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

        if runtime.recovery_status == RECONCILIATION_REQUIRED:
            # A restart must never lift the reconciliation fence. Durable
            # RECONCILIATION_REQUIRED records evidence the runtime could not
            # prove -- stale Robot trades, ownership or protection ambiguity --
            # and reconcile_restart() does not re-examine any of it, so falling
            # through here would land on READY and reopen admission over the
            # very ambiguity that raised the fence. Only the explicit operator
            # path (reconcile_required() -> reconcile_robot) may clear it.
            # Persist nothing and advance no candidate state: the durable
            # reason must survive the restart exactly as written.
            return RobotRecoveryResult(runtime, ())

        was_paused = runtime.recovery_status == PAUSED
        return self._reconcile_running(runtime, open_positions, approved, was_paused=was_paused)

    def reconcile_required(self) -> RobotRecoveryResult:
        """Begin the explicit operator exit from RECONCILIATION_REQUIRED.

        Legal only from ``(ROBOT_RUNNING, RECONCILIATION_REQUIRED)``. Reuses
        the same pure restart policy/candidate recovery as ``recover()`` but
        intentionally leaves durable state at RECONCILING on policy success;
        the runtime reconciliation pass must still prove pending-entry,
        protection, ownership and stale-ledger evidence before it may publish
        PAUSED. Admission therefore never opens during the command.
        """
        runtime = self._store.get_robot_runtime_state(self._account_id)
        if (
            runtime is None
            or runtime.mode != ROBOT_RUNNING
            or runtime.recovery_status != RECONCILIATION_REQUIRED
        ):
            raise RobotRecoveryError(
                "reconcile_robot is legal only from "
                "(ROBOT_RUNNING, RECONCILIATION_REQUIRED)"
            )
        _candidates, open_positions, approved = self._load_candidate_sets()
        return self._reconcile_running(
            runtime, open_positions, approved, was_paused=True,
            hold_reconciling=True,
        )

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
        hold_reconciling: bool = False,
    ) -> RobotRecoveryResult:
        runtime = self._set_runtime(
            runtime,
            mode=ROBOT_RUNNING,
            recovery_status=RECONCILING,
            reason=(
                "operator reconciliation in progress"
                if hold_reconciling else "restart recovery in progress"
            ),
        )
        try:
            if not hold_reconciling:
                self._validate_open_trade_integrity()
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
                recovery_status=(
                    RECONCILING if hold_reconciling
                    else PAUSED if was_paused else READY
                ),
                reason=(
                    "operator reconciliation awaiting runtime evidence"
                    if hold_reconciling else None
                ),
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

    def _validate_open_trade_integrity(self) -> None:
        """Prove durable OPEN Robot lifecycle state before reopening admission.

        Candidate labels are not position authority. A normal restart may
        publish READY only when every OPEN candidate has exactly one matching
        open Robot trade, the current net position still equals that trade's
        durable entry attestation, both protection legs exist, and no
        protection-close obligation is unresolved. Explicit maintenance
        reconciliation is intentionally exempt so it can repair stale state.
        """

        candidates = self._store.load_robot_candidates(self._account_id)
        open_candidates = tuple(item for item in candidates if item.status == "OPEN")
        open_trades = self._store.load_open_robot_trades(self._account_id)

        candidate_ids = {item.candidate_id for item in open_candidates}
        trade_candidate_ids = {item.candidate_id for item in open_trades}
        if candidate_ids != trade_candidate_ids or len(open_trades) != len(trade_candidate_ids):
            raise RobotRecoveryError(
                "Robot OPEN candidate/trade ownership is incomplete or ambiguous"
            )

        obligations = self._store.load_unresolved_paper_protection_obligations(
            self._account_id,
        )
        if obligations:
            raise RobotRecoveryError(
                "Robot restart has unresolved protection-close obligation(s)"
            )

        for candidate in open_candidates:
            trade = self._store.get_open_robot_trade_for_symbol(
                self._account_id, candidate.symbol,
            )
            if trade is None or trade.candidate_id != candidate.candidate_id:
                raise RobotRecoveryError(
                    f"Robot trade ownership is ambiguous for {candidate.symbol.value}"
                )
            if (
                trade.entry_quantity is None
                or trade.entry_quantity <= 0
                or trade.entry_position_version is None
            ):
                raise RobotRecoveryError(
                    f"Robot entry ownership attestation is missing for {candidate.symbol.value}"
                )

            position_key = PositionKey(
                self._account_id, Category.LINEAR, candidate.symbol, 0,
            )
            position = self._store.get_position_projection(position_key)
            expected_side = (
                PositionSide.LONG if trade.direction == "LONG"
                else PositionSide.SHORT if trade.direction == "SHORT"
                else None
            )
            if (
                expected_side is None
                or position is None
                or position.side is not expected_side
                or position.quantity.value != trade.entry_quantity
                or position.version != trade.entry_position_version
                or position.average_entry is None
                or position.average_entry.value != trade.average_entry
            ):
                raise RobotRecoveryError(
                    f"Robot position attestation no longer matches {candidate.symbol.value}"
                )

            protection = self._store.get_protection_projection(position_key)
            if (
                protection is None
                or protection.stop_loss is None
                or protection.take_profit is None
            ):
                raise RobotRecoveryError(
                    f"Robot protection is incomplete for {candidate.symbol.value}"
                )

    def _latest_geometry_indices(self, approved) -> dict[str, int]:
        if not approved:
            return {}
        provider = self._latest_geometry_index_provider
        result: dict[str, int] = {}
        for candidate in approved:
            if (
                (
                    candidate.signal_snapshot.get("pattern") == "IKIGAI_BOX"
                    and isinstance(candidate.robot_state, Mapping)
                    and candidate.robot_state.get("phase") == "BOX_ENTRY_READY"
                )
                or robot_l_shape.is_l_shape_snapshot(candidate.signal_snapshot)
            ):
                continue
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
