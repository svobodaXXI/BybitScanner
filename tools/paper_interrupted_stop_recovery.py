"""Incident-scoped continuation of the 2026-11-04 blocked PAPER STOP.

Never repeats canonical STOP, reconciliation, trading commands or an uncertain
SIGINT. Only a fresh exact JASMY/FLOW proof can authorize one *new* exceptional
handoff, with separate owner approval. Restore EDITOR_ONLY, not PAPER_AUTO.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sqlite3
import stat
import sys

from tools.flat_paper_recovery_transition import get_snapshots
from tools.paper_two_orphan_proof import PROOF_LABEL, inspect_read_only
from tools.runtime_intent import expected_database_identity
from tools.stop_robot_runtime import (
    ABSENT, PRESENT, RuntimeShutdown, SCOPE_ALL, ShutdownResult,
    _database_path, _environment, build_dual_orphan_handoff,
)
from tools.vps_gitless_release_activate import (
    ActivationBlocked, TRANSACTIONS, _sync_directory, _trusted_file,
    activate_staged_release, inspect_staged_release,
)
from tools.vps_release_identity import MANIFEST, ReleaseIdentityBlocked, verify_release
from tools.vps_release_resume import _systemd_state

# Only the actually attempted operation and the verified old backend.
PRIOR_TARGET = "094d74f6699528b47578cb740e8e06a45d8c7840"
OLD_BACKEND = "f100ef369a1105443332b5729b558464c27be48f"
BACKEND_UNIT = "bybitscanner-paper-backend.service"
# Running a module from a verified Git staging checkout must never make that
# checkout the installed root. The Gitless release is a fixed VPS location.
INSTALLED_ROOT = Path("/opt/BybitScanner")
MARKER_PREFIX = ".editor-only-dual-orphan-"


class RecoveryBlocked(RuntimeError):
    pass


def _require(value: bool, reason: str) -> None:
    if not value:
        raise RecoveryBlocked(reason)


def _trusted_journal(transactions: Path, uid: int) -> None:
    _require(transactions.is_dir() and not transactions.is_symlink(),
             "protected_transaction_directory_missing")
    meta = transactions.stat()
    _require(meta.st_uid == uid and not meta.st_mode & 0o077,
             "untrusted_transaction_directory")
    parent = transactions.parent
    _require(parent.is_dir() and not parent.is_symlink()
             and parent.stat().st_uid == uid and not parent.stat().st_mode & 0o022,
             "untrusted_transaction_parent")


def _receipt(transactions: Path, phase: str, uid: int, *, target: str) -> bool:
    path = transactions / (MARKER_PREFIX + phase + "-" + PRIOR_TARGET)
    if not path.exists() and not path.is_symlink():
        return False
    try:
        content = _trusted_file(path, uid)
    except (ActivationBlocked, OSError, ValueError) as exc:
        raise RecoveryBlocked("untrusted_recovery_receipt:" + phase) from exc
    _require(content == (target + "\n").encode("ascii"),
             "recovery_receipt_mismatch:" + phase)
    return True


def _record(transactions: Path, phase: str, uid: int, *, target: str) -> None:
    path = transactions / (MARKER_PREFIX + phase + "-" + PRIOR_TARGET)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write((target + "\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(transactions)


def _backend_stopped() -> bool:
    try:
        info = _systemd_state(BACKEND_UNIT)
        from tools.legacy_runtime_process import probe_listener_pids
        return (isinstance(info, dict)
                and info.get("ActiveState") in ("inactive", "failed")
                and str(info.get("MainPID")) == "0"
                and not probe_listener_pids("127.0.0.1", 8765))
    except (OSError, ValueError):
        return False


def recover_editor_only(
    *, target: str, stage: Path, root: Path = INSTALLED_ROOT, transactions: Path = TRANSACTIONS,
    manifest: Path = MANIFEST, uid: int = 0,
    proof=None, handoff=None, telegram=None, installer=None, resume=None,
    backend_stopped=None, inspect=None,
) -> str:
    """One authorized exceptional handoff and Gitless EDITOR_ONLY activation.

    A prior STOP attempt is never counted as a successful STOP. A durable new
    handoff intent is created before SIGINT; if exit outcome is lost, no retry.
    Each subsequent phase can only continue from its own fsynced receipt and
    independent stopped-service verification.
    """
    from tools.paper_maintenance import resume_installed_release

    _require(len(target) == 40 and all(c in "0123456789abcdef" for c in target)
             and target not in (OLD_BACKEND, PRIOR_TARGET), "invalid_approved_target")
    _require(os.geteuid() == uid, "root_operator_required")
    _require(root.is_dir() and not root.is_symlink() and not (root / ".git").exists(),
             "unexpected_installed_layout")
    _require(stage.is_dir() and not stage.is_symlink(),
             "staged_release_missing")
    _trusted_journal(transactions, uid)
    try:
        _require(_trusted_file(transactions / (".chatops-invoked-" + PRIOR_TARGET), uid)
                 == (PRIOR_TARGET + "\n").encode("ascii"),
                 "prior_chatops_intent_mismatch")
        _require(
            _trusted_file(transactions / (".stop-invoked-" + PRIOR_TARGET), uid)
            == b"STOP_INVOKED; not install authorization\\n",
            "prior_canonical_stop_intent_mismatch",
        )
    except (ActivationBlocked, OSError, ValueError) as exc:
        raise RecoveryBlocked("original_stop_intent_unproven") from exc
    _require(not (transactions / PRIOR_TARGET).exists(),
             "original_install_transaction_not_absent")
    _require(not (transactions / (".stop-confirmed-" + PRIOR_TARGET)).exists(),
             "original_stop_success_already_recorded")
    _require(not any(
        p.name != ".stop-invoked-" + PRIOR_TARGET
        for p in transactions.glob(".stop-invoked-*")
    ), "other_unresolved_stop_intent")

    env = _environment(Path("/etc/bybitscanner/paper.env"))
    expected_db = expected_database_identity(root, env)
    _require(bool(expected_db) and len(expected_db) == 64,
             "paper_database_identity_unproven")
    prior_release = verify_release(root, manifest)
    _require(prior_release in (OLD_BACKEND, target),
             "installed_release_changed")
    if prior_release == target:
        _require(_receipt(transactions, "handoff-proven", uid, target=target),
                 "target_installed_without_confirmed_handoff")
        status = (resume or resume_installed_release)(
            target, root=root, env_file=Path("/etc/bybitscanner/paper.env"))
        return status

    # The old release must still be byte-for-byte pinned before either proof
    # or activation. No tracked files are hot-swapped under the live Backend.
    (inspect or inspect_staged_release)(
        target, stage=stage, root=root, manifest=manifest, uid=uid)
    started = _receipt(transactions, "handoff-attempt", uid, target=target)
    backend_confirmed = _receipt(transactions, "backend-exited", uid, target=target)
    handoff_proven = _receipt(transactions, "handoff-proven", uid, target=target)
    _require(not handoff_proven or backend_confirmed,
             "handoff_receipt_order_invalid")
    _require(not backend_confirmed or started,
             "backend_exit_receipt_without_attempt")

    if not started:
        # Fresh HTTP/SQLite proof is only a preflight, NOT a STOP receipt.
        snapshots = get_snapshots()
        from tools.paper_two_orphan_proof import inspect_read_only as real_proof
        evidence = (proof or real_proof)(
            _database_path(root, env), expected_identity=expected_db,
            snapshots=snapshots,
        )
        _require(evidence == PROOF_LABEL, "immutable_dual_orphan_proof_unproven")
        owner = RuntimeShutdown(root=root, env=env)
        _require(owner._probe_backend() == PRESENT, "old_backend_not_proven")
        owner._require_scanner_stopped()
        owner._require_autopilot_off()
        owner._probe_telegram()  # fail closed on foreign Telegram owner
        _record(transactions, "handoff-attempt", uid, target=target)
        # The existing incident-specific function repeats immutable SQL proof
        # under BEGIN IMMEDIATE and reattests exact PID/listener/cgroup.
        outcome = (handoff or build_dual_orphan_handoff(env))()
        _require(outcome == "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed",
                 "exceptional_handoff_outcome_unknown_no_retry")
        _record(transactions, "backend-exited", uid, target=target)
        backend_confirmed = True
    else:
        _require(backend_confirmed, "prior_handoff_outcome_unknown_no_retry")

    _require((backend_stopped or _backend_stopped)(),
             "backend_stopped_identity_not_proven")
    if not handoff_proven:
        owner = RuntimeShutdown(root=root, env=env)
        state = owner._probe_telegram()
        telegram_attempted = _receipt(transactions, "telegram-attempt", uid, target=target)
        if state == PRESENT:
            _require(not telegram_attempted, "telegram_shutdown_outcome_unknown_no_retry")
            _record(transactions, "telegram-attempt", uid, target=target)
            # Existing canonical Telegram shutdown uses exact DB identity.
            if telegram is None:
                from tools.stop_robot_runtime import TELEGRAM
                owner._shutdown(owner._telegram + "/shutdown",
                                owner._telegram + "/health",
                                "Telegram monitoring", TELEGRAM, "telegram")
            else:
                telegram()
        _require(owner._probe_telegram() == ABSENT,
                 "telegram_absence_unproven")
        # Installation still rechecks every systemd unit and listener.
        _record(transactions, "handoff-proven", uid, target=target)

    receipt = (installer or activate_staged_release)(
        target, stage=stage,
        stopped_proof=ShutdownResult(
            SCOPE_ALL, True, "Fresh separately authorized dual-orphan handoff",
            runtime_stopped=True,
        ),
        root=root, manifest=manifest, transactions=transactions, uid=uid,
    )
    _require(isinstance(receipt, str) and receipt.startswith("INSTALLED_STOPPED:"),
             "immutable_release_install_unproven")
    return (resume or resume_installed_release)(
        target, root=root, env_file=Path("/etc/bybitscanner/paper.env"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exact 2026-11-04 interrupted PAPER STOP recovery")
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--target", required=True)
    parser.add_argument("--execute-exceptional-handoff", action="store_true")
    args = parser.parse_args(argv)
    if not args.execute_exceptional_handoff:
        print("BLOCKED: exact target and separately authorized handoff required")
        return 2
    try:
        outcome = recover_editor_only(
            target=args.target, stage=args.stage, root=INSTALLED_ROOT,
        )
    except Exception as exc:
        # Preserve every one-shot receipt. Never retry an unknown result or
        # expose env/secrets/HTTP bodies to the operator.
        print("BLOCKED: " + type(exc).__name__ + "; no retry, no deployment continuation")
        return 2
    print(outcome)
    return 0 if outcome.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
