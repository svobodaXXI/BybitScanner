"""Read-only recovery checkpoint for a Gitless PAPER release switched while STOPPED.

A failed operator instruction is NOT a restart authorization. This checkpoint
never stops/starts services, repeats SIGINT, changes SQL, resets systemd, or
deploys code. Use it after the exact release and its protected manifest are
already installed; then invoke the existing unit-preparation helper separately.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import socket
import subprocess
import sys

from tools.vps_release_identity import ReleaseIdentityBlocked, verify_release
from tools.vps_systemd_unit_prepare import UNITS

ROOT = Path("/opt/BybitScanner")
MANIFEST = Path("/etc/bybitscanner/paper-release-manifest.json")
UNIT_DIR = Path("/etc/systemd/system")
PORTS = (8765, 8766)


class ResumeBlocked(ValueError):
    pass


def _systemd_state(unit: str, *, run=subprocess.run) -> dict[str, str]:
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
    if state.get("DropInPaths"):
        raise ResumeBlocked("unexpected_systemd_dropin")
    if state["LoadState"] == "loaded" and state.get("FragmentPath") != str(UNIT_DIR / unit):
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
