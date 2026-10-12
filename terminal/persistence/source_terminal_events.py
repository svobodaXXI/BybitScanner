"""A3-R3b: append-only source-terminal events in a sidecar SQLite file.

Proven terminal events of a SHADOW source signal (Scanner candidate or BOX_PLAN_ONLY)
release that signal's virtual SHADOW reservation in the portfolio collector. The file
sits next to the PAPER DB (same derivation as ``.live_accounts.sqlite3``) and has its own
application_id/user_version, so the PAPER schema and its migrations are untouched.

Identity is (trading_account_id, candidate_ref, snapshot_sha256). Rows are immutable:
UPDATE/DELETE abort. No producer, TTL or reset lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

APPLICATION_ID = 0x42535445  # "BSTE": BybitScanner source-terminal events
USER_VERSION = 1
ALLOWED_TERMINAL_STATUSES = {
    "SCANNER": frozenset({"EXPIRED", "INVALIDATED"}),
    "BOX_PLAN": frozenset({"EXPIRED"}),
}

_SCHEMA = (
    """CREATE TABLE source_terminal_events (
        event_id TEXT PRIMARY KEY CHECK (length(event_id) = 64),
        trading_account_id TEXT NOT NULL CHECK (length(trim(trading_account_id)) > 0),
        candidate_ref TEXT NOT NULL CHECK (length(trim(candidate_ref)) > 0),
        snapshot_sha256 TEXT NOT NULL CHECK (length(snapshot_sha256) = 64),
        source TEXT NOT NULL CHECK (source IN ('SCANNER', 'BOX_PLAN')),
        terminal_status TEXT NOT NULL CHECK (
            (source = 'SCANNER' AND terminal_status IN ('EXPIRED', 'INVALIDATED'))
            OR (source = 'BOX_PLAN' AND terminal_status = 'EXPIRED')),
        rule TEXT NOT NULL CHECK (length(trim(rule)) > 0),
        rule_version TEXT NOT NULL CHECK (length(trim(rule_version)) > 0),
        evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json) AND json_type(evidence_json) = 'object'),
        observed_at_ms INTEGER NOT NULL CHECK (observed_at_ms >= 0),
        UNIQUE (trading_account_id, candidate_ref, snapshot_sha256)
    ) WITHOUT ROWID""",
    """CREATE TRIGGER source_terminal_event_immutable BEFORE UPDATE ON source_terminal_events
       BEGIN SELECT RAISE(ABORT, 'source terminal events are immutable'); END""",
    """CREATE TRIGGER source_terminal_event_no_delete BEFORE DELETE ON source_terminal_events
       BEGIN SELECT RAISE(ABORT, 'source terminal events cannot be deleted'); END""",
)
_COLUMNS = ("event_id", "trading_account_id", "candidate_ref", "snapshot_sha256", "source",
            "terminal_status", "rule", "rule_version", "evidence_json", "observed_at_ms")


class SourceTerminalEventError(RuntimeError):
    """The sidecar store is missing, foreign, incomplete or inconsistent."""


@dataclass(frozen=True, slots=True)
class SourceTerminalEvent:
    trading_account_id: str
    candidate_ref: str
    snapshot_sha256: str
    source: str
    terminal_status: str
    rule: str
    rule_version: str
    evidence_json: str
    observed_at_ms: int

    @property
    def event_id(self) -> str:
        key = "\0".join((self.trading_account_id, self.candidate_ref, self.snapshot_sha256))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def row(self) -> tuple:
        return (self.event_id, self.trading_account_id, self.candidate_ref, self.snapshot_sha256,
                self.source, self.terminal_status, self.rule, self.rule_version,
                self.evidence_json, self.observed_at_ms)


def source_terminal_events_path(database_path: str | Path) -> Path:
    """Sidecar path next to the PAPER DB, derived like ``.live_accounts.sqlite3``."""
    return Path(database_path).with_suffix(".source_terminal_events.sqlite3")


def _validate(event: SourceTerminalEvent) -> None:
    if ALLOWED_TERMINAL_STATUSES.get(event.source) is None:
        raise SourceTerminalEventError(f"unsupported source: {event.source!r}")
    if event.terminal_status not in ALLOWED_TERMINAL_STATUSES[event.source]:
        raise SourceTerminalEventError(
            f"terminal status {event.terminal_status!r} is not allowed for {event.source}")
    if not isinstance(json.loads(event.evidence_json), dict):
        raise SourceTerminalEventError("evidence_json must be a JSON object")


def _check_identity(connection: sqlite3.Connection) -> None:
    application_id = connection.execute("PRAGMA application_id").fetchone()[0]
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if application_id != APPLICATION_ID or version != USER_VERSION:
        raise SourceTerminalEventError("not a source-terminal events store of a supported version")


def append_source_terminal_event(path: str | Path, event: SourceTerminalEvent) -> tuple[SourceTerminalEvent, bool]:
    """Writer: idempotent append. Returns (stored event, created). Never overwrites."""
    _validate(event)
    connection = sqlite3.connect(Path(path), isolation_level=None, timeout=5)
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0:
                for statement in _SCHEMA:
                    connection.execute(statement)
                connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                connection.execute(f"PRAGMA user_version = {USER_VERSION}")
            _check_identity(connection)
            existing = connection.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM source_terminal_events"
                " WHERE trading_account_id = ? AND candidate_ref = ? AND snapshot_sha256 = ?",
                (event.trading_account_id, event.candidate_ref, event.snapshot_sha256),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if tuple(existing) != event.row():
                    raise SourceTerminalEventError("a different event already exists for this identity")
                return event, False
            connection.execute(
                f"INSERT INTO source_terminal_events ({', '.join(_COLUMNS)})"
                f" VALUES ({', '.join('?' * len(_COLUMNS))})", event.row())
            connection.execute("COMMIT")
            return event, True
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
    finally:
        connection.close()


def load_terminal_identities(path: str | Path, trading_account_id: str) -> frozenset[tuple[str, str]] | None:
    """Reader: (candidate_ref, snapshot_sha256) proven terminal for one account.

    ``None`` when the file does not exist (nothing proven). Any other problem raises
    SourceTerminalEventError, so callers can keep every reservation instead of a subset.
    Read-only; never creates or modifies the file.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error as error:
        raise SourceTerminalEventError("source-terminal events store is unreadable") from error
    try:
        _check_identity(connection)
        identities = set()
        for row in connection.execute(
                f"SELECT {', '.join(_COLUMNS)} FROM source_terminal_events WHERE trading_account_id = ?",
                (trading_account_id,)):
            event = SourceTerminalEvent(*row[1:])
            if row[0] != event.event_id:
                raise SourceTerminalEventError("event identity does not match its key")
            _validate(event)
            identities.add((event.candidate_ref, event.snapshot_sha256))
        return frozenset(identities)
    except (sqlite3.Error, ValueError, TypeError) as error:
        raise SourceTerminalEventError("source-terminal events store is incomplete or inconsistent") from error
    finally:
        connection.close()
