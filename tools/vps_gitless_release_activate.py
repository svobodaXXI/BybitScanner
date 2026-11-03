"""Offline, stopped-only Gitless PAPER release installation.

This is an internal helper of the one-command coordinator, NOT an alternate
trading/process stop command. Old and new tracked bytes are independently
attested. Interrupted file installation resumes from a root-owned transaction
with rollback bytes, never by replaying a trading action or sending a signal.
"""
from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Callable

from tools.vps_release_identity import (
    MANIFEST, ROOT, ReleaseIdentityBlocked, _validate_manifest,
    create_manifest, git_blob_hash, verify_release,
)
from tools.vps_release_resume import _assert_no_listeners, _systemd_state
from tools.vps_systemd_unit_prepare import UNITS

UNIT_DIR = Path("/etc/systemd/system")
TRANSACTIONS = Path("/var/lib/bybitscanner/release-transactions")


class ActivationBlocked(ValueError):
    pass


def _demand(condition: bool, reason: str) -> None:
    if not condition:
        raise ActivationBlocked(reason)


def _trusted_file(path: Path, uid: int) -> bytes:
    _demand(path.is_file() and not path.is_symlink(), "untrusted_release_metadata")
    meta = path.stat()
    _demand(meta.st_uid == uid and not meta.st_mode & 0o022, "unprotected_release_metadata")
    return path.read_bytes()


def _manifest(payload: bytes) -> dict:
    try:
        obj = json.loads(payload)
    except (ValueError, UnicodeError) as exc:
        raise ActivationBlocked("invalid_manifest_json") from exc
    try:
        _validate_manifest(obj)
    except ReleaseIdentityBlocked as exc:
        raise ActivationBlocked(str(exc)) from exc
    return obj


def _safe_path(root: Path, name: str) -> Path:
    _demand(root.is_dir() and not root.is_symlink(), "unsafe_release_root")
    path = root
    for part in name.split("/"):
        _demand(bool(part) and part not in (".", "..") and "\\" not in part,
                "invalid_release_path")
        path = path / part
        _demand(not path.is_symlink(), "release_path_symlink")
        if part != name.split("/")[-1] and path.exists():
            _demand(path.is_dir(), "release_parent_not_directory")
    return path


def _blob(path: Path) -> str | None:
    if not path.exists():
        return None
    _demand(path.is_file() and not path.is_symlink(), "release_path_not_regular")
    return git_blob_hash(path.read_bytes())


def _check_files(root: Path, old: dict, new: dict) -> None:
    """Every file must be either old, target, or legitimately not yet created."""
    for name in sorted(set(old) | set(new)):
        _demand(not (
            name == "config.py" or name == "paper_runtime.sqlite3"
            or name.startswith(("venv/", "runtime/", "Backups/", ".git/"))
        ), "release_touches_runtime_owned_file")
        path = _safe_path(root, name)
        got = _blob(path)
        permitted = {old.get(name), new.get(name)}
        if name in old and name in new:
            permitted.discard(None)
        _demand(got in permitted, "tracked_or_untracked_collision:" + name)


def _check_units(unit_dir: Path, root: Path, stage: Path,
                 old: dict, new: dict, *, old_units: dict[str, bool]) -> None:
    _demand(unit_dir.is_dir() and not unit_dir.is_symlink(), "unsafe_unit_directory")
    for unit in UNITS:
        name = "deploy/systemd/" + unit
        _demand(name in old and name in new, "missing_tracked_systemd_unit")
        destination = unit_dir / unit
        _demand(not destination.is_symlink(), "systemd_unit_symlink")
        got = destination.read_bytes() if destination.is_file() else None
        old_bytes = _safe_path(root, name).read_bytes() if (
            _blob(_safe_path(root, name)) == old[name]
        ) else None
        new_bytes = _safe_path(stage, name).read_bytes()
        # A transaction may have already copied the new tracked file, so
        # old unit bytes can come from the pinned rollback snapshot instead.
        if old_units[unit]:
            _demand(got is not None and (
                (old_bytes is not None and got == old_bytes) or got == new_bytes
            ), "systemd_unit_modified:" + unit)
        else:
            _demand(got is None or got == new_bytes,
                    "untracked_systemd_unit_collision:" + unit)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_file(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".paper-release-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        _sync_directory(path.parent)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def _stopped(states: Callable, listeners: Callable) -> None:
    for unit in UNITS:
        state = states(unit)
        _demand(isinstance(state, dict)
                and state.get("ActiveState") in ("inactive", "failed")
                and str(state.get("MainPID")) == "0",
                "PAPER_unit_not_stopped:" + unit)
    listeners()


def _new_manifest(stage: Path, sha: str) -> dict:
    _demand(stage.is_dir() and not stage.is_symlink(), "unsafe_stage_root")
    try:
        return create_manifest(stage, sha)
    except (ReleaseIdentityBlocked, OSError) as exc:
        raise ActivationBlocked("staging_release_unproven:" + type(exc).__name__) from exc


def inspect_staged_release(sha: str, *, stage: Path, root: Path = ROOT,
                           manifest: Path = MANIFEST, unit_dir: Path = UNIT_DIR,
                           uid: int = 0) -> dict:
    """Read-only before freeze: refuse dirty tracked files and user-file collisions."""
    _demand(root.is_dir() and not root.is_symlink(), "unsafe_release_root")
    new = _new_manifest(stage, sha)
    old = _manifest(_trusted_file(manifest, uid))
    _demand(old["build_sha"] != sha, "target_already_installed")
    try:
        verify_release(root, manifest, require_protected_manifest=True)
    except ReleaseIdentityBlocked as exc:
        raise ActivationBlocked("installed_release_unproven") from exc
    _check_files(root, old["blobs"], new["blobs"])
    units = {}
    _demand(unit_dir.is_dir() and not unit_dir.is_symlink(), "unsafe_unit_directory")
    for unit in UNITS:
        name = "deploy/systemd/" + unit
        _demand(name in old["blobs"] and name in new["blobs"], "missing_tracked_systemd_unit")
        installed = unit_dir / unit
        _demand(not installed.is_symlink(), "systemd_unit_symlink")
        if installed.exists():
            _demand(installed.is_file() and installed.read_bytes()
                    == _safe_path(root, name).read_bytes(),
                    "systemd_unit_modified:" + unit)
        units[unit] = installed.exists()
    return {"old": old, "new": new, "units_before": units}


def activate_staged_release(
    sha: str, *, stage: Path, stopped_proof: object,
    root: Path = ROOT, manifest: Path = MANIFEST,
    unit_dir: Path = UNIT_DIR, transactions: Path = TRANSACTIONS,
    uid: int = 0, states: Callable = _systemd_state,
    listeners: Callable = _assert_no_listeners,
) -> str:
    """Switch tracked files only after canonical stop or a trusted prior receipt.

    A previous transaction is the sole restart entitlement, and is checked
    against exact stage bytes and stopped host reality. It cannot itself
    authorize a new STOP, Close-All or SIGINT.
    """
    _demand(os.geteuid() == uid, "release_requires_trusted_operator")
    _demand(transactions.is_dir() and not transactions.is_symlink(),
            "missing_protected_transaction_directory")
    parent_stat = transactions.stat()
    _demand(parent_stat.st_uid == uid and not parent_stat.st_mode & 0o077,
            "unprotected_transaction_directory")
    _demand(not manifest.is_symlink(), "manifest_symlink")
    _demand(manifest.parent.is_dir() and not manifest.parent.is_symlink(),
            "unsafe_manifest_directory")
    stage_manifest = _new_manifest(stage, sha)
    journal = transactions / sha
    with (transactions / ".release.lock").open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _stopped(states, listeners)
        if journal.exists():
            _demand(journal.is_dir() and not journal.is_symlink(), "untrusted_transaction")
            rec = _manifest(_trusted_file(journal / "target.json", uid))
            original = _manifest(_trusted_file(journal / "old.json", uid))
            _demand(rec == stage_manifest and original["build_sha"] != sha,
                    "transaction_target_mismatch")
            _demand(_manifest(_trusted_file(manifest, uid)) in (rec, original),
                    "manifest_changed_during_transaction")
            units_before = json.loads(_trusted_file(journal / "units.json", uid))
            _demand(set(units_before) == set(UNITS) and
                    all(type(x) is bool for x in units_before.values()),
                    "corrupt_transaction_units")
            for name, digest in original["blobs"].items():
                backup = _safe_path(journal / "rollback", name)
                _demand(_blob(backup) == digest, "rollback_backup_missing_or_changed:" + name)
        else:
            _demand(getattr(stopped_proof, "ok", False) is True
                    and getattr(stopped_proof, "runtime_stopped", False) is True,
                    "canonical_safe_stop_unproven")
            data = inspect_staged_release(
                sha, stage=stage, root=root, manifest=manifest, unit_dir=unit_dir, uid=uid,
            )
            original, rec, units_before = data["old"], data["new"], data["units_before"]
            pending = Path(tempfile.mkdtemp(prefix=".prepare-" + sha + "-", dir=transactions))
            (pending / "rollback").mkdir(mode=0o700)
            for name in original["blobs"]:
                backup = _safe_path(pending / "rollback", name)
                backup.parent.mkdir(parents=True, exist_ok=True)
                backup.write_bytes(_safe_path(root, name).read_bytes())
                backup.chmod(0o600)
            _atomic_file(pending / "old.json", json.dumps(original, sort_keys=True).encode(), 0o600)
            _atomic_file(pending / "target.json", json.dumps(rec, sort_keys=True).encode(), 0o600)
            _atomic_file(pending / "units.json", json.dumps(units_before, sort_keys=True).encode(), 0o600)
            _sync_directory(pending)
            os.rename(pending, journal)
            _sync_directory(transactions)

        old_blobs, new_blobs = original["blobs"], rec["blobs"]
        _check_files(root, old_blobs, new_blobs)
        # Compare units against pinned rollback data rather than the possibly
        # already-upgraded tracked source on an interrupted transaction.
        for unit in UNITS:
            name = "deploy/systemd/" + unit
            _demand(name in old_blobs and name in new_blobs, "missing_tracked_systemd_unit")
            installed = unit_dir / unit
            _demand(not installed.is_symlink(), "systemd_unit_symlink")
            got = installed.read_bytes() if installed.is_file() else None
            previous = _safe_path(journal / "rollback", name).read_bytes()
            target = _safe_path(stage, name).read_bytes()
            permitted = {previous, target} if units_before[unit] else {None, target}
            _demand(got in permitted, "systemd_unit_modified:" + unit)

        for name, digest in sorted(new_blobs.items()):
            source = _safe_path(stage, name)
            raw = source.read_bytes()
            _demand(git_blob_hash(raw) == digest, "staging_changed_during_switch:" + name)
            destination = _safe_path(root, name)
            if _blob(destination) == digest:
                continue
            _atomic_file(destination, raw, stat.S_IMODE(source.stat().st_mode))
        for name in sorted(set(old_blobs) - set(new_blobs)):
            dest = _safe_path(root, name)
            if dest.exists():
                _demand(_blob(dest) == old_blobs[name], "old_tracked_file_changed:" + name)
                dest.unlink()
                _sync_directory(dest.parent)
        for unit in UNITS:
            source = _safe_path(stage, "deploy/systemd/" + unit)
            data = source.read_bytes()
            _demand(git_blob_hash(data) == new_blobs["deploy/systemd/" + unit],
                    "staging_unit_changed:" + unit)
            dest = unit_dir / unit
            if not dest.is_file() or dest.read_bytes() != data:
                _atomic_file(dest, data, stat.S_IMODE(source.stat().st_mode))

        # Install the protected release manifest last; it is the commit point.
        # A crash before it is written is recoverable via the pinned rollback.
        installed_manifest = _manifest(_trusted_file(manifest, uid))
        _demand(installed_manifest in (rec, original),
                "manifest_changed_during_switch")
        if installed_manifest != rec:
            _atomic_file(manifest, json.dumps(rec, sort_keys=True).encode(), 0o600)
        try:
            actual = verify_release(root, manifest, require_protected_manifest=True)
        except ReleaseIdentityBlocked as exc:
            raise ActivationBlocked("post_switch_release_unproven") from exc
        _demand(actual == sha, "post_switch_target_mismatch")
        _sync_directory(unit_dir)
        return "INSTALLED_STOPPED: exact Gitless tracked release; rollback pinned; no services started"
