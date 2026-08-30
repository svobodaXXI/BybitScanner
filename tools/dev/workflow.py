"""Shared fail-closed primitives for developer workflow commands."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


RECEIPT_NAME = "latest-pass.json"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Git:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str) -> CommandResult:
        completed = subprocess.run(
            ("git", *args), cwd=self.root, text=True, capture_output=True, check=False
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def require_ok(result: CommandResult, operation: str) -> str:
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"{operation} failed" + (f": {detail}" if detail else ""))
    return result.stdout.strip()


def repository_root(git: Git) -> Path:
    return Path(require_ok(git.run("rev-parse", "--show-toplevel"), "repository discovery")).resolve()


def normalize_task_paths(root: Path, values: Sequence[str]) -> tuple[list[str], list[str]]:
    if not values:
        raise ValueError("at least one --path is required")
    exact: list[str] = []
    files: list[str] = []
    seen_values: set[str] = set()
    seen_files: set[str] = set()
    for value in values:
        candidate = Path(value)
        absolute = (candidate if candidate.is_absolute() else root / candidate).resolve()
        try:
            relative = absolute.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"task path is outside repository: {value}") from exc
        normalized = relative.as_posix()
        if normalized == ".git" or normalized.startswith(".git/"):
            raise ValueError("task paths cannot target Git metadata")
        if normalized not in seen_values:
            exact.append(normalized)
            seen_values.add(normalized)
        matches = sorted(p for p in absolute.rglob("*") if p.is_file()) if absolute.is_dir() else [absolute]
        for match in matches:
            item = match.relative_to(root).as_posix()
            if item not in seen_files:
                files.append(item)
                seen_files.add(item)
    return exact, files


def fingerprint(root: Path, relative_path: str) -> dict[str, str]:
    path = root / relative_path
    if not path.exists():
        return {"state": "missing", "sha256": hashlib.sha256(b"").hexdigest()}
    if not path.is_file():
        raise ValueError(f"task path is not a file: {relative_path}")
    return {"state": "file", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def fingerprints(root: Path, files: Sequence[str]) -> dict[str, dict[str, str]]:
    return {path: fingerprint(root, path) for path in files}


def index_snapshot(root: Path, git: Git) -> tuple[str, bytes]:
    """Return the exact real-index state without refreshing or otherwise mutating it."""
    raw = require_ok(git.run("rev-parse", "--git-path", "index"), "real index discovery")
    path = Path(raw)
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        return "file", path.read_bytes()
    except FileNotFoundError:
        return "missing", b""


def receipt_path(root: Path, git: Git) -> Path:
    raw = require_ok(git.run("rev-parse", "--git-dir"), "Git directory discovery")
    directory = Path(raw)
    if not directory.is_absolute():
        directory = root / directory
    return directory.resolve() / "bybitscanner" / RECEIPT_NAME


def read_receipt(root: Path, git: Git) -> dict:
    path = receipt_path(root, git)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError("PASS verification receipt is missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"PASS verification receipt is unreadable: {exc}") from exc
    if receipt.get("status") != "PASS":
        raise RuntimeError("latest verification receipt is not PASS")
    return receipt


def compact(status: str, scope: Sequence[str], checks: Sequence[str], failed: Sequence[str], blockers: Sequence[str]) -> str:
    def value(items: Sequence[str]) -> str:
        return ", ".join(items) if items else "NONE"
    return "\n".join((
        f"STATUS {status}", f"SCOPE {value(scope)}", f"CHECKS {value(checks)}",
        f"FAILED {value(failed)}", f"BLOCKERS {value(blockers)}",
    ))
