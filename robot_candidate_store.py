"""Durable immutable Scanner snapshots for Robot v0.1 admission.

This module owns only the signal-handoff envelope.  It does not own trading,
market data, Scanner analysis, sizing, or execution.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
from typing import Any, Mapping


DEFAULT_STORE_DIR = (
    Path(__file__).resolve().parent
    / "runtime"
    / "terminal"
    / "robot_candidates"
)

SCHEMA_VERSION = "1.0"
STATUS_AVAILABLE = "AVAILABLE"
STATUS_APPROVED = "APPROVED"


class RobotCandidateError(RuntimeError):
    """Base error for durable Robot candidate handoff state."""


class RobotCandidateNotFound(RobotCandidateError):
    """Raised when a callback references no durable candidate snapshot."""


class RobotCandidateCorrupt(RobotCandidateError):
    """Raised when persisted state cannot be trusted."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _candidate_path(candidate_id: str, store_dir: Path) -> Path:
    safe_id = str(candidate_id).strip()

    if not safe_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        for character in safe_id
    ):
        raise RobotCandidateError("invalid candidate_id")

    return store_dir / f"{safe_id}.json"


def _json_default(value: Any) -> Any:
    item = getattr(value, "item", None)
    if callable(item):
        return item()

    if isinstance(value, Path):
        return str(value)

    raise TypeError(
        f"unsupported Robot snapshot value: {type(value).__name__}"
    )


def _json_round_trip(value: Any) -> Any:
    """Freeze a detached JSON-safe copy without silently stringifying data."""

    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return json.loads(serialized)


def _read_record(path: Path) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RobotCandidateNotFound(path.stem) from exc
    except Exception as exc:
        raise RobotCandidateCorrupt(
            f"cannot read candidate {path.name}"
        ) from exc

    if not isinstance(record, dict):
        raise RobotCandidateCorrupt("candidate record is not an object")

    if record.get("schema_version") != SCHEMA_VERSION:
        raise RobotCandidateCorrupt("unsupported candidate schema")

    if record.get("candidate_id") != path.stem:
        raise RobotCandidateCorrupt("candidate identity mismatch")

    if record.get("status") not in {STATUS_AVAILABLE, STATUS_APPROVED}:
        raise RobotCandidateCorrupt("invalid candidate status")

    snapshot = record.get("signal_snapshot")
    if not isinstance(snapshot, dict):
        raise RobotCandidateCorrupt("candidate snapshot is missing")

    return record


def _write_new_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(
        record,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.write("\n")
    except FileExistsError:
        raise
    except Exception as exc:
        raise RobotCandidateError(
            f"cannot persist candidate {path.name}"
        ) from exc


def _replace_record(path: Path, record: Mapping[str, Any]) -> None:
    temp_path = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
    payload = json.dumps(
        record,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )

    try:
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(path)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RobotCandidateError(
            f"cannot update candidate {path.name}"
        ) from exc


def create_signal_snapshot(
    signal_snapshot: Mapping[str, Any],
    *,
    timeframe: str,
    store_dir: Path | str | None = None,
    candidate_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Persist a new immutable signal snapshot and return its envelope."""

    if not isinstance(signal_snapshot, Mapping):
        raise RobotCandidateError("signal_snapshot must be a mapping")

    frozen_snapshot = _json_round_trip(deepcopy(dict(signal_snapshot)))
    symbol = str(frozen_snapshot.get("symbol", "")).strip()

    if not symbol:
        raise RobotCandidateError("signal snapshot has no symbol")

    normalized_timeframe = str(timeframe).strip()
    if not normalized_timeframe:
        raise RobotCandidateError("signal snapshot has no timeframe")

    directory = Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR

    attempts = 1 if candidate_id is not None else 8

    for _ in range(attempts):
        resolved_id = (
            str(candidate_id).strip()
            if candidate_id is not None
            else secrets.token_hex(12)
        )
        path = _candidate_path(resolved_id, directory)
        record = {
            "schema_version": SCHEMA_VERSION,
            "candidate_id": resolved_id,
            "status": STATUS_AVAILABLE,
            "created_at": created_at or _utc_now_iso(),
            "approved_at": None,
            "symbol": symbol,
            "timeframe": normalized_timeframe,
            "approval": None,
            "signal_snapshot": frozen_snapshot,
        }

        try:
            _write_new_record(path, record)
            return deepcopy(record)
        except FileExistsError:
            if candidate_id is not None:
                raise RobotCandidateError(
                    f"candidate already exists: {resolved_id}"
                )

    raise RobotCandidateError("could not allocate candidate identity")


def load_candidate(
    candidate_id: str,
    *,
    store_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Load a detached copy of one durable candidate envelope."""

    directory = Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR
    record = _read_record(_candidate_path(candidate_id, directory))
    return deepcopy(record)


def approve_candidate(
    candidate_id: str,
    *,
    approval: Mapping[str, Any] | None = None,
    store_dir: Path | str | None = None,
    approved_at: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Idempotently transition AVAILABLE -> APPROVED.

    Returns ``(record, changed)``.  A repeat callback for the same durable
    candidate returns the already-approved record with ``changed=False``.
    The ``signal_snapshot`` value is copied byte-for-byte at the data-model
    level and never recomputed from Telegram callback fields.
    """

    directory = Path(store_dir) if store_dir is not None else DEFAULT_STORE_DIR
    path = _candidate_path(candidate_id, directory)
    record = _read_record(path)

    if record["status"] == STATUS_APPROVED:
        return deepcopy(record), False

    frozen_snapshot = deepcopy(record["signal_snapshot"])
    record["status"] = STATUS_APPROVED
    record["approved_at"] = approved_at or _utc_now_iso()
    record["approval"] = (
        _json_round_trip(dict(approval))
        if approval is not None
        else {}
    )

    if record["signal_snapshot"] != frozen_snapshot:
        raise RobotCandidateCorrupt("signal snapshot mutation detected")

    _replace_record(path, record)
    return deepcopy(record), True
