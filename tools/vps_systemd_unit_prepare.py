"""Prepare installed PAPER systemd units before an already authorized start.

Only daemon-reload and conditionally reset an already-loaded failed unit.
Never starts/stops services, installs release files, handles SQL, or touches LIVE.
The CLI also offers bounded continuation of a previously enabled diagnostic
pin after a proven owner UPDATE; failure never grants or blocks PAPER authority.
Call only after the exact approved release is installed and PAPER units are
stopped. An independent MAIN service may remain active during PAPER start.
"""
from __future__ import annotations

import os
import subprocess
import sys

PAPER_UNITS = (
    "bybitscanner-paper-backend.service",
    "bybitscanner-telegram.service",
    "bybitscanner-paper-start.service",
)
# All four tracked units require a protected stop when their release files
# are replaced. Do not reuse this stricter list for normal PAPER-only START.
UNITS = PAPER_UNITS + ("bybitscanner-manual-main-read.service",)


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

    # Do not reset any unit until all reviewed identities are known and loaded.
    states: dict[str, tuple[str, str]] = {}
    for unit in PAPER_UNITS:
        result = command("show", unit, "--property=LoadState,ActiveState", "--no-pager")
        if result is None or result.returncode != 0:
            return f"BLOCKED: systemd_unit_state_unavailable:{unit}; no reset or start"
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if values.get("LoadState") != "loaded" or values.get("ActiveState") not in (
            "inactive", "failed",
        ):
            return f"BLOCKED: systemd_unit_not_stopped_and_loaded:{unit}; no reset or start"
        states[unit] = (values["LoadState"], values["ActiveState"])

    for unit in PAPER_UNITS:
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


def _continue_diagnostic_pin(*, run=subprocess.run, configured=None) -> str:
    if configured is None:
        configured = os.path.lexists("/etc/bybitscanner/github-diagnostic")
    if not configured:
        return "SKIPPED_UNCONFIGURED"
    try:
        result = run([sys.executable, "-m", "tools.github_diagnostic_runtime", "--carry-forward"],
                     capture_output=True, text=True, timeout=12, check=False)
        for status in ("ADVANCED", "UNCHANGED", "SKIPPED_DISABLED", "SKIPPED_UNCONFIGURED"):
            if (result.returncode == 0
                    and result.stdout.strip() == "DIAGNOSTIC_PIN_CONTINUITY=" + status):
                return status
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        pass
    return "BLOCKED"


def main() -> int:
    result = prepare_units()
    print(result)
    if result.startswith("READY:"):
        print("DIAGNOSTIC_PIN_CONTINUITY=" + _continue_diagnostic_pin())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
