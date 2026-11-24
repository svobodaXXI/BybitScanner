"""Owner-clicked local Machine Time release preparation. Never touches VPS/PAPER."""
from __future__ import annotations

import argparse
import base64
import json
import hashlib
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import socket
import time
import stat
import subprocess
import sys
import tempfile
from zipfile import ZipFile
from urllib.request import ProxyHandler, build_opener

from research.local_replay_viewer.desktop_update import find_asset, fetch_verified, require_forward_update, UpdateBlocked

USER_STATE = ("simulator-v2-data", "paper-episode-facts", "public-m5-cache", "python-wheels")
APP = "MachineTime"
MAX_MEMBERS = 5000
MAX_EXTRACTED = 260_000_000


def _check_state_tree(source: Path) -> None:
    if source.is_symlink():
        raise UpdateBlocked("local_data_symlink")
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            entry = Path(root) / name
            if entry.is_symlink():
                raise UpdateBlocked("local_data_symlink")
        if len(dirs) + len(files) > MAX_MEMBERS:
            raise UpdateBlocked("local_data_unbounded")


def _copy_state(source: Path, target: Path) -> None:
    if not source.exists():
        return
    if not source.is_dir():
        raise UpdateBlocked("local_state_not_directory")
    _check_state_tree(source)
    shutil.copytree(source, target, symlinks=False)
    # Fail closed if a file changes during copying. Existing state is never
    # moved, removed or modified. Owner can retry manually after correcting.
    for root, _, files in os.walk(source):
        for name in files:
            original = Path(root) / name
            copied = target / original.relative_to(source)
            if copied.stat().st_size != original.stat().st_size:
                raise UpdateBlocked("local_data_changed_during_copy")
            def digest(p: Path) -> str:
                h = hashlib.sha256()
                with p.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                return h.hexdigest()
            if digest(original) != digest(copied):
                raise UpdateBlocked("local_data_changed_during_copy")


def _unpack_release(archive: Path, dest: Path, *, sha: str) -> None:
    with ZipFile(archive) as pack:
        infos = pack.infolist()
        if len(infos) > MAX_MEMBERS:
            raise UpdateBlocked("archive_too_many_files")
        total = 0
        seen: set[str] = set()
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            parts = path.parts
            if (not parts or parts[0] != APP or len(parts) < 2
                    or any(p in ("", ".", "..") for p in parts)
                    or "\\" in name or ":" in name or name.casefold() in seen
                    or any(p.rstrip(" .") != p or p.upper().split(".")[0] in
                           {"CON", "PRN", "AUX", "NUL", "COM1", "LPT1"} for p in parts)
                    or ((info.external_attr >> 16) & 0o170000) == stat.S_IFLNK
                    or (parts[1] in USER_STATE)
                    or name.startswith(APP + "/.wedge-python/")):
                raise UpdateBlocked("untrusted_simulator_archive")
            seen.add(name.casefold())
            total += info.file_size
            if total > MAX_EXTRACTED:
                raise UpdateBlocked("simulator_archive_too_large")
        for info in infos:
            name = PurePosixPath(info.filename)
            target = dest.joinpath(*name.parts[1:])
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with pack.open(info) as reader, target.open("xb") as writer:
                shutil.copyfileobj(reader, writer, length=1024 * 1024)
    marker = dest / "desktop-build-sha.txt"
    if (not marker.is_file() or marker.read_text(encoding="ascii").strip() != sha
            or not (dest / "START_LOCAL.cmd").is_file()
            or not (dest / "server.py").is_file()
            or not (dest / "dist" / "replay.html").is_file()):
        raise UpdateBlocked("simulator_release_identity_unproven")


def prepare_simulator_update(here: Path) -> tuple[Path, str]:
    """Prepare one immutable new version; do not mutate running application."""
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise UpdateBlocked("update_requires_owner_windows")
    if not here.is_dir() or here.is_symlink():
        raise UpdateBlocked("untrusted_simulator_root")
    asset = find_asset("simulator")
    marker = here / "desktop-build-sha.txt"
    if marker.is_file():
        require_forward_update(marker.read_text(encoding="ascii").strip(), asset.sha)
    root = Path(os.environ["LOCALAPPDATA"]) / "BybitScanner" / APP / "releases"
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink():
        raise UpdateBlocked("untrusted_simulator_releases_root")
    version = root / asset.sha
    if version.exists():
        raise UpdateBlocked("simulator_release_already_staged")
    # Installation path is create-only. An error leaves existing viewer and
    # all prior versions untouched.
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=str(root)))
    try:
        archive = stage / asset.name
        fetch_verified(asset, archive)
        unpacked = stage / APP
        unpacked.mkdir()
        _unpack_release(archive, unpacked, sha=asset.sha)
        archive.unlink()
        for name in USER_STATE:
            _copy_state(here / name, unpacked / name)
        # The optional bundled public replay must survive an app-only update.
        optional_bundled = here / "real-h1-august.json"
        if optional_bundled.is_file() and not optional_bundled.is_symlink():
            shutil.copy2(optional_bundled, unpacked / optional_bundled.name)
            if hashlib.sha256(optional_bundled.read_bytes()).digest() != hashlib.sha256(
                (unpacked / optional_bundled.name).read_bytes()
            ).digest():
                raise UpdateBlocked("bundled_archive_changed_during_copy")
        elif optional_bundled.is_symlink():
            raise UpdateBlocked("bundled_archive_untrusted")
        stage.rename(version)
        return version / APP / "START_LOCAL.cmd", asset.sha
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def launch_new_simulator(launcher: Path) -> None:
    if launcher.name != "START_LOCAL.cmd" or not launcher.is_file() or os.name != "nt":
        raise UpdateBlocked("simulator_launch_untrusted")
    subprocess.Popen(["cmd.exe", "/c", str(launcher)], cwd=str(launcher.parent),
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
                     close_fds=True)



def schedule_relaunch(launcher: Path, port: int) -> None:
    """Start independent *local* helper before shutting down old loopback.

    If the helper cannot start, preserve the running old viewer. The helper
    waits for the listening port to become free before opening the new viewer.
    """
    _verified_launch_path(launcher)
    if port not in range(1, 65536):
        raise UpdateBlocked("invalid_local_port")
    try:
        subprocess.Popen(
            [sys.executable, "-B", "-m",
             "research.local_replay_viewer.simulator_self_update",
             "--launch", str(launcher), "--wait-port", str(port)],
            cwd=str(launcher.parent), close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        )
    except OSError as exc:
        raise UpdateBlocked("local_relaunch_helper_unavailable") from exc


def _verified_launch_path(launcher: Path) -> None:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local or os.name != "nt":
        raise UpdateBlocked("owner_windows_required_for_relaunch")
    prefix = (Path(local) / "BybitScanner" / APP / "releases").resolve()
    if (launcher.name != "START_LOCAL.cmd" or not launcher.is_file()
            or launcher.is_symlink()
            or not launcher.resolve().is_relative_to(prefix)
            or launcher.parent.name != APP):
        raise UpdateBlocked("simulator_launch_untrusted")
    marker = launcher.parent / "desktop-build-sha.txt"
    if not marker.is_file() or not re.fullmatch("[0-9a-f]{40}", marker.read_text().strip()):
        raise UpdateBlocked("simulator_release_identity_unproven")



# Only the existing owner shortcut is eligible. Never create another link or
# scan/rewrite arbitrary shortcuts, and never touch an unrelated application.
_SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$name = 'Машина времени (актуальная).lnk'
$dirs = @([Environment]::GetFolderPath('Desktop'))
if ($env:PUBLIC) { $dirs += (Join-Path $env:PUBLIC 'Desktop') }
$links = @($dirs | Where-Object { $_ } | ForEach-Object {
    Join-Path $_ $name
} | Select-Object -Unique | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
if ($links.Count -ne 1) { throw 'shortcut_missing_or_ambiguous' }
$w = New-Object -ComObject WScript.Shell
$s = $w.CreateShortcut($links[0])
if ($env:BS_MT_NEW_TARGET) {
    if ($links[0] -ne $env:BS_MT_EXPECTED_LINK -or
        $s.TargetPath -ne $env:BS_MT_EXPECTED_TARGET -or $s.Arguments -or
        $s.WorkingDirectory -ne (Split-Path -Parent $s.TargetPath)) {
        throw 'shortcut_changed'
    }
    $s.TargetPath = $env:BS_MT_NEW_TARGET
    $s.WorkingDirectory = Split-Path -Parent $s.TargetPath
    $s.Save()
    $s = $w.CreateShortcut($links[0])
}
@{path=$links[0]; target=$s.TargetPath; workdir=$s.WorkingDirectory;
  arguments=$s.Arguments} | ConvertTo-Json -Compress
"""


def _owner_shortcut(*, expected: dict | None = None,
                    launcher: Path | None = None) -> dict:
    env = os.environ.copy()
    for key in ("BS_MT_NEW_TARGET", "BS_MT_EXPECTED_LINK", "BS_MT_EXPECTED_TARGET"):
        env.pop(key, None)
    if expected is not None and launcher is not None:
        env.update(BS_MT_NEW_TARGET=str(launcher),
                   BS_MT_EXPECTED_LINK=expected["path"],
                   BS_MT_EXPECTED_TARGET=expected["target"])
    shell = Path(env["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    encoded = base64.b64encode(_SHORTCUT_SCRIPT.encode("utf-16-le")).decode("ascii")
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive",
                             "-EncodedCommand", encoded],
                            env=env, capture_output=True, encoding="utf-8",
                            timeout=15, check=True)
    value = json.loads(result.stdout)
    if (not isinstance(value, dict) or
            any(not isinstance(value.get(key), str)
                for key in ("path", "target", "workdir", "arguments"))):
        raise UpdateBlocked("shortcut_metadata_unproven")
    return value


def _canonical_launcher_sha(launcher: Path, root: Path) -> str:
    sha = launcher.parent.parent.name
    if (not re.fullmatch(r"[0-9a-f]{40}", sha)
            or launcher != root / sha / APP / "START_LOCAL.cmd"
            or launcher.is_symlink() or not launcher.is_file()
            or launcher.resolve() != launcher
            or (launcher.parent / "desktop-build-sha.txt").is_symlink()
            or (launcher.parent / "desktop-build-sha.txt").read_text(
                encoding="ascii").strip() != sha):
        raise UpdateBlocked("shortcut_release_unproven")
    return sha


def _advance_owner_shortcut(launcher: Path, root: Path) -> None:
    new_sha = _canonical_launcher_sha(launcher, root)
    old_link = _owner_shortcut()
    old = Path(old_link["target"])
    if old_link["arguments"] or Path(old_link["workdir"]) != old.parent:
        raise UpdateBlocked("shortcut_customized")
    old_sha = _canonical_launcher_sha(old, root)
    if old_sha == new_sha:
        return
    # A shortcut can have been manually redirected to a newer release. Never
    # downgrade it, nor overwrite changes made while the ancestry check runs.
    require_forward_update(old_sha, new_sha)
    updated = _owner_shortcut(expected=old_link, launcher=launcher)
    if (updated["path"] != old_link["path"] or
            Path(updated["target"]) != launcher or
            Path(updated["workdir"]) != launcher.parent or updated["arguments"]):
        raise UpdateBlocked("shortcut_save_unproven")


def _wait_for_release_identity(launcher: Path, port: int) -> bool:
    sha = launcher.parent.parent.name
    opener = build_opener(ProxyHandler({}))
    for _ in range(120):
        try:
            with opener.open(
                f"http://127.0.0.1:{port}/local-replay/desktop-version", timeout=1
            ) as response:
                if json.loads(response.read(512)) == {"sha": sha}:
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(1)
    return False


def _relaunch_after_port_closes(launcher: Path, port: int) -> int:
    _verified_launch_path(launcher)
    if not 1 <= port <= 65535:
        return 2
    for _ in range(120):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                time.sleep(0.25)
                continue
        except OSError:
            launch_new_simulator(launcher)
            # The verified package must actually be running before its
            # shortcut can replace the prior known-good target.
            try:
                if not _wait_for_release_identity(launcher, port):
                    raise UpdateBlocked("shortcut_new_viewer_unproven")
                root = (Path(os.environ["LOCALAPPDATA"]) / "BybitScanner" /
                        APP / "releases").resolve()
                _advance_owner_shortcut(launcher, root)
            except (UpdateBlocked, OSError, ValueError, KeyError, subprocess.SubprocessError):
                # The viewer launch remains independent of shortcut maintenance.
                print("MACHINE_TIME_SHORTCUT_NOT_UPDATED", flush=True)
                return 2
            print("MACHINE_TIME_SHORTCUT_UPDATED", flush=True)
            return 0
    return 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--wait-port", type=int, required=True)
    args = parser.parse_args()
    try:
        raise SystemExit(_relaunch_after_port_closes(args.launch, args.wait_port))
    except (UpdateBlocked, OSError, ValueError):
        raise SystemExit(2)
