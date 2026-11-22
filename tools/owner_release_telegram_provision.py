"""Fail-closed, disabled preparation of the existing owner release adapter.

Called ONLY under paper_maintenance's canonical owner lifecycle lock. No
timer enable, daemon-reload, signing keys, config, GitHub/Telegram polling,
Backend, Scanner, Robot or PAPER operations. Never overwrite old receipts.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import stat
import tempfile

from tools.owner_release_telegram_runtime import (
    OWNER_UNIT_NAMES, CONFIG, STATE, _check_ledger, _check_sources, _check_units,
    _check_relay_inbox, _private_json,
)
from tools.owner_update_grant import GrantLedger
from tools.telegram_release_inbox import INBOX
from tools.vps_gitless_release_activate import _manifest, _trusted_file
from tools.vps_release_identity import (
    MANIFEST, ROOT, SHA40, git_blob_hash, _safe_file, verify_release,
)


def _directory(path: Path, *, uid: int, owner: int) -> bool:
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or path.parent.is_symlink()
            or parent.st_uid != uid or parent.st_mode & 0o022):
        raise ValueError("untrusted owner release parent")
    created = False
    try:
        os.mkdir(path, 0o700)
        created = True
        if owner != uid:
            os.chown(path, owner, -1)
    except FileExistsError:
        pass
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or path.is_symlink()
            or info.st_uid != owner or stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("untrusted owner release directory")
    return created


def _new_exact_file(path: Path, payload: bytes, *, uid: int, mode: int) -> None:
    """Create only if absent; otherwise require exact protected bytes."""
    if path.exists() or path.is_symlink():
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != mode
                or path.read_bytes() != payload):
            raise ValueError("existing owner release file differs")
        return
    fd, temp_name = tempfile.mkstemp(prefix=".owner-release-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_name, path, follow_symlinks=False)
        except FileExistsError as exc:
            raise ValueError("owner release file created concurrently") from exc
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        os.unlink(temp_name)


def prepare(expected_sha: str, *, root=ROOT, manifest_path=MANIFEST,
            unit_dir=Path("/etc/systemd/system"),
            state=STATE, inbox=INBOX, config=CONFIG, uid=0, relay_uid=None) -> str:
    """Install only disabled, exact-pinned files and empty private journals."""
    if os.geteuid() != uid or type(expected_sha) is not str or not SHA40.fullmatch(expected_sha):
        raise ValueError("owner or exact SHA required")
    if os.path.lexists(config):
        raise ValueError("owner release config already present; no preparation")
    installed = verify_release(root, manifest_path, require_protected_manifest=(uid == 0))
    if installed != expected_sha:
        raise ValueError("installed release changed")
    _check_sources(root, manifest_path, installed)
    manifest = _manifest(_trusted_file(manifest_path, uid))
    if relay_uid is None:
        relay_uid = pwd.getpwnam("bybitscanner").pw_uid
    if type(relay_uid) is not int or relay_uid <= 0:
        raise ValueError("untrusted relay owner")
    unit_info = unit_dir.lstat()
    if (not stat.S_ISDIR(unit_info.st_mode) or unit_info.st_uid != uid
            or unit_info.st_mode & 0o022 or unit_dir.is_symlink()):
        raise ValueError("untrusted systemd unit directory")
    expected_units = {}
    for name in OWNER_UNIT_NAMES:
        rel = "deploy/systemd/" + name
        raw = _trusted_file(_safe_file(root, rel), uid)
        if manifest["blobs"].get(rel) != git_blob_hash(raw):
            raise ValueError("owner release unit source not pinned")
        path = unit_dir / name
        if path.exists() or path.is_symlink():
            _new_exact_file(path, raw, uid=uid, mode=0o644)
        expected_units[path] = raw

    # Protect user-owned prior setup: do not recreate a missing journal in
    # an existing state directory or overwrite any nonmatching unit.
    existing = state.exists() or state.is_symlink()
    if existing:
        _directory(state, uid=uid, owner=uid)
        if _private_json(state / "pending.json") != {"pending": None}:
            raise ValueError("existing approval state not idle")
        for name in ("prompts", "grants"):
            _check_ledger(state / name, uid=uid)

    _directory(state, uid=uid, owner=uid)
    if not existing:
        _new_exact_file(state / "pending.json", b'{"pending":null}', uid=uid, mode=0o600)
        for name in ("prompts", "grants"):
            if not _directory(state / name, uid=uid, owner=uid):
                raise ValueError("unexpected existing approval ledger")
            GrantLedger(state / name).initialize()

    _check_ledger(state / "prompts", uid=uid)
    _check_ledger(state / "grants", uid=uid)
    _directory(inbox, uid=uid, owner=relay_uid)
    _check_relay_inbox(inbox, relay_uid)

    for path, raw in expected_units.items():
        _new_exact_file(path, raw, uid=uid, mode=0o644)
    _check_units(root, manifest_path, unit_dir, uid=uid)
    if verify_release(root, manifest_path, require_protected_manifest=(uid == 0)) != expected_sha:
        raise ValueError("installed release changed during preparation")
    return "READY: OWNER_RELEASE_PREPARED_DISABLED; config/keys/timer remain absent"
