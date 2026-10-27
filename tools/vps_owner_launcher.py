"""VPS-first, fail-closed remote PAPER core launcher (owner Windows client).

This module deliberately does not activate PAPER_AUTO, start local trading, or
handle SSH credentials. The owner must install trusted SSH access separately.
It is NOT yet wired to the canonical Windows shortcut.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from typing import Mapping

_TARGET_RE = re.compile(r"^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$")
_REMOTE = (
    "systemctl start bybitscanner-paper-start.service"
    " && /opt/BybitScanner/venv/bin/python -c "
    "'import json,urllib.request;"
    "u=\"http://127.0.0.1:8765\";"
    "h=json.load(urllib.request.urlopen(u+\"/api/health\",timeout=5));"
    "s=json.load(urllib.request.urlopen(u+\"/api/scanner/status\",timeout=5));"
    "p=json.load(urllib.request.urlopen(u+\"/api/robot/protection-health\",timeout=5));"
    "a=json.load(urllib.request.urlopen(u+\"/api/robot/autopilot\",timeout=5));"
    "assert h.get(\"mode\")==\"paper\" and h.get(\"paper_live_safe\") is True;"
    "assert p.get(\"healthy\") is True;"
    "print(\"PAPER_CORE\",json.dumps({\"scanner\":s.get(\"mode\"),"
    "\"autopilot\":a.get(\"mode\"),\"protection\":p.get(\"healthy\")}))'"
)


def ssh_argv(target: str, key_path: str) -> list[str]:
    """No shell on Windows and no interactive password/passphrase prompts."""
    if not _TARGET_RE.fullmatch(target):
        raise ValueError("invalid VPS SSH target (user@host required)")
    if not key_path:
        raise ValueError("VPS SSH key path is not configured")
    return [
        "ssh", "-i", key_path,
        "-o", "BatchMode=yes",
        "-o", "IdentitiesOnly=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8",
        "-o", "ConnectionAttempts=1",
        target, _REMOTE,
    ]


def launch(env: Mapping[str, str] | None = None, *, run=subprocess.run) -> int:
    settings = os.environ if env is None else env
    try:
        argv = ssh_argv(
            settings.get("BYBITSCANNER_VPS_SSH_TARGET", ""),
            os.path.expandvars(settings.get("BYBITSCANNER_VPS_SSH_KEY", "")),
        )
    except ValueError as error:
        print(f"VPS LAUNCH BLOCKED: {error}", file=sys.stderr)
        return 2
    try:
        result = run(argv, capture_output=True, text=True, timeout=210, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"VPS LAUNCH FAILED: {type(error).__name__}; local trading NOT started", file=sys.stderr)
        return 1
    if result.returncode:
        # Do not echo arbitrary remote stderr: upstream diagnostics can contain secrets.
        print(f"VPS LAUNCH BLOCKED: SSH/remote exit={result.returncode}; local trading NOT started",
              file=sys.stderr)
        return 1
    if "PAPER_CORE" not in result.stdout:
        print("VPS LAUNCH UNVERIFIED: missing PAPER core confirmation", file=sys.stderr)
        return 1
    print(result.stdout.strip())
    if '"autopilot": "PAPER_AUTO"' not in result.stdout:
        print("PAPER CORE READY; PAPER_AUTO is not confirmed. No automatic trading claim.")
        return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed VPS-first PAPER core launcher")
    parser.parse_args(argv)
    return launch()


if __name__ == "__main__":
    sys.exit(main())
