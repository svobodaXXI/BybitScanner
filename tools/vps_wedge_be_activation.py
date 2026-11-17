"""One-shot, fail-closed Wedge BE opt-in inside the existing owner monolith.

Never starts Scanner, Robot or PAPER_AUTO. The original PAPER env is retained as
a uniquely named same-directory backup. Unknown STOP/resume outcomes are not
retried; recovery requires separate owner investigation.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
import time
import uuid

ROOT = Path("/opt/BybitScanner")
ENV = Path("/etc/bybitscanner/paper.env")
OWNER_ENV = Path("/etc/bybitscanner/owner.env")
SIMULATOR_ENV = Path("/etc/bybitscanner/simulator.env")
FLAG = b"BYBITSCANNER_ROBOT_WEDGE_BE_PAPER_AUTO"


class WedgeBEBlocked(ValueError):
    pass


def _read_env(path: Path, *, required: bool, uid: int) -> tuple[bytes | None, os.stat_result | None]:
    parent = path.parent.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or path.parent.is_symlink()
            or parent.st_uid != uid or parent.st_mode & 0o022):
        raise WedgeBEBlocked("environment_parent_untrusted")
    if path.is_symlink():
        raise WedgeBEBlocked("environment_symlink")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        if required:
            raise WedgeBEBlocked("paper_environment_missing")
        return None, None
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o022):
            raise WedgeBEBlocked("environment_permissions_untrusted")
        data = stream.read(65537)
    if len(data) > 65536 or b"\0" in data or b"\r" in data:
        raise WedgeBEBlocked("environment_format_untrusted")
    return data, info


def _unchanged(path: Path, original: bytes | None, info: os.stat_result | None, uid: int) -> bool:
    try:
        data, now = _read_env(path, required=info is not None, uid=uid)
    except (OSError, WedgeBEBlocked):
        return False
    return (data == original and (info is None or (
        now is not None and (now.st_dev, now.st_ino, now.st_mode, now.st_uid, now.st_gid)
        == (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid))))


def _no_be_key(data: bytes | None) -> bool:
    # Fail closed on any existing appearance, even in comments or quotes.
    return data is None or FLAG not in data


def _write_once(path: Path, original: bytes, info: os.stat_result, *, uid: int) -> None:
    """Persist recoverable original and replace only a proven unchanged file."""
    if not original or not _no_be_key(original) or not _unchanged(path, original, info, uid):
        raise WedgeBEBlocked("paper_env_changed_before_commit")
    backup = path.with_name(path.name + ".before-wedge-be-" + uuid.uuid4().hex)
    os.link(path, backup, follow_symlinks=False)
    fd = -1
    temp = ""
    try:
        fd, temp = tempfile.mkstemp(prefix=".wedge-be-", dir=str(path.parent))
        with os.fdopen(fd, "wb") as stream:
            fd = -1
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            stream.write(original + (b"" if original.endswith(b"\n") else b"\n") + FLAG + b"=1\n")
            stream.flush()
            os.fsync(stream.fileno())
        if not _unchanged(path, original, info, uid):
            raise WedgeBEBlocked("paper_env_changed_during_commit")
        os.replace(temp, path)
        temp = ""
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if fd != -1:
            os.close(fd)
        if temp and os.path.exists(temp):
            os.unlink(temp)


def enable_wedge_be(target: str, *, root: Path = ROOT, env_file: Path = ENV,
                    owner_env: Path = OWNER_ENV, simulator_env: Path = SIMULATOR_ENV,
                    uid: int = 0) -> str:
    """Protected EDITOR_ONLY STOP -> opt in -> EDITOR_ONLY resume, once only."""
    from tools import paper_maintenance as m
    from tools.vps_release_identity import verify_release
    from tools.vps_release_resume import check_resume, ResumeBlocked
    from tools.vps_simulator_device_provision import _robot_stopped, _runtime_env

    try:
        if os.geteuid() != uid or not re.fullmatch("[0-9a-f]{40}", target):
            raise WedgeBEBlocked("root_and_exact_sha_required")
        if verify_release(root) != target:
            raise WedgeBEBlocked("installed_release_mismatch")

        original, info = _read_env(env_file, required=True, uid=uid)
        owner, owner_info = _read_env(owner_env, required=False, uid=uid)
        simulator, sim_info = _read_env(simulator_env, required=False, uid=uid)
        if not all(_no_be_key(value) for value in (original, owner, simulator)):
            raise WedgeBEBlocked("existing_or_conflicting_be_configuration_preserved")
        if FLAG.decode("ascii") in _runtime_env():
            raise WedgeBEBlocked("active_backend_be_configuration_conflict")

        identity = m._durable_editor_freeze(root, env_file)
        if not (m._editor_runtime_ready(target, identity)
                and m._paper_start_quiescent(root, env_file)
                and _robot_stopped(root=root, env_file=env_file)):
            raise WedgeBEBlocked("editor_only_flat_and_robot_stop_unproven")

        stopped = m._stop_exact_installed_paper_once(target, env_file=env_file, trusted_uid=uid)
        if not stopped.startswith("READY:"):
            return "BLOCKED: wedge_be_canonical_stop_unproven; no_retry"

        for attempt in range(30):
            try:
                if check_resume(target, root=root).startswith("RESUME_READY:"):
                    break
            except (ResumeBlocked, OSError, ValueError):
                pass
            if attempt == 29:
                return "BLOCKED: wedge_be_stopped_resume_unproven; no_retry"
            time.sleep(0.5)

        if (m._durable_editor_freeze(root, env_file) != identity
                or not m._paper_start_quiescent(root, env_file)
                or not _robot_stopped(root=root, env_file=env_file)
                or not _unchanged(env_file, original, info, uid)
                or not _unchanged(owner_env, owner, owner_info, uid)
                or not _unchanged(simulator_env, simulator, sim_info, uid)):
            return "BLOCKED: wedge_be_post_stop_invariants_unproven; no_env_change_or_retry"

        _write_once(env_file, original, info, uid=uid)

        resumed = m.resume_installed_release(target, root=root, env_file=env_file)
        if not resumed.startswith("READY:"):
            return "BLOCKED: wedge_be_editor_resume_unproven; no_retry"
        effective = _runtime_env()
        if (effective.get(FLAG.decode("ascii")) != "1"
                or m._durable_editor_freeze(root, env_file) != identity
                or not m._editor_runtime_ready(target, identity)
                or not m._paper_start_quiescent(root, env_file)
                or not _robot_stopped(root=root, env_file=env_file)
                or not _unchanged(owner_env, owner, owner_info, uid)
                or not _unchanged(simulator_env, simulator, sim_info, uid)):
            return "BLOCKED: wedge_be_effective_runtime_unproven; no_retry"
        return "READY: wedge BE ON in exact Backend; EDITOR_ONLY restored; no Robot or Scanner started"
    except (WedgeBEBlocked, OSError, ValueError, TypeError, sqlite3.Error) as exc:
        return "BLOCKED: wedge_be_preflight_or_postcondition:" + type(exc).__name__ + "; no_retry"
