"""Opt-in Scanner producer for Trading Diary D3.

This module records Scanner decision-time observations into the D2 Diary sidecar.
It is deliberately observational: it never dispatches orders, changes Scanner
admission, or alters Terminal PAPER/LIVE execution authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from terminal.diary import (
    DecisionEventId,
    DecisionEventKind,
    DecisionEventRecord,
    DiaryDecisionStore,
    SetupInstanceId,
    SetupInstanceRecord,
)
from terminal.domain.models import Controller, Origin, PositionSide, Symbol


DIARY_PATH_ENV = "TRADING_DIARY_DECISION_DB"
SCANNER_STRATEGY_VERSION = "scanner-admission-v1"
SCANNER_ENTRY_MODE = "SCANNER_SIGNAL_ONLY"


@dataclass(frozen=True, slots=True)
class ScannerDiaryWriteResult:
    status: str
    setup_instance_id: SetupInstanceId | None = None
    decision_event_id: DecisionEventId | None = None


_DIRECTION_BY_PATTERN = {
    "falling wedge": PositionSide.LONG,
    "rising wedge": PositionSide.SHORT,
}


def _primitive(value: Any) -> Any:
    """Convert common dataframe/numpy values into deterministic JSON primitives."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, dict):
        return {str(key): _primitive(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _primitive(item_method())
        except Exception:
            pass
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        try:
            return isoformat()
        except Exception:
            pass
    return str(value)


def _direction(analysis: dict[str, Any]) -> PositionSide | None:
    confirmation = analysis.get("confirmation") or {}
    raw = str(confirmation.get("direction") or "").strip().upper()
    if raw == "LONG":
        return PositionSide.LONG
    if raw == "SHORT":
        return PositionSide.SHORT
    pattern = str(analysis.get("pattern") or "").strip().lower()
    return _DIRECTION_BY_PATTERN.get(pattern)


def _reason_code(signal_decision: dict[str, Any], *, approved: bool) -> str:
    raw = str(signal_decision.get("reason") or "").strip()
    if not raw:
        raw = "APPROVED" if approved else "REJECTED"
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    if not normalized:
        normalized = "APPROVED" if approved else "REJECTED"
    return f"SCANNER_{normalized[:80]}"


def _pattern_setup_id(pattern: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", pattern.lower()).strip("_") or "unknown"
    return f"scanner:{slug}"


def _snapshot(
    *,
    symbol: str,
    timeframe: str,
    scanner_mode: str,
    analysis_result: dict[str, Any],
    analysis: dict[str, Any],
    direction: PositionSide,
) -> dict[str, Any]:
    return {
        "schema": "scanner-diary-d3-v1",
        "symbol": symbol.upper(),
        "timeframe": str(timeframe),
        "scanner_mode": str(scanner_mode),
        "pattern": str(analysis.get("pattern") or "Unknown"),
        "direction": direction.value,
        "final_score": _primitive(analysis.get("final_score", analysis.get("score"))),
        "quality": _primitive(analysis.get("quality") or {}),
        "confirmation": _primitive(analysis.get("confirmation") or {}),
        "signal": _primitive(analysis.get("signal") or {}),
        "highs": _primitive(analysis_result.get("highs") or []),
        "lows": _primitive(analysis_result.get("lows") or []),
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _inline_snapshot_ref(canonical_json: str) -> tuple[str, str]:
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    encoded = base64.urlsafe_b64encode(canonical_json.encode("utf-8")).decode("ascii").rstrip("=")
    return digest, f"inline-json-sha256:{digest}:{encoded}"


def _setup_fingerprint(
    *, symbol: str, timeframe: str, pattern: str, direction: PositionSide,
    highs: Any, lows: Any,
) -> str:
    structural = _canonical_json({
        "symbol": symbol.upper(),
        "timeframe": str(timeframe),
        "pattern": pattern,
        "direction": direction.value,
        "highs": _primitive(highs or []),
        "lows": _primitive(lows or []),
    })
    return hashlib.sha256(structural.encode("utf-8")).hexdigest()


def record_scanner_diary_observation(
    *,
    symbol: str,
    analysis_result: dict[str, Any],
    timeframe: str,
    scanner_mode: str,
    observed_at_ms: int,
    database_path: str | Path | None = None,
) -> ScannerDiaryWriteResult:
    """Persist one eligible Scanner setup decision without changing Scanner behavior.

    Re-observing the same structural setup with the same decision-time snapshot is
    idempotent. A changed snapshot produces another append-only decision event while
    retaining the same SetupInstanceId as long as the pivot structure is unchanged.
    """
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must not be negative")
    raw_path = str(database_path) if database_path is not None else os.getenv(DIARY_PATH_ENV, "").strip()
    if not raw_path:
        return ScannerDiaryWriteResult("DISABLED")

    analysis = analysis_result.get("result") if analysis_result else None
    if not isinstance(analysis, dict):
        return ScannerDiaryWriteResult("NO_SETUP")
    pattern = str(analysis.get("pattern") or "").strip()
    if not pattern or pattern in {"No wedge", "Unknown"}:
        return ScannerDiaryWriteResult("NO_SETUP")

    direction = _direction(analysis)
    if direction is None:
        return ScannerDiaryWriteResult("UNRESOLVED_DIRECTION")

    signal_decision = analysis.get("signal") or {}
    approved = bool(signal_decision.get("approved", False))
    setup_hash = _setup_fingerprint(
        symbol=symbol,
        timeframe=timeframe,
        pattern=pattern,
        direction=direction,
        highs=analysis_result.get("highs"),
        lows=analysis_result.get("lows"),
    )
    setup_instance_id = SetupInstanceId(f"si_scanner_{setup_hash[:24]}")
    setup_id = _pattern_setup_id(pattern)

    payload = _snapshot(
        symbol=symbol,
        timeframe=timeframe,
        scanner_mode=scanner_mode,
        analysis_result=analysis_result,
        analysis=analysis,
        direction=direction,
    )
    canonical = _canonical_json(payload)
    snapshot_digest, snapshot_ref = _inline_snapshot_ref(canonical)
    reason_code = _reason_code(signal_decision, approved=approved)
    event_kind = DecisionEventKind.STRATEGY if approved else DecisionEventKind.SETUP_OUTCOME
    next_state = "ARMED" if approved else "SKIPPED"
    event_payload = f"{setup_instance_id.value}|{event_kind.value}|{next_state}|{reason_code}|{snapshot_digest}"
    decision_event_id = DecisionEventId(
        "de_scanner_" + hashlib.sha256(event_payload.encode("utf-8")).hexdigest()[:24]
    )

    path = Path(raw_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    with DiaryDecisionStore.open(path) as store:
        existing_setup = store.get_setup_instance(setup_instance_id)
        if existing_setup is None:
            setup = SetupInstanceRecord(
                setup_instance_id=setup_instance_id,
                symbol=Symbol(symbol),
                timeframe=str(timeframe),
                pattern=pattern,
                direction=direction,
                strategy_version=SCANNER_STRATEGY_VERSION,
                setup_id=setup_id,
                hypothesis_id=None,
                entry_mode=SCANNER_ENTRY_MODE,
                origin=Origin.ROBOT,
                created_at_ms=observed_at_ms,
            )
            store.create_setup_instance(setup)
        else:
            expected = SetupInstanceRecord(
                setup_instance_id=setup_instance_id,
                symbol=Symbol(symbol),
                timeframe=str(timeframe),
                pattern=pattern,
                direction=direction,
                strategy_version=SCANNER_STRATEGY_VERSION,
                setup_id=setup_id,
                hypothesis_id=None,
                entry_mode=SCANNER_ENTRY_MODE,
                origin=Origin.ROBOT,
                created_at_ms=existing_setup.created_at_ms,
            )
            if existing_setup != expected:
                raise ValueError("stable Scanner setup identity conflicts with persisted setup evidence")

        existing_event = store.get_decision_event(decision_event_id)
        if existing_event is not None:
            return ScannerDiaryWriteResult("UNCHANGED", setup_instance_id, decision_event_id)

        event = DecisionEventRecord(
            decision_event_id=decision_event_id,
            setup_instance_id=setup_instance_id,
            kind=event_kind,
            previous_state="CANDIDATE",
            next_state=next_state,
            reason_code=reason_code,
            origin=Origin.ROBOT,
            controller=Controller.ROBOT,
            strategy_version=SCANNER_STRATEGY_VERSION,
            hypothesis_id=None,
            setup_id=setup_id,
            entry_mode=SCANNER_ENTRY_MODE,
            feature_snapshot_ref=snapshot_ref,
            risk_snapshot_ref=None,
            order_plan_id=None,
            occurred_at_ms=observed_at_ms,
        )
        if approved:
            store.append_decision_event(event)
        else:
            store.record_setup_outcome(event)

    return ScannerDiaryWriteResult("RECORDED", setup_instance_id, decision_event_id)
