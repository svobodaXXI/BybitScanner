"""PreToolUse hook (Edit|Write|NotebookEdit): path-scoped routing hint.

Mirrors _scope_kind / _authority_refs from tools/dev/task_context.py, adapted to a
single touched path per tool call instead of a task-scoped path list. Advisory only:
never sets permissionDecision, so it can never block or auto-approve a tool call --
it only annotates. Must never throw or exit non-zero; a failure here degrades to
silence, not a blocked edit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _relative_path(root: Path, raw: str) -> str:
    candidate = Path(raw)
    try:
        absolute = candidate if candidate.is_absolute() else (root / candidate)
        return absolute.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return candidate.as_posix()


def _scope_kind(path: str) -> str:
    lowered = path.lower()
    if lowered in {"agents.md", "claude.md"} or lowered.startswith("documents/"):
        return "documentation"
    if lowered.startswith("terminal/frontend/"):
        return "frontend"
    if lowered.startswith(("terminal/", "trading/", "paper_trader/")):
        return "backend_trading"
    if lowered.startswith((".claude/", "tools/project_sync/", "tools/dev/")):
        return "developer_workflow"
    return "project_code"


_AUTHORITY_REFS = {
    "frontend": (
        "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
        "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
    ),
    "backend_trading": (
        "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
        "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
    ),
    "documentation": (
        "DOCUMENTS/PROJECT_RULES.md",
        "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
    ),
    "developer_workflow": (
        "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
        "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
    ),
    "project_code": (
        "DOCUMENTS/PROJECT_RULES.md",
        "DOCUMENTS/ARCHITECTURE.md",
    ),
}


def _touched_path(tool_input: dict) -> str | None:
    for key in ("file_path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def build_context(payload: dict) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    raw_path = _touched_path(tool_input)
    if not raw_path:
        return None
    root = _repo_root()
    relative = _relative_path(root, raw_path)
    kind = _scope_kind(relative)
    refs = _AUTHORITY_REFS.get(kind, ())
    ref_text = ", ".join(refs) if refs else "AGENTS.md routing (no extra scoped authority)"
    return f"[scope] {relative} -> {kind}; authority: {ref_text}"


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    try:
        context = build_context(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 - advisory hint must never block an edit
        context = None
    if context:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": context,
            }
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
