"""Read-only recovery checkpoint for a Gitless PAPER release switched while STOPPED.

A failed operator instruction is NOT a restart authorization. This checkpoint
never stops/starts services, repeats SIGINT, changes SQL, resets systemd, or
deploys code. Use it after the exact release and its protected manifest are
already installed; then invoke the existing unit-preparation helper separately.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
from tools.vps_systemd_unit_prepare import UNITS

ROOT = Path("/opt/BybitScanner")
MANIFEST = Path("/etc/bybitscanner/paper-release-manifest.json")
UNIT_DIR = Path("/etc/systemd/system")
PORTS = (8765, 8766)

# These are the observed, owner-owned networking customizations on the PAPER VPS.
# Only their precise Environment assignments are approved, not arbitrary
# drop-ins with familiar names. No start/stop, DB or security directive is
# eligible for override. Revisions require a reviewed code/release change.
REVIEWED_DROPINS: dict[str, dict[str, tuple[str, ...]]] = {
    "bybitscanner-paper-backend.service": {
        "telegram-proxy.conf": (
            'Environment="HTTPS_PROXY=socks5h://127.0.0.1:10809"',
            'Environment="HTTP_PROXY=socks5h://127.0.0.1:10809"',
            'Environment="NO_PROXY=127.0.0.1,localhost,::1,.bybit.com,.bybit.com.cn,.bybit-tr.com"',
        ),
    },
    "bybitscanner-telegram.service": {
        "proxy.conf": (
            'Environment="HTTPS_PROXY=socks5h://127.0.0.1:10809"',
            'Environment="HTTP_PROXY=socks5h://127.0.0.1:10809"',
            'Environment="NO_PROXY=127.0.0.1,localhost,::1"',
        ),
        "terminal-ingress.conf": (
            "Environment=BYBITSCANNER_TERMINAL_HTTPS_URL=https://83.217.213.181",
        ),
    },
}


def _verify_reviewed_dropins(
    unit: str, reported: str, *,
    unit_dir: Path = UNIT_DIR, trusted_uid: int = 0,
) -> None:
    """Fail closed on unreviewed origin/content, symlinks or weak ownership.

    systemd's DropInPaths is authoritative for the loaded configuration. Reject
    any directive besides the precise reviewed assignments; filenames alone
    are never sufficient authorization.
    """
    paths = reported.split()
    if not paths:
        return
    approved = REVIEWED_DROPINS.get(unit, {})
    names: set[str] = set()
    for name in paths:
        path = Path(name)
        if not path.is_absolute() or path.name not in approved or path.name in names:
            raise ResumeBlocked("unexpected_systemd_dropin")
        if path != unit_dir / (unit + ".d") / path.name:
            raise ResumeBlocked("unexpected_systemd_dropin")
        names.add(path.name)
        try:
            stat = path.lstat()
            if (not path.is_file() or path.is_symlink() or stat.st_uid != trusted_uid
                    or stat.st_mode & 0o022):
                raise ResumeBlocked("unsafe_systemd_dropin_file")
            lines = tuple(
                line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        except (OSError, UnicodeError) as exc:
            raise ResumeBlocked("unreadable_systemd_dropin") from exc
        # Only blank lines may differ; comments, extra sections and directives
        # are not silently accepted, because systemd syntax is not an INI subset.
        if lines != ("[Service]", *approved[path.name]):
            raise ResumeBlocked("unreviewed_systemd_dropin_content")




class ResumeBlocked(ValueError):
    pass


def _systemd_state(unit: str, *, run=subprocess.run, unit_dir: Path = UNIT_DIR, trusted_uid: int = 0) -> dict[str, str]:
    try:
        reply = run(
            ["systemctl", "show", unit, "--property=LoadState,ActiveState,MainPID,FragmentPath,DropInPaths",
             "--no-pager"],
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ResumeBlocked("systemd_unreachable") from exc
    if reply.returncode:
        raise ResumeBlocked("systemd_state_unavailable")
    state = dict(line.split("=", 1) for line in reply.stdout.splitlines() if "=" in line)
    if state.get("ActiveState") not in ("inactive", "failed") or state.get("MainPID") != "0":
        raise ResumeBlocked("PAPER_unit_not_stopped")
    if state.get("LoadState") not in ("loaded", "not-found"):
        raise ResumeBlocked("unexpected_systemd_load_state")
    # A stale/non-reloaded unit may be not-found; the next authorized step
    # reloads units. Never accept a drop-in overriding safety or identity.
    _verify_reviewed_dropins(unit, state.get("DropInPaths", ""), unit_dir=unit_dir, trusted_uid=trusted_uid)
    if state["LoadState"] == "loaded" and state.get("FragmentPath") != str(unit_dir / unit):
        raise ResumeBlocked("unexpected_systemd_unit_origin")
    return state


def _assert_no_listeners() -> None:
    # No bind, no network call. Refuse any local TCP listener on the backend
    # or Telegram ports, including IPv6 or a non-systemd owner.
    try:
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            for line in Path(table).read_text().splitlines()[1:]:
                fields = line.split()
                if len(fields) < 4:
                    raise ResumeBlocked("invalid_tcp_snapshot")
                port = int(fields[1].rsplit(":", 1)[1], 16)
                if fields[3] == "0A" and port in PORTS:
                    raise ResumeBlocked("PAPER_port_owned_by_another_process")
    except ResumeBlocked:
        raise
    except (OSError, IndexError, ValueError) as exc:
        raise ResumeBlocked("tcp_snapshot_unavailable") from exc


def check_resume(target: str, *, root: Path = ROOT,
                 manifest: Path = MANIFEST, unit_dir: Path = UNIT_DIR,
                 states=_systemd_state, listeners=_assert_no_listeners,
                 verify=verify_release) -> str:
    if len(target) != 40 or any(char not in "0123456789abcdef" for char in target):
        raise ResumeBlocked("invalid_approved_target")
    # Verify installed tracked bytes; a marker SHA alone is not evidence.
    try:
        actual = verify(root, manifest)
    except (ReleaseIdentityBlocked, OSError) as exc:
        raise ResumeBlocked("installed_release_unproven") from exc
    if actual != target:
        raise ResumeBlocked("installed_release_differs_from_approved_target")
    for unit in UNITS:
        local = unit_dir / unit
        expected = root / "deploy/systemd" / unit
        try:
            if (local.is_symlink() or not local.is_file()
                    or local.read_bytes() != expected.read_bytes()):
                raise ResumeBlocked("installed_unit_does_not_match_release")
        except OSError as exc:
            raise ResumeBlocked("installed_unit_unreadable") from exc
    for unit in UNITS:
        states(unit)
    listeners()
    return "RESUME_READY: approved tracked release and units installed, PAPER processes stopped; no action performed"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read-only proof for resuming a stopped PAPER deploy")
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args(argv)
    try:
        print(check_resume(args.expected_sha))
        return 0
    except ResumeBlocked as exc:
        print("BLOCKED: " + str(exc) + "; no service action", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
