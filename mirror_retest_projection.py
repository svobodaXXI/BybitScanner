"""MIRROR observation projection: bounded, cursor-based, strictly OBSERVE_ONLY read of the ObservationJournal.

Read-only. It opens the journal with ``"rb"`` only (never creates, repairs, truncates or locks it) and imports nothing
from ``terminal``. It is the MIRROR side of the contract in ``DOCUMENTS/research/mirror_retest_r0/CONTRACT.md``
("Observation read API"). Two entry points with one code path and identical answers:

* ``project_observations(path, ...)`` — stateless, one full scan per call;
* ``ObservationProjector(path).project(...)`` — for a long-lived reader (the future backend adapter). It keeps a
  *verified* index of the journal prefix it has already validated. Every call re-hashes that whole prefix (SHA-256 of the
  exact bytes) before trusting the index, so any change, corruption, truncation or replacement of already-read data is
  detected with certainty and the index is rebuilt from a full scan. Only the bytes appended since the last call are
  parsed and validated, and only the lines of the requested page are read back from disk (and re-validated). Nothing is
  cached that is not re-proven on every call. (MIRROR-OBSERVATION-PROJECTION-2)

Rules (every one tested):

* ``seq`` is the 1-based number of a *complete, non-empty* journal line. The journal is append-only, so a seq never moves.
  A last line without a newline is an in-flight append: it is ignored (``partial_tail``) and not counted as malformed.
* Every complete line of the file (up to ``max_scan_bytes``) has been validated before any answer: one line that grants
  anything — ``mode != OBSERVE_ONLY``, ``executable`` or ``admission_allowed`` not exactly ``False``, a decision other than
  ``WAIT``/``BLOCK`` — makes the call fail with ``ProjectionViolation``; nothing is returned partially, and the failure
  repeats on every call while that line is in the file.
* Malformed lines (bad JSON, not an object, missing/ill-typed required fields) and repeated ``observation_id`` are skipped
  and counted, never repaired. Lines of another account scope are skipped and counted.
* Cursor: ``after`` = last seen ``seq``. If the file is shorter than the cursor, or ``journal_id`` (hash of the first
  complete line) no longer matches the caller's, the file was truncated or replaced: ``cursor_reset`` is true and the page
  restarts at seq 1.
* ``facts`` (R0 account numbers) and ``r0_*`` are never emitted. Unknown legacy fields are `None`, never guessed.
"""

from __future__ import annotations

from bisect import bisect_right
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any, Mapping

SOURCE = "MIRROR_RETEST_JOURNAL"
STRATEGY_ID = "MIRROR_RETEST"
MODE_OBSERVE_ONLY = "OBSERVE_ONLY"
ALLOWED_DECISIONS = frozenset({"WAIT", "BLOCK"})
ALLOWED_EVENTS = frozenset({"NAKED_BREAKOUT", "RETEST_PROVEN", "RETEST_UNPROVEN", "DATA_GAP"})
DEFAULT_LIMIT = 100
MAX_LIMIT = 200
MAX_SCAN_BYTES = 8 * 1024 * 1024
_CHUNK = 1024 * 1024


class ProjectionUnavailable(RuntimeError):
    """The journal cannot be projected safely; the caller must answer 503 and show the source as unavailable."""


class ProjectionViolation(ProjectionUnavailable):
    """A journal line grants or implies trading permission (or breaks the OBSERVE_ONLY contract)."""


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _optional_text(record: Mapping[str, Any], key: str) -> str | None:
    value = record.get(key)
    return value if isinstance(value, str) and value else None


def _check_permission(record: Mapping[str, Any], line_no: int) -> None:
    if record.get("mode") != MODE_OBSERVE_ONLY:
        raise ProjectionViolation(f"line {line_no}: mode is not OBSERVE_ONLY")
    if record.get("executable") is not False or record.get("admission_allowed") is not False:
        raise ProjectionViolation(f"line {line_no}: record is executable or admission-allowed")
    if record.get("decision") not in ALLOWED_DECISIONS:
        raise ProjectionViolation(f"line {line_no}: decision is not WAIT or BLOCK")


def _project(record: Mapping[str, Any], seq: int) -> dict[str, Any] | None:
    """The outbound shape of one valid record, or None if it is malformed. Whitelist only: no ``facts``."""

    boundary_id, symbol = record.get("boundary_id"), record.get("symbol")
    reasons = record.get("reasons")
    if (not isinstance(record.get("observation_id"), str) or not record["observation_id"]
            or not isinstance(boundary_id, str) or ":" not in boundary_id
            or not isinstance(symbol, str) or not symbol
            or record.get("event") not in ALLOWED_EVENTS
            or not isinstance(record.get("phase"), str)
            or not _is_int(record.get("candle_close_time_ms")) or record["candle_close_time_ms"] <= 0
            or not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons)):
        return None
    ref, side = boundary_id.rsplit(":", 1)
    recorded = record.get("recorded_at_ms")
    return {
        "seq": seq,
        "observation_id": record["observation_id"],
        "candidate_ref": _optional_text(record, "candidate_ref") or ref,
        "boundary_id": boundary_id,
        "boundary_side": side,
        "symbol": symbol,
        "timeframe": _optional_text(record, "timeframe"),
        "pattern": _optional_text(record, "pattern"),
        "event": record["event"],
        "phase": record["phase"],
        "campaign_direction": _optional_text(record, "campaign_direction"),
        "decision": record["decision"],
        "reasons": list(reasons),
        "candle_close_time_ms": record["candle_close_time_ms"],
        "recorded_at_ms": recorded if _is_int(recorded) else None,
        "mode": MODE_OBSERVE_ONLY,
        "executable": False,
        "admission_allowed": False,
    }


def _classify(stripped: bytes, seq: int, account_scope: str) -> tuple[str, dict[str, Any] | None]:
    """``("ok", projected) | ("malformed", None) | ("foreign", None)``; raises ``ProjectionViolation``."""

    try:
        record = json.loads(stripped.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "malformed", None
    if not isinstance(record, dict) or not isinstance(record.get("observation_id"), str):
        return "malformed", None                         # not recognisably an observation at all
    _check_permission(record, seq)
    projected = _project(record, seq)
    if projected is None:
        return "malformed", None
    account = record.get("account_id")
    if isinstance(account, str) and account and account != account_scope:
        return "foreign", projected
    projected["account_id"] = account if isinstance(account, str) and account else None
    return "ok", projected


class _Index:
    """What is proven about the journal prefix ``[0, length)``: every complete line in it was validated."""

    def __init__(self) -> None:
        self.length = 0                                   # bytes of the verified prefix (ends at a newline)
        self.hasher = hashlib.sha256()                    # state after hashing exactly that prefix
        self.digest = self.hasher.hexdigest()
        self.total = self.malformed = self.duplicates = self.foreign = 0
        self.seen: set[str] = set()
        self.valid_seqs: list[int] = []                   # seq of every returned (valid, unique, own-account) line
        self.offsets: dict[int, tuple[int, int]] = {}     # seq -> (byte offset, byte length) for those lines
        self.journal_id: str | None = None


class ObservationProjector:
    """Long-lived, thread-safe projector over one journal path (see module docstring)."""

    def __init__(self, path: str | Path, *, account_scope: str = "paper", max_scan_bytes: int = MAX_SCAN_BYTES) -> None:
        self.path = Path(path)
        self.account_scope = account_scope
        self.max_scan_bytes = max_scan_bytes
        self._index = _Index()
        self._lock = threading.Lock()
        self.stats = {"calls": 0, "rebuilds": 0, "bytes_hashed": 0, "bytes_parsed": 0, "page_lines_read": 0}

    # -- verification and incremental scan ---------------------------------------------------------

    def _prefix_unchanged(self, handle, size: int) -> bool:
        index = self._index
        if index.length == 0:
            return True
        if size < index.length:
            return False
        hasher, remaining = hashlib.sha256(), index.length
        handle.seek(0)
        while remaining:
            chunk = handle.read(min(_CHUNK, remaining))
            if not chunk:
                return False
            hasher.update(chunk)
            remaining -= len(chunk)
        self.stats["bytes_hashed"] += index.length
        return hasher.hexdigest() == index.digest

    def _extend(self, handle, size: int) -> bool:
        """Validate the complete lines after the verified prefix; commit only if all of them pass. Returns partial_tail."""

        index = self._index
        handle.seek(index.length)
        tail = handle.read(size - index.length)
        self.stats["bytes_parsed"] += len(tail)
        cut = tail.rfind(b"\n") + 1                       # complete lines only; the rest is an append in flight
        complete, partial = tail[:cut], tail[cut:]
        total, malformed, duplicates, foreign = index.total, index.malformed, index.duplicates, index.foreign
        new_ids: set[str] = set()
        new_seqs: list[int] = []
        new_offsets: dict[int, tuple[int, int]] = {}
        journal_id = index.journal_id
        position = 0
        for raw in complete.splitlines(keepends=True):
            start, position = position, position + len(raw)
            stripped = raw.strip()
            if not stripped:
                continue
            total += 1
            if journal_id is None:
                journal_id = hashlib.sha256(stripped).hexdigest()[:16]
            status, projected = _classify(stripped, total, self.account_scope)   # may raise: nothing committed
            if status == "malformed":
                malformed += 1
                continue
            observation_id = projected["observation_id"]
            if observation_id in index.seen or observation_id in new_ids:
                duplicates += 1
                continue
            new_ids.add(observation_id)
            if status == "foreign":
                foreign += 1
                continue
            new_seqs.append(total)
            new_offsets[total] = (index.length + start, len(raw))
        hasher = index.hasher.copy()
        hasher.update(complete)
        index.hasher, index.digest, index.length = hasher, hasher.hexdigest(), index.length + len(complete)
        index.total, index.malformed, index.duplicates, index.foreign = total, malformed, duplicates, foreign
        index.seen |= new_ids
        index.valid_seqs.extend(new_seqs)
        index.offsets.update(new_offsets)
        index.journal_id = journal_id
        return bool(partial.strip())

    def _read_page(self, handle, seqs: list[int]) -> list[dict[str, Any]]:
        rows = []
        for seq in seqs:
            offset, length = self._index.offsets[seq]
            handle.seek(offset)
            raw = handle.read(length)
            status, projected = _classify(raw.strip(), seq, self.account_scope)
            if status != "ok":                            # cannot happen after a verified prefix: fail closed
                raise ProjectionUnavailable(f"line {seq} changed while it was read")
            rows.append(projected)
        self.stats["page_lines_read"] += len(seqs)
        return rows

    # -- public ----------------------------------------------------------------------------------------

    def project(self, *, after: int = 0, limit: int = DEFAULT_LIMIT, journal_id: str | None = None,
                now_ms: int | None = None) -> dict[str, Any]:
        """One bounded page of observations with ``seq > after``. Raises ``ProjectionUnavailable`` on anything unsafe."""

        if not _is_int(after) or after < 0:
            raise ValueError("after must be a non-negative integer")
        if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}")
        observed_at = int(time.time() * 1000) if now_ms is None else int(now_ms)
        base: dict[str, Any] = {
            "ok": True, "source": SOURCE, "strategy_id": STRATEGY_ID, "mode": MODE_OBSERVE_ONLY,
            "account_scope": self.account_scope, "observed_at_ms": observed_at,
        }
        with self._lock:
            self.stats["calls"] += 1
            if not self.path.exists():
                self._index = _Index()
                return {**base, "journal_present": False, "journal_id": None, "observations": [], "next_seq": after,
                        "truncated": False, "cursor_reset": False, "total_lines": 0, "malformed_lines": 0,
                        "duplicate_lines": 0, "foreign_account_lines": 0, "partial_tail": False}
            try:
                with self.path.open("rb") as handle:
                    size = handle.seek(0, 2)
                    if size > self.max_scan_bytes:
                        raise ProjectionUnavailable("journal exceeds the scan limit")
                    if not self._prefix_unchanged(handle, size):
                        self._index = _Index()            # changed / truncated / replaced: re-prove everything
                        self.stats["rebuilds"] += 1
                    partial_tail = self._extend(handle, size)
                    index = self._index
                    reset = after > index.total or (
                        journal_id is not None and index.journal_id is not None and journal_id != index.journal_id)
                    start = 0 if reset else bisect_right(index.valid_seqs, after)
                    seqs = index.valid_seqs[start:start + limit]
                    truncated = start + limit < len(index.valid_seqs)
                    rows = self._read_page(handle, seqs)
            except ProjectionUnavailable:
                raise
            except OSError as exc:
                raise ProjectionUnavailable(f"journal is not readable: {type(exc).__name__}") from exc
            return {
                **base, "journal_present": True, "journal_id": index.journal_id, "observations": rows,
                "next_seq": rows[-1]["seq"] if rows else (0 if reset else after),
                "truncated": truncated, "cursor_reset": reset, "total_lines": index.total,
                "malformed_lines": index.malformed, "duplicate_lines": index.duplicates,
                "foreign_account_lines": index.foreign, "partial_tail": partial_tail,
            }


def project_observations(
    path: str | Path,
    *,
    after: int = 0,
    limit: int = DEFAULT_LIMIT,
    journal_id: str | None = None,
    account_scope: str = "paper",
    max_scan_bytes: int = MAX_SCAN_BYTES,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Stateless form: a fresh ``ObservationProjector`` per call (one full validating scan)."""

    return ObservationProjector(path, account_scope=account_scope, max_scan_bytes=max_scan_bytes).project(
        after=after, limit=limit, journal_id=journal_id, now_ms=now_ms)
