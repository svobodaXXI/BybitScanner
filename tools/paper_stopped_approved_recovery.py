"""One-shot recovery of the proven partially stopped PAPER Editor upgrade.

Incident boundary: the 2026-11-06 canonical STOP for PRIOR_TARGET returned
BLOCKED after Robot and Scanner became STOPPED. Never replay that STOP. A
separately authorized, exact-PID SIGINT is possible only with fresh FLAT and
inert-APPROVED evidence under a SQLite writer reservation. No LIVE/Market,
no database edits, no autopilot restart, no signal retry on uncertain outcome.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import os
from pathlib import Path
import sqlite3
import sys
import time

from tools.flat_paper_recovery_transition import (
    _frozen_snapshot, _has_exact_local_listener, _process_start_token,
    _send_exact_sigint, _service_pid, get_snapshots,
)
from tools.paper_interrupted_stop_recovery import _trusted_journal
from tools.runtime_intent import expected_database_identity
from tools.stop_robot_runtime import (
    ABSENT, PRESENT, RuntimeShutdown, SCOPE_ALL, ShutdownResult,
    _database_path, _environment,
)
from tools.vps_gitless_release_activate import (
    ActivationBlocked, TRANSACTIONS, _sync_directory, _trusted_file,
    activate_staged_release, inspect_staged_release,
)
from tools.vps_release_identity import MANIFEST, verify_release
from tools.vps_release_resume import _systemd_state

PRIOR_TARGET = "1e9129f51e5b620f71503bb1814f14a431498fc5"
OLD_BACKEND = "4090641514b8f558a0054fd577b2750b944fd8d6"
ROOT = Path("/opt/BybitScanner")
ENV_FILE = Path("/etc/bybitscanner/paper.env")
MARKER_PREFIX = ".stopped-approved-recovery-"
BACKEND_UNIT = "bybitscanner-paper-backend.service"


class PartialStopBlocked(RuntimeError):
    pass


def _demand(condition: bool, reason: str) -> None:
    if not condition:
        raise PartialStopBlocked(reason)


def _one(conn: sqlite3.Connection, sql: str, params=()) -> tuple:
    rows = conn.execute(sql, params).fetchall()
    _demand(len(rows) == 1, "missing_or_ambiguous_runtime_state")
    return tuple(rows[0])


def prove_stopped_inert_approvals(
    conn: sqlite3.Connection, *, expected_identity: str, snapshots: dict,
) -> str:
    """Pure durable/API proof; caller holds an unchanged SQLite snapshot.

    A committed STOPPED state and empty monitor coverage are insufficient:
    every active APPROVED must be independently inert, with no subsequent
    execution, trade, working order, command, obligation, or checkpoint.
    """
    backend = snapshots["backend"]
    scanner = snapshots["scanner"]
    autopilot = snapshots["autopilot"]
    protection = snapshots["protection"]
    _demand(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("build_sha") == OLD_BACKEND
        and backend.get("database_identity") == expected_identity
        and bool(backend.get("process_instance_id")),
        "backend_identity_or_live_fence_unproven",
    )
    _demand(scanner.get("ok") is True and scanner.get("mode") == "SCANNER_STOPPED",
            "scanner_not_stopped")
    _demand(autopilot.get("ok") is True and autopilot.get("mode") == "OFF",
            "autopilot_not_off")
    _demand(
        protection.get("ok") is True and protection.get("healthy") is True
        and protection.get("covered_symbols") == []
        and protection.get("armed_symbols") == []
        and protection.get("coverage_roles") == {}
        and protection.get("unhealthy_symbols") == {},
        "protection_not_quiescent",
    )
    _demand(conn.execute("PRAGMA quick_check").fetchone() == ("ok",),
            "paper_database_integrity_unproven")
    _demand(
        _one(conn, "SELECT mode,recovery_status FROM robot_runtime_state "
                   "WHERE trading_account_id='paper'")
        == ("ROBOT_STOPPED", "ROBOT_STOPPED"), "robot_not_durably_stopped",
    )
    _demand(
        _one(conn, "SELECT mode FROM scanner_runtime_state "
                   "WHERE trading_account_id='paper'") == ("SCANNER_STOPPED",),
        "scanner_not_durably_stopped",
    )
    _demand(
        _one(conn, "SELECT mode FROM robot_autopilot_state "
                   "WHERE trading_account_id='paper'") == ("OFF",),
        "autopilot_not_durably_off",
    )
    for symbol, side, raw, sync in conn.execute(
        "SELECT symbol,side,quantity,sync_state FROM position_projections "
        "WHERE trading_account_id='paper'"
    ):
        try:
            value = Decimal(str(raw))
        except (TypeError, InvalidOperation, ValueError) as exc:
            raise PartialStopBlocked("paper_position_invalid") from exc
        _demand(bool(symbol) and side == "Flat" and value.is_finite()
                and value == 0 and sync in ("synced", "synchronized"),
                "paper_position_not_flat_and_synced")
    for table, condition in (
        ("robot_trades", "exit_time_ms IS NULL"),
        ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
        ("trading_commands", "current_state IS NULL OR current_state NOT IN "
         "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
        ("paper_protection_obligations", "status IS NULL OR status!='RESOLVED'"),
        ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
    ):
        _demand(conn.execute(
            f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
            f"AND ({condition}) LIMIT 1"
        ).fetchone() is None, "unfinished_paper_ownership:" + table)
    candidates = conn.execute(
        "SELECT candidate_id,symbol,status,approved_at_ms FROM robot_candidates "
        "WHERE trading_account_id='paper' "
        "AND (status IS NULL OR status NOT IN "
        "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))"
    ).fetchall()
    seen = set()
    for candidate_id, symbol, status, approved_at in candidates:
        _demand(
            isinstance(candidate_id, str) and candidate_id
            and candidate_id not in seen and isinstance(symbol, str) and symbol
            and status == "APPROVED" and type(approved_at) is int and approved_at > 0,
            "active_candidate_not_proven_inert",
        )
        seen.add(candidate_id)
        _demand(conn.execute(
            "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
            "AND candidate_id=? LIMIT 1", (candidate_id,)
        ).fetchone() is None, "candidate_has_trading_history")
        _demand(conn.execute(
            "SELECT 1 FROM executions WHERE trading_account_id='paper' "
            "AND symbol=? AND (exchange_timestamp_ms IS NULL "
            "OR exchange_timestamp_ms>=?) LIMIT 1",
            (symbol, approved_at),
        ).fetchone() is None, "post_approval_execution_exists")
        for table in ("paper_limit_orders", "trading_commands"):
            _demand(conn.execute(
                f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                "AND symbol=? AND (created_at_ms IS NULL OR created_at_ms>=?) LIMIT 1",
                (symbol, approved_at),
            ).fetchone() is None, "post_approval_or_unknown_timestamp:" + table)
    return "STOPPED_INERT_APPROVALS_PROVEN_ONLY"


def _receipt(transactions: Path, phase: str, uid: int, *, target: str) -> bool:
    path = transactions / (MARKER_PREFIX + phase + "-" + PRIOR_TARGET)
    if not path.exists() and not path.is_symlink():
        return False
    _demand(
        _trusted_file(path, uid) == (target + "\n").encode("ascii"),
        "recovery_receipt_invalid:" + phase,
    )
    return True


def _record(transactions: Path, phase: str, uid: int, *, target: str) -> None:
    path = transactions / (MARKER_PREFIX + phase + "-" + PRIOR_TARGET)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write((target + "\n").encode("ascii"))
        f.flush()
        os.fsync(f.fileno())
    _sync_directory(transactions)


def _backend_stopped() -> bool:
    from tools.legacy_runtime_process import probe_listener_pids
    try:
        state = _systemd_state(BACKEND_UNIT)
        return (
            state.get("ActiveState") in ("inactive", "failed")
            and str(state.get("MainPID")) == "0"
            and not probe_listener_pids("127.0.0.1", 8765)
        )
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def _snapshots_and_read_only_proof(db: Path, identity: str) -> dict:
    snapshots = get_snapshots()
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=5) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        _demand(
            prove_stopped_inert_approvals(conn, expected_identity=identity,
                                         snapshots=snapshots)
            == "STOPPED_INERT_APPROVALS_PROVEN_ONLY",
            "inert_approval_preflight_unproven",
        )
    return snapshots


def _single_backend_handoff(db: Path, identity: str, snapshots: dict) -> str:
    """One exact pidfd SIGINT; no network I/O inside SQLite writer barrier."""
    pid = _service_pid()
    start = _process_start_token(pid)
    _demand(_has_exact_local_listener(pid), "backend_listener_owner_unproven")
    _demand(snapshots["backend"].get("build_sha") == OLD_BACKEND,
            "backend_build_changed")
    fresh = get_snapshots()
    _demand(
        fresh["backend"].get("process_instance_id")
        == snapshots["backend"].get("process_instance_id"),
        "backend_instance_changed",
    )
    with _frozen_snapshot(db) as conn:
        _demand(
            prove_stopped_inert_approvals(conn, expected_identity=identity,
                                         snapshots=fresh)
            == "STOPPED_INERT_APPROVALS_PROVEN_ONLY", "final_proof_missing",
        )
        opened = [p for _, name, p in conn.execute("PRAGMA database_list")
                  if name == "main"]
        _demand(len(opened) == 1 and Path(opened[0]).resolve() == db.resolve(),
                "opened_database_changed")
        _demand(
            _service_pid() == pid and _process_start_token(pid) == start
            and _has_exact_local_listener(pid),
            "backend_process_changed",
        )
        _send_exact_sigint(pid, start)
    # Backend cleanup may need the SQLite writer slot. Never hold it while
    # waiting for exit or poll /health to infer process termination.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}/stat").exists():
            return "INTERRUPT_EXIT_OBSERVED"
        time.sleep(0.25)
    return "OUTCOME_UNKNOWN"


def recover_editor_only(
    *, target: str, stage: Path, root: Path = ROOT,
    transactions: Path = TRANSACTIONS, manifest: Path = MANIFEST, uid: int = 0,
    proof=None, handoff=None, telegram=None, installer=None, resume=None,
    backend_stopped=None, inspect=None,
) -> str:
    """Explicitly authorized partial STOP continuation, never a STOP replay."""
    from tools.paper_maintenance import (
        _complete_stop_intent, _proven_prior_exceptional_completion,
        resume_installed_release,
    )

    def finish_resume() -> str:
        status = (resume or resume_installed_release)(
            target, root=root, env_file=ENV_FILE,
        )
        if isinstance(status, str) and status.startswith("READY:"):
            _complete_stop_intent(transactions, target, uid=uid)
        return status

    _demand(len(target) == 40 and all(c in "0123456789abcdef" for c in target)
            and target != PRIOR_TARGET and target != OLD_BACKEND,
            "invalid_target")
    _demand(os.geteuid() == uid, "root_operator_required")
    _demand(root.is_dir() and not root.is_symlink() and not (root / ".git").exists(),
            "unexpected_installed_layout")
    _demand(stage.is_dir() and not stage.is_symlink(), "staging_missing")
    _trusted_journal(transactions, uid)
    _demand(
        _trusted_file(transactions / (".stop-invoked-" + PRIOR_TARGET), uid)
        == b"STOP_INVOKED; not install authorization\\n",
        "prior_STOP_intent_mismatch",
    )
    _demand(not (transactions / PRIOR_TARGET).exists()
            and not (transactions / (".stop-confirmed-" + PRIOR_TARGET)).exists(),
            "prior_STOP_already_completed_or_installed")
    # The original 094d handoff may coexist, but other incomplete STOP
    # attempts may not be silently retired or replayed.
    for marker in transactions.glob(".stop-invoked-*"):
        prior = marker.name.removeprefix(".stop-invoked-")
        _demand(
            prior == PRIOR_TARGET or _proven_prior_exceptional_completion(
                transactions, prior, root=root, uid=uid,
            ),
            "other_unknown_STOP_intent",
        )
    prior_release = verify_release(root, manifest)
    _demand(prior_release in (OLD_BACKEND, target), "installed_release_changed")
    env = _environment(ENV_FILE)
    expected_db = expected_database_identity(root, env)
    _demand(isinstance(expected_db, str) and len(expected_db) == 64,
            "database_identity_unproven")
    if prior_release == target:
        _demand(_receipt(transactions, "handoff-proven", uid, target=target),
                "target_installed_without_handoff_proof")
        return finish_resume()
    (inspect or inspect_staged_release)(
        target, stage=stage, root=root, manifest=manifest, uid=uid,
    )
    started = _receipt(transactions, "handoff-attempt", uid, target=target)
    backend_exited = _receipt(transactions, "backend-exited", uid, target=target)
    complete = _receipt(transactions, "handoff-proven", uid, target=target)
    _demand(not backend_exited or started, "backend_receipt_without_intent")
    _demand(not complete or backend_exited, "handoff_receipt_without_backend")

    if not started:
        db = _database_path(root, env)
        _demand(db.is_file() and not db.is_symlink(), "database_path_unproven")
        snapshots = (proof or _snapshots_and_read_only_proof)(db, expected_db)
        owner = RuntimeShutdown(root=root, env=env)
        _demand(owner._probe_backend() == PRESENT, "backend_not_proven")
        owner._require_scanner_stopped()
        owner._require_autopilot_off()
        owner._probe_telegram()
        _record(transactions, "handoff-attempt", uid, target=target)
        outcome = (handoff or _single_backend_handoff)(
            db, expected_db, snapshots,
        )
        _demand(outcome == "INTERRUPT_EXIT_OBSERVED",
                "backend_signal_outcome_unknown_no_retry")
        _record(transactions, "backend-exited", uid, target=target)
    else:
        _demand(backend_exited, "prior_backend_signal_unknown_no_retry")

    _demand((backend_stopped or _backend_stopped)(),
            "backend_stopped_identity_not_proven")
    if not complete:
        owner = RuntimeShutdown(root=root, env=env)
        state = owner._probe_telegram()
        attempted = _receipt(transactions, "telegram-attempt", uid, target=target)
        if state == PRESENT:
            _demand(not attempted, "telegram_outcome_unknown_no_retry")
            _record(transactions, "telegram-attempt", uid, target=target)
            if telegram is None:
                from tools.stop_robot_runtime import TELEGRAM
                owner._shutdown(
                    owner._telegram + "/shutdown", owner._telegram + "/health",
                    "Telegram monitoring", TELEGRAM, "telegram",
                )
            else:
                telegram()
        _demand(owner._probe_telegram() == ABSENT,
                "telegram_not_proven_absent")
        _record(transactions, "handoff-proven", uid, target=target)

    receipt = (installer or activate_staged_release)(
        target, stage=stage, root=root, manifest=manifest, transactions=transactions,
        uid=uid, stopped_proof=ShutdownResult(
            SCOPE_ALL, True, "Incident-scoped proven partial STOP completion",
            runtime_stopped=True,
        ),
    )
    _demand(isinstance(receipt, str) and receipt.startswith("INSTALLED_STOPPED:"),
            "release_not_installed_stopped")
    return finish_resume()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One-shot partial PAPER STOP recovery")
    parser.add_argument("--target", required=True)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--execute-stopped-approved-handoff", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_stopped_approved_handoff:
        print("BLOCKED: separate owner authorization required")
        return 2
    try:
        status = recover_editor_only(target=args.target, stage=args.stage)
    except Exception as exc:
        print("BLOCKED: " + type(exc).__name__ + ":" + str(exc)
              + "; no retry or trading restart")
        return 2
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
