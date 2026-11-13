"""One-shot successor of the 2026-11-13 known PAUSED-drain refusal.

The ORIGINAL canonical STOP was refused while an OPEN trade was protected. The
installed older monolith recorded only its STOP intent; it did NOT record the
deferred outcome introduced by #1039. Never forge that deferred receipt or
repeat canonical STOP. Run this separate, explicitly authorized continuation
ONLY from an immutable, attested new staging checkout, with the old Backend
still exactly installed. No LIVE, Market, SQL updates or protection bypass.

If a continuation POST has an unknown outcome, its fsynced attempt receipt
forbids a retry. A completed receipt enables only stopped-only installation.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

from tools.vps_gitless_release_activate import (
    TRANSACTIONS, _manifest, _sync_directory, _trusted_file,
    inspect_staged_release, activate_staged_release,
)
from tools.vps_release_identity import MANIFEST, verify_release
from tools.stop_robot_runtime import (
    RuntimeShutdown, ShutdownResult, SCOPE_ALL, _database_path, _environment,
    _assert_legacy_paper_quiescence,
    SafeStopError,
)
from tools.runtime_intent import expected_database_identity

ROOT = Path("/opt/BybitScanner")
ENV_FILE = Path("/etc/bybitscanner/paper.env")
# The one historical known-returned STOP refusal. These pins are *constraints*,
# not a substitute for fresh host/process/DB/ledger evidence.
OLD_SHA = "b5d9184ae1158803ab9528b4efb0026d726077c2"
PRIOR_STOP = "7d868ba46daae1f845cd9387ca53f85d9ddb94e7"
EXPECTED_PROCESS_INSTANCE = "16781b55-f70a-4077-ad42-1810640867cc"
PREFIX = ".paused-drain-successor-"


class PausedSuccessorBlocked(ValueError):
    pass


def _demand(value: bool, reason: str) -> None:
    if not value:
        raise PausedSuccessorBlocked(reason)


def _sha(value: str) -> bool:
    return isinstance(value, str) and len(value) == 40 and all(x in "0123456789abcdef" for x in value)


def _payload(target: str) -> bytes:
    return (json.dumps({
        "contract": "paused-drain-successor-v1",
        "original_stop": PRIOR_STOP,
        "old_sha": OLD_SHA,
        "target_sha": target,
        "original_process_instance": EXPECTED_PROCESS_INSTANCE,
    }, sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _marker(transactions: Path, phase: str) -> Path:
    return transactions / (PREFIX + phase + "-" + PRIOR_STOP)


def _receipt(transactions: Path, phase: str, target: str, uid: int) -> bool:
    path = _marker(transactions, phase)
    if not path.exists() and not path.is_symlink():
        return False
    _demand(_trusted_file(path, uid) == _payload(target), "paused_successor_receipt_mismatch")
    return True


def _write_once(transactions: Path, phase: str, target: str) -> None:
    path = _marker(transactions, phase)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(_payload(target))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(transactions)


def _trusted_prior(transactions: Path, uid: int) -> None:
    from tools.paper_interrupted_stop_recovery import _trusted_journal
    _trusted_journal(transactions, uid)
    _demand(
        _trusted_file(transactions / (".stop-invoked-" + PRIOR_STOP), uid)
        == b"STOP_INVOKED; not install authorization\\n",
        "original_STOP_intent_missing_or_changed",
    )
    _demand(not (transactions / PRIOR_STOP).exists()
            and not (transactions / PRIOR_STOP).is_symlink()
            and not (transactions / (".stop-confirmed-" + PRIOR_STOP)).exists()
            and not (transactions / (".stop-confirmed-" + PRIOR_STOP)).is_symlink(),
            "original_STOP_was_not_a_known_refusal")


def proven_paused_successor(
    transactions: Path, prior: str, target: str | None = None, *,
    root: Path = ROOT, uid: int = 0, require_ready: bool = True,
) -> bool:
    """Read-only durable proof for the original STOP's exceptional successor.

    Only a separately fsynced completed phase AND the exact Gitless install
    transaction can retire the old STOP fence. Original STOP is never confirmed.
    """
    if prior != PRIOR_STOP:
        return False
    try:
        if not transactions.is_dir() or transactions.is_symlink():
            return False
        _trusted_prior(transactions, uid)
        raw = _trusted_file(_marker(transactions, "completed"), uid)
        payload = json.loads(raw.decode("ascii"))
        next_sha = payload["target_sha"]
        if (not _sha(next_sha) or next_sha in (OLD_SHA, PRIOR_STOP)
                or (target is not None and next_sha != target)
                or raw != _payload(next_sha)
                or not _receipt(transactions, "attempt", next_sha, uid)):
            return False
        journal = transactions / next_sha
        if (not journal.is_dir() or journal.is_symlink()
                or journal.stat().st_uid != uid
                or journal.stat().st_mode & 0o077):
            return False
        old = _manifest(_trusted_file(journal / "old.json", uid))
        new = _manifest(_trusted_file(journal / "target.json", uid))
        _trusted_file(journal / "units.json", uid)
        if old["build_sha"] != OLD_SHA or new["build_sha"] != next_sha:
            return False
        if require_ready:
            if _trusted_file(journal / "editor-ready", uid) != next_sha.encode("ascii"):
                return False
        return verify_release(root) == next_sha
    except (OSError, ValueError, UnicodeError, TypeError, KeyError):
        return False


def _prove_no_live_ownership(root: Path, env_file: Path, owner: RuntimeShutdown) -> None:
    """Read-only proof; every APPROVED candidate is inspected separately."""
    from terminal.domain.models import TradingAccountId
    from terminal.persistence.sqlite_store import SQLiteStore

    env = _environment(env_file)
    db = _database_path(root, env)
    _demand(db.is_file() and not db.is_symlink(), "PAPER_database_unproven")
    identity = expected_database_identity(root, env)
    _demand(isinstance(identity, str) and len(identity) == 64,
            "PAPER_DB_identity_unproven")
    owner.require_known_natural_drain_ready(OLD_SHA)

    # Historical process instance, not merely the old build SHA, must survive.
    status, health = owner._get(owner._backend + "/api/health", 5)
    _demand(status == 200 and isinstance(health, dict)
            and health.get("ok") is True
            and health.get("database_identity") == identity
            and health.get("build_sha") == OLD_SHA
            and health.get("paper_live_safe") is True
            and health.get("process_instance_id") == EXPECTED_PROCESS_INSTANCE,
            "original_backend_instance_changed")

    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=3) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        _demand(conn.execute("PRAGMA quick_check").fetchone()[0] == "ok",
                "PAPER_DB_integrity_unproven")
        _assert_legacy_paper_quiescence(conn)
        candidates = conn.execute(
            "SELECT candidate_id, status FROM robot_candidates WHERE trading_account_id=? "
            "AND (status IS NULL OR status NOT IN "
            "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))",
            ("paper",),
        ).fetchall()
        _demand(all(status == "APPROVED" for _, status in candidates),
                "active_candidate_not_approved")
        _demand(len({cid for cid, _ in candidates}) == len(candidates),
                "ambiguous_candidate_identity")
        store = SQLiteStore(conn, db, 3000)
        for cid, _ in candidates:
            candidate = store.get_robot_candidate(cid)
            _demand(candidate is not None and candidate.trading_account_id == TradingAccountId("paper")
                    and store.prove_approved_candidate_never_traded(candidate),
                    "approval_not_proven_inert")


def recover_paused_successor(
    target: str, stage: Path, *, root: Path = ROOT, env_file: Path = ENV_FILE,
    transactions: Path = TRANSACTIONS, manifest: Path = MANIFEST, uid: int = 0,
) -> str:
    """One authorized no-STOP-replay action; seal attempt before any owner POST."""
    from tools.paper_maintenance import (
        _proven_prior_exceptional_completion, _complete_stop_intent,
        resume_installed_release,
    )
    from tools.paper_interrupted_stop_recovery import _trusted_journal

    _demand(_sha(target) and target not in (OLD_SHA, PRIOR_STOP), "invalid_successor_SHA")
    _demand(os.geteuid() == uid, "root_required")
    _demand(stage.is_dir() and not stage.is_symlink()
            and Path(__file__).resolve().parents[1] == stage.resolve(),
            "must_execute_attested_staging_source_not_live_backend_code")
    _demand(root.is_dir() and not root.is_symlink()
            and not (root / ".git").exists(), "not_Gitless_layout")
    _trusted_journal(transactions, uid)
    _trusted_prior(transactions, uid)

    # No competing outstanding STOP, and no ready or ambiguous successor work.
    for marker in transactions.glob(".stop-invoked-*"):
        prior = marker.name.removeprefix(".stop-invoked-")
        _demand(prior == PRIOR_STOP or _proven_prior_exceptional_completion(
            transactions, prior, root=root, uid=uid,
        ), "other_unresolved_STOP_intent")
    _demand(not (transactions / (".stop-invoked-" + target)).exists(),
            "successor_has_other_STOP_intent")

    # The successor may resume an *already sealed* stopped-only install, never
    # replay an attempted shutdown whose outcome was unknown.
    attempted = _receipt(transactions, "attempt", target, uid)
    completed = _receipt(transactions, "completed", target, uid)
    _demand(not completed or attempted, "completed_without_attempt")
    installed = verify_release(root, manifest)
    _demand(installed in (OLD_SHA, target), "installed_release_changed")
    if not completed:
        _demand(not attempted, "prior_continuation_outcome_unknown_no_retry")
        _demand(installed == OLD_SHA, "old_backend_no_longer_installed")
        _demand(not (transactions / target).exists(), "unexpected_successor_install_journal")

        inspect_staged_release(target, stage=stage, root=root, manifest=manifest, uid=uid)
        owner = RuntimeShutdown(root=root, env=_environment(env_file))
        _prove_no_live_ownership(root, env_file, owner)
        _demand(verify_release(root, manifest) == OLD_SHA, "old_release_changed_before_attempt")

        lock_fd = os.open(transactions / ".release.lock", os.O_RDWR | os.O_NOFOLLOW)
        with os.fdopen(lock_fd, "rb") as lock:
            metadata = os.fstat(lock.fileno())
            _demand(stat.S_ISREG(metadata.st_mode)
                    and metadata.st_uid == uid and not metadata.st_mode & 0o077,
                    "untrusted_release_lock")
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            _trusted_prior(transactions, uid)
            _demand(not _marker(transactions, "attempt").exists(),
                    "concurrent_or_prior_continuation")
            _prove_no_live_ownership(root, env_file, owner)
            _write_once(transactions, "attempt", target)

        # NO canonical STOP replay. This starts only from PAUSED/no OPEN
        # ownership and uses the existing canonical engine for remaining steps.
        try:
            result = owner.continue_known_natural_drain(OLD_SHA)
        except Exception as exc:
            raise PausedSuccessorBlocked(
                "continuation_outcome_unknown_no_retry:" + type(exc).__name__
            ) from exc
        _demand(isinstance(result, ShutdownResult) and result.scope == SCOPE_ALL
                and result.ok is True and result.runtime_stopped is True,
                "continuation_unproven_no_retry")
        _write_once(transactions, "completed", target)
    else:
        _demand(installed == OLD_SHA or (transactions / target).is_dir(),
                "installed_successor_without_transaction")
        result = ShutdownResult(
            SCOPE_ALL, True, "Prior fsynced successor continuation", runtime_stopped=True,
        )

    if verify_release(root, manifest) == OLD_SHA:
        receipt = activate_staged_release(
            target, stage=stage, stopped_proof=result, root=root,
            manifest=manifest, transactions=transactions, uid=uid,
        )
        _demand(isinstance(receipt, str) and receipt.startswith("INSTALLED_STOPPED:"),
                "successor_install_unproven")
    _demand(proven_paused_successor(
        transactions, PRIOR_STOP, target, root=root, uid=uid, require_ready=False,
    ), "completed_successor_install_proof_unproven")

    status = resume_installed_release(target, root=root, env_file=env_file)
    if isinstance(status, str) and status.startswith("READY:"):
        _complete_stop_intent(transactions, target, uid=uid)
        _demand(proven_paused_successor(
            transactions, PRIOR_STOP, target, root=root, uid=uid, require_ready=True,
        ), "successor_editor_ready_receipt_unproven")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Approved historical PAUSED-drain successor")
    parser.add_argument("target_sha")
    parser.add_argument("--stage", required=True, type=Path)
    options = parser.parse_args(argv)
    try:
        result = recover_paused_successor(options.target_sha, options.stage)
    except Exception as exc:
        print("BLOCKED: paused_drain_successor:"
              + type(exc).__name__ + ":" + str(exc).replace("\n", " ")[:220]
              + "; no STOP replay, no retry, no LIVE")
        return 2
    print(result)
    return 0 if result.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
