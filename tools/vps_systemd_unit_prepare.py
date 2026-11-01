"""Prepare installed PAPER systemd units before an already authorized start.

Only daemon-reload and conditionally reset an already-loaded failed unit.
Never starts/stops services, installs files, handles SQL, or touches LIVE.
Call only after the exact approved release and its three service files are
installed and the previous PAPER runtime has been safely stopped.
"""
from __future__ import annotations

import subprocess
import sys

UNITS = (
    "bybitscanner-paper-backend.service",
    "bybitscanner-telegram.service",
    "bybitscanner-paper-start.service",
)


def prepare_units(*, run=subprocess.run) -> str:
    def command(*args: str):
        try:
            return run(
                ["systemctl", *args], capture_output=True, text=True,
                timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

    result = command("daemon-reload")
    if result is None or result.returncode != 0:
        return "BLOCKED: systemd_daemon_reload_failed; no unit reset or start"

    # Do not reset any unit until all three identities are known and loaded.
    states: dict[str, tuple[str, str]] = {}
    for unit in UNITS:
        result = command("show", unit, "--property=LoadState,ActiveState", "--no-pager")
        if result is None or result.returncode != 0:
            return f"BLOCKED: systemd_unit_state_unavailable:{unit}; no reset or start"
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if values.get("LoadState") != "loaded" or values.get("ActiveState") not in (
            "inactive", "failed",
        ):
            return f"BLOCKED: systemd_unit_not_stopped_and_loaded:{unit}; no reset or start"
        states[unit] = (values["LoadState"], values["ActiveState"])

    for unit in UNITS:
        if states[unit][1] != "failed":
            continue
        result = command("reset-failed", unit)
        if result is None or result.returncode != 0:
            # A reset error does not prove a failed unit. One read-only recheck
            # distinguishes harmless state convergence from a genuine blocker.
            check = command("show", unit, "--property=LoadState,ActiveState", "--no-pager")
            if check is None or check.returncode != 0:
                return f"BLOCKED: systemd_reset_failed_unverified:{unit}; no start"
            values = dict(line.split("=", 1) for line in check.stdout.splitlines() if "=" in line)
            if values.get("LoadState") != "loaded" or values.get("ActiveState") != "inactive":
                return f"BLOCKED: systemd_reset_failed_unresolved:{unit}; no start"
    return "READY: PAPER systemd units loaded; failed state cleared where required; no start performed"


def main() -> int:
    result = prepare_units()
    print(result)
    return 0 if result.startswith("READY:") else 2


if __name__ == "__main__":
    raise SystemExit(main())
