"""Durable, account-and-controller-scoped Diary statistics archive (#930).

Never writes to the trading/PAPER database. Only fully attributed immutable trade
episodes can be materialized. An ambiguous/manual+robot mixed episode blocks
publication instead of contaminating either account's report.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Mapping, Sequence

from terminal.diary.models import TradeEpisode
from terminal.diary.statistics_runtime import project_runtime_statistics
from terminal.domain.models import ExecutionDedupKey, Origin, TradingAccountId


class StatisticsScopeError(RuntimeError):
    pass


OWNERS = frozenset({"MANUAL", "ROBOT"})
ORIGINS = {
    Origin.TERMINAL_MANUAL: "MANUAL",
    Origin.ROBOT: "ROBOT",
}


def _scope(account_id: str, owner: str) -> tuple[str, str]:
    if not isinstance(account_id, str) or not account_id.strip() or account_id != account_id.strip():
        raise StatisticsScopeError("account_identity_required")
    if not isinstance(owner, str) or owner not in OWNERS:
        raise StatisticsScopeError("statistics_owner_required")
    return account_id, owner


def _attributed_episodes(
    account_id: str, owner: str,
    episodes: Sequence[TradeEpisode],
    origin_evidence: Mapping[ExecutionDedupKey, Origin],
) -> tuple[TradeEpisode, ...]:
    """Prove every execution of every episode belongs to exactly one owner."""
    selected: list[TradeEpisode] = []
    seen_ids: set[str] = set()
    for episode in episodes:
        if not isinstance(episode, TradeEpisode):
            raise StatisticsScopeError("invalid_trade_episode")
        if episode.position_key.trading_account_id != TradingAccountId(account_id):
            raise StatisticsScopeError("cross_account_statistics_evidence")
        if episode.trade_episode_id.value in seen_ids:
            raise StatisticsScopeError("duplicate_trade_episode")
        seen_ids.add(episode.trade_episode_id.value)
        owners: set[str] = set()
        for allocation in episode.allocations:
            key = allocation.execution_key
            if key.trading_account_id != TradingAccountId(account_id):
                raise StatisticsScopeError("cross_account_statistics_evidence")
            origin = origin_evidence.get(key)
            mapped = ORIGINS.get(origin)
            if mapped is None:
                raise StatisticsScopeError("unattributed_statistics_evidence")
            owners.add(mapped)
        if len(owners) != 1:
            raise StatisticsScopeError("mixed_controller_trade_episode")
        if owner in owners:
            selected.append(episode)
    return tuple(selected)


class ScopedStatisticsArchive:
    """Append-only materializations per (account_id, MANUAL|ROBOT, revision).

    Revision must come from the authoritative source snapshot, not a UI counter.
    No implicit legacy migrations, no fallback, no factor store write.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        if self._path.name != "scoped_diary_statistics.sqlite3":
            raise StatisticsScopeError("independent_statistics_database_required")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self._path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS scoped_statistics (
                account_id TEXT NOT NULL,
                owner TEXT NOT NULL CHECK(owner IN ('MANUAL', 'ROBOT')),
                source_revision INTEGER NOT NULL CHECK(source_revision > 0),
                report_json TEXT NOT NULL,
                report_sha256 TEXT NOT NULL,
                PRIMARY KEY(account_id, owner, source_revision)
            )
        """)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def publish(
        self, *, account_id: str, owner: str, source_revision: int,
        episodes: Sequence[TradeEpisode],
        origin_evidence: Mapping[ExecutionDedupKey, Origin],
        factor_store_path: str | Path,
    ) -> dict[str, object]:
        account_id, owner = _scope(account_id, owner)
        if type(source_revision) is not int or source_revision <= 0:
            raise StatisticsScopeError("source_revision_required")
        selected = _attributed_episodes(account_id, owner, tuple(episodes), origin_evidence)
        # A legitimate empty *attributed* result must still be based on a fully
        # checked source snapshot. Unknown/mixed attribution raises above.
        statistics = project_runtime_statistics(selected, factor_store_path=factor_store_path)
        report = {
            "account_id": account_id, "owner": owner,
            "source_revision": source_revision, "statistics": statistics,
        }
        payload = json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        # Check-and-append under one SQLite writer reservation. Concurrent
        # publishers cannot pass the revision gate on an old snapshot.
        self._db.execute("BEGIN IMMEDIATE")
        try:
            latest = self._db.execute(
                """SELECT source_revision, report_sha256 FROM scoped_statistics
                   WHERE account_id=? AND owner=?
                   ORDER BY source_revision DESC LIMIT 1""",
                (account_id, owner),
            ).fetchone()
            if latest is not None:
                if source_revision < latest[0]:
                    raise StatisticsScopeError("stale_statistics_source")
                if source_revision == latest[0]:
                    if digest != latest[1]:
                        raise StatisticsScopeError("conflicting_statistics_replay")
                    self._db.rollback()  # idempotent read; release the writer lock
                    return report
            self._db.execute(
                """INSERT INTO scoped_statistics
                   (account_id, owner, source_revision, report_json, report_sha256)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_id, owner, source_revision, payload, digest),
            )
            self._db.commit()
        except BaseException:
            self._db.rollback()
            raise
        return report

    def latest(self, *, account_id: str, owner: str) -> dict[str, object] | None:
        account_id, owner = _scope(account_id, owner)
        row = self._db.execute(
            """SELECT report_json, report_sha256 FROM scoped_statistics
               WHERE account_id=? AND owner=?
               ORDER BY source_revision DESC LIMIT 1""",
            (account_id, owner),
        ).fetchone()
        if row is None:
            return None  # Unknown history is not evidence of zero PnL.
        raw, digest = row
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != digest:
            raise StatisticsScopeError("corrupt_statistics_snapshot")
        result = json.loads(raw)
        if result.get("account_id") != account_id or result.get("owner") != owner:
            raise StatisticsScopeError("cross_scope_statistics_snapshot")
        return result



def load_latest_scoped_statistics_read_only(
    archive_path: str | Path, *, account_id: str, owner: str,
) -> dict[str, object] | None:
    """Serve one verified scope without creating, migrating or writing an archive.

    An absent archive is UNAVAILABLE, not a fabricated report of zero trades.
    """
    account_id, owner = _scope(account_id, owner)
    path = Path(archive_path)
    if (not path.is_absolute() or path.name != "scoped_diary_statistics.sqlite3"
            or path.is_symlink() or not path.is_file()):
        raise StatisticsScopeError("scoped_statistics_archive_unavailable")
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute(
                """SELECT report_json, report_sha256 FROM scoped_statistics
                   WHERE account_id=? AND owner=?
                   ORDER BY source_revision DESC LIMIT 1""",
                (account_id, owner),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise StatisticsScopeError("scoped_statistics_archive_unavailable") from exc
    if row is None:
        return None
    raw, digest = row
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != digest:
        raise StatisticsScopeError("corrupt_statistics_snapshot")
    try:
        result = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise StatisticsScopeError("corrupt_statistics_snapshot") from exc
    if (not isinstance(result, dict)
            or result.get("account_id") != account_id
            or result.get("owner") != owner
            or type(result.get("source_revision")) is not int
            or result["source_revision"] < 1
            or not isinstance(result.get("statistics"), dict)):
        raise StatisticsScopeError("cross_scope_statistics_snapshot")
    return result
