"""Opt-in Scanner producer for Trading Diary D4 P0 automatic factors.

The producer only persists factors already present in the Scanner decision-time
analysis. Missing values stay missing: no zero/False defaults are invented.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from terminal.diary import DecisionEventId, SetupInstanceId
from terminal.diary.factors import (
    DiaryFactorStore,
    FactorObservation,
    FactorProvenance,
    FactorSubjectKind,
    P0_FACTOR_DEFINITIONS_V1,
)


FACTOR_DB_ENV = "TRADING_DIARY_FACTOR_DB"
SCANNER_FACTOR_SOURCE_VERSION = "scanner-d4-p0-v1"


@dataclass(frozen=True, slots=True)
class ScannerFactorWriteResult:
    status: str
    recorded: int = 0


def _finite_number(value: Any) -> int | float | None:
    if type(value) is bool:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value == value and value not in (float("inf"), float("-inf")):
            return value
        return None
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _finite_number(item_method())
        except Exception:
            return None
    return None


def _bool_or_none(value: Any) -> bool | None:
    if type(value) is bool:
        return value
    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            item = item_method()
            return item if type(item) is bool else None
        except Exception:
            return None
    return None


def _p0_values(analysis: dict[str, Any]) -> dict[str, bool | int | float]:
    confirmation = analysis.get("confirmation") or {}
    values: dict[str, bool | int | float] = {}

    final_score = _finite_number(analysis.get("final_score", analysis.get("score")))
    if final_score is not None:
        values["scanner.final_score"] = final_score

    confirmation_score = _finite_number(confirmation.get("confirmation_score"))
    if confirmation_score is not None:
        values["scanner.confirmation_score"] = confirmation_score

    for key, source_key in (
        ("scanner.breakout", "breakout"),
        ("scanner.volume_confirmation", "volume"),
        ("scanner.volatility_confirmation", "volatility"),
    ):
        value = _bool_or_none(confirmation.get(source_key))
        if value is not None:
            values[key] = value

    return values


def _same_evidence_except_observed_at(
    existing: FactorObservation,
    candidate: FactorObservation,
) -> bool:
    return (
        existing.observation_id == candidate.observation_id
        and existing.factor_key == candidate.factor_key
        and existing.factor_version == candidate.factor_version
        and existing.subject_kind is candidate.subject_kind
        and existing.subject_id == candidate.subject_id
        and existing.provenance is candidate.provenance
        and existing.source_version == candidate.source_version
        and existing.value == candidate.value
    )


def record_scanner_p0_factors(
    *,
    setup_instance_id: SetupInstanceId,
    decision_event_id: DecisionEventId,
    analysis: dict[str, Any],
    observed_at_ms: int,
    database_path: str | Path | None = None,
) -> ScannerFactorWriteResult:
    """Persist available D4 P0 factors for one immutable Scanner decision event."""
    if observed_at_ms < 0:
        raise ValueError("observed_at_ms must not be negative")
    raw_path = str(database_path) if database_path is not None else os.getenv(FACTOR_DB_ENV, "").strip()
    if not raw_path:
        return ScannerFactorWriteResult("DISABLED")

    values = _p0_values(analysis)
    if not values:
        return ScannerFactorWriteResult("NO_FACTORS")

    path = Path(raw_path)
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)

    recorded = 0
    definitions = {definition.factor_key: definition for definition in P0_FACTOR_DEFINITIONS_V1}
    with DiaryFactorStore.open(path) as store:
        store.register_definitions(P0_FACTOR_DEFINITIONS_V1)
        for factor_key, value in sorted(values.items()):
            definition = definitions[factor_key]
            identity_material = (
                f"{decision_event_id.value}|{factor_key}|{definition.version}"
            )
            observation_id = "fo_scanner_" + hashlib.sha256(
                identity_material.encode("utf-8")
            ).hexdigest()[:24]
            observation = FactorObservation(
                observation_id=observation_id,
                factor_key=factor_key,
                factor_version=definition.version,
                subject_kind=FactorSubjectKind.SETUP_INSTANCE,
                subject_id=setup_instance_id.value,
                observed_at_ms=observed_at_ms,
                provenance=FactorProvenance.SCANNER_DERIVED,
                source_version=f"{SCANNER_FACTOR_SOURCE_VERSION}:{decision_event_id.value}",
                value=value,
            )
            existing = store.get_observation(observation_id)
            if existing is not None and _same_evidence_except_observed_at(existing, observation):
                continue
            store.append_observation(observation)
            recorded += 1

    return ScannerFactorWriteResult("RECORDED" if recorded else "UNCHANGED", recorded)
