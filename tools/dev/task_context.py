"""Generate compact, non-authoritative task context from the current checkout."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Sequence

from .workflow import Git, normalize_task_paths, repository_root, require_ok


SCHEMA = "bybitscanner.task-context.v1"
AUTHORITY = "NON_AUTHORITATIVE_DERIVED"


def _read_required(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"required authority is unavailable: {relative}: {exc}") from exc


def _section(document: str, heading: str) -> str | None:
    pattern = re.compile(
        rf"^#\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^#\s+|\Z)",
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(document)
    return match.group("body").strip() if match else None


def _field(section: str | None, name: str) -> str | None:
    if not section:
        return None
    match = re.search(
        rf"^{re.escape(name)}:\s*\n+\s*(?P<value>[^\n]+)", section, re.MULTILINE | re.IGNORECASE
    )
    return match.group("value").strip().strip("`") if match else None


def _version(document: str) -> str:
    match = re.search(r"^(?:Version|Версия):\s*\n+\s*([^\n]+)", document, re.MULTILINE)
    if not match:
        raise RuntimeError("workflow/protocol version cannot be resolved")
    return match.group(1).strip()


def _scope_kind(paths: Sequence[str]) -> str:
    lowered = tuple(path.lower() for path in paths)
    if all(path == "agents.md" or path.startswith("documents/") for path in lowered):
        return "documentation"
    if any(path.startswith("terminal/frontend/") for path in lowered):
        return "frontend"
    if any(path.startswith(("terminal/", "trading/", "paper_trader/")) for path in lowered):
        return "backend_trading"
    if any(path.startswith(("tools/project_sync/", "tools/dev/")) for path in lowered):
        return "developer_workflow"
    return "project_code"


def _authority_refs(kind: str) -> list[str]:
    common = [
        "AGENTS.md#Staged recovery",
        "DOCUMENTS/PROJECT_STATE.md#CURRENT_DEVELOPMENT_PRIORITY",
        "DOCUMENTS/ASSISTANT_PROTOCOL.md#28. STAGED_CONTEXT_RECOVERY_PROTOCOL",
    ]
    routed = {
        "frontend": [
            "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
            "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
            "DOCUMENTS/ARCHITECTURE.md#TRADING TERMINAL",
        ],
        "backend_trading": [
            "DOCUMENTS/PROJECT_STATE.md#TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE",
            "DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md",
            "DOCUMENTS/PROJECT_CONTRACTS.md",
        ],
        "documentation": [
            "DOCUMENTS/PROJECT_RULES.md",
            "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
        ],
        "developer_workflow": [
            "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-DEVELOPMENT-LIFECYCLE-001",
            "DOCUMENTS/PROJECT_CONTRACTS.md#CONTRACT-CONTEXT-DUMP-001",
        ],
        "project_code": ["DOCUMENTS/PROJECT_RULES.md", "DOCUMENTS/ARCHITECTURE.md"],
    }
    return common + routed[kind]


def _active_state(state: str, kind: str) -> tuple[dict[str, str] | None, list[str]]:
    priority = _section(state, "CURRENT_DEVELOPMENT_PRIORITY")
    workspace = _section(state, "TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE")
    section = workspace if kind in {"frontend", "backend_trading"} else priority
    mission = _field(section, "Active mission")
    checkpoint = _field(section, "Checkpoint") or _field(section, "Priority")
    lifecycle = _field(section, "Lifecycle state") or _field(section, "Priority level")
    owning = _field(section, "Owning record")
    active = None
    if mission and mission.upper() != "NONE":
        active = {"mission": mission}
        if owning:
            active["record"] = owning
    constraints: list[str] = []
    for label in ("Implementation status", "Current authorized action", "Next phase"):
        value = _field(section, label)
        if value and any(token in value.upper() for token in ("NOT_AUTHORIZED", "REQUIRES", "NONE")):
            constraints.append(f"{label}: {value}")
    current = {"checkpoint": checkpoint or "UNRESOLVED", "state": lifecycle or "UNRESOLVED"}
    return ({**(active or {}), **current} if active else current), constraints


def build_task_context(
    root: Path, path_values: Sequence[str], *, hint: str | None = None, git: Git | None = None
) -> dict[str, object]:
    """Build a deterministic task bootstrap without writing repository files."""
    active_git = git or Git(root)
    exact_paths, _ = normalize_task_paths(root, path_values)
    agents = _read_required(root, "AGENTS.md")
    state = _read_required(root, "DOCUMENTS/PROJECT_STATE.md")
    protocol = _read_required(root, "DOCUMENTS/ASSISTANT_PROTOCOL.md")
    if "Generated ContextDumps" not in agents or "non-authoritative" not in agents:
        raise RuntimeError("AGENTS.md derived-context authority boundary cannot be confirmed")
    branch = require_ok(active_git.run("branch", "--show-current"), "branch discovery")
    head = require_ok(active_git.run("rev-parse", "HEAD"), "HEAD discovery")
    if not branch:
        raise RuntimeError("detached HEAD is not supported")
    kind = _scope_kind(exact_paths)
    active, constraints = _active_state(state, kind)
    result: dict[str, object] = {
        "schema": SCHEMA,
        "authority": AUTHORITY,
        "notice": "Disposable bootstrap; repository authority and current Git/filesystem state prevail.",
        "git": {"branch": branch, "head": head, "last_safe_commit": head},
        "task": {"paths": exact_paths, "scope_kind": kind},
        "current": active,
        "workflow": {"lifecycle": "TASK -> SPEC -> CONTEXT -> IMPLEMENT -> VERIFY -> RECORD", "assistant_protocol_version": _version(protocol)},
        "communication": {
            "technical_repo": "English",
            "user_confirmations_approvals_safety_actions": "Russian",
            "preserve_literals": True,
            "duplicate_bilingual_statement": False,
        },
        "authority_refs": _authority_refs(kind),
        "unresolved_constraints": constraints,
    }
    if hint:
        result["task"]["hint"] = hint.strip()  # type: ignore[index]
    return result


def generate(path_values: Sequence[str], *, hint: str | None = None, git: Git | None = None) -> str:
    probe = git or Git(Path.cwd())
    root = repository_root(probe)
    payload = build_task_context(root, path_values, hint=hint, git=git or Git(root))
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", action="append", required=True, dest="paths")
    parser.add_argument("--hint")
    args = parser.parse_args(argv)
    try:
        print(generate(args.paths, hint=args.hint), end="")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
