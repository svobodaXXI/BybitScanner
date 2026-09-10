"""PostToolUse hook (Edit|Write): advisory budget check, AGENTS.md/CLAUDE.md only.

No-ops immediately for any other path. Reuses tools/project_sync/governance/
context_budget.py's measure_reference instead of reimplementing byte counting.
Advisory only: never returns a blocking decision and never exits with code 2 --
a warning surfaces via systemMessage, the turn continues unconditionally.

Budgets:
- AGENTS.md: 10240 bytes, the project-approved agents_target_bytes_max from
  DOCUMENTS/CHANGE_REQUESTS/CR-DOC-AI-CONTEXT-001.md phase_6_final_measurements.
- CLAUDE.md: 4096 bytes, a locally chosen soft budget (no project-approved target
  exists for this Claude-Code-specific file yet); kept far below AGENTS.md's
  budget since CLAUDE.md is meant to be the short always-loaded bridge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BUDGETS = {"agents.md": 10240, "claude.md": 4096}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _touched_path(payload: dict) -> str | None:
    tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else {}
    tool_response = payload.get("tool_response") if isinstance(payload.get("tool_response"), dict) else {}
    for source in (tool_response, tool_input):
        for key in ("filePath", "file_path"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _relative_basename(root: Path, raw: str) -> str:
    candidate = Path(raw)
    try:
        absolute = candidate if candidate.is_absolute() else (root / candidate)
        relative = absolute.resolve().relative_to(root.resolve())
    except ValueError:
        relative = Path(raw)
    return relative.name


def check(payload: dict) -> str | None:
    root = _repo_root()
    raw_path = _touched_path(payload)
    if not raw_path:
        return None
    # Preserve on-disk case for the actual read; only the lookup key is lowered,
    # so this stays correct on case-sensitive filesystems (not just Windows).
    original_name = _relative_basename(root, raw_path)
    budget = BUDGETS.get(original_name.lower())
    if budget is None:
        return None

    sys.path.insert(0, str(root))
    from tools.project_sync.governance.context_budget import measure_reference  # noqa: E402

    footprint = measure_reference(root, original_name)
    if footprint.bytes <= budget:
        return None
    over = footprint.bytes - budget
    return (
        f"[budget] {original_name} is {footprint.bytes} bytes, {over} over the "
        f"{budget}-byte target. Consider trimming duplication before checkpoint "
        f"(see AGENTS.md editing history for the pattern)."
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    try:
        warning = check(payload) if isinstance(payload, dict) else None
    except Exception:  # noqa: BLE001 - advisory check must never block a write
        warning = None
    if warning:
        print(json.dumps({
            "systemMessage": warning,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": warning,
            },
        }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
