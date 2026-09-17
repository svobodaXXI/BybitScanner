"""Operator boundary for evidence-backed legacy PAPER protection recovery.

This application command deliberately performs only the durable attestation
repair defined by CR-ROBOT-LEGACY-PROTECTION-RECOVERY-001.  It opens its own
short-lived SQLiteStore connection, matching the existing Robot operator
control/admission pattern, and delegates all ownership proof plus atomic
persistence to ``terminal.persistence.legacy_protection_recovery``.

It never submits, cancels, amends, or closes an order and it never invokes
Robot reconciliation.  A later, separately authorized reconciliation command
remains responsible for any market side effect.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from terminal.persistence.legacy_protection_recovery import (
    LegacyEntryAttestationResult,
    attest_legacy_robot_entry,
)
from terminal.persistence.sqlite_store import SQLiteStore


DEFAULT_DATABASE_PATH = Path(
    os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3")
)


def _now_ms(clock_ms: Callable[[], int] | None) -> int:
    value = (clock_ms or (lambda: int(time.time() * 1000)))()
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError("legacy protection recovery clock returned invalid timestamp")
    return value


def attest_legacy_protection_recovery(
    *,
    trade_id: str,
    obligation_id: str,
    client_action_id: str,
    database_path: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> LegacyEntryAttestationResult:
    """Durably attest one exact legacy Robot entry from proven PAPER evidence.

    The caller supplies identities only.  Quantity/version are reconstructed
    by the persistence proof and cannot be provided by the operator.
    ``RECONCILIATION_REQUIRED`` legality is independently enforced inside the
    proof helper.  The short-lived connection is always closed, including on
    rejection.
    """

    resolved = Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    store = SQLiteStore.open(resolved)
    try:
        return attest_legacy_robot_entry(
            store,
            trade_id=trade_id,
            obligation_id=obligation_id,
            client_action_id=client_action_id,
            authorized_at_ms=_now_ms(clock_ms),
        )
    finally:
        store.close()
