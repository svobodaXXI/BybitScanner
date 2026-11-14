"""Explicit owner-imported PAPER episode facts: immutable local research cache.

No VPS requests, credential handling, Robot execution or PAPER DB connection.
Files are addressed only by validated episode ID, not arbitrary request paths.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

EPISODE_ID = re.compile(r"te_[a-f0-9]{24}\Z")
MAX_BYTES = 4 * 1024 * 1024


class LocalEpisodeConflict(ValueError):
    pass


def _record(raw: bytes) -> tuple[str, bytes]:
    if not 2 <= len(raw) <= MAX_BYTES:
        raise ValueError("invalid_episode_size")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("invalid_episode_json") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_episode_json")
    episode_id = payload.get("trade_episode_id")
    if not isinstance(episode_id, str) or not EPISODE_ID.fullmatch(episode_id):
        raise ValueError("invalid_episode_id")
    if (payload.get("ok") is not True
        or payload.get("schema") != "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1"
        or payload.get("namespace") != "PAPER_READ_ONLY"
        or payload.get("account_id") != "paper"
        or payload.get("source") != "PAPER_EXECUTIONS_ATTRIBUTED"
        or payload.get("replay_evidence") != "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES"
        or payload.get("owner") not in ("ROBOT", "MANUAL")
        or not isinstance(payload.get("execution_allocations"), list)
        or not payload["execution_allocations"]):
        raise ValueError("invalid_episode_evidence")
    # Write the exact bytes, not normalized or rounded financial values.
    return episode_id, raw


def _root(directory: Path) -> Path:
    if directory.is_symlink():
        raise ValueError("symlink_archive_forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError("invalid_episode_archive")
    return directory


def store_episode(directory: Path, raw: bytes) -> str:
    episode_id, exact = _record(raw)
    target = _root(directory) / (episode_id + ".json")
    if target.is_symlink():
        raise ValueError("symlink_episode_forbidden")
    if target.exists():
        previous = target.read_bytes()
        # Equivalent JSON encoding may be re-imported, but conflicting evidence
        # for the same stable identity is never silently replaced.
        if previous == exact or json.loads(previous) == json.loads(exact):
            return episode_id
        raise LocalEpisodeConflict("episode_identity_conflict")
    fd, temp_name = tempfile.mkstemp(prefix=".episode-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(exact)
            stream.flush()
            os.fsync(stream.fileno())
        # Exclusive creation: no replacement race even across viewer instances.
        try:
            os.link(temp_name, target)
        except FileExistsError:
            return store_episode(directory, exact)
        return episode_id
    finally:
        Path(temp_name).unlink(missing_ok=True)


def load_episode(directory: Path, episode_id: str) -> bytes | None:
    if not EPISODE_ID.fullmatch(episode_id) or directory.is_symlink():
        raise ValueError("invalid_episode_lookup")
    target = directory / (episode_id + ".json")
    if target.is_symlink():
        raise ValueError("symlink_episode_forbidden")
    if not target.is_file():
        return None
    raw = target.read_bytes()
    found_id, _ = _record(raw)
    if found_id != episode_id:
        raise ValueError("local_episode_corrupt")
    return raw
