"""Source-consistent PAPER Diary reporter; no trading/database mutations.

Reads one WAL-consistent snapshot of the existing execution/command ledgers and
writes only a distinct scoped Diary archive. This CLI is intentionally not
registered with the PAPER start/stop chain. The service/timer is opt-in only.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from terminal.diary.models import DiaryEnvironment, TradeEpisode
from terminal.diary.reconstruction import TradeEpisodeReconstructor
from terminal.diary.scope_evidence import load_order_origins_from_connection
from terminal.diary.scoped_statistics_archive import (
    ScopedStatisticsArchive, StatisticsScopeError, _attributed_episodes,
)
from terminal.domain.models import ExecutionDedupKey, Origin
from terminal.persistence.sqlite_store import _execution_from_row


@dataclass(frozen=True)
class PaperSourceSnapshot:
    source_revision: int
    episodes: tuple[TradeEpisode, ...]
    origins: Mapping[ExecutionDedupKey, Origin]


def load_paper_source_snapshot(db_path: str | Path) -> PaperSourceSnapshot:
    """Use ONE read-only transaction for fills + command provenance + account proof."""
    path = Path(db_path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise StatisticsScopeError("paper_source_db_required")
    try:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
    except sqlite3.Error as exc:
        raise StatisticsScopeError("paper_source_unavailable") from exc
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        # Even an empty source history needs durable proof of a real PAPER account.
        account = conn.execute(
            "SELECT 1 FROM paper_accounts WHERE trading_account_id='paper'",
        ).fetchone()
        if account is None:
            raise StatisticsScopeError("paper_account_not_proven")
        rows = conn.execute(
            """SELECT * FROM executions WHERE trading_account_id='paper'
               ORDER BY exchange_timestamp_ms, trading_account_id, category, exec_id""",
        ).fetchall()
        executions = tuple(_execution_from_row(row) for row in rows)
        origins = load_order_origins_from_connection(conn, account_id="paper")
        conn.rollback()
    except sqlite3.Error as exc:
        raise StatisticsScopeError("paper_source_unavailable") from exc
    finally:
        conn.close()
    if any(item.dedup_key.trading_account_id.value != "paper" for item in executions):
        raise StatisticsScopeError("cross_account_statistics_evidence")
    # The immutable execution set is append-only. Count is a monotonic,
    # crash-persistent source revision; repeat-with-changed-facts is a conflict
    # at the archive digest gate rather than a fabricated later revision.
    return PaperSourceSnapshot(
        source_revision=len(executions) + 1,
        episodes=TradeEpisodeReconstructor().reconstruct(
            executions, environment=DiaryEnvironment.PAPER,
        ),
        origins=origins,
    )


def refresh_paper_scoped_statistics(
    *, paper_db_path: str | Path, archive_path: str | Path,
) -> dict[str, dict[str, object]]:
    """Materialize both MANUAL and ROBOT only from fully proven source evidence."""
    source, archive_file = Path(paper_db_path), Path(archive_path)
    if (not archive_file.is_absolute() or archive_file.name != "scoped_diary_statistics.sqlite3"
            or source.resolve() == archive_file.resolve()
            or source.resolve().parent == archive_file.resolve().parent
            or archive_file.is_symlink()):
        raise StatisticsScopeError("independent_statistics_database_required")
    snapshot = load_paper_source_snapshot(source)
    # Validate BOTH scopes before writing either report. Mixed/unknown ownership
    # leaves the prior archive unchanged; no silent partial attribution.
    for owner in ("MANUAL", "ROBOT"):
        _attributed_episodes("paper", owner, snapshot.episodes, snapshot.origins)
    # D5 factor updates have a separate revision lineage; do not silently
    # combine them into an executions-only source revision.
    unavailable_factors = archive_file.parent / "scoped_factors_unavailable.sqlite3"
    if unavailable_factors.exists():
        raise StatisticsScopeError("unversioned_factor_source_collision")
    archive = ScopedStatisticsArchive(archive_file)
    try:
        return {
            owner: archive.publish(
                account_id="paper", owner=owner,
                source_revision=snapshot.source_revision,
                episodes=snapshot.episodes,
                origin_evidence=snapshot.origins,
                factor_store_path=unavailable_factors,
            )
            for owner in ("MANUAL", "ROBOT")
        }
    finally:
        archive.close()


def main() -> None:
    db = os.environ.get("BYBITSCANNER_DIARY_SOURCE_DB", "").strip()
    archive = os.environ.get("BYBITSCANNER_DIARY_ARCHIVE_DB", "").strip()
    if not db or not archive:
        raise SystemExit("BLOCKED: explicit PAPER source and separate archive paths required")
    result = refresh_paper_scoped_statistics(
        paper_db_path=db, archive_path=archive,
    )
    # No account keys, paths, source fills, balances or trade payload in logs.
    print(
        "SCOPED_DIARY_REFRESH_OK",
        "revision=" + str(result["MANUAL"]["source_revision"]),
        "manual_total=" + str(result["MANUAL"]["statistics"]["sample"]["total"]),
        "robot_total=" + str(result["ROBOT"]["statistics"]["sample"]["total"]),
    )


if __name__ == "__main__":
    main()
