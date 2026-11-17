"""One-click local VPS Manager replacement. NO SSH, PAPER or trading operations."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time

from research.local_replay_viewer.desktop_update import find_asset, fetch_verified, UpdateBlocked

NAME = "BybitScanner-VPS-Manager.exe"


def _installed_path() -> Path:
    if not getattr(sys, "frozen", False) or os.name != "nt":
        raise UpdateBlocked("manager_update_requires_installed_windows_exe")
    path = Path(sys.executable).resolve()
    appdata = Path(os.environ.get("LOCALAPPDATA", "")).resolve()
    expected = appdata / "BybitScanner" / "VPSManager"
    if (not expected.is_dir() or not path.is_relative_to(expected)
            or path.name.lower() != NAME.lower()):
        raise UpdateBlocked("manager_update_requires_trusted_install")
    return path


def stage_manager() -> str:
    """Called only on owner click, never in a timer or startup hook."""
    current = _installed_path()
    release = find_asset("manager")
    marker = Path(getattr(sys, "_MEIPASS", "")) / "desktop-build-sha.txt"
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == release.sha:
        raise UpdateBlocked("manager_already_current")
    stage_dir = current.parent / (".desktop-update-" + release.sha)
    stage_dir.mkdir(exist_ok=True)
    executable = stage_dir / NAME
    if executable.exists():
        raise UpdateBlocked("prior_update_stage_present; do_not_retry_automatically")
    fetch_verified(release, executable)
    # This is the *verified new binary*, not a shell command, and no secrets,
    # SSH keys, tokens, source repositories or server handles are passed.
    try:
        subprocess.Popen(
            [str(executable), "--replace-running-manager", str(current),
             "--old-pid", str(os.getpid())],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise UpdateBlocked("verified_updater_launch_failed") from exc
    return "VERIFIED_MANAGER_UPDATE_HANDOFF"


def commit_manager(*, original: str, old_pid: int) -> int:
    """Executes only from the newly downloaded verified Manager binary.

    Waiting for the old process releases the executable lock on Windows.
    The original installation is kept intact until replacement is possible.
    A bounded rollback restores the previous EXE on launch failure.
    """
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return 2
    source = Path(sys.executable).resolve()
    target = Path(original).resolve()
    root = Path(os.environ.get("LOCALAPPDATA", "")).resolve() / "BybitScanner" / "VPSManager"
    if (source.name.lower() != NAME.lower() or target.name.lower() != NAME.lower()
            or not source.is_relative_to(root) or not target.is_relative_to(root)
            or not source.parent.name.startswith(".desktop-update-")
            or not source.parent.parent == target.parent
            or not 1 <= old_pid <= 2**31 - 1 or old_pid == os.getpid()):
        return 2
    old = target.with_name(target.stem + "-previous-" + str(int(time.time_ns())) + ".exe")
    # Every successful update keeps the prior owner executable; no cleanup.
    if old.exists() or old.is_symlink():
        return 2
    for _ in range(40):
        try:
            target.replace(old)
            break
        except PermissionError:
            time.sleep(0.25)
        except OSError:
            return 2
    else:
        return 2
    try:
        source.replace(target)
        subprocess.Popen([str(target)], close_fds=True)
    except OSError:
        if not target.exists():
            old.replace(target)
        return 2
    return 0
