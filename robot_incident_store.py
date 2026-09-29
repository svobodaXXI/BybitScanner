"""Best-effort durable Robot incident diagnostics.

Each incident is stored as one immutable JSON file. The runtime-facing helper
never raises: diagnostics must not become a new Scanner/Robot safety blocker.
Only normalized metadata is persisted; raw exception messages, credentials,
tokens, database paths and other arbitrary strings are intentionally excluded.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import time
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
DEFAULT_INCIDENT_DIR = (
    Path(__file__).resolve().parent
    / "runtime"
    / "terminal"
    / "robot_incidents"
)
MAX_INCIDENTS = 200

_SAFE_CODE = re.compile(r"^[A-Z0-9_]{1,80}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
_SAFE_SYMBOL = re.compile(r"^[A-Z0-9]{1,32}$")
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9 _.+()-]{1,80}$")


class RobotIncidentError(RuntimeError):
    """Raised only by the strict incident writer used in tests/tools."""


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalized_code(value: object, field: str) -> str:
    text = str(value or "").strip().upper()
    if not _SAFE_CODE.fullmatch(text):
        raise RobotIncidentError(f"{field} must be an uppercase reason code")
    return text


def _normalized_identifier(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not _SAFE_ID.fullmatch(text):
        raise RobotIncidentError(f"{field} contains unsupported characters")
    return text


def _normalized_symbol(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if not _SAFE_SYMBOL.fullmatch(text):
        raise RobotIncidentError("symbol contains unsupported characters")
    return text


def _normalized_text(value: object | None, field: str) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    if not text:
        return None
    if len(text) > 80 or not _SAFE_TEXT.fullmatch(text):
        raise RobotIncidentError(f"{field} contains unsupported characters")
    return text


def _error_metadata(error: BaseException | None) -> dict[str, object]:
    if error is None:
        return {}
    result: dict[str, object] = {
        "error_class": type(error).__name__[:80],
    }
    cause = error.__cause__
    if cause is not None:
        result["cause_class"] = type(cause).__name__[:80]
    errno = getattr(error, "errno", None)
    if isinstance(errno, int) and not isinstance(errno, bool):
        result["errno"] = errno
    return result


def _normalized_fact_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise RobotIncidentError("incident fact float must be finite")
        return value
    if isinstance(value, str):
        return _normalized_text(value, "incident fact")
    raise RobotIncidentError(
        f"unsupported incident fact type: {type(value).__name__}"
    )


def _normalized_facts(facts: Mapping[str, object] | None) -> dict[str, object]:
    if facts is None:
        return {}
    normalized: dict[str, object] = {}
    for raw_key, raw_value in facts.items():
        key = _normalized_code(raw_key, "incident fact key").lower()
        normalized[key] = _normalized_fact_value(raw_value)
    return normalized


def _utc_iso(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(
        timestamp_ms / 1000, tz=timezone.utc
    ).isoformat(timespec="milliseconds")


def record_robot_incident(
    *,
    lifecycle_stage: str,
    reason_code: str,
    symbol: object | None = None,
    timeframe: object | None = None,
    pattern: object | None = None,
    candidate_id: object | None = None,
    trade_id: object | None = None,
    error: BaseException | None = None,
    facts: Mapping[str, object] | None = None,
    incident_dir: Path | str | None = None,
    retention: int = MAX_INCIDENTS,
    occurred_at_ms: int | None = None,
) -> dict[str, Any]:
    """Write one sanitized immutable incident and enforce bounded retention."""

    if not isinstance(retention, int) or isinstance(retention, bool) or retention < 1:
        raise RobotIncidentError("retention must be a positive integer")

    timestamp_ms = _now_ms() if occurred_at_ms is None else occurred_at_ms
    if (
        not isinstance(timestamp_ms, int)
        or isinstance(timestamp_ms, bool)
        or timestamp_ms < 0
    ):
        raise RobotIncidentError("occurred_at_ms must be a non-negative integer")

    incident_id = f"{timestamp_ms:013d}-{secrets.token_hex(6)}"
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "incident_id": incident_id,
        "occurred_at_ms": timestamp_ms,
        "occurred_at": _utc_iso(timestamp_ms),
        "lifecycle_stage": _normalized_code(lifecycle_stage, "lifecycle_stage"),
        "reason_code": _normalized_code(reason_code, "reason_code"),
        "symbol": _normalized_symbol(symbol),
        "timeframe": _normalized_text(timeframe, "timeframe"),
        "pattern": _normalized_text(pattern, "pattern"),
        "candidate_id": _normalized_identifier(candidate_id, "candidate_id"),
        "trade_id": _normalized_identifier(trade_id, "trade_id"),
        "facts": _normalized_facts(facts),
    }
    record.update(_error_metadata(error))

    directory = Path(incident_dir) if incident_dir is not None else DEFAULT_INCIDENT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{incident_id}.json"
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True)

    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")

    incident_files = sorted(directory.glob("*.json"), key=lambda item: item.name)
    excess = len(incident_files) - retention
    if excess > 0:
        for stale in incident_files[:excess]:
            try:
                stale.unlink()
            except FileNotFoundError:
                pass

    return record


def try_record_robot_incident(**kwargs: object) -> bool:
    """Best-effort runtime wrapper: diagnostics never change safety behavior."""

    try:
        record_robot_incident(**kwargs)
        return True
    except Exception as error:
        print(
            "[ROBOT INCIDENT DIAGNOSTIC ERROR] "
            f"error_class={type(error).__name__}"
        )
        return False
