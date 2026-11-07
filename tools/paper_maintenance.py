"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path
from decimal import Decimal

from tools.stop_robot_runtime import RuntimeShutdown, ShutdownResult, SCOPE_ALL, _environment


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





def _proven_one_flat_successor(
    journal_root: Path, prior: str, target: str, *,
    uid: int, root: Path, require_ready: bool,
) -> bool:
    """Bind a failed STOP to one independently attested successor release."""
    from tools.paper_stopped_approved_recovery import (
        PartialStopBlocked, _one_flat_receipt, _one_flat_snapshot,
    )
    from tools.vps_gitless_release_activate import ActivationBlocked
    from tools.paper_interrupted_stop_recovery import _trusted_journal
    from tools.vps_gitless_release_activate import _manifest, _trusted_file
    from tools.vps_release_identity import verify_release

    try:
        _trusted_journal(journal_root, uid)
        if (len(prior) != 40 or len(target) != 40
                or any(ch not in "0123456789abcdef" for ch in prior + target)
                or prior == target
                or (journal_root / prior).exists()
                or (journal_root / (".stop-confirmed-" + prior)).exists()
                or _trusted_file(journal_root / (".stop-invoked-" + prior), uid)
                != b"STOP_INVOKED; not install authorization\\n"):
            return False
        if not all(_one_flat_receipt(journal_root, prior, phase, target, uid=uid)
                   for phase in ("handoff-attempt", "backend-exited", "handoff-proven")):
            return False
        snapshot = _one_flat_snapshot(journal_root, prior, uid=uid)
        old_sha = snapshot["backend"].get("build_sha")
        if (not isinstance(old_sha, str) or len(old_sha) != 40
                or any(ch not in "0123456789abcdef" for ch in old_sha)
                or old_sha == target):
            return False
        journal = journal_root / target
        if (not journal.is_dir() or journal.is_symlink()
                or journal.stat().st_uid != uid or journal.stat().st_mode & 0o077):
            return False
        old = _manifest(_trusted_file(journal / "old.json", uid))
        new = _manifest(_trusted_file(journal / "target.json", uid))
        _trusted_file(journal / "units.json", uid)
        if old["build_sha"] != old_sha or new["build_sha"] != target:
            return False
        if require_ready:
            done = journal / "editor-ready"
            return done.is_file() and not done.is_symlink() and (
                _trusted_file(done, uid) == target.encode("ascii")
            )
        return verify_release(root) == target
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            sqlite3.Error, UnicodeError, ActivationBlocked, PartialStopBlocked):
        return False



def _proven_stopped_backend_handoff_to(
    journal_root: Path, target: str, *, uid: int,
) -> bool:
    """Attest the new one-shot handoff before sealing EDITOR_ONLY.

    This is *not* a canonical STOP receipt. The Backend must already have
    exited under the separately authorized pinned signal and the protected
    installer must have committed the verified target release.
    """
    from tools.paper_stopped_approved_recovery import (
        OLD_BACKEND, PRIOR_TARGET, PartialStopBlocked, _receipt,
    )
    from tools.paper_interrupted_stop_recovery import RecoveryBlocked, _trusted_journal
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, _manifest, _trusted_file,
    )
    from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
    # The same protected installer can be reached by the generic Flat/OPEN
    # one-shot continuation, but never by a second canonical STOP.
    for marker in journal_root.glob(".one-flat-handoff-handoff-proven-*"):
        prior = marker.name.removeprefix(".one-flat-handoff-handoff-proven-")
        if _proven_one_flat_successor(
            journal_root, prior, target, uid=uid, root=REPO, require_ready=False,
        ):
            return True
    try:
        _trusted_journal(journal_root, uid)
        if (verify_release(REPO) != target
                or (journal_root / PRIOR_TARGET).exists()
                or (journal_root / (".stop-confirmed-" + PRIOR_TARGET)).exists()
                or _trusted_file(journal_root / (".stop-invoked-" + PRIOR_TARGET), uid)
                != b"STOP_INVOKED; not install authorization\\n"):
            return False
        journal = journal_root / target
        if (not journal.is_dir() or journal.is_symlink()
                or journal.stat().st_uid != uid or journal.stat().st_mode & 0o077):
            return False
        old = _manifest(_trusted_file(journal / "old.json", uid))
        new = _manifest(_trusted_file(journal / "target.json", uid))
        _trusted_file(journal / "units.json", uid)
        return (
            old["build_sha"] == OLD_BACKEND and new["build_sha"] == target
            and target not in (PRIOR_TARGET, OLD_BACKEND)
            and all(_receipt(journal_root, phase, uid, target=target)
                    for phase in ("handoff-attempt", "backend-exited", "handoff-proven"))
        )
    except (ActivationBlocked, PartialStopBlocked, RecoveryBlocked, ReleaseIdentityBlocked,
            OSError, ValueError, TypeError, KeyError):
        return False


def _complete_stop_intent(journal_root: Path, target: str, *, uid: int) -> None:
    """Record post-resume success only; never grant STOP or install authority."""
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, _sync_directory, _trusted_file,
    )
    marker = journal_root / (".stop-invoked-" + target)
    journal = journal_root / target
    if not journal.exists():
        return  # No protected installer transaction to attest.
    if marker.exists() or marker.is_symlink():
        _trusted_file(marker, uid)
    elif _proven_stopped_backend_handoff_to(journal_root, target, uid=uid):
        pass  # A distinct, sealed one-shot handoff; no canonical STOP receipt.
    else:
        # An exceptional prior-target handoff can install the pinned release
        # without a same-target ordinary STOP marker. Only its *own* protected
        # transaction and proved installed bytes may close EDITOR_ONLY; an
        # arbitrary journal/READY string cannot mint a trading entitlement.
        from tools.paper_interrupted_stop_recovery import (
            PRIOR_TARGET, RecoveryBlocked, _receipt, _trusted_journal,
        )
        # Only the known prior-target exceptional STOP has a protected
        # alternate handoff. Legacy ordinary resumptions without either
        # marker keep their former no-receipt behavior.
        if not (journal_root / (".stop-invoked-" + PRIOR_TARGET)).exists():
            return
        from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
        from tools.vps_gitless_release_activate import _manifest
        try:
            _trusted_journal(journal_root, uid)
            original = _manifest(_trusted_file(journal / "old.json", uid))
            pinned = _manifest(_trusted_file(journal / "target.json", uid))
            _trusted_file(journal / "units.json", uid)
            prior_stop = _trusted_file(journal_root / (".stop-invoked-" + PRIOR_TARGET), uid)
            if (pinned["build_sha"] != target
                    or original["build_sha"] == target
                    or prior_stop != b"STOP_INVOKED; not install authorization\\n"
                    or not _receipt(journal_root, "handoff-proven", uid, target=target)
                    or not _receipt(journal_root, "backend-exited", uid, target=target)
                    or verify_release(REPO) != target):
                raise ActivationBlocked("exceptional_editor_receipt_proof_unproven")
        except (RecoveryBlocked, ReleaseIdentityBlocked, OSError, ValueError) as exc:
            raise ActivationBlocked("exceptional_editor_receipt_proof_unproven") from exc
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


def _record_one_shot_stop_intent(
    journal_root: Path, target: str, *, uid: int, root: Path = REPO,
) -> bool:
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
            if _proven_prior_exceptional_completion(
                journal_root, previous, root=root, uid=uid,
            ):
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



def _proven_prior_exceptional_completion(
    journal_root: Path, prior: str, *, root: Path, uid: int,
) -> bool:
    """Historical STOP intent is inert only after a durable verified handoff.

    Its original STOP remains unconfirmed. The protected successor release
    journal and handoff receipts, *not* the current installed SHA alone,
    prove the old intent was superseded. This remains true after later
    verified upgrades; unknown or incomplete handoffs remain a global fence.
    """
    from tools.paper_interrupted_stop_recovery import (
        OLD_BACKEND as LEGACY_BACKEND, PRIOR_TARGET as LEGACY_TARGET,
        MARKER_PREFIX as LEGACY_PREFIX, RecoveryBlocked,
        _receipt as legacy_receipt, _trusted_journal,
    )
    from tools.paper_stopped_approved_recovery import (
        OLD_BACKEND as NEW_BACKEND, PRIOR_TARGET as NEW_TARGET,
        MARKER_PREFIX as NEW_PREFIX, PartialStopBlocked,
        _receipt as new_receipt,
    )
    from tools.vps_gitless_release_activate import (
        ActivationBlocked, _manifest, _trusted_file,
    )
    from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release

    if prior == LEGACY_TARGET:
        old_backend, prefix, receipt = LEGACY_BACKEND, LEGACY_PREFIX, legacy_receipt
    elif prior == NEW_TARGET:
        old_backend, prefix, receipt = NEW_BACKEND, NEW_PREFIX, new_receipt
    else:
        receipt_path = journal_root / (".one-flat-handoff-handoff-proven-" + prior)
        if not receipt_path.exists() and not receipt_path.is_symlink():
            return False
        from tools.vps_gitless_release_activate import _trusted_file
        try:
            successor = _trusted_file(receipt_path, uid).decode("ascii").removesuffix("\n")
        except (OSError, ValueError, UnicodeError):
            return False
        return _proven_one_flat_successor(
            journal_root, prior, successor, uid=uid, root=root, require_ready=True,
        )
    try:
        _trusted_journal(journal_root, uid)
        if ((journal_root / prior).exists()
                or (journal_root / (".stop-confirmed-" + prior)).exists()
                or _trusted_file(journal_root / (".stop-invoked-" + prior), uid)
                != b"STOP_INVOKED; not install authorization\\n"):
            return False
        if prior == LEGACY_TARGET and (
            _trusted_file(journal_root / (".chatops-invoked-" + prior), uid)
            != (prior + "\n").encode("ascii")
        ):
            return False
        # The handoff-proven receipt binds the original STOP to exactly one
        # successor SHA, even when that successor is no longer installed.
        raw = _trusted_file(journal_root / (prefix + "handoff-proven-" + prior), uid)
        successor = raw.decode("ascii").removesuffix("\n")
        if (len(successor) != 40
                or any(ch not in "0123456789abcdef" for ch in successor)
                or successor in (old_backend, prior)
                or raw != (successor + "\n").encode("ascii")):
            return False
        journal = journal_root / successor
        if (not journal.is_dir() or journal.is_symlink()
                or journal.stat().st_uid != uid or journal.stat().st_mode & 0o077):
            return False
        old = _manifest(_trusted_file(journal / "old.json", uid))
        new = _manifest(_trusted_file(journal / "target.json", uid))
        _trusted_file(journal / "units.json", uid)
        if (old["build_sha"] != old_backend or new["build_sha"] != successor
                or not all(receipt(journal_root, phase, uid, target=successor)
                           for phase in ("handoff-attempt", "backend-exited",
                                         "handoff-proven"))):
            return False
        ready = journal / "editor-ready"
        if ready.exists() or ready.is_symlink():
            return _trusted_file(ready, uid) == successor.encode("ascii")
        # Only the earlier #855 legacy handoff may lack editor-ready; it
        # remains historical solely while its successor is *still* verified
        # as installed. A later release requires a sealed ready receipt.
        return prior == LEGACY_TARGET and verify_release(root) == successor
    except (ActivationBlocked, RecoveryBlocked, PartialStopBlocked,
            ReleaseIdentityBlocked, OSError, ValueError, TypeError,
            UnicodeError, KeyError):
        return False


def deploy_staged_editor_only(
    target: str, *, stage: Path, root: Path = REPO, env_file: Path | None = None,
    dual_orphan_handoff: bool = False, proven_one_flat_orphan_handoff: bool = False,
    stop=None, preflight=None,
    installer=None, resume=None, manifest=None, unit_dir=None,
    transactions=None, trusted_uid: int = 0,
    frontend_bundle: Path | None = None,
    frontend_expected_index_sha256: str | None = None,
    frontend_publisher=None,
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
    from tools.stop_robot_runtime import (
        build_dual_orphan_handoff, build_proven_one_flat_orphan_handoff,
    )

    if len(target) != 40 or any(ch not in "0123456789abcdef" for ch in target):
        return "BLOCKED: invalid_approved_target"
    if dual_orphan_handoff and proven_one_flat_orphan_handoff:
        return "BLOCKED: competing_exceptional_handoff_options"
    if (not root.is_dir() or root.is_symlink() or (root / ".git").exists()
            or not stage.is_dir() or stage.is_symlink()):
        return "BLOCKED: incorrect_Gitless_release_layout"
    manifest_path = manifest or MANIFEST
    installed_units = unit_dir or UNIT_DIR
    journal_root = transactions or TRANSACTIONS
    journal = journal_root / target

    resume_action = resume or resume_installed_release
    install_action = installer or activate_staged_release
    if frontend_bundle is not None:
        # Fail before *any* irreversible STOP if the UI artifact is absent,
        # from another SHA or changed after its build receipt.
        from tools.vps_terminal_frontend_publish import (
            FrontendPublishBlocked, inspect_bundle,
        )
        try:
            inspect_bundle(frontend_bundle, target)
        except (FrontendPublishBlocked, OSError, ValueError, UnicodeError) as exc:
            return "BLOCKED: frontend_preflight_unproven:" + type(exc).__name__

    def finish_resume() -> str:
        observed = resume_action(target, root=root, env_file=env_file)
        if isinstance(observed, str) and observed.startswith("READY:"):
            if frontend_bundle is not None:
                from tools.vps_terminal_frontend_publish import publish_frontend
                try:
                    sync = (frontend_publisher or publish_frontend)(
                        target, bundle=frontend_bundle, root=root,
                        expected_index_sha256=frontend_expected_index_sha256,
                    )
                    if not isinstance(sync, str) or not sync.startswith("FRONTEND_READY:"):
                        return "BLOCKED: frontend_publisher_postcondition_unproven"
                except (OSError, ValueError, UnicodeError) as exc:
                    return "BLOCKED: frontend_publication_unproven:" + type(exc).__name__
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
                and not _proven_prior_exceptional_completion(
                    journal_root, marker.name.removeprefix(".stop-invoked-"),
                    root=root, uid=trusted_uid,
                )
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
                    if proven_one_flat_orphan_handoff and (
                        not isinstance(current, str)
                        or len(current) != 40
                        or any(c not in "0123456789abcdef" for c in current)
                    ):
                        return "BLOCKED: old_release_not_pinned_for_one_orphan_handoff"
                    callback = build_dual_orphan_handoff(env) if dual_orphan_handoff else None
                    one_orphan = (
                        build_proven_one_flat_orphan_handoff(env, current)
                        if proven_one_flat_orphan_handoff else None
                    )
                    action = RuntimeShutdown(
                        root=root, env=env, dual_orphan_handoff=callback,
                        proven_one_flat_orphan_handoff=one_orphan,
                    ).run
                else:
                    action = stop
                if not _record_one_shot_stop_intent(
                    journal_root, target, uid=trusted_uid, root=root,
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
                    # Preserve the canonical refusal reason for the operator;
                    # never infer STOP success or authorize a replay from it.
                    reason = getattr(result, "message", None)
                    if not isinstance(reason, str) or not reason.strip():
                        reason = "reason_unavailable"
                    return (
                        "BLOCKED: canonical_safe_stop_unproven: "
                        + reason.replace(chr(10), " ").replace(chr(13), " ")[:500]
                        + "; no retry, no deployment"
                    )
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


def _editor_retire_inert_approvals(root: Path, env_file: Path | None) -> bool | None:
    """Retire proven inert APPROVED ideas via the existing canonical Robot STOP.

    None: not in PAUSED (reconcile may be needed); False: unsafe or unknown
    PAUSED/STOP outcome (do not replay reconcile); True: STOP and quiescence
    confirmed. No new candidate lifecycle writer or incident-specific IDs.
    """
    from tools.stop_robot_runtime import _database_path, _environment, _post_robot_json
    from terminal.application.robot_control import stop_robot

    db = _database_path(root, _environment(env_file))
    if not db.is_file() or db.is_symlink():
        return False
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                return False
            state = conn.execute(
                "SELECT mode, recovery_status FROM robot_runtime_state "
                "WHERE trading_account_id='paper'"
            ).fetchall()
            if state != [("ROBOT_RUNNING", "PAUSED")]:
                return None
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
            for symbol, side, raw, sync in positions:
                quantity = Decimal(str(raw))
                if (not symbol or side != "Flat" or not quantity.is_finite()
                        or quantity != 0 or sync not in ("synced", "synchronized")):
                    return False
            candidates = conn.execute(
                "SELECT candidate_id, symbol, status, approved_at_ms "
                "FROM robot_candidates WHERE trading_account_id='paper' "
                "AND (status IS NULL OR status NOT IN "
                "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))"
            ).fetchall()
            if (not candidates
                    or len({row[0] for row in candidates}) != len(candidates)
                    or len({row[1] for row in candidates}) != len(candidates)
                    or any(not isinstance(cid, str) or not cid
                           or not isinstance(symbol, str) or not symbol
                           or status != "APPROVED"
                           or type(approved) is not int or approved <= 0
                           for cid, symbol, status, approved in candidates)):
                return False
            # Historical fills before approval are not new entry work.
            # A later fill/order/command/trade must instead block the STOP path.
            for cid, symbol, _, approved in candidates:
                if (conn.execute(
                    "SELECT 1 FROM executions WHERE trading_account_id='paper' "
                    "AND symbol=? AND (exchange_timestamp_ms IS NULL "
                    "OR exchange_timestamp_ms>=?) LIMIT 1",
                    (symbol, approved),
                ).fetchone() is not None or conn.execute(
                    "SELECT 1 FROM paper_limit_orders WHERE trading_account_id='paper' "
                    "AND symbol=? AND (created_at_ms IS NULL "
                    "OR created_at_ms>=?) LIMIT 1",
                    (symbol, approved),
                ).fetchone() is not None or conn.execute(
                    "SELECT 1 FROM trading_commands WHERE trading_account_id='paper' "
                    "AND symbol=? AND (created_at_ms IS NULL "
                    "OR created_at_ms>=?) LIMIT 1",
                    (symbol, approved),
                ).fetchone() is not None or conn.execute(
                    "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
                    "AND candidate_id=? LIMIT 1",
                    (cid,),
                ).fetchone() is not None):
                    return False
            for table, condition in (
                ("robot_trades", "exit_time_ms IS NULL"),
                ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
                ("trading_commands", "current_state IS NULL OR current_state NOT IN "
                 "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
                ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
                ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
            ):
                if conn.execute(
                    f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                    f"AND ({condition}) LIMIT 1"
                ).fetchone() is not None:
                    return False
    except (sqlite3.Error, ValueError, TypeError, ArithmeticError):
        return False

    # One canonical operation, including its own safety checks and synchronous
    # candidate terminalization. No direct SQLite writes or repeated STOP.
    try:
        stop_robot(http_post=_post_robot_json, database_path=db)
    except Exception:
        return False  # STOP may have committed: never replay it here.
    return _paper_start_quiescent(root, env_file)

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
            # Resume the *observed* phase. A prior successful reconcile may
            # have left PAUSED with inert APPROVED rows; it cannot be replayed.
            retired = _editor_retire_inert_approvals(root, env_file)
            if retired is False:
                return "BLOCKED: PAPER_Robot_STOP_outcome_unknown_or_unproven; no_replay"
            if retired is None:
                outcome = _editor_reconcile_once(
                    target, identity, root=root, env_file=env_file,
                )
                if outcome is not None:
                    return outcome
                if (_durable_editor_freeze(root, env_file) != identity
                        or not _editor_runtime_ready(target, identity)):
                    return "BLOCKED: PAPER_editor_identity_changed_after_reconcile"
                if not _paper_start_quiescent(root, env_file):
                    retired = _editor_retire_inert_approvals(root, env_file)
                    if retired is not True:
                        return "BLOCKED: PAPER_stale_owners_after_reconcile; START_not_attempted"
            # Re-prove frozen ingress and complete ownership after the
            # actual canonical STOP, before starting the PAPER core.
            if (_durable_editor_freeze(root, env_file) != identity
                    or not _editor_runtime_ready(target, identity)
                    or not _paper_start_quiescent(root, env_file)):
                return "BLOCKED: PAPER_post_transition_reproof_failed; START_not_attempted"
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


def _active_exact_paper_blocker(
    target: str, *, root: Path, env_file: Path | None,
) -> str | None:
    """Report active, exact-release PAPER without mutating it on failed START.

    A running backend with closed admission (notably Robot REQUIRED) is
    not EDITOR_ONLY. Never route it through a second STOP/deploy/start merely
    because the normal READY proof failed. The canonical owner must resolve
    the underlying durable reason under a separately authorized operation.
    """
    from tools.runtime_intent import expected_database_identity, http_get
    from tools.stop_robot_runtime import _database_path

    try:
        env = _environment(env_file)
        identity = expected_database_identity(root, env)
        reply = http_get("http://127.0.0.1:8765/api/health", 3)
        health = reply.json()
        if (reply.status != 200 or not isinstance(health, dict)
                or health.get("ok") is not True
                or health.get("component") != "paper_backend"
                or health.get("mode") != "paper"
                or health.get("build_sha") != target
                or health.get("database_identity") != identity):
            return None
        if health.get("paper_live_safe") is not True:
            return "BLOCKED: active_exact_PAPER_live_isolation_unproven; no_stop_or_restart"

        db = _database_path(root, env)
        if not db.is_file() or db.is_symlink():
            return "BLOCKED: active_exact_PAPER_database_unproven; no_stop_or_restart"
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            rows = conn.execute(
                "SELECT mode, recovery_status, reason FROM robot_runtime_state "
                "WHERE trading_account_id='paper'"
            ).fetchall()
        if len(rows) != 1:
            return "BLOCKED: active_exact_PAPER_Robot_state_unproven; no_stop_or_restart"
        mode, recovery, reason = rows[0]
        if (mode, recovery) == ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"):
            # Diagnostic only. Do not auto-reconcile unknown exposure or
            # invent an exit to manufacture admission readiness.
            detail = " ".join(str(reason or "unavailable").split())[:180]
            return (
                "BLOCKED: active_PAPER_Robot_RECONCILIATION_REQUIRED; "
                "admission_closed; protection_preserved; reason=" + detail
            )
        return (
            "BLOCKED: active_exact_PAPER_not_ready; "
            "Robot=" + str(mode)[:40] + "/" + str(recovery)[:40]
            + "; no_stop_or_restart"
        )
    except (OSError, TypeError, ValueError, sqlite3.Error):
        return None


_INGRESS_OVERFLOW_FENCE = re.compile(
    r"^ROBOT_PROTECTION_COVERAGE_LOST symbol=([A-Z0-9]+) reason=ingress_overflow$"
)


def _active_required_flat_proof(db: Path) -> tuple[str, str, str | None] | None:
    """One read-only PAPER ledger snapshot; APPROVED alone is not exposure.

    No admission can be revived while a trade, fill after approval, working
    LIMIT, command, obligation, checkpoint or position remains unresolved.
    """
    if not db.is_file() or db.is_symlink():
        return None
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
                return None
            states = conn.execute(
                "SELECT mode, recovery_status, reason FROM robot_runtime_state "
                "WHERE trading_account_id='paper'"
            ).fetchall()
            if len(states) != 1:
                return None
            for symbol, side, raw, sync in conn.execute(
                "SELECT symbol, side, quantity, sync_state FROM position_projections "
                "WHERE trading_account_id='paper'"
            ):
                quantity = Decimal(str(raw))
                if (not symbol or side != "Flat" or not quantity.is_finite()
                        or quantity != 0 or sync not in ("synced", "synchronized")):
                    return None
            for table, condition in (
                ("robot_trades", "exit_time_ms IS NULL"),
                ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
                ("trading_commands", "current_state IS NULL OR current_state NOT IN "
                 "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
                ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
                ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
            ):
                if conn.execute(
                    f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                    f"AND ({condition}) LIMIT 1"
                ).fetchone() is not None:
                    return None
            candidates = conn.execute(
                "SELECT candidate_id, symbol, status, approved_at_ms "
                "FROM robot_candidates WHERE trading_account_id='paper' "
                "AND (status IS NULL OR status NOT IN "
                "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))"
            ).fetchall()
            for cid, symbol, status, approved in candidates:
                if (not isinstance(cid, str) or not cid
                        or not isinstance(symbol, str) or not symbol
                        or status != "APPROVED"
                        or type(approved) is not int or approved <= 0):
                    return None
                if conn.execute(
                    "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
                    "AND candidate_id=? LIMIT 1", (cid,),
                ).fetchone() is not None:
                    return None
                if conn.execute(
                    "SELECT 1 FROM executions WHERE trading_account_id='paper' "
                    "AND symbol=? AND (exchange_timestamp_ms IS NULL "
                    "OR exchange_timestamp_ms>=?) LIMIT 1",
                    (symbol, approved),
                ).fetchone() is not None:
                    return None
            return tuple(states[0])
    except (sqlite3.Error, ValueError, TypeError, ArithmeticError):
        return None


def _recent_ingress_quiet(health: object, overflow_symbol: str) -> bool:
    """Read existing Autopilot 60s load window; ignore lifetime high-watermark."""
    if not isinstance(health, dict):
        return False
    if (health.get("ok") is not True or health.get("healthy") is not True
            or health.get("unhealthy_symbols") != {}):
        return False
    roles = health.get("coverage_roles")
    if not isinstance(roles, dict) or any(
        role != "ENTRY_PENDING" for role in roles.values()
    ):
        # EXPOSURE cannot be taken through this narrow FLAT recovery.
        return False
    covered = health.get("covered_symbols")
    if not isinstance(covered, (list, tuple)) or set(covered) != set(roles):
        return False
    metrics, recent = health.get("ingress"), health.get("ingress_recent")
    if not isinstance(metrics, dict) or not isinstance(recent, dict):
        return False
    if (metrics.get("last_overflow_symbol") != overflow_symbol
            or type(metrics.get("capacity")) is not int
            or metrics["capacity"] <= 0
            or type(metrics.get("current_pending")) is not int
            or metrics["current_pending"] != 0
            or type(recent.get("current_pending")) is not int
            or recent["current_pending"] != 0
            or type(recent.get("recent_samples")) is not int
            or (covered and recent["recent_samples"] < 1)):
        return False
    for key in ("recent_max_queue_latency_ms", "recent_max_processing_ms"):
        value = recent.get(key)
        if (type(value) not in (int, float) or
                not 0 <= value < 2000):
            return False
    return True


def _record_required_reconcile_once(
    target: str, identity: str, state: tuple[str, str, str | None], *,
    db: Path, journal_root: Path | None = None, trusted_uid: int = 0,
) -> bool:
    """Fsync an existing owner-journal intent BEFORE one canonical reconcile.

    The exact durable Robot version identifies a distinct continuity event.
    A lost response cannot cause a second reconcile on the same event, even
    from a new invocation. This receipt authorizes no trade or release switch.
    """
    from tools.vps_gitless_release_activate import TRANSACTIONS, _sync_directory

    root = journal_root or TRANSACTIONS
    if (not root.is_dir() or root.is_symlink()
            or root.stat().st_uid != trusted_uid
            or root.stat().st_mode & 0o077):
        return False
    if not db.is_file() or db.is_symlink():
        return False
    try:
        with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                "SELECT mode, recovery_status, reason, version, updated_at_ms "
                "FROM robot_runtime_state WHERE trading_account_id='paper'"
            ).fetchall()
        if (len(rows) != 1 or tuple(rows[0][:3]) != state
                or type(rows[0][3]) is not int or rows[0][3] < 0
                or type(rows[0][4]) is not int or rows[0][4] < 0):
            return False
        source = (target, identity, str(rows[0][3]), str(rows[0][4]), str(state[2]))
        key = hashlib.sha256("\n".join(source).encode("utf-8")).hexdigest()
        marker = root / (".robot-required-reconcile-" + key)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(marker, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(b"ONE_SHOT_CANONICAL_RECONCILE_INVOKED\n")
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(root)
        return True
    except (FileExistsError, OSError, ValueError, TypeError, sqlite3.Error):
        return False


def _recover_active_ingress_overflow(
    target: str, *, root: Path, env_file: Path | None,
    clock=time.monotonic, sleep=time.sleep,
) -> str:
    """One authorized live-PAPER recovery inside the existing monolithic START.

    Freeze new ingress through the canonical stop coordinator, retain Backend
    and all protection, prove FLAT and a calm queue, reconcile exactly once,
    resume via canonical Robot/Scanner intents, then use the existing
    token-protected PAPER_AUTO startup helper. Never replay uncertain POSTs.
    """
    from tools.runtime_intent import (
        expected_database_identity, http_get, http_post_json,
    )
    from tools.stop_robot_runtime import (
        RuntimeShutdown, SafeStopError, _database_path,
    )
    from tools.vps_paper_auto_start import (
        StartupBlocked, enable_from_authorized_start,
    )
    from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release

    env = _environment(env_file)
    # The owner oneshot uses the protected optional owner.env. Read it only
    # when it is not already inherited by this explicitly authorized command.
    if not env.get("BYBITSCANNER_AUTOPILOT_OWNER_TOKEN"):
        from tools.vps_check import OWNER_ENV_FILE, parse_env_file
        try:
            if OWNER_ENV_FILE.is_file() and not OWNER_ENV_FILE.is_symlink():
                env.update(parse_env_file(OWNER_ENV_FILE))
        except OSError:
            pass
    if (env.get("BYBITSCANNER_VPS_PAPER_AUTO_ON_START") != "1"
            or len(env.get("BYBITSCANNER_AUTOPILOT_OWNER_TOKEN", "").strip()) < 32):
        return "BLOCKED: active_PAPER_recovery_owner_auto_authority_unproven; no_mutation"

    db = _database_path(root, env)
    origin = (env.get("BYBITSCANNER_PAPER_BACKEND_URL")
              or "http://127.0.0.1:8765").rstrip("/")
    if origin != "http://127.0.0.1:8765":
        return "BLOCKED: active_PAPER_recovery_noncanonical_backend; no_mutation"

    def get(path: str) -> dict:
        reply = http_get(origin + path, 5)
        body = reply.json()
        if reply.status != 200 or not isinstance(body, dict) or body.get("ok") is not True:
            raise ValueError("PAPER read-only endpoint unproven: " + path)
        return body

    def post(path: str, payload: dict) -> dict | None:
        # Each call is made once. Timeout/unknown response is never replayed.
        try:
            reply = http_post_json(
                origin + path, payload,
                180 if path == "/api/robot/reconcile" else 30,
            )
            body = reply.json()
            if (reply.status != 200 or not isinstance(body, dict)
                    or body.get("ok") is not True):
                return None
            return body
        except Exception:
            return None

    try:
        if verify_release(root) != target:
            return "BLOCKED: active_PAPER_release_changed; no_mutation"
        expected = expected_database_identity(root, env)
        health = get("/api/health")
        if (health.get("build_sha") != target
                or health.get("component") != "paper_backend"
                or health.get("mode") != "paper"
                or health.get("database_identity") != expected
                or health.get("paper_live_safe") is not True):
            return "BLOCKED: active_PAPER_identity_or_LIVE_fence_unproven; no_mutation"
        def backend_same() -> bool:
            current = get("/api/health")
            return (
                current.get("component") == "paper_backend"
                and current.get("mode") == "paper"
                and current.get("build_sha") == target
                and current.get("database_identity") == expected
                and current.get("paper_live_safe") is True
                and current.get("process_instance_id") == process_instance
            )

        process_instance = health.get("process_instance_id")
        if not isinstance(process_instance, str) or not process_instance.strip():
            return "BLOCKED: active_PAPER_process_identity_unproven; no_mutation"
        state = _active_required_flat_proof(db)
        if state is None:
            return "BLOCKED: active_PAPER_flat_ownership_unproven; no_mutation"
        mode, recovery, reason = state
        incident = _INGRESS_OVERFLOW_FENCE.fullmatch(str(reason or ""))
        # PAUSED/READY are resumable post-reconcile phases only when ingress
        # is frozen. Other REQUIRED reasons never authorize this route.
        if not (mode == "ROBOT_RUNNING" and
                (recovery in ("PAUSED", "READY") or
                 (recovery == "RECONCILIATION_REQUIRED" and incident))):
            return "BLOCKED: active_PAPER_recovery_not_proven_ingress_overflow; no_mutation"
        symbol = incident.group(1) if incident else None
        if recovery == "RECONCILIATION_REQUIRED":
            RuntimeShutdown(root=root, env=env).freeze_ingress_for_required_recovery()
        else:
            if (get("/api/scanner/status").get("mode") != "SCANNER_STOPPED"
                    or get("/api/robot/autopilot").get("mode") != "OFF"):
                return "BLOCKED: active_PAPER_recovery_phase_not_frozen; no_mutation"

        deadline = clock() + 75.0
        streak = 0
        while True:
            state = _active_required_flat_proof(db)
            if state is None or state[:2] != (mode, recovery):
                return "BLOCKED: active_PAPER_durable_state_changed; no_replay"
            if (get("/api/scanner/status").get("mode") != "SCANNER_STOPPED"
                    or get("/api/robot/autopilot").get("mode") != "OFF"):
                return "BLOCKED: active_PAPER_ingress_reopened; no_replay"
            coverage = get("/api/robot/protection-health")
            ingress = coverage.get("ingress")
            last = ingress.get("last_overflow_symbol") if isinstance(ingress, dict) else None
            if symbol is None:
                symbol = last
            if not isinstance(symbol, str) or not symbol:
                return "BLOCKED: active_PAPER_overflow_identity_unknown; no_replay"
            if _recent_ingress_quiet(coverage, symbol):
                streak += 1
                if streak >= 2:
                    break
            else:
                streak = 0
            remaining = deadline - clock()
            if remaining <= 0:
                return "BLOCKED: active_PAPER_ingress_not_quiet; protection_preserved"
            sleep(min(2.0, remaining))
        if (not backend_same() or _active_required_flat_proof(db) != state):
            return "BLOCKED: active_PAPER_post_freeze_identity_changed; no_replay"

        if recovery == "RECONCILIATION_REQUIRED":
            if not _record_required_reconcile_once(
                target, expected, state, db=db,
            ):
                return "BLOCKED: active_PAPER_prior_reconcile_attempt; no_replay"
            reply = post("/api/robot/reconcile", {})
            if (reply is None or reply.get("success") is not True
                    or reply.get("recovery_status") != "PAUSED"
                    or (_active_required_flat_proof(db) or ())[:2]
                    != ("ROBOT_RUNNING", "PAUSED")):
                return "BLOCKED: active_PAPER_canonical_reconcile_unproven; no_replay"
        if recovery != "READY":
            if not backend_same():
                return "BLOCKED: active_PAPER_backend_changed_before_Robot; no_replay"
            robot = post("/api/runtime/intent", {"intent": "ROBOT"})
            if (robot is None or robot.get("intent") != "ROBOT"
                    or robot.get("final", {}).get("robot") != "READY"
                    or robot.get("final", {}).get("protection") != "HEALTHY"):
                return "BLOCKED: active_PAPER_Robot_READY_unproven; no_replay"
        # Never revive Scanner before Robot and protection have converged.
        if not backend_same():
            return "BLOCKED: active_PAPER_backend_changed_before_Scanner; no_replay"
        scanner = post("/api/runtime/intent", {"intent": "SCANNER"})
        if (scanner is None or scanner.get("intent") != "SCANNER"
                or scanner.get("final", {}).get("scanner") != "RUNNING"):
            return "BLOCKED: active_PAPER_Scanner_RUNNING_unproven; no_replay"
        if not backend_same():
            return "BLOCKED: active_PAPER_backend_changed_before_AUTO; no_replay"
        try:
            enable_from_authorized_start(env)
        except StartupBlocked:
            return "BLOCKED: active_PAPER_AUTO_enable_unproven; no_replay"
        return _paper_full_readiness(
            root=root, env_file=env_file, target=target,
            require_gitless_telegram=True,
        )
    except (ReleaseIdentityBlocked, SafeStopError, OSError, ValueError,
            TypeError, sqlite3.Error):
        return "BLOCKED: active_PAPER_recovery_preflight_or_transition_unproven; no_replay"


class _MaintenanceParser(argparse.ArgumentParser):
    """Keep CLI refusal visible even when PowerShell truncates stderr usage."""

    def error(self, message: str) -> None:
        # A parsing error is always before STOP intent, deployment and API calls.
        # One bounded line survives SSH/PowerShell's native-command error surface.
        self.exit(2, "BLOCKED: paper_maintenance_cli: " + message.replace("\n", " ")[:240] + "\n")


def main(argv=None) -> int:
    parser = _MaintenanceParser(description="Fail-closed one-action PAPER maintenance")
    parser.add_argument("sha")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--resume-installed-editor-only", action="store_true",
                        help="only after an exact Gitless release was safely installed")
    parser.add_argument("--staged-gitless-editor-only", type=Path,
                        help="owner-approved exact staged checkout; safe-stop and install once")
    parser.add_argument("--start-paper-after-editor", action="store_true",
                        help="after safe Gitless Editor recovery, start owner PAPER oneshot")
    parser.add_argument("--publish-frontend-only", action="store_true",
                        help="verified existing EDITOR_ONLY; static-only publication, no systemd or STOP")
    parser.add_argument("--frontend-bundle", type=Path,
                        help="exact-SHA Vite artifact; publish static files after EDITOR_ONLY proof")
    parser.add_argument("--frontend-current-index-sha256",
                        help="required for first adoption of an untracked HTTPS index")
    parser.add_argument("--dual-orphan-handoff-20261103", action="store_true",
                        help="separate explicit opt-in to exact JASMY/FLOW protected handoff")
    parser.add_argument("--proven-one-flat-orphan-handoff", action="store_true",
                        help="explicit owner opt-in: one immutable manual Flat/OPEN close, no trade replay")
    parser.add_argument("--resume-one-flat-from-prior-stop", metavar="SHA",
                        help="separately authorized continuation of a proven failed STOP; never replay STOP")
    parser.add_argument("--expected-old-backend", metavar="SHA",
                        help="exact installed Backend observed at the failed STOP")
    args = parser.parse_args(argv)
    if args.resume_installed_editor_only and args.staged_gitless_editor_only:
        parser.error("choose exactly one Gitless operation")
    if args.frontend_bundle and not (args.publish_frontend_only
                                    or args.staged_gitless_editor_only):
        parser.error("frontend publication requires --publish-frontend-only or staged Gitless update")
    if args.publish_frontend_only and (not args.frontend_bundle
            or args.resume_installed_editor_only or args.staged_gitless_editor_only
            or args.start_paper_after_editor or args.proven_one_flat_orphan_handoff
            or args.dual_orphan_handoff_20261103
            or args.resume_one_flat_from_prior_stop
            or args.expected_old_backend):
        parser.error("frontend-only cannot replay STOP, resume, start or exceptional handoff")
    if args.frontend_current_index_sha256 and not args.frontend_bundle:
        parser.error("frontend index pin requires a frontend bundle")
    if args.frontend_bundle and args.start_paper_after_editor:
        parser.error("static frontend publication is EDITOR_ONLY, not trading START")
    if args.start_paper_after_editor and not (
        args.staged_gitless_editor_only or args.resume_installed_editor_only
    ):
        parser.error("full PAPER start requires verified Gitless Editor recovery")
    if args.dual_orphan_handoff_20261103 and not args.staged_gitless_editor_only:
        parser.error("exceptional handoff requires staged Gitless operation")
    if args.proven_one_flat_orphan_handoff and not args.staged_gitless_editor_only:
        parser.error("one orphan handoff requires staged Gitless operation")
    if args.proven_one_flat_orphan_handoff and args.dual_orphan_handoff_20261103:
        parser.error("choose exactly one exceptional handoff policy")
    if bool(args.resume_one_flat_from_prior_stop) != bool(args.expected_old_backend):
        parser.error("partial continuation requires both exact old Backend and STOP SHA")
    if args.resume_one_flat_from_prior_stop and (
        not args.staged_gitless_editor_only
        or args.proven_one_flat_orphan_handoff
        or args.dual_orphan_handoff_20261103
        or args.resume_installed_editor_only
        or args.start_paper_after_editor
    ):
        parser.error("partial one-flat continuation requires Editor staging alone")
    if args.publish_frontend_only:
        # This branch never invokes shutdown, service start, release switch,
        # Robot commands or a DB write. Installed EDITOR_ONLY must be proven.
        from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
        from tools.vps_terminal_frontend_publish import (
            FrontendPublishBlocked, inspect_bundle, publish_frontend,
        )
        try:
            if verify_release(REPO) != args.sha:
                raise FrontendPublishBlocked("installed_frontend_source_sha_mismatch")
            identity = _durable_editor_freeze(REPO, args.env_file)
            if not _editor_runtime_ready(args.sha, identity):
                raise FrontendPublishBlocked("editor_only_runtime_not_proven")
            inspect_bundle(args.frontend_bundle, args.sha)
            status = publish_frontend(
                args.sha, bundle=args.frontend_bundle, root=REPO,
                expected_index_sha256=args.frontend_current_index_sha256,
            )
        except (ReleaseIdentityBlocked, FrontendPublishBlocked,
                OSError, ValueError, UnicodeError, sqlite3.Error) as exc:
            status = "BLOCKED: frontend_only_preflight_or_publication:" + type(exc).__name__
        print(status)
        return 0 if status.startswith("FRONTEND_READY:") else 2
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
                # A degraded but live PAPER owner must not be mistaken for a
                # stopped EDITOR_ONLY state. In particular REQUIRED with
                # PAPER_AUTO still configured is closed admission, not READY.
                blocked = _active_exact_paper_blocker(
                    args.sha, root=REPO, env_file=args.env_file,
                )
                if blocked is not None:
                    if ((blocked.startswith(
                            "BLOCKED: active_PAPER_Robot_RECONCILIATION_REQUIRED")
                            and "reason=ROBOT_PROTECTION_COVERAGE_LOST" in blocked)
                            or blocked.startswith(
                                "BLOCKED: active_exact_PAPER_not_ready; "
                                "Robot=ROBOT_RUNNING/PAUSED")
                            or blocked.startswith(
                                "BLOCKED: active_exact_PAPER_not_ready; "
                                "Robot=ROBOT_RUNNING/READY")):
                        blocked = _recover_active_ingress_overflow(
                            args.sha, root=REPO, env_file=args.env_file,
                        )
                    print(blocked)
                    return 0 if blocked.startswith("READY:") else 2
    if args.resume_one_flat_from_prior_stop:
        from tools.paper_stopped_approved_recovery import (
            recover_one_flat_after_failed_stop,
        )
        try:
            status = recover_one_flat_after_failed_stop(
                target=args.sha, stage=args.staged_gitless_editor_only,
                prior_stop=args.resume_one_flat_from_prior_stop,
                expected_old_sha=args.expected_old_backend,
            )
        except Exception as exc:
            status = ("BLOCKED: one_flat_partial_STOP_recovery:"
                      + type(exc).__name__ + ":"
                      + str(exc).replace(chr(10), " ")[:280]
                      + "; no STOP replay or deployment on unknown outcome")
    elif args.staged_gitless_editor_only:
        status = deploy_staged_editor_only(
            args.sha, stage=args.staged_gitless_editor_only,
            env_file=args.env_file,
            dual_orphan_handoff=args.dual_orphan_handoff_20261103,
            proven_one_flat_orphan_handoff=args.proven_one_flat_orphan_handoff,
            frontend_bundle=args.frontend_bundle,
            frontend_expected_index_sha256=args.frontend_current_index_sha256,
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
