"""MIRROR observation projection: bounded, cursor-based, strictly OBSERVE_ONLY read of the ObservationJournal.

Pure and read-only. It opens the journal with ``"rb"`` only (never creates, repairs, truncates or locks it), imports nothing
from ``terminal`` and holds no state between calls. It is the MIRROR side of the contract in
``DOCUMENTS/research/mirror_retest_r0/CONTRACT.md`` ("Observation read API"); a backend adapter only has to call
``project_observations`` and serialize the dict.

Rules (every one tested):

* ``seq`` is the 1-based number of a *complete, non-empty* journal line. The journal is append-only, so a seq never moves.
  A last line without a newline is an in-flight append: it is ignored (``partial_tail``) and not counted as malformed.
* The WHOLE file (up to ``max_scan_bytes``) is validated on every call, not only the requested page: one line that grants
  anything — ``mode != OBSERVE_ONLY``, ``executable`` or ``admission_allowed`` not exactly ``False``, a decision other than
  ``WAIT``/``BLOCK`` — makes the call fail with ``ProjectionUnavailable``; nothing is returned partially.
* Malformed lines (bad JSON, not an object, missing/ill-typed required fields) and repeated ``observation_id`` are skipped
  and counted, never repaired. Lines of another account scope are skipped and counted.
* Cursor: ``after`` = last seen ``seq``. If the file is shorter than the cursor, or ``journal_id`` (hash of the first
  complete line) no longer matches the caller's, the file was truncated or replaced: ``cursor_reset`` is true and the page
  restarts at seq 1.
* ``facts`` (R0 account numbers) and ``r0_*`` are never emitted. Unknown legacy fields are `None`, never guessed.
"""

from __future__ import annotations

import hashlib
import json
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
    """One bounded page of observations with ``seq > after``. Raises ``ProjectionUnavailable`` on anything unsafe."""

    if not _is_int(after) or after < 0:
        raise ValueError("after must be a non-negative integer")
    if not _is_int(limit) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}")
    observed_at = int(time.time() * 1000) if now_ms is None else int(now_ms)
    path = Path(path)
    base: dict[str, Any] = {
        "ok": True, "source": SOURCE, "strategy_id": STRATEGY_ID, "mode": MODE_OBSERVE_ONLY,
        "account_scope": account_scope, "observed_at_ms": observed_at,
    }
    if not path.exists():
        return {**base, "journal_present": False, "journal_id": None, "observations": [], "next_seq": after,
                "truncated": False, "cursor_reset": False, "total_lines": 0, "malformed_lines": 0,
                "duplicate_lines": 0, "foreign_account_lines": 0, "partial_tail": False}

    page: list[dict[str, Any]] = []        # seq > after
    head: list[dict[str, Any]] = []        # seq >= 1: used only if the cursor has to be reset
    more_page = more_head = False
    seen: set[str] = set()
    total = malformed = duplicates = foreign = 0
    partial_tail = False
    first_line: bytes | None = None
    scanned = 0
    try:
        with path.open("rb") as handle:
            for raw in handle:
                scanned += len(raw)
                if scanned > max_scan_bytes:
                    raise ProjectionUnavailable("journal exceeds the scan limit")
                if not raw.endswith(b"\n"):
                    partial_tail = bool(raw.strip())      # an append in flight: neither read nor counted
                    break
                stripped = raw.strip()
                if not stripped:
                    continue
                total += 1
                if first_line is None:
                    first_line = stripped
                try:
                    record = json.loads(stripped.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    malformed += 1
                    continue
                if not isinstance(record, dict):
                    malformed += 1
                    continue
                if not isinstance(record.get("observation_id"), str):
                    malformed += 1                         # not recognisably an observation at all
                    continue
                _check_permission(record, total)           # whole file, not only the page: fail closed
                projected = _project(record, total)
                if projected is None:
                    malformed += 1
                    continue
                if projected["observation_id"] in seen:
                    duplicates += 1
                    continue
                seen.add(projected["observation_id"])
                account = record.get("account_id")
                if isinstance(account, str) and account and account != account_scope:
                    foreign += 1
                    continue
                projected["account_id"] = account if isinstance(account, str) and account else None
                if len(head) < limit:
                    head.append(projected)
                else:
                    more_head = True
                if total > after:
                    if len(page) < limit:
                        page.append(projected)
                    else:
                        more_page = True
    except ProjectionUnavailable:
        raise
    except OSError as exc:
        raise ProjectionUnavailable(f"journal is not readable: {type(exc).__name__}") from exc

    current_id = hashlib.sha256(first_line).hexdigest()[:16] if first_line is not None else None
    reset = after > total or (journal_id is not None and current_id is not None and journal_id != current_id)
    rows, truncated = (head, more_head) if reset else (page, more_page)
    return {
        **base, "journal_present": True, "journal_id": current_id, "observations": rows,
        "next_seq": rows[-1]["seq"] if rows else (0 if reset else after),
        "truncated": truncated, "cursor_reset": reset, "total_lines": total, "malformed_lines": malformed,
        "duplicate_lines": duplicates, "foreign_account_lines": foreign, "partial_tail": partial_tail,
    }
