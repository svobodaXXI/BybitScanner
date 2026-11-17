"""Protected one-device Simulator pairing through the existing PAPER owner monolith.

Only tools.paper_maintenance may call provision_owner_pc; no separate CLI, HTTP
endpoint, pairing authority, or runtime service. The secret is generated on the
VPS after canonical STOP and never leaves the protected owner env except through
the already owner-authenticated, pre-existing /pair API. No secret in argv/logs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import tempfile
import time

ORIGIN = "https://83.217.213.181"  # Owner verified TLS and anonymous 401 on main PC.
OWNER_ENV = Path("/etc/bybitscanner/owner.env")
PAPER_ENV = Path("/etc/bybitscanner/paper.env")
ROOT = Path("/opt/BybitScanner")
UNIT = "bybitscanner-paper-backend.service"
KEY_ORIGIN = "BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN"
KEY_DEVICES = "BYBITSCANNER_SIMULATOR_BRIDGE_DEVICES_JSON"
FACTS_ROUTE = b"location = /api/diary/simulator-bridge/facts {"


class ProvisionBlocked(ValueError):
    """A fixed, non-secret reason for refusing one-shot provisioning."""


def _owner_bytes(path: Path, *, uid: int) -> bytes | None:
    try:
        parent = path.parent.lstat()
    except OSError as exc:
        raise ProvisionBlocked("owner_env_directory_unreadable") from exc
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid or parent.st_mode & 0o022:
        raise ProvisionBlocked("owner_env_directory_untrusted")
    if path.is_symlink():
        raise ProvisionBlocked("owner_env_symlink")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProvisionBlocked("owner_env_unreadable") from exc
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o077):
            raise ProvisionBlocked("owner_env_permissions_untrusted")
        data = os.read(fd, 8193)
        if len(data) > 8192 or b"\0" in data or b"\r" in data:
            raise ProvisionBlocked("owner_env_format_untrusted")
        data.decode("ascii")
        return data
    except (OSError, UnicodeError) as exc:
        raise ProvisionBlocked("owner_env_unreadable") from exc
    finally:
        os.close(fd)


def _ensure_unconfigured(original: bytes | None) -> None:
    # Refuse any prior/partial configuration, even comments, quoted names or
    # duplicate assignments. Never overwrite an unknown device key.
    if original is not None and b"BYBITSCANNER_SIMULATOR_BRIDGE_" in original:
        raise ProvisionBlocked("existing_pairing_preserved")


def _paper_env_bytes(path: Path, *, uid: int) -> bytes:
    """The other effective EnvironmentFile must not carry conflicting relay keys."""
    try:
        if path.is_symlink():
            raise ProvisionBlocked("paper_env_symlink")
        info = path.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o022):
            raise ProvisionBlocked("paper_env_untrusted")
        data = path.read_bytes()
        if len(data) > 65536 or b"BYBITSCANNER_SIMULATOR_BRIDGE_" in data:
            raise ProvisionBlocked("paper_env_relay_conflict")
        return data
    except OSError as exc:
        raise ProvisionBlocked("paper_env_unavailable") from exc


def _runtime_env(*, runner=subprocess.run) -> dict[str, str]:
    try:
        reply = runner(
            ["systemctl", "show", UNIT,
             "--property=ActiveState,MainPID", "--no-pager"],
            capture_output=True, text=True, check=False, timeout=10,
        )
        if reply.returncode:
            raise ProvisionBlocked("backend_owner_unproven")
        fields = dict(line.split("=", 1) for line in reply.stdout.splitlines() if "=" in line)
        pid = int(fields.get("MainPID", "0"))
        if fields.get("ActiveState") != "active" or pid <= 1:
            raise ProvisionBlocked("backend_not_active")
        raw = Path(f"/proc/{pid}/environ").read_bytes()
        if len(raw) > 131072:
            raise ProvisionBlocked("backend_environment_unproven")
        result: dict[str, str] = {}
        for part in raw.split(b"\0"):
            if not part:
                continue
            if b"=" not in part:
                raise ProvisionBlocked("backend_environment_unproven")
            key, value = part.split(b"=", 1)
            name = key.decode("ascii")
            if name in result:
                raise ProvisionBlocked("duplicate_backend_environment")
            result[name] = value.decode("utf-8")
        return result
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        if isinstance(exc, ProvisionBlocked):
            raise
        raise ProvisionBlocked("backend_environment_unproven") from exc


def _robot_stopped(*, root: Path, env_file: Path) -> bool:
    from tools.stop_robot_runtime import _database_path, _environment
    db = _database_path(root, _environment(env_file))
    if not db.is_file() or db.is_symlink():
        return False
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as conn:
        conn.execute("PRAGMA query_only=ON")
        states = conn.execute(
            "SELECT mode, recovery_status FROM robot_runtime_state "
            "WHERE trading_account_id='paper'"
        ).fetchall()
    return states == [("ROBOT_STOPPED", "ROBOT_STOPPED")]


def _atomic_install(path: Path, prior: bytes | None, new: bytes, *, uid: int) -> None:
    if _owner_bytes(path, uid=uid) != prior:
        raise ProvisionBlocked("owner_env_changed_after_stop")
    fd, name = tempfile.mkstemp(prefix=".owner-env-pair-", dir=str(path.parent))
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(new)
            stream.flush()
            os.fsync(stream.fileno())
        if _owner_bytes(path, uid=uid) != prior:
            raise ProvisionBlocked("owner_env_changed_during_write")
        os.replace(tmp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if tmp.exists():
            tmp.unlink()


def provision_owner_pc(target: str, *, root: Path = ROOT,
                       env_file: Path = PAPER_ENV, owner_env: Path = OWNER_ENV,
                       uid: int = 0) -> str:
    """One guarded STOP -> secret in root-only existing owner.env -> EDITOR_ONLY resume.

    Unknown STOP or start outcomes are never retried. No PAPER_AUTO start, SQL
    writes, new Nginx route, second process, LIVE or arbitrary device selection.
    """
    from tools import paper_maintenance as m
    from tools.vps_manual_main_gateway import inspect_authenticated_site
    from tools.vps_release_identity import verify_release
    from tools.vps_release_resume import check_resume, ResumeBlocked
    from terminal.diary.simulator_launch_relay import SimulatorLaunchRelay

    try:
        if os.geteuid() != uid or not re.fullmatch("[0-9a-f]{40}", target):
            raise ProvisionBlocked("root_and_exact_sha_required")
        if verify_release(root) != target:
            raise ProvisionBlocked("installed_release_mismatch")
        prior = _owner_bytes(owner_env, uid=uid)
        _ensure_unconfigured(prior)
        paper_prior = _paper_env_bytes(env_file, uid=uid)
        active_env = _runtime_env()
        if active_env.get(KEY_ORIGIN) or active_env.get(KEY_DEVICES):
            raise ProvisionBlocked("runtime_relay_already_configured")
        site, old_site, proposed = inspect_authenticated_site(root=root)
        if old_site != proposed or old_site.count(FACTS_ROUTE) != 1:
            raise ProvisionBlocked("reviewed_facts_ingress_unproven")
        identity = m._durable_editor_freeze(root, env_file)
        if not (m._editor_runtime_ready(target, identity)
                and m._paper_start_quiescent(root, env_file)
                and _robot_stopped(root=root, env_file=env_file)):
            raise ProvisionBlocked("editor_only_and_flat_preflight_unproven")

        # This uses the same durable exactly-once canonical STOP as owner "stop".
        stopped = m._stop_exact_installed_paper_once(target, env_file=env_file, trusted_uid=uid)
        if not stopped.startswith("READY:"):
            return "BLOCKED: canonical_stop_unproven; no_retry_or_env_change"

        # Read-only settle for systemd's stop transition; never reissue STOP.
        for attempt in range(30):
            try:
                if check_resume(target, root=root).startswith("RESUME_READY:"):
                    break
            except (ResumeBlocked, OSError, ValueError):
                pass
            if attempt == 29:
                return "BLOCKED: stopped_systemd_resume_unproven; no_retry_or_env_change"
            time.sleep(0.5)

        # Re-prove PAPER source/FLAT and quiescence after STOP before
        # touching even a protected configuration file.
        if (m._durable_editor_freeze(root, env_file) != identity
                or not m._paper_start_quiescent(root, env_file)
                or not _robot_stopped(root=root, env_file=env_file)
                or _paper_env_bytes(env_file, uid=uid) != paper_prior):
            return "BLOCKED: post_stop_editor_freeze_unproven; no_env_change_or_retry"

        token = secrets.token_urlsafe(48)
        devices = {"owner-pc": token}
        SimulatorLaunchRelay(origin=ORIGIN, devices=devices)
        prefix = prior or b""
        if prefix and not prefix.endswith(b"\n"):
            prefix += b"\n"
        line = (KEY_ORIGIN + "=" + ORIGIN + "\n"
                + KEY_DEVICES + "='" + json.dumps(devices, separators=(",", ":")) + "'\n")
        _atomic_install(owner_env, prior, prefix + line.encode("ascii"), uid=uid)

        resumed = m.resume_installed_release(target, root=root, env_file=env_file)
        if not resumed.startswith("READY:"):
            return "BLOCKED: editor_only_resume_unproven; no_retry"
        observed = _runtime_env()
        try:
            applied = json.loads(observed.get(KEY_DEVICES, ""))
        except (ValueError, TypeError):
            applied = None
        if (observed.get(KEY_ORIGIN) != ORIGIN or applied != devices
                or not m._editor_runtime_ready(target, identity)
                or m._durable_editor_freeze(root, env_file) != identity
                or not _robot_stopped(root=root, env_file=env_file)
                or not m._paper_start_quiescent(root, env_file)):
            return "BLOCKED: owner_pc_relay_postconditions_unproven; no_retry"
        return "READY: owner-pc relay provisioned; exact EDITOR_ONLY restored; token withheld"
    except ProvisionBlocked as exc:
        return "BLOCKED: simulator_owner_pc_preflight:" + str(exc)
    except (OSError, ValueError, TypeError, sqlite3.Error, subprocess.TimeoutExpired):
        return "BLOCKED: simulator_owner_pc_preflight_unproven; no_retry"
