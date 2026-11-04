"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path
from decimal import Decimal

from tools.stop_robot_runtime import RuntimeShutdown, SCOPE_ALL, _environment


def _durable_editor_freeze(root: Path, env_file: Path | None) -> str:
    """Prove admission freeze from the existing PAPER SQLite, without writing it."""
    import sqlite3
    from tools.runtime_intent import expected_database_identity
    from tools.stop_robot_runtime import _database_path

    env = _environment(env_file)
    path = _database_path(root, env)
    if not path.is_file() or path.is_symlink():
        raise ValueError("PAPER_database_missing_or_symlink")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("PAPER_database_integrity_unproven")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("PAPER_database_foreign_key_conflict")
        scanner = conn.execute(
            "SELECT mode FROM scanner_runtime_state WHERE trading_account_id='paper'"
        ).fetchone()
        autopilot = conn.execute(
            "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'"
        ).fetchone()
    if scanner != ("SCANNER_STOPPED",) or autopilot != ("OFF",):
        raise ValueError("EDITOR_ONLY_requires_durable_Scanner_STOPPED_and_Autopilot_OFF")
    return expected_database_identity(root, env)


def _editor_backend_ready(target: str, database_identity: str) -> bool:
    """Prove the running backend's exact release and frozen trading admission."""
    from tools.runtime_intent import http_get

    try:
        health = http_get("http://127.0.0.1:8765/api/health", 3)
        scanner = http_get("http://127.0.0.1:8765/api/scanner/status", 3)
        autopilot = http_get("http://127.0.0.1:8765/api/robot/autopilot", 3)
        if not all(x.status == 200 for x in (health, scanner, autopilot)):
            return False
        h, s, a = (x.json() for x in (health, scanner, autopilot))
        return (
            isinstance(h, dict) and h.get("ok") is True
            and h.get("component") == "paper_backend"
            and h.get("mode") == "paper"
            and h.get("paper_live_safe") is True
            and h.get("build_sha") == target
            and h.get("database_identity") == database_identity
            and isinstance(s, dict) and s.get("ok") is True
            and s.get("mode") == "SCANNER_STOPPED"
            and isinstance(a, dict) and a.get("ok") is True
            and a.get("trading_account_id") == {"value": "paper"}
            and a.get("mode") == "OFF"
        )
    except Exception:
        return False


def _editor_telegram_ready(database_identity: str) -> bool:
    from tools.runtime_intent import http_get

    try:
        response = http_get("http://127.0.0.1:8766/health", 3)
        if response.status != 200:
            return False
        body = response.json()
        return (isinstance(body, dict)
                and body.get("component") == "telegram_monitoring"
                and body.get("status") == "ready"
                and body.get("database_identity") == database_identity)
    except Exception:
        return False


def _editor_runtime_ready(target: str, database_identity: str) -> bool:
    return (_editor_backend_ready(target, database_identity)
            and _editor_telegram_ready(database_identity))


def _resume_missing_telegram(
    target: str, database_identity: str, *, root: Path, runner,
    probe,
) -> str:
    """A partial successful resume only needs its proven-absent Telegram worker."""
    from tools.legacy_runtime_process import LegacyOwnerUnproven, probe_listener_pids
    from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
    from tools.vps_release_resume import ResumeBlocked, UNIT_DIR, _systemd_state

    unit = "bybitscanner-telegram.service"
    try:
        if verify_release(root) != target:
            raise ResumeBlocked("installed_release_differs")
        installed = UNIT_DIR / unit
        source = root / "deploy/systemd" / unit
        if (installed.is_symlink() or not installed.is_file()
                or installed.read_bytes() != source.read_bytes()):
            raise ResumeBlocked("telegram_unit_mismatch")
        state = _systemd_state(unit)
        if (not isinstance(state, dict)
                or state.get("ActiveState") not in ("inactive", "failed")
                or str(state.get("MainPID")) != "0"):
            raise ResumeBlocked("telegram_unit_not_stopped")
        if probe_listener_pids("127.0.0.1", 8766):
            raise ResumeBlocked("telegram_listener_not_absent")
    except (ResumeBlocked, ReleaseIdentityBlocked, LegacyOwnerUnproven, OSError):
        return "BLOCKED: Telegram_owner_or_release_not_proven; no start attempted"
    try:
        result = runner(
            [*PREFIX, "systemctl", "start", unit],
            cwd=root, capture_output=True, text=True, timeout=180, check=False,
        )
        if result.returncode != 0:
            return "BLOCKED: Telegram_start_failed_or_unknown; no retry"
    except (OSError, subprocess.TimeoutExpired):
        return "BLOCKED: Telegram_start_outcome_unknown; no retry"
    if not probe(target, database_identity):
        return "BLOCKED: EDITOR_ONLY_postconditions_unproven; Backend preserved"
    return "READY: Telegram recovered in EDITOR_ONLY; Backend not restarted"


def resume_installed_release(
    target: str, *, root: Path, env_file: Path | None,
    runner=subprocess.run, resume_proof=None, freeze_proof=None,
    runtime_ready=None,
) -> str:
    """Resume a VERIFIED, already-installed Gitless release without STOP/deploy.

    An active-but-unreachable Backend cannot pass the stopped/listener proof.
    Each service start is attempted once; on unknown outcome, the next run
    must independently re-observe readiness, not re-send STOP or SIGINT.
    This is not an installer, and never starts Scanner or PAPER_AUTO.
    """
    from tools.vps_release_resume import ResumeBlocked, check_resume

    if len(target) != 40 or any(c not in "0123456789abcdef" for c in target):
        return "BLOCKED: invalid_approved_target"
    try:
        identity = (freeze_proof or _durable_editor_freeze)(root, env_file)
        if not isinstance(identity, str) or len(identity) != 64:
            return "BLOCKED: PAPER_database_identity_unproven"
    except (OSError, ValueError, sqlite3.Error) as exc:
        return "BLOCKED: editor_only_freeze_unproven:" + type(exc).__name__
    probe = runtime_ready or _editor_runtime_ready
    if probe(target, identity):
        from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
        if resume_proof is None:
            try:
                if verify_release(root) != target:
                    return "BLOCKED: installed_release_content_changed"
            except (ReleaseIdentityBlocked, OSError):
                return "BLOCKED: installed_release_content_unproven"
        return "READY: exact installed PAPER release, Telegram and EDITOR_ONLY already proven; no mutation"
    # If the backend was started before a transport failure, do not restart
    # it or re-run STOP. Recover only a proven-absent worker, one time.
    if runtime_ready is None and _editor_backend_ready(target, identity):
        return _resume_missing_telegram(
            target, identity, root=root, runner=runner, probe=probe,
        )
    try:
        receipt = (resume_proof or check_resume)(target, root=root)
        if not isinstance(receipt, str) or not receipt.startswith("RESUME_READY:"):
            raise ResumeBlocked("installed_release_resume_unproven")
    except (ResumeBlocked, OSError, ValueError) as exc:
        return "BLOCKED: installed_release_not_stopped_and_verified:" + type(exc).__name__

    def command(*argv: str) -> bool:
        try:
            answer = runner(list(argv), cwd=root, capture_output=True, text=True,
                            timeout=180, check=False)
            return answer.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    if not command(*PREFIX, str(root / "venv/bin/python"), "-m",
                   "tools.vps_systemd_unit_prepare"):
        return "BLOCKED: unit_prepare_failed_or_unknown; no service started"
    if not command(*PREFIX, "systemctl", "start", "bybitscanner-paper-backend.service"):
        return "BLOCKED: backend_start_failed_or_unknown; do not retry before observing owner"
    if not command(*PREFIX, "systemctl", "start", "bybitscanner-telegram.service"):
        return "BLOCKED: telegram_start_failed_or_unknown; Backend preserved, no trade ingress requested"
    if not probe(target, identity):
        return "BLOCKED: EDITOR_ONLY_postconditions_unproven; no Scanner or PAPER_AUTO requested"
    return "READY: exact installed PAPER release, Telegram and EDITOR_ONLY proven; no Scanner/PAPER_AUTO start"


REPO = Path("/opt/BybitScanner")
SERVICE = "bybitscanner-paper-start.service"
PREFIX = ("sudo", "-n")




def _complete_stop_intent(journal_root: Path, target: str, *, uid: int) -> None:
    """Record post-resume success only; never grant STOP or install authority."""
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, _sync_directory, _trusted_file,
    )
    marker = journal_root / (".stop-invoked-" + target)
    if not marker.exists():
        return  # An existing release may predate one-shot STOP fencing.
    _trusted_file(marker, uid)
    journal = journal_root / target
    if not journal.exists():
        return  # No protected installer transaction to attest.
    if (not journal.is_dir() or journal.is_symlink()
            or journal.stat().st_uid != uid or journal.stat().st_mode & 0o077):
        raise ActivationBlocked("untrusted_completed_release_transaction")
    done = journal / "editor-ready"
    if done.exists():
        if _trusted_file(done, uid) != target.encode("ascii"):
            raise ActivationBlocked("completed_release_receipt_mismatch")
        return
    fd = os.open(done, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(target.encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(journal)


def _record_one_shot_stop_intent(journal_root: Path, target: str, *, uid: int) -> bool:
    """Durably fence STOP replay before the first irreversible owner call.

    This is only a stop-attempt marker, never an install entitlement. A crash
    before the installer's protected transaction requires a separate verified
    recovery decision, not a second STOP or an unproven release switch.
    """
    from tools.vps_gitless_release_activate import ActivationBlocked, _sync_directory, _trusted_file

    parent = journal_root.parent
    if (not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != uid or parent.stat().st_mode & 0o022):
        raise ActivationBlocked("untrusted_stop_intent_parent")
    if not journal_root.exists():
        journal_root.mkdir(mode=0o700)
        _sync_directory(parent)
    if (not journal_root.is_dir() or journal_root.is_symlink()
            or journal_root.stat().st_uid != uid
            or journal_root.stat().st_mode & 0o077):
        raise ActivationBlocked("untrusted_stop_intent_directory")
    # Do not follow a user-substituted lock symlink or trust an externally
    # writable lock inode when serializing irreversible STOP intent.
    lock_path = journal_root / ".release.lock"
    descriptor = os.open(
        lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600,
    )
    with os.fdopen(descriptor, "a+b") as lock:
        meta = os.fstat(lock.fileno())
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != uid
                or meta.st_mode & 0o077):
            raise ActivationBlocked("untrusted_release_lock")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # An unresolved STOP from another requested release is still the same
        # runtime side effect. Changing the target SHA must not replay it.
        for marker in journal_root.glob(".stop-invoked-*"):
            previous = marker.name.removeprefix(".stop-invoked-")
            if (len(previous) != 40 or any(ch not in "0123456789abcdef" for ch in previous)
                    or marker.is_symlink() or not marker.is_file()
                    or marker.stat().st_uid != uid or marker.stat().st_mode & 0o077):
                raise ActivationBlocked("untrusted_prior_STOP_intent")
            # A previous READY install may be superseded; a mere journal
            # directory or a STOP intent is not completion evidence.
            completed = journal_root / previous / "editor-ready"
            if completed.exists() or completed.is_symlink():
                if (journal_root / previous).is_symlink():
                    raise ActivationBlocked("untrusted_completed_release_transaction")
                if _trusted_file(completed, uid) != previous.encode("ascii"):
                    raise ActivationBlocked("completed_release_receipt_mismatch")
                continue
            return False
        marker = journal_root / (".stop-invoked-" + target)
        if marker.exists() or marker.is_symlink():
            return False
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        try:
            fd = os.open(marker, flags, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"STOP_INVOKED; not install authorization\\n")
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(journal_root)
        return True



def _confirmed_stop_receipt(
    journal_root: Path, target: str, old_sha: str, *, uid: int,
    record: bool = False,
) -> bool:
    """A durable successful STOP return, distinct from the pre-call intent.

    Only the canonical successful response may create this receipt. Recovery
    also re-proves the old installed release, exact stage and stopped host;
    neither a STOP attempt marker nor absent listeners alone can grant it.
    """
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, _sync_directory, _trusted_file,
    )

    parent = journal_root.parent
    if (not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != uid or parent.stat().st_mode & 0o022
            or not journal_root.is_dir() or journal_root.is_symlink()
            or journal_root.stat().st_uid != uid
            or journal_root.stat().st_mode & 0o077):
        raise ActivationBlocked("untrusted_stop_receipt_directory")
    if (not isinstance(old_sha, str) or len(old_sha) != 40
            or any(ch not in "0123456789abcdef" for ch in old_sha)):
        raise ActivationBlocked("old_release_identity_unproven")
    marker = journal_root / (".stop-invoked-" + target)
    if _trusted_file(marker, uid) != b"STOP_INVOKED; not install authorization\\n":
        raise ActivationBlocked("stop_intent_receipt_mismatch")
    payload = f"CANONICAL_ALL_STOP_CONFIRMED:{old_sha}:{target}\n".encode("ascii")
    receipt = journal_root / (".stop-confirmed-" + target)
    if record:
        # O_EXCL means even a pre-existing apparently valid receipt cannot
        # turn another STOP invocation into a second confirmation.
        fd = os.open(
            receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(journal_root)
        return True
    if not receipt.exists() and not receipt.is_symlink():
        return False
    if _trusted_file(receipt, uid) != payload:
        raise ActivationBlocked("stop_completed_receipt_mismatch")
    return True



def deploy_staged_editor_only(
    target: str, *, stage: Path, root: Path = REPO, env_file: Path | None = None,
    dual_orphan_handoff: bool = False, stop=None, preflight=None,
    installer=None, resume=None, manifest=None, unit_dir=None,
    transactions=None, trusted_uid: int = 0,
) -> str:
    """Single bounded intent: preflight -> canonical STOP -> Gitless switch -> Editor.

    No stage mutation before exact old/target evidence. A durable prior
    installation transaction may resume read-only ownership proofs without
    invoking STOP or any other trading action again. EDITOR_ONLY does not
    resume Scanner or PAPER_AUTO.
    """
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, TRANSACTIONS, UNIT_DIR, activate_staged_release,
        inspect_staged_release,
    )
    from tools.vps_release_identity import (
        MANIFEST, ReleaseIdentityBlocked, verify_release,
    )
    from tools.stop_robot_runtime import build_dual_orphan_handoff

    if len(target) != 40 or any(ch not in "0123456789abcdef" for ch in target):
        return "BLOCKED: invalid_approved_target"
    if (not root.is_dir() or root.is_symlink() or (root / ".git").exists()
            or not stage.is_dir() or stage.is_symlink()):
        return "BLOCKED: incorrect_Gitless_release_layout"
    manifest_path = manifest or MANIFEST
    installed_units = unit_dir or UNIT_DIR
    journal_root = transactions or TRANSACTIONS
    journal = journal_root / target

    resume_action = resume or resume_installed_release
    install_action = installer or activate_staged_release

    def finish_resume() -> str:
        observed = resume_action(target, root=root, env_file=env_file)
        if isinstance(observed, str) and observed.startswith("READY:"):
            _complete_stop_intent(journal_root, target, uid=trusted_uid)
        return observed
    try:
        try:
            current = verify_release(root, manifest_path)
        except (ReleaseIdentityBlocked, OSError):
            if not journal.is_dir() or journal.is_symlink():
                return "BLOCKED: installed_release_unproven_without_transaction"
            current = None
        if current == target:
            # Already-ready installations must be idempotent (and may have
            # live units); never touch their protected journal in that case.
            observed = finish_resume()
            if (not journal.is_dir() or
                    (isinstance(observed, str) and observed.startswith("READY:"))):
                return observed
            # If manifest commit preceded a crash copying systemd units, a
            # stopped-only installer can complete the pinned transaction.
            # It reattests stopped units and ports; no STOP is replayed.
            receipt = install_action(
                target, stage=stage, stopped_proof=None, root=root,
                manifest=manifest_path, unit_dir=installed_units,
                transactions=journal_root, uid=trusted_uid,
            )
            if (not isinstance(receipt, str)
                    or not receipt.startswith("INSTALLED_STOPPED:")):
                return "BLOCKED: installed_release_postcondition_unknown; do not start"
            return finish_resume()
        if not journal.is_dir():
            # A pending STOP for any other SHA remains a global one-shot fence.
            # For this SHA, only a separately fsynced successful STOP return
            # can bridge the crash window before the installer creates a journal.
            pending = [
                marker for marker in journal_root.glob(".stop-invoked-*")
                if not (journal_root / marker.name.removeprefix(".stop-invoked-")).is_dir()
            ] if journal_root.is_dir() else []
            if pending:
                if (len(pending) != 1
                        or pending[0].name != ".stop-invoked-" + target
                        or not _confirmed_stop_receipt(
                            journal_root, target, current, uid=trusted_uid,
                        )):
                    return "BLOCKED: prior_STOP_outcome_unproven_without_install_journal; no replay"
                (preflight or inspect_staged_release)(
                    target, stage=stage, root=root, manifest=manifest_path,
                    unit_dir=installed_units, uid=trusted_uid,
                )
                # An fsynced receipt documents the canonical success already
                # observed, not a guess based on missing processes. The real
                # installer independently reattests stopped units/listeners.
                result = ShutdownResult(
                    SCOPE_ALL, True, "Verified prior canonical stop receipt",
                    runtime_stopped=True,
                )
            else:
                (preflight or inspect_staged_release)(
                    target, stage=stage, root=root, manifest=manifest_path,
                    unit_dir=installed_units, uid=trusted_uid,
                )
                # Ordinary STOP is a single mutating action. The exact dual-orphan
                # fallback requires its own explicit opt-in, never implied by update.
                if stop is None:
                    env = _environment(env_file)
                    callback = build_dual_orphan_handoff(env) if dual_orphan_handoff else None
                    action = RuntimeShutdown(
                        root=root, env=env, dual_orphan_handoff=callback,
                    ).run
                else:
                    action = stop
                if not _record_one_shot_stop_intent(
                    journal_root, target, uid=trusted_uid,
                ):
                    return "BLOCKED: prior_STOP_outcome_unproven_without_install_journal; no replay"
                try:
                    result = action(SCOPE_ALL)
                except Exception as exc:
                    # The stop may already have performed a trading/runtime action.
                    # The durable intent prevents replay; never install on an
                    # exception or try to infer completion from missing processes.
                    return ("BLOCKED: canonical_safe_stop_outcome_unknown:"
                            + type(exc).__name__ + "; no retry, no deployment")
                if not (getattr(result, "ok", False) is True
                        and getattr(result, "runtime_stopped", False) is True):
                    return "BLOCKED: canonical_safe_stop_unproven; no retry, no deployment"
                # Write the receipt only after a confirmed successful canonical
                # STOP. If this write fails, do not install or repeat STOP.
                _confirmed_stop_receipt(
                    journal_root, target, current, uid=trusted_uid, record=True,
                )
        else:
            result = None  # Already recorded protected transaction; no STOP replay.
        receipt = install_action(
            target, stage=stage, stopped_proof=result, root=root,
            manifest=manifest_path, unit_dir=installed_units,
            transactions=journal_root, uid=trusted_uid,
        )
        if not isinstance(receipt, str) or not receipt.startswith("INSTALLED_STOPPED:"):
            return "BLOCKED: installed_release_postcondition_unknown; do not start"
    except (ActivationBlocked, ReleaseIdentityBlocked, OSError, ValueError) as exc:
        return "BLOCKED: Gitless_switch_unproven:" + type(exc).__name__ + ":" + str(exc)
    return finish_resume()


def run_maintenance(target: str, *, root: Path = REPO, runner=subprocess.run,
                    stop=None, env_file: Path | None = None,
                    wait_seconds: float = 0, poll_seconds: float = 30,
                    clock=time.monotonic, sleep=time.sleep, readiness=None) -> str:
    if len(target) != 40 or any(char not in "0123456789abcdef" for char in target):
        return "BLOCKED: target must be an exact 40-character commit SHA"
    if wait_seconds < 0 or poll_seconds <= 0:
        return "BLOCKED: invalid waiting period"
    # An installed Gitless PAPER tree cannot be upgraded with git merge.
    # Reject this known VPS layout BEFORE attempting a live runtime stop.
    # The approved immutable-release activation must be provided by the
    # unified service path, never by hot-patching an active checkout.
    if not (root / ".git").is_dir():
        return "BLOCKED: gitless_install_requires_verified_immutable_release_switch; runtime unchanged"

    def execute(*argv: str):
        try:
            return runner(list(argv), cwd=root, capture_output=True,
                          text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def command(*argv: str) -> bool:
        reply = execute(*argv)
        return reply is not None and reply.returncode == 0

    # Preflight is read-only for runtime: do not stop a working protected
    # service to discover a dirty tree or invalid/unavailable target later.
    if not command("git", "fetch", "origin", "stable/adfb50b-forward"):
        return "BLOCKED: cannot fetch approved stable"
    # Ignore explicitly ignored runtime DB/log files but refuse any tracked
    # or untracked source change before touching an actively protected service.
    working = execute("git", "status", "--porcelain", "--untracked-files=normal")
    if working is None or working.returncode != 0 or working.stdout.strip():
        return "BLOCKED: working tree contains changes"
    branch = execute("git", "branch", "--show-current")
    if (branch is None or branch.returncode != 0
            or branch.stdout.strip() != "stable/adfb50b-forward"):
        return "BLOCKED: installed branch is not canonical stable"
    if not command("git", "merge-base", "--is-ancestor", target,
                   "origin/stable/adfb50b-forward"):
        return "BLOCKED: target is not on approved stable"
    if not command("git", "merge-base", "--is-ancestor", "HEAD", target):
        return "BLOCKED: target is not a fast-forward from installed HEAD"

    shutdown = stop if stop is not None else RuntimeShutdown(
        root=root, env=_environment(env_file)
    ).run
    # This is a trading/runtime mutation, not a health probe. An ambiguous
    # response cannot authorize a second STOP, even after a waiting period.
    # All retries/resumption must first observe exact owner/process state.
    result = shutdown(SCOPE_ALL)
    if not (result.ok and result.runtime_stopped):
        return "BLOCKED: canonical safe-stop unproven; no mutation retry; PAPER protection retained"

    if not command("git", "merge", "--ff-only", target):
        return "BLOCKED: fast-forward failed after safe-stop"
    installed = execute("git", "rev-parse", "--verify", "HEAD")
    if installed is None or installed.returncode != 0 or installed.stdout.strip() != target:
        return "BLOCKED: installed HEAD differs from approved target"
    # The target release owns this narrow helper. Reload and prove all three
    # installed units are loaded/stopped before any conditional reset-failed.
    # Do not start the PAPER core after an ambiguous systemd preparation.
    if not command(*PREFIX, str(root / "venv/bin/python"), "-m",
                   "tools.vps_systemd_unit_prepare"):
        return "BLOCKED: PAPER systemd units not proven ready; no start attempted"
    if not command(*PREFIX, "systemctl", "start", SERVICE):
        return "BLOCKED: PAPER core start failed; no admission bypass attempted"
    return _paper_full_readiness(root=root, env_file=env_file, readiness=readiness,
                                 target=target)


def _paper_full_readiness(*, root: Path, env_file: Path | None, readiness=None,
                          target: str | None = None,
                          require_gitless_telegram: bool = False) -> str:
    # The oneshot says only that startup was requested; do not report READY
    # unless the PAPER backend has independently proven its safety.
    from tools.runtime_intent import Unreachable, expected_database_identity, http_get
    try:
        health = http_get("http://127.0.0.1:8765/api/health", 5)
        protection = http_get("http://127.0.0.1:8765/api/robot/protection-health", 5)
        scanner = http_get("http://127.0.0.1:8765/api/scanner/status", 5)
        autopilot = http_get("http://127.0.0.1:8765/api/robot/autopilot", 5)
        h, p, s, a = (reply.json() for reply in
                       (health, protection, scanner, autopilot))
        if not all(reply.status == 200 for reply in
                   (health, protection, scanner, autopilot)):
            raise ValueError("backend verification endpoint failed")
        if not all(isinstance(payload, dict) for payload in (h, p, s, a)):
            raise ValueError("malformed PAPER readiness evidence")
        if (h.get("ok") is not True or h.get("component") != "paper_backend"
                or any(payload.get("ok") is not True for payload in (p, s, a))
                or h.get("mode") != "paper" or h.get("paper_live_safe") is not True
                or h.get("robot_admission_ready") is not True
                or h.get("scanner_acceptance_ready") is not True
                or (target is not None and h.get("build_sha") != target)
                or p.get("healthy") is not True
                or s.get("mode") != "SCANNER_RUNNING"
                or a.get("mode") != "PAPER_AUTO"
                or a.get("trading_account_id") != {"value": "paper"}):
            raise ValueError("PAPER state not ready")
    except (Unreachable, ValueError, KeyError, OSError, TypeError):
        return "BLOCKED: PAPER core started but PAPER_AUTO/protection readiness not proven; do not enable new admission"
    # Both the checkout path and Gitless installer must prove the same PAPER
    # DB identity as the running Backend. Service health alone is not ownership.
    identity_block = ("BLOCKED: Gitless_PAPER_Telegram_or_database_identity_unproven"
                      if require_gitless_telegram
                      else "BLOCKED: PAPER_backend_database_identity_unproven")
    try:
        expected = expected_database_identity(root, _environment(env_file))
        if h.get("database_identity") != expected:
            return identity_block
        if require_gitless_telegram and not _editor_telegram_ready(expected):
            return identity_block
    except (OSError, ValueError, TypeError, sqlite3.Error):
        return identity_block
    # An enabled Autopilot is not proof that Robot can admit trades.
    # Read the canonical durable state without mutating the PAPER DB.
    try:
        if readiness is not None:
            if not readiness():
                raise ValueError("Robot readiness rejected")
        else:
            import sqlite3
            from tools.stop_robot_runtime import _database_path
            db = _database_path(root, _environment(env_file))
            with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT mode, recovery_status FROM robot_runtime_state "
                    "WHERE trading_account_id='paper'"
                ).fetchone()
            if row != ("ROBOT_RUNNING", "READY"):
                raise ValueError("Robot is not READY")
            if _environment(env_file).get("BYBITSCANNER_STOP_REENTRY_AUTO") != "1":
                raise ValueError("STOP reentry is not enabled")
    except Exception:
        return "BLOCKED: PAPER core started but Robot READY/reentry not proven"
    return "READY: exact HEAD, PAPER-only, Robot, Scanner, PAPER_AUTO, reentry and protection confirmed"


def _paper_start_quiescent(root: Path, env_file: Path | None) -> bool:
    """Never re-enable PAPER_AUTO on unresolved incident owners or entry ideas.

    EDITOR_ONLY remains usable for canonical reconciliation. The existing
    oneshot may resume trading only after durable STOPPED/PAUSED/READY evidence
    and all old entry/exit ownership is fully retired. Canonical reconcile
    succeeds into PAUSED; the existing runtime intent owns PAUSED -> READY.
    No SQL mutations.
    """
    from tools.stop_robot_runtime import _database_path
    db = _database_path(root, _environment(env_file))
    if not db.is_file() or db.is_symlink():
        return False
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        states = conn.execute(
            "SELECT mode, recovery_status FROM robot_runtime_state "
            "WHERE trading_account_id='paper'"
        ).fetchall()
        if len(states) != 1 or tuple(states[0]) not in (
            ("ROBOT_STOPPED", "ROBOT_STOPPED"),
            ("ROBOT_RUNNING", "PAUSED"),
            ("ROBOT_RUNNING", "READY"),
        ):
            return False
        # Robot ledgers can be empty while a separate manual PAPER position
        # remains open. Never restart ingress on that unprotected exposure.
        positions = conn.execute(
            "SELECT symbol, side, quantity, sync_state FROM position_projections "
            "WHERE trading_account_id='paper'"
        ).fetchall()
        for symbol, side, raw_quantity, sync_state in positions:
            try:
                quantity = Decimal(str(raw_quantity))
            except (ValueError, ArithmeticError):
                return False
            if (not symbol or side != "Flat" or not quantity.is_finite()
                    or quantity != 0 or sync_state not in ("synced", "synchronized")):
                return False
        for table, condition in (
            ("robot_trades", "exit_time_ms IS NULL"),
            ("robot_candidates",
             "status IS NULL OR status NOT IN "
             "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED')"),
            ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
            ("trading_commands",
             "current_state IS NULL OR current_state NOT IN "
             "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
            ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
            ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
        ):
            if conn.execute(
                f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                f"AND ({condition}) LIMIT 1"
            ).fetchone() is not None:
                return False
    return True


def _editor_flat_reconcile_preflight(root: Path, env_file: Path | None) -> bool:
    """Read-only, incident-scoped proof before invoking owner Robot reconciliation.

    No candidate/order is retired here. Never reconcile under live exposure,
    working LIMIT or unresolved dispatch. Only the old JASMY/FLOW orphan
    identities and exact six frozen entry ideas are eligible.
    """
    from tools.stop_robot_runtime import _database_path
    from tools.paper_incident_approvals import (
        IDLE_APPROVALS, JASMY_CANDIDATE_ID, JASMY_TRADE_ID,
        prove_six_inert_approvals,
    )
    from tools.flat_paper_recovery_gate import FlatRecoveryBlocked

    expected_symbols = frozenset({"JASMYUSDT", "FLOWUSDT"})
    frozen_symbols = frozenset(IDLE_APPROVALS)
    path = _database_path(root, _environment(env_file))
    if not path.is_file() or path.is_symlink():
        return False
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            return False
        states = conn.execute(
            "SELECT mode, recovery_status FROM robot_runtime_state "
            "WHERE trading_account_id='paper'"
        ).fetchall()
        if [tuple(x) for x in states] != [("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")]:
            return False
        scanner = conn.execute(
            "SELECT mode FROM scanner_runtime_state WHERE trading_account_id='paper'"
        ).fetchall()
        autopilot = conn.execute(
            "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'"
        ).fetchall()
        if scanner != [("SCANNER_STOPPED",)] or autopilot != [("OFF",)]:
            return False
        positions = conn.execute(
            "SELECT symbol, side, quantity, sync_state FROM position_projections "
            "WHERE trading_account_id='paper'"
        ).fetchall()
        if not positions:
            return False
        for symbol, side, raw_quantity, sync in positions:
            quantity = Decimal(str(raw_quantity))
            if (not symbol or side != "Flat" or not quantity.is_finite()
                    or quantity != 0 or sync not in ("synced", "synchronized")):
                return False
        trades = conn.execute(
            "SELECT trade_id, candidate_id, symbol FROM robot_trades "
            "WHERE trading_account_id='paper' AND exit_time_ms IS NULL"
        ).fetchall()
        if (len(trades) != 2
                or len({trade_id for trade_id, _, _ in trades}) != 2
                or len({cid for _, cid, _ in trades}) != 2
                or {symbol for _, _, symbol in trades} != expected_symbols
                or any((trade_id, cid) != (JASMY_TRADE_ID, JASMY_CANDIDATE_ID)
                       for trade_id, cid, symbol in trades if symbol == "JASMYUSDT")):
            return False
        for _, _, symbol in trades:
            if sum(position[0] == symbol for position in positions) != 1:
                return False
        rows = conn.execute(
            "SELECT candidate_id, symbol, status, approved_at_ms FROM robot_candidates "
            "WHERE trading_account_id='paper' "
            "AND (status IS NULL OR status NOT IN "
            "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))"
        ).fetchall()
        open_owners = {(candidate_id, symbol, "OPEN") for _, candidate_id, symbol in trades}
        approvals = [row for row in rows if row[2] == "APPROVED"]
        if (len(rows) != len(trades) + len(approvals)
                or len(set(rows)) != len(rows)
                or {(cid, sym, status) for cid, sym, status, _ in rows if status == "OPEN"}
                   != open_owners
                or len({sym for _, sym, _, _ in approvals}) != len(approvals)
                or any(sym not in frozen_symbols for _, sym, _, _ in approvals)):
            return False
        if approvals:
            # The same immutable six-owner proof used by the protected
            # handoff must hold before canonical reconciliation can run.
            # Reusing it here prevents a candidate that merely shares a
            # symbol from receiving the old incident's authority.
            try:
                prove_six_inert_approvals(conn, approvals, positions)
            except (FlatRecoveryBlocked, sqlite3.Error, ValueError, TypeError):
                return False
        for table, condition in (
            ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
            ("trading_commands",
             "current_state IS NULL OR current_state NOT IN "
             "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
            ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
            ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
        ):
            if conn.execute(
                f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                f"AND ({condition}) LIMIT 1"
            ).fetchone() is not None:
                return False
    return True


def _record_editor_reconcile_once(
    target: str, identity: str, *, journal_root: Path | None = None,
    trusted_uid: int = 0,
) -> bool:
    """Fsync one protected one-shot owner intent. Unknown result cannot replay."""
    from tools.vps_gitless_release_activate import (
        TRANSACTIONS, _sync_directory, _trusted_file,
    )
    root = journal_root or TRANSACTIONS
    journal = root / target
    if (not root.is_dir() or root.is_symlink()
            or root.stat().st_uid != trusted_uid or root.stat().st_mode & 0o077
            or not journal.is_dir() or journal.is_symlink()
            or journal.stat().st_uid != trusted_uid
            or journal.stat().st_mode & 0o077
            or _trusted_file(journal / "editor-ready", trusted_uid) != target.encode("ascii")):
        return False
    marker = journal / "robot-reconcile-invoked"
    if marker.exists() or marker.is_symlink():
        return False
    try:
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as stream:
        stream.write((target + "\n" + identity + "\n").encode("ascii"))
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(journal)
    return True


def _editor_reconcile_once(
    target: str, identity: str, *, root: Path, env_file: Path | None,
) -> str | None:
    """One canonical owner reconcile; never retry a POST with unknown outcome."""
    from tools.runtime_intent import http_post_json
    try:
        if not _editor_flat_reconcile_preflight(root, env_file):
            return "BLOCKED: Editor_Robot_reconcile_preflight_unproven; PAPER_START_not_attempted"
        if not _record_editor_reconcile_once(target, identity):
            return "BLOCKED: prior_Editor_Robot_reconcile_outcome_unknown; no_replay"
        response = http_post_json("http://127.0.0.1:8765/api/robot/reconcile", {}, 180.0)
        if response.status != 200:
            return "BLOCKED: canonical_Editor_Robot_reconcile_failed; no_replay"
        body = response.json()
        if (not isinstance(body, dict) or body.get("ok") is not True
                or body.get("success") is not True):
            return "BLOCKED: canonical_Editor_Robot_reconcile_not_proven; no_replay"
        # Do not infer success from an HTTP 200 or from a partial candidate
        # terminalization; actual durable postconditions are checked next.
        return None
    except Exception:
        return "BLOCKED: Editor_Robot_reconcile_outcome_unknown; no_replay"


def start_installed_paper_from_editor(
    target: str, *, root: Path = REPO, env_file: Path | None = None,
    runner=subprocess.run, editor_status: str,
) -> str:
    """Use existing owner PAPER oneshot only after verified Editor recovery."""
    if not editor_status.startswith("READY:"):
        return "BLOCKED: editor_only_not_ready; PAPER start not attempted"
    # Exact installed source is re-proved immediately before trading activation.
    from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
    try:
        if verify_release(root) != target:
            return "BLOCKED: installed_release_differs_from_approved_target"
        identity = _durable_editor_freeze(root, env_file)
        if not _editor_runtime_ready(target, identity):
            return "BLOCKED: editor_only_runtime_not_proven"
        if not _paper_start_quiescent(root, env_file):
            outcome = _editor_reconcile_once(target, identity, root=root, env_file=env_file)
            if outcome is not None:
                return outcome
            # Re-prove the exact backend, frozen ingress and the entire PAPER
            # ledger after the owner mutation, before starting any ingress.
            if (_durable_editor_freeze(root, env_file) != identity
                    or not _editor_runtime_ready(target, identity)
                    or not _paper_start_quiescent(root, env_file)):
                return "BLOCKED: PAPER_stale_owners_after_reconcile; START_not_attempted"
    except (ReleaseIdentityBlocked, OSError, ValueError, sqlite3.Error):
        return "BLOCKED: editor_only_release_or_freeze_unproven"
    try:
        response = runner(
            [*PREFIX, "systemctl", "start", SERVICE],
            cwd=root, capture_output=True, text=True, timeout=300, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "BLOCKED: PAPER_core_start_outcome_unknown; no replay"
    if response.returncode != 0:
        return "BLOCKED: PAPER_core_start_failed; no replay"
    # The existing oneshot owns Scanner, Robot and PAPER_AUTO transitions;
    # these independent postconditions must also prove the exact release.
    return _paper_full_readiness(
        root=root, env_file=env_file, target=target,
        require_gitless_telegram=True,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed one-action PAPER maintenance")
    parser.add_argument("sha")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--resume-installed-editor-only", action="store_true",
                        help="only after an exact Gitless release was safely installed")
    parser.add_argument("--staged-gitless-editor-only", type=Path,
                        help="owner-approved exact staged checkout; safe-stop and install once")
    parser.add_argument("--start-paper-after-editor", action="store_true",
                        help="after safe Gitless Editor recovery, start owner PAPER oneshot")
    parser.add_argument("--dual-orphan-handoff-20261103", action="store_true",
                        help="separate explicit opt-in to exact JASMY/FLOW protected handoff")
    args = parser.parse_args(argv)
    if args.resume_installed_editor_only and args.staged_gitless_editor_only:
        parser.error("choose exactly one Gitless operation")
    if args.start_paper_after_editor and not (
        args.staged_gitless_editor_only or args.resume_installed_editor_only
    ):
        parser.error("full PAPER start requires verified Gitless Editor recovery")
    if args.dual_orphan_handoff_20261103 and not args.staged_gitless_editor_only:
        parser.error("exceptional handoff requires staged Gitless operation")
    if args.start_paper_after_editor and (
        args.staged_gitless_editor_only or args.resume_installed_editor_only
    ):
        # A repeated one-action START is read-only when the exact approved
        # Gitless release and all PAPER postconditions are already proven.
        # Do not route an active trading runtime through EDITOR_ONLY freeze,
        # canonical STOP, or systemctl start a second time.
        from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
        if (len(args.sha) == 40
                and all(ch in "0123456789abcdef" for ch in args.sha)):
            try:
                installed = verify_release(REPO)
            except (ReleaseIdentityBlocked, OSError):
                installed = None
            if installed == args.sha:
                observed = _paper_full_readiness(
                    root=REPO, env_file=args.env_file, target=args.sha,
                    require_gitless_telegram=True,
                )
                if observed.startswith("READY:"):
                    print("READY: exact installed Gitless PAPER already running; no mutation")
                    return 0
    if args.staged_gitless_editor_only:
        status = deploy_staged_editor_only(
            args.sha, stage=args.staged_gitless_editor_only,
            env_file=args.env_file,
            dual_orphan_handoff=args.dual_orphan_handoff_20261103,
        )
    elif args.resume_installed_editor_only:
        status = resume_installed_release(args.sha, root=REPO, env_file=args.env_file)
        if status.startswith("READY:"):
            # Standalone recovery must finalize the same pinned transaction
            # as staged deploy; otherwise the next planned release remains
            # fenced by its previously successful STOP attempt.
            from tools.vps_gitless_release_activate import ActivationBlocked, TRANSACTIONS
            try:
                _complete_stop_intent(TRANSACTIONS, args.sha, uid=0)
            except (ActivationBlocked, OSError, ValueError) as exc:
                status = ("BLOCKED: completed_release_receipt_unproven:"
                          + type(exc).__name__)
    else:
        status = run_maintenance(args.sha, env_file=args.env_file,
                                 wait_seconds=args.wait_seconds)
    if args.start_paper_after_editor and status.startswith("READY:"):
        status = start_installed_paper_from_editor(
            args.sha, root=REPO, env_file=args.env_file, editor_status=status,
        )
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
