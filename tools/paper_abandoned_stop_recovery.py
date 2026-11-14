"""One-shot recovery of an abandoned confirmed STOP before Gitless installation.

This is NOT an install or a STOP replay. It preserves the original receipts,
fences unknown outcomes durably, and only restores the exact previous EDITOR_ONLY
Backend while a separately verified Telegram monitor remains healthy.

The tool must be shipped via an independently authorized, protected mechanism;
its presence in GitHub is not authorization to copy it onto a stopped VPS.
"""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys

from tools.vps_gitless_release_activate import (
    TRANSACTIONS, _sync_directory, _trusted_file,
)
from tools.vps_release_identity import verify_release

ROOT = Path("/opt/BybitScanner")
SHA_CHARS = set("0123456789abcdef")
BACKEND = "bybitscanner-paper-backend.service"
PREFIX = ("sudo", "-n")


class AbandonedStopBlocked(RuntimeError):
    pass


def _demand(value: bool, reason: str) -> None:
    if not value:
        raise AbandonedStopBlocked(reason)


def _sha(value: str) -> bool:
    return len(value) == 40 and all(c in SHA_CHARS for c in value)


def _receipt_payload(old: str, target: str) -> bytes:
    return (old + ":" + target + "\n").encode("ascii")


def _paths(transactions: Path, target: str) -> tuple[Path, Path]:
    return (transactions / (".abandoned-stop-attempt-" + target),
            transactions / (".abandoned-stop-restored-" + target))


def _trusted_directory(path: Path, uid: int) -> None:
    _demand(path.is_dir() and not path.is_symlink()
            and path.stat().st_uid == uid
            and not path.stat().st_mode & 0o077,
            "untrusted_release_transaction_directory")


def _write_once(path: Path, payload: bytes, directory: Path) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(directory)


def proven_abandoned_stop(
    transactions: Path, target: str, *, root: Path, uid: int,
    require_installed: bool = True,
) -> bool:
    """Only a sealed, exactly matched old-release recovery retires the STOP fence."""
    from tools.paper_maintenance import _confirmed_stop_receipt
    try:
        if not _sha(target):
            return False
        _trusted_directory(transactions, uid)
        attempt, restored = _paths(transactions, target)
        if (transactions / target).exists() or (transactions / target).is_symlink():
            return False
        payload = _trusted_file(restored, uid)
        if len(payload) != 82 or payload[-1:] != b"\n":
            return False
        old = payload[:40].decode("ascii")
        if not _sha(old) or old == target or payload != _receipt_payload(old, target):
            return False
        if _trusted_file(attempt, uid) != payload:
            return False
        if not _confirmed_stop_receipt(transactions, target, old, uid=uid):
            return False
        return not require_installed or verify_release(root) == old
    except (OSError, ValueError, UnicodeError, AbandonedStopBlocked):
        return False


def _host_preflight(old: str, identity: str, *, root: Path, env_file: Path | None) -> bool:
    from tools.paper_maintenance import _durable_editor_freeze, _editor_telegram_ready
    from tools.paper_stopped_approved_recovery import _post_shutdown_durable_proof
    from tools.stop_robot_runtime import _database_path, _environment
    from tools.vps_release_resume import _systemd_state
    from tools.legacy_runtime_process import probe_listener_pids

    _demand(_durable_editor_freeze(root, env_file) == identity,
            "editor_freeze_or_database_identity_changed")
    db = _database_path(root, _environment(env_file))
    _post_shutdown_durable_proof(db, identity, root=root)
    # Backend's loaded unit must be exactly the installed tracked release.
    system_unit = Path("/etc/systemd/system") / BACKEND
    release_unit = root / "deploy/systemd" / BACKEND
    _demand(system_unit.is_file() and not system_unit.is_symlink()
            and release_unit.is_file() and not release_unit.is_symlink()
            and system_unit.read_bytes() == release_unit.read_bytes(),
            "backend_unit_not_exact_installed_release")
    state = _systemd_state(BACKEND)
    _demand(state.get("ActiveState") in ("inactive", "failed")
            and state.get("MainPID") == "0", "backend_owner_not_stopped")
    scanner = _systemd_state("bybitscanner-scanner.service")
    _demand(scanner.get("ActiveState") in ("inactive", "failed")
            and scanner.get("MainPID") == "0", "scanner_service_not_stopped")
    _demand(not any(probe_listener_pids(address, 8765)
                    for address in ("127.0.0.1", "0.0.0.0", "::1")),
            "backend_listener_not_absent")
    if _editor_telegram_ready(identity):
        return False  # Preserve an already healthy Telegram owner.
    # A stopped Telegram owner is eligible for exactly one start under the same
    # recovery attempt fence. An active-but-unhealthy owner must never be reset.
    telegram = "bybitscanner-telegram.service"
    system_telegram = Path("/etc/systemd/system") / telegram
    release_telegram = root / "deploy/systemd" / telegram
    _demand(system_telegram.is_file() and not system_telegram.is_symlink()
            and release_telegram.is_file() and not release_telegram.is_symlink()
            and system_telegram.read_bytes() == release_telegram.read_bytes(),
            "telegram_unit_not_exact_installed_release")
    telegram_state = _systemd_state(telegram)
    _demand(telegram_state.get("ActiveState") in ("inactive", "failed")
            and telegram_state.get("MainPID") == "0", "telegram_owner_not_stopped")
    _demand(not any(probe_listener_pids(address, 8766)
                    for address in ("127.0.0.1", "0.0.0.0", "::1")),
            "telegram_listener_not_absent")
    return True


def recover_abandoned_stop(
    target: str, old: str, *, root: Path = ROOT,
    transactions: Path = TRANSACTIONS, env_file: Path | None = None,
    uid: int = 0, runner=subprocess.run,
    freeze=None, host_preflight=None, ready=None,
) -> str:
    """One owner-approved attempt; no repeat start if the first outcome is unknown."""
    from tools.paper_maintenance import (
        _confirmed_stop_receipt, _durable_editor_freeze, _editor_runtime_ready,
        _proven_prior_exceptional_completion,
    )

    _demand(_sha(target) and _sha(old) and target != old, "invalid_exact_sha_pair")
    _demand(os.geteuid() == uid, "trusted_operator_required")
    _trusted_directory(transactions, uid)
    # Existing canonical lock is shared with STOP staging to prevent concurrent actions.
    lock_path = transactions / ".release.lock"
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
    with os.fdopen(lock_fd, "rb") as lock:
        meta = os.fstat(lock.fileno())
        _demand(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid
                and not meta.st_mode & 0o077, "untrusted_release_lock")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AbandonedStopBlocked("concurrent_release_operation") from exc
        _demand(verify_release(root) == old, "previous_release_changed")
        _demand(not (transactions / target).exists()
                and not (transactions / target).is_symlink(),
                "target_install_journal_exists")
        _demand(_confirmed_stop_receipt(transactions, target, old, uid=uid),
                "old_to_target_canonical_STOP_unproven")

        # Never recover into a second unresolved release transaction.
        for marker in transactions.glob(".stop-invoked-*"):
            other = marker.name.removeprefix(".stop-invoked-")
            if other == target:
                continue
            _demand(_sha(other) and (
                (transactions / other / "editor-ready").exists()
                and _trusted_file(transactions / other / "editor-ready", uid)
                == other.encode("ascii")
                or _proven_prior_exceptional_completion(
                    transactions, other, root=root, uid=uid)),
                "another_unresolved_STOP_intent")

        attempt, restored = _paths(transactions, target)
        payload = _receipt_payload(old, target)
        probe = ready or _editor_runtime_ready
        if restored.exists() or restored.is_symlink():
            _demand(proven_abandoned_stop(transactions, target, root=root, uid=uid)
                    and probe(old, (freeze or _durable_editor_freeze)(root, env_file)),
                    "completed_abandoned_stop_postcondition_unproven")
            return "READY: previously restored exact EDITOR_ONLY; no new service action"
        _demand(not attempt.exists() and not attempt.is_symlink(),
                "prior_recovery_attempt_outcome_unknown_no_retry")

        identity = (freeze or _durable_editor_freeze)(root, env_file)
        _demand(isinstance(identity, str) and len(identity) == 64,
                "PAPER_database_identity_unproven")
        start_telegram = (host_preflight or _host_preflight)(
            old, identity, root=root, env_file=env_file) is True
        _demand(verify_release(root) == old, "installed_release_changed_during_preflight")
        _write_once(attempt, payload, transactions)
        # One durable attempt fences BOTH services, including transport failure
        # between starts. Never start Backend until Telegram identity is proven.
        if start_telegram:
            try:
                telegram_result = runner(
                    [*PREFIX, "systemctl", "start", "bybitscanner-telegram.service"],
                    cwd=root, capture_output=True, text=True, timeout=180, check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise AbandonedStopBlocked("telegram_start_outcome_unknown_no_retry") from exc
            _demand(telegram_result.returncode == 0, "telegram_start_failed_no_retry")
            from tools.paper_maintenance import _editor_telegram_ready
            _demand(_editor_telegram_ready(identity),
                    "telegram_postcondition_unproven_no_retry")
        try:
            result = runner(
                [*PREFIX, "systemctl", "start", BACKEND],
                cwd=root, capture_output=True, text=True, timeout=180, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AbandonedStopBlocked("backend_start_outcome_unknown_no_retry") from exc
        _demand(result.returncode == 0, "backend_start_failed_no_retry")
        _demand(probe(old, identity), "EDITOR_ONLY_postcondition_unproven_no_retry")
        _demand((freeze or _durable_editor_freeze)(root, env_file) == identity,
                "editor_freeze_changed_after_start")
        _demand(verify_release(root) == old, "release_changed_after_start")
        _write_once(restored, payload, transactions)
        return "READY: previous EDITOR_ONLY restored; abandoned STOP sealed; no STOP replay"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="One-shot confirmed-STOP no-stage recovery")
    parser.add_argument("--abandoned-target", required=True)
    parser.add_argument("--installed-sha", required=True)
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    args = parser.parse_args(argv)
    try:
        print(recover_abandoned_stop(
            args.abandoned_target, args.installed_sha, env_file=args.env_file))
        return 0
    except Exception as exc:
        print("BLOCKED: abandoned_stop_recovery:" + type(exc).__name__
              + ":" + str(exc).replace("\n", " ")[:180]
              + "; no STOP or retry", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
