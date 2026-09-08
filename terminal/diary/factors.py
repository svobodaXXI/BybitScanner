"""Trading Diary D4 automatic factor registry and observations.

The factor layer is observational/research-only. Definitions are versioned and
immutable; observations are append-only and never drive Scanner admission,
strategy/risk approval, order dispatch, execution, or reconciliation.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class FactorValueKind(str, Enum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class FactorSubjectKind(str, Enum):
    SETUP_INSTANCE = "SETUP_INSTANCE"
    TRADE_EPISODE = "TRADE_EPISODE"


class FactorTiming(str, Enum):
    DECISION_TIME = "DECISION_TIME"
    POST_TRADE = "POST_TRADE"


class FactorProvenance(str, Enum):
    SCANNER_DERIVED = "SCANNER_DERIVED"
    MARKET_DATA_DERIVED = "MARKET_DATA_DERIVED"
    EXECUTION_DERIVED = "EXECUTION_DERIVED"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"


@dataclass(frozen=True, slots=True)
class FactorDefinition:
    factor_key: str
    version: int
    value_kind: FactorValueKind
    subject_kind: FactorSubjectKind
    timing: FactorTiming
    unit: str | None
    description: str

    def __post_init__(self) -> None:
        if not self.factor_key.strip():
            raise ValueError("factor_key must be non-empty")
        if self.version < 1:
            raise ValueError("factor version must be positive")
        if not self.description.strip():
            raise ValueError("factor description must be non-empty")
        if self.unit is not None and not self.unit.strip():
            raise ValueError("factor unit must be non-empty when supplied")

    @property
    def identity(self) -> tuple[str, int]:
        return (self.factor_key, self.version)


@dataclass(frozen=True, slots=True)
class FactorObservation:
    observation_id: str
    factor_key: str
    factor_version: int
    subject_kind: FactorSubjectKind
    subject_id: str
    observed_at_ms: int
    provenance: FactorProvenance
    source_version: str
    value: bool | int | float | str

    def __post_init__(self) -> None:
        if not self.observation_id.strip():
            raise ValueError("observation_id must be non-empty")
        if not self.factor_key.strip():
            raise ValueError("factor_key must be non-empty")
        if self.factor_version < 1:
            raise ValueError("factor_version must be positive")
        if not self.subject_id.strip():
            raise ValueError("subject_id must be non-empty")
        if self.observed_at_ms < 0:
            raise ValueError("observed_at_ms must not be negative")
        if not self.source_version.strip():
            raise ValueError("source_version must be non-empty")
        if isinstance(self.value, float) and (self.value != self.value or self.value in (float("inf"), float("-inf"))):
            raise ValueError("factor float value must be finite")


P0_FACTOR_DEFINITIONS_V1: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        factor_key="scanner.final_score",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.SETUP_INSTANCE,
        timing=FactorTiming.DECISION_TIME,
        unit="score",
        description="Scanner final score at decision time.",
    ),
    FactorDefinition(
        factor_key="scanner.confirmation_score",
        version=1,
        value_kind=FactorValueKind.DECIMAL,
        subject_kind=FactorSubjectKind.SETUP_INSTANCE,
        timing=FactorTiming.DECISION_TIME,
        unit="score",
        description="Scanner confirmation score at decision time.",
    ),
    FactorDefinition(
        factor_key="scanner.breakout",
        version=1,
        value_kind=FactorValueKind.BOOLEAN,
        subject_kind=FactorSubjectKind.SETUP_INSTANCE,
        timing=FactorTiming.DECISION_TIME,
        unit=None,
        description="Whether Scanner confirmation marked a breakout at decision time.",
    ),
    FactorDefinition(
        factor_key="scanner.volume_confirmation",
        version=1,
        value_kind=FactorValueKind.BOOLEAN,
        subject_kind=FactorSubjectKind.SETUP_INSTANCE,
        timing=FactorTiming.DECISION_TIME,
        unit=None,
        description="Whether Scanner confirmation marked volume confirmation at decision time.",
    ),
    FactorDefinition(
        factor_key="scanner.volatility_confirmation",
        version=1,
        value_kind=FactorValueKind.BOOLEAN,
        subject_kind=FactorSubjectKind.SETUP_INSTANCE,
        timing=FactorTiming.DECISION_TIME,
        unit=None,
        description="Whether Scanner confirmation marked volatility confirmation at decision time.",
    ),
)


class FactorPersistenceError(RuntimeError):
    pass


class FactorImmutableConflict(FactorPersistenceError):
    pass


class FactorLinkageError(FactorPersistenceError):
    pass


class DiaryFactorStore:
    """Append-only SQLite sidecar for automatic/versioned research factors."""

    SCHEMA_VERSION = 1

    def __init__(self, connection: sqlite3.Connection, path: Path):
        self._connection = connection
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> "DiaryFactorStore":
        database_path = Path(path)
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version not in (0, cls.SCHEMA_VERSION):
            connection.close()
            raise FactorPersistenceError(f"unsupported factor schema version: {version}")
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """CREATE TABLE IF NOT EXISTS factor_definitions (
                    factor_key TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    value_kind TEXT NOT NULL,
                    subject_kind TEXT NOT NULL,
                    timing TEXT NOT NULL,
                    unit TEXT,
                    description TEXT NOT NULL,
                    PRIMARY KEY (factor_key, version)
                ) WITHOUT ROWID"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS factor_observations (
                    observation_id TEXT PRIMARY KEY,
                    factor_key TEXT NOT NULL,
                    factor_version INTEGER NOT NULL,
                    subject_kind TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    provenance TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    FOREIGN KEY (factor_key, factor_version)
                        REFERENCES factor_definitions(factor_key, version)
                ) WITHOUT ROWID"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_factor_subject ON factor_observations(subject_kind, subject_id, observed_at_ms, observation_id)"
            )
            if version == 0:
                connection.execute(f"PRAGMA user_version = {cls.SCHEMA_VERSION}")
            connection.commit()
        except Exception:
            connection.rollback()
            connection.close()
            raise
        return cls(connection, database_path)

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "DiaryFactorStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def register_definition(self, definition: FactorDefinition) -> FactorDefinition:
        existing = self.get_definition(definition.factor_key, definition.version)
        if existing is not None:
            if existing != definition:
                raise FactorImmutableConflict("factor definition identity already has different semantics")
            return existing
        self._connection.execute(
            "INSERT INTO factor_definitions VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                definition.factor_key,
                definition.version,
                definition.value_kind.value,
                definition.subject_kind.value,
                definition.timing.value,
                definition.unit,
                definition.description,
            ),
        )
        self._connection.commit()
        return definition

    def register_definitions(self, definitions: Iterable[FactorDefinition]) -> None:
        for definition in definitions:
            self.register_definition(definition)

    def get_definition(self, factor_key: str, version: int) -> FactorDefinition | None:
        row = self._connection.execute(
            "SELECT * FROM factor_definitions WHERE factor_key=? AND version=?",
            (factor_key, version),
        ).fetchone()
        if row is None:
            return None
        return FactorDefinition(
            factor_key=row["factor_key"],
            version=int(row["version"]),
            value_kind=FactorValueKind(row["value_kind"]),
            subject_kind=FactorSubjectKind(row["subject_kind"]),
            timing=FactorTiming(row["timing"]),
            unit=row["unit"],
            description=row["description"],
        )

    def append_observation(self, observation: FactorObservation) -> FactorObservation:
        definition = self.get_definition(observation.factor_key, observation.factor_version)
        if definition is None:
            raise FactorLinkageError("factor observation requires a registered definition")
        if definition.subject_kind is not observation.subject_kind:
            raise FactorLinkageError("factor observation subject kind contradicts definition")
        self._validate_value(definition.value_kind, observation.value)
        existing = self.get_observation(observation.observation_id)
        if existing is not None:
            if existing != observation:
                raise FactorImmutableConflict("factor observation identity already has different evidence")
            return existing
        self._connection.execute(
            "INSERT INTO factor_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                observation.observation_id,
                observation.factor_key,
                observation.factor_version,
                observation.subject_kind.value,
                observation.subject_id,
                observation.observed_at_ms,
                observation.provenance.value,
                observation.source_version,
                json.dumps(observation.value, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        self._connection.commit()
        return observation

    def get_observation(self, observation_id: str) -> FactorObservation | None:
        row = self._connection.execute(
            "SELECT * FROM factor_observations WHERE observation_id=?",
            (observation_id,),
        ).fetchone()
        return self._observation_from_row(row) if row is not None else None

    def load_observations(
        self,
        *,
        subject_kind: FactorSubjectKind,
        subject_id: str,
    ) -> tuple[FactorObservation, ...]:
        rows = self._connection.execute(
            """SELECT * FROM factor_observations
               WHERE subject_kind=? AND subject_id=?
               ORDER BY observed_at_ms, observation_id""",
            (subject_kind.value, subject_id),
        ).fetchall()
        return tuple(self._observation_from_row(row) for row in rows)

    @staticmethod
    def _validate_value(kind: FactorValueKind, value: Any) -> None:
        if kind is FactorValueKind.BOOLEAN:
            if type(value) is not bool:
                raise ValueError("BOOLEAN factor requires bool")
        elif kind is FactorValueKind.INTEGER:
            if type(value) is not int:
                raise ValueError("INTEGER factor requires int")
        elif kind is FactorValueKind.DECIMAL:
            if type(value) not in (int, float):
                raise ValueError("DECIMAL factor requires int or float")
        elif kind is FactorValueKind.TEXT:
            if not isinstance(value, str):
                raise ValueError("TEXT factor requires str")

    @staticmethod
    def _observation_from_row(row: sqlite3.Row) -> FactorObservation:
        return FactorObservation(
            observation_id=row["observation_id"],
            factor_key=row["factor_key"],
            factor_version=int(row["factor_version"]),
            subject_kind=FactorSubjectKind(row["subject_kind"]),
            subject_id=row["subject_id"],
            observed_at_ms=int(row["observed_at_ms"]),
            provenance=FactorProvenance(row["provenance"]),
            source_version=row["source_version"],
            value=json.loads(row["value_json"]),
        )
