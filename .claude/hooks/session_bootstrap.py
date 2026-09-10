"""SessionStart hook: session-general bootstrap only (git state + active priority).

Budgeted deliberately short (target: well under 500 bytes of injected text) because
this runs on every session, on top of CLAUDE.md and AGENTS.md when loaded. It must
never throw, never block session start, and never read anything path-specific --
that part belongs to pretool_scope_context.py, which knows which file is being
touched.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, timeout=5, check=False,
    )
    return result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else ""


def _git_summary(root: Path) -> str:
    branch = _run(["git", "branch", "--show-current"], root) or "DETACHED"
    head = _run(["git", "rev-parse", "--short", "HEAD"], root) or "unknown"
    status = _run(["git", "status", "--porcelain"], root)
    dirty = len([line for line in status.splitlines() if line.strip()]) if status is not None else 0
    return f"branch={branch} head={head} dirty={dirty} file(s)"


def _priority(root: Path) -> str:
    path = root / "DOCUMENTS" / "PROJECT_STATE.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "unknown (PROJECT_STATE.md unreadable)"
    match = re.search(r"^Current work priority:\s*\n+\s*([^\n]+)", text, re.MULTILINE)
    return match.group(1).strip() if match else "unknown (see PROJECT_STATE.md)"


def build_context() -> str:
    root = _repo_root()
    try:
        git_line = _git_summary(root)
    except (OSError, subprocess.SubprocessError):
        git_line = "git state unavailable"
    try:
        priority_line = _priority(root)
    except Exception:  # noqa: BLE001 - never block session start
        priority_line = "unknown"
    return (
        f"[session bootstrap] {git_line}\n"
        f"priority={priority_line} (full detail: DOCUMENTS/PROJECT_STATE.md)"
    )


def main() -> int:
    try:
        sys.stdin.read()  # drain stdin payload; SessionStart carries no fields we need
    except Exception:  # noqa: BLE001
        pass
    try:
        context = build_context()
    except Exception:  # noqa: BLE001 - advisory bootstrap must never fail the session
        context = ""
    if context:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
