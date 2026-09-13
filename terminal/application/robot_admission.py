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
