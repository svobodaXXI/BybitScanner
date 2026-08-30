"""Fail-closed task-delta transactions stored inside repository Git metadata."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tools.dev.workflow import Git, normalize_task_paths, repository_root, require_ok


FORMAT_VERSION = 1
METADATA_NAME = "transaction.json"
CLASSIFICATIONS = {
    "CLEAN_BASELINE", "PREEXISTING_DIRTY", "PREEXISTING_UNTRACKED", "TASK_NEW", "MIXED"
}


class TransactionError(RuntimeError):
    """Raised when transaction assumptions cannot be proved safely."""


@dataclass(frozen=True)
class ProofResult:
    status: str
    detail: str


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_dir(root: Path, git: Git) -> Path:
    value = Path(require_ok(git.run("rev-parse", "--git-dir"), "Git directory discovery"))
    return (value if value.is_absolute() else root / value).resolve()


def _branch(git: Git) -> str:
    return require_ok(git.run("symbolic-ref", "--quiet", "--short", "HEAD"), "branch discovery")


def _head_bytes(git: Git, path: str) -> bytes | None:
    completed = subprocess.run(
        ("git", "show", f"HEAD:{path}"), cwd=git.root, capture_output=True, check=False
    )
    if completed.returncode == 0:
        return completed.stdout
    exists = git.run("cat-file", "-e", f"HEAD:{path}")
    if exists.returncode:
        return None
    raise TransactionError(f"cannot read HEAD blob: {path}")


def _read_worktree(root: Path, path: str) -> bytes | None:
    target = root / path
    if not target.exists():
        return None
    if not target.is_file():
        raise TransactionError(f"task path is not a file: {path}")
    return target.read_bytes()


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def begin(paths: Sequence[str], *, git: Git | None = None, task_id: str | None = None) -> dict:
    active = git or Git(Path.cwd())
    root = repository_root(active)
    active = Git(root)
    exact, files = normalize_task_paths(root, paths)
    # Missing declared files are legitimate task-new targets.
    files = sorted(set(files) | {path for path in exact if not (root / path).is_dir()})
    identifier = task_id or f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
    if not identifier or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in identifier):
        raise ValueError("task id may contain only letters, digits, '-' and '_'")
    directory = _git_dir(root, active) / "bybitscanner" / "tasks" / identifier
    if directory.exists():
        raise TransactionError(f"transaction already exists: {identifier}")

    records: list[dict] = []
    for relative in files:
        head = _head_bytes(active, relative)
        baseline = _read_worktree(root, relative)
        if head is None and baseline is not None:
            initial = "PREEXISTING_UNTRACKED"
        elif head is not None and baseline != head:
            initial = "PREEXISTING_DIRTY"
        else:
            initial = "CLEAN_BASELINE"
        record = {
            "path": relative,
            "initial": initial,
            "head_sha256": _sha(head) if head is not None else None,
            "baseline_sha256": _sha(baseline) if baseline is not None else None,
            "baseline_present": baseline is not None,
            "snapshot": None,
        }
        if initial in {"PREEXISTING_DIRTY", "PREEXISTING_UNTRACKED"}:
            snapshot = f"baseline/{len(records):06d}.bin"
            target = directory / snapshot
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(baseline or b"")
            record["snapshot"] = snapshot
        records.append(record)

    metadata = {
        "format_version": FORMAT_VERSION,
        "task_id": identifier,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(root),
        "branch": _branch(active),
        "head": require_ok(active.run("rev-parse", "HEAD"), "HEAD discovery"),
        "scope": exact,
        "files": records,
    }
    _write_json_atomic(directory / METADATA_NAME, metadata)
    return metadata


def _load(root: Path, task_id: str, git: Git) -> tuple[Path, dict]:
    directory = _git_dir(root, git) / "bybitscanner" / "tasks" / task_id
    try:
        metadata = json.loads((directory / METADATA_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TransactionError(f"transaction metadata is missing or corrupt: {exc}") from exc
    if metadata.get("format_version") != FORMAT_VERSION or metadata.get("task_id") != task_id:
        raise TransactionError("transaction metadata is stale or corrupt")
    if Path(metadata.get("repo_root", "")).resolve() != root:
        raise TransactionError("transaction repository does not match")
    files = metadata.get("files")
    if not isinstance(files, list):
        raise TransactionError("transaction metadata is stale or corrupt")
    seen: set[str] = set()
    for record in files:
        if not isinstance(record, dict):
            raise TransactionError("transaction metadata is stale or corrupt")
        relative = record.get("path")
        initial = record.get("initial")
        snapshot = record.get("snapshot")
        if (
            not isinstance(relative, str) or not relative or relative in seen
            or Path(relative).is_absolute() or ".." in Path(relative).parts
            or initial not in {"CLEAN_BASELINE", "PREEXISTING_DIRTY", "PREEXISTING_UNTRACKED"}
            or not isinstance(record.get("baseline_present"), bool)
            or (record.get("baseline_sha256") is not None and not isinstance(record.get("baseline_sha256"), str))
            or (record.get("head_sha256") is not None and not isinstance(record.get("head_sha256"), str))
            or (snapshot is not None and (not isinstance(snapshot, str) or Path(snapshot).is_absolute() or ".." in Path(snapshot).parts))
        ):
            raise TransactionError("transaction metadata is stale or corrupt")
        seen.add(relative)
    return directory, metadata


def _validate(root: Path, git: Git, metadata: dict) -> list[str]:
    blockers: list[str] = []
    try:
        if _branch(git) != metadata["branch"]:
            blockers.append("BRANCH_CHANGED")
        if require_ok(git.run("rev-parse", "HEAD"), "HEAD discovery") != metadata["head"]:
            blockers.append("HEAD_CHANGED")
    except (KeyError, RuntimeError):
        blockers.append("METADATA_CORRUPT")
    return blockers


def inspect(task_id: str, *, git: Git | None = None) -> dict:
    active = git or Git(Path.cwd())
    root = repository_root(active)
    active = Git(root)
    try:
        directory, metadata = _load(root, task_id, active)
    except TransactionError as exc:
        return {"status": "CORRUPT", "task_id": task_id, "files": [], "blockers": [str(exc)]}
    blockers = _validate(root, active, metadata)
    results = []
    for record in metadata.get("files", []):
        try:
            current = _read_worktree(root, record["path"])
            current_hash = _sha(current) if current is not None else None
            baseline_hash = record["baseline_sha256"]
            if current_hash == baseline_hash:
                classification = record["initial"]
            elif record["initial"] == "CLEAN_BASELINE":
                classification = "TASK_NEW"
            else:
                classification = "MIXED"
            if record.get("snapshot"):
                snapshot = directory / record["snapshot"]
                if not snapshot.is_file() or _sha(snapshot.read_bytes()) != baseline_hash:
                    blockers.append(f"BASELINE_CORRUPT:{record['path']}")
            results.append({"path": record["path"], "classification": classification})
        except (KeyError, OSError, TransactionError):
            blockers.append("METADATA_CORRUPT")
            break
    return {
        "status": "STALE" if blockers else "OK", "task_id": task_id,
        "files": sorted(results, key=lambda item: item["path"]), "blockers": sorted(set(blockers)),
    }


def compact_status(task_id: str, *, git: Git | None = None) -> str:
    value = inspect(task_id, git=git)
    files = ", ".join(f"{item['path']}={item['classification']}" for item in value["files"]) or "NONE"
    blockers = ", ".join(value["blockers"]) or "NONE"
    return f"STATUS {value['status']}\nTASK {task_id}\nFILES {files}\nBLOCKERS {blockers}"


def _merge(current: bytes, base: bytes, other: bytes) -> bytes:
    with tempfile.TemporaryDirectory(prefix="bybitscanner-task-merge-") as temporary:
        folder = Path(temporary)
        names = [folder / name for name in ("current", "base", "other")]
        for path, data in zip(names, (current, base, other), strict=True):
            path.write_bytes(data)
        result = subprocess.run(
            ("git", "merge-file", "--stdout", str(names[0]), str(names[1]), str(names[2])),
            capture_output=True, check=False,
        )
        if result.returncode != 0:
            raise TransactionError("three-way merge conflicted or could not be applied unambiguously")
        return result.stdout


def derive_candidate(task_id: str, *, git: Git | None = None) -> dict[str, ProofResult]:
    active = git or Git(Path.cwd())
    root = repository_root(active)
    active = Git(root)
    directory, metadata = _load(root, task_id, active)
    blockers = _validate(root, active, metadata)
    if blockers:
        raise TransactionError("transaction is stale: " + ", ".join(blockers))
    proofs: dict[str, ProofResult] = {}
    candidates: dict[str, bytes] = {}
    for record in metadata["files"]:
        relative = record["path"]
        head = _head_bytes(active, relative)
        current = _read_worktree(root, relative)
        if record["initial"] == "PREEXISTING_UNTRACKED":
            raise TransactionError(f"pre-existing untracked path cannot be separated safely: {relative}")
        if head is None:
            if record["baseline_present"]:
                raise TransactionError(f"tracked baseline assumption failed: {relative}")
            candidate = current
            proof = ProofResult("PASS", "task-created path")
        else:
            if record.get("snapshot"):
                snapshot = directory / record["snapshot"]
                try:
                    baseline = snapshot.read_bytes()
                except OSError as exc:
                    raise TransactionError(f"baseline snapshot is missing: {relative}") from exc
                if _sha(baseline) != record["baseline_sha256"]:
                    raise TransactionError(f"baseline snapshot is corrupt: {relative}")
            else:
                baseline = head
            if current is None:
                raise TransactionError(f"tracked path deletion is not supported in Phase 1: {relative}")
            candidate = _merge(head, baseline, current)
            reconstructed = _merge(candidate, head, baseline)
            if reconstructed != current:
                raise TransactionError(f"inverse proof failed: {relative}")
            proof = ProofResult("PASS", "inverse reconstruction is byte-exact")
        if candidate is not None:
            candidates[relative] = candidate
        proofs[relative] = proof
    candidate_root = directory / "candidate"
    if candidate_root.exists():
        shutil.rmtree(candidate_root)
    for relative, candidate in candidates.items():
        target = candidate_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(candidate)
    return proofs
