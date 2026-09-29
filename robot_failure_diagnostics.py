"""Best-effort durable Robot incident diagnostics.

This module is observability only. Diagnostic persistence must never become a
trading, protection, Scanner-delivery, or recovery blocker.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Mapping


SCHEMA_VERSION = 1
MAX_INCIDENT_RECORDS = 200
INCIDENT_DIR_ENV = "BYBITSCANNER_ROBOT_INCIDENT_DIR"
PAPER_DB_ENV = "BYBITSCANNER_PAPER_DB"


def _default_incident_dir() -> Path:
    explicit = os.environ.get(INCIDENT_DIR_ENV, "").strip()
    if explicit:
        return Path(explicit)

    database = os.environ.get(PAPER_DB_ENV, "").strip()
    if database:
        return Path(database).expanduser().parent / "robot_incidents"

    return Path(__file__).resolve().parent / "runtime" / "robot_incidents"


def _safe_text(value: Any, *, limit: int = 120) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    safe = "".join(
        character
        for character in raw
        if character.isalnum() or character in " _.-:"
    ).strip()
    return safe[:limit] or None


def _safe_fact(value: Any) -> bool | int | None | str:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    safe = _safe_text(value, limit=80)
    return safe if safe is not None else "UNAVAILABLE"


def _prune(directory: Path, *, keep: int) -> None:
    records = sorted(directory.glob("*.json"))
    for path in records[:-keep]:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def record_robot_incident(
    *,
    incident_type: str,
    stage: str,
    reason_code: str,
    symbol: str | None = None,
    timeframe: str | None = None,
    pattern: str | None = None,
    candidate_id: str | None = None,
    trade_id: str | None = None,
    error: BaseException | None = None,
    error_class: str | None = None,
    facts: Mapping[str, Any] | None = None,
    selected_recovery_action: str | None = None,
    incident_dir: Path | str | None = None,
    timestamp_ms: int | None = None,
) -> bool:
    """Write one bounded sanitized incident record; fail open on diagnostics IO.

    Raw exception text is deliberately never persisted. Callers provide a
    normalized reason code and only bounded deciding facts.
    """

    try:
        directory = (
            Path(incident_dir) if incident_dir is not None else _default_incident_dir()
        )
        directory.mkdir(parents=True, exist_ok=True)

        now_ms = (
            int(timestamp_ms)
            if timestamp_ms is not None
            else int(time.time() * 1000)
        )
        now_ns = time.time_ns()
        record = {
            "schema_version": SCHEMA_VERSION,
            "timestamp_ms": now_ms,
            "incident_type": _safe_text(incident_type),
            "stage": _safe_text(stage),
            "reason_code": _safe_text(reason_code),
            "symbol": _safe_text(symbol),
            "timeframe": _safe_text(timeframe),
            "pattern": _safe_text(pattern),
            "candidate_id": _safe_text(candidate_id),
            "trade_id": _safe_text(trade_id),
            "error_class": _safe_text(
                error_class or (type(error).__name__ if error is not None else None)
            ),
            "selected_recovery_action": _safe_text(selected_recovery_action),
            "facts": {
                str(key): _safe_fact(value)
                for key, value in (facts or {}).items()
            },
        }

        name = f"{now_ns:020d}-{secrets.token_hex(4)}.json"
        path = directory / name
        temp = directory / f".{name}.tmp"
        payload = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        try:
            temp.write_text(payload + "\n", encoding="utf-8")
            temp.replace(path)
        finally:
            try:
                temp.unlink(missing_ok=True)
            except Exception:
                pass

        _prune(directory, keep=MAX_INCIDENT_RECORDS)
        return True
    except Exception:
        # Diagnostics are never allowed to block Scanner delivery or Robot
        # protection/recovery. Do not print the underlying exception because it
        # may contain an absolute path or other sensitive context.
        print("[ROBOT DIAGNOSTIC ERROR] incident_write_failed")
        return False


def load_recent_robot_incidents(
    *,
    incident_dir: Path | str | None = None,
    limit: int = 50,
) -> tuple[dict[str, Any], ...]:
    """Read recent valid incident records for bounded operator diagnosis."""

    directory = (
        Path(incident_dir) if incident_dir is not None else _default_incident_dir()
    )
    if limit <= 0 or not directory.exists():
        return ()

    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
            result.append(payload)
    return tuple(result)
