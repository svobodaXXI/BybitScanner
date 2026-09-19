"""Durable Robot v0.1 candidate admission gate.

The gate is the boundary between the Scanner/Telegram candidate handoff and
Terminal SQLite Robot authority. It admits no candidate unless durable Robot
runtime state is ROBOT_RUNNING + READY. It never submits, retries, amends,
cancels, or closes an order.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping
import time

from robot_candidate_store import approve_candidate, load_candidate
from robot_state_machine import is_supported_pattern
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    PersistenceError,
    RobotCandidateRecord,
    SQLiteStore,
)


PAPER_ACCOUNT_ID = TradingAccountId("paper")
DEFAULT_DATABASE_PATH = Path(
    os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3")
)


class RobotAdmissionRejected(PersistenceError):
    """Raised when a candidate cannot cross the durable Robot admission gate."""


def active_robot_owner_candidate_ids(
    store: SQLiteStore,
    trading_account_id: TradingAccountId,
    symbol: Symbol,
    *,
    excluding_candidate_id: str | None = None,
) -> tuple[str, ...]:
    """Return candidate ids that already own exposure on ``symbol``.

    Robot v0.1 PAPER uses one-way ``position_idx=0`` net positions. Ownership
    belongs to an OPEN lifecycle, or to an APPROVED lifecycle whose own entry
    LIMIT has authoritative non-zero fill evidence. Unfilled APPROVED
    candidates are not owners and remain recoverable.
    """
    owners: list[str] = []
    # Only APPROVED/OPEN can own exposure; skip snapshots and finished history.
    for record in store.load_active_robot_candidate_states(trading_account_id):
        if record.symbol != symbol or record.candidate_id == excluding_candidate_id:
            continue
        if record.status == "OPEN":
            owners.append(record.candidate_id)
            continue
        if record.status != "APPROVED" or not isinstance(record.robot_state, Mapping):
            continue
        execution = record.robot_state.get("execution")
        if not isinstance(execution, Mapping):
            continue
        order_id = execution.get("limit_order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            continue
        order = store.get_paper_limit(order_id, trading_account_id)
        if order is not None and order.filled_quantity > 0:
            owners.append(record.candidate_id)
    return tuple(sorted(set(owners)))


def admit_robot_candidate(
    candidate_id: str,
    *,
    approval: Mapping[str, Any] | None = None,
    database_path: Path | str | None = None,
    store_dir: Path | str | None = None,
    clock_ms=None,
) -> tuple[RobotCandidateRecord, bool]:
    """Admit one approved Scanner candidate into authoritative SQLite state.

    Existing durable admission is returned idempotently. A new candidate is
    admitted only while the durable Robot runtime is ROBOT_RUNNING + READY.
    """

    candidate = load_candidate(candidate_id, store_dir=store_dir)
    if candidate["status"] not in {"AVAILABLE", "APPROVED"}:
        raise RobotAdmissionRejected("Scanner candidate is not admissible")

    symbol = Symbol(str(candidate["symbol"]).strip())
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, dict):
        raise RobotAdmissionRejected("Scanner candidate snapshot is invalid")
    if not is_supported_pattern(snapshot.get("pattern")):
        raise RobotAdmissionRejected("Scanner candidate pattern is not supported by Robot")

    source_timeframe = str(candidate.get("timeframe", "")).strip()
    if source_timeframe != "1":
        if snapshot.get("robot_handoff_ready") is not True:
            raise RobotAdmissionRejected(
                "Scanner candidate has no proven Robot 1m handoff"
            )
        if not isinstance(snapshot.get("robot_geometry"), dict):
            raise RobotAdmissionRejected(
                "Scanner candidate has no projected Robot geometry"
            )
        cursor = snapshot.get("scanner_geometry_cursor")
        if (
            not isinstance(cursor, dict)
            or str(cursor.get("timeframe", "")).strip() != "1"
        ):
            raise RobotAdmissionRejected(
                "Scanner candidate has no Robot 1m geometry cursor"
            )

    resolved_database_path = (
        Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    )
    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise RobotAdmissionRejected("Robot admission clock returned invalid timestamp")

    store = SQLiteStore.open(resolved_database_path)
    try:
        existing = store.get_robot_candidate(candidate_id)
        if existing is not None:
            if (
                existing.trading_account_id != PAPER_ACCOUNT_ID
                or existing.symbol != symbol
            ):
                raise RobotAdmissionRejected("Robot candidate identity conflicts with durable state")
            return existing, False

        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotAdmissionRejected("Robot runtime state is unavailable")
        if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
            raise RobotAdmissionRejected("Robot admission is not ready")

        owners = active_robot_owner_candidate_ids(
            store, PAPER_ACCOUNT_ID, symbol, excluding_candidate_id=candidate_id,
        )
        if owners:
            raise RobotAdmissionRejected(
                "Robot symbol already has an active exposure owner: " + ",".join(owners)
            )

        record, created = store.create_robot_candidate(
            candidate_id=candidate_id,
            trading_account_id=PAPER_ACCOUNT_ID,
            symbol=symbol,
            status="APPROVED",
            signal_snapshot=snapshot,
            approved_at_ms=now,
            updated_at_ms=now,
        )
    finally:
        store.close()

    # Legacy JSON is only the Scanner handoff envelope. Its approval marker is
    # updated after authoritative SQLite admission and remains idempotent.
    approve_candidate(
        candidate_id,
        approval=approval,
        store_dir=store_dir,
    )
    return record, created
