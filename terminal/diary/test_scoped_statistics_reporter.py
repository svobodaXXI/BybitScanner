from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from terminal.diary.scoped_statistics_archive import (
    ScopedStatisticsArchive, StatisticsScopeError, load_latest_scoped_statistics_read_only,
)
from terminal.diary.scoped_statistics_reporter import (
    load_paper_source_snapshot, refresh_paper_scoped_statistics,
)


def source_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE paper_accounts (trading_account_id TEXT PRIMARY KEY);
    INSERT INTO paper_accounts VALUES ('paper');
    CREATE TABLE executions (
        trading_account_id TEXT, category TEXT, exec_id TEXT, order_id TEXT,
        symbol TEXT, side TEXT, price TEXT, quantity TEXT, fee TEXT,
        exchange_timestamp_ms INTEGER
    );
    CREATE TABLE trading_commands (
        command_id TEXT, trading_account_id TEXT, exchange_order_id TEXT,
        origin TEXT, controller TEXT
    );
    """)
    con.commit()
    con.close()


def add_fill(path: Path, *, account: str, exec_id: str, order_id: str,
             side: str, price: str, occurred: int, origin: str, controller: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute(
            "INSERT INTO executions VALUES (?, 'linear', ?, ?, 'BTCUSDT', ?, ?, '1', '0.1', ?)",
            (account, exec_id, order_id, side, price, occurred),
        )
        con.execute(
            "INSERT INTO trading_commands VALUES (?, ?, ?, ?, ?)",
            ("cmd-" + exec_id, account, order_id, origin, controller),
        )
        con.commit()
    finally:
        con.close()


def test_automated_archive_is_durable_scoped_and_does_not_modify_source(tmp_path: Path):
    paper = tmp_path / "source" / "paper.sqlite3"
    paper.parent.mkdir()
    source_db(paper)
    for i, (account, side, price, owner, controller) in enumerate((
        ("paper", "Buy", "100", "terminal_manual", "manual"),
        ("paper", "Sell", "105", "terminal_manual", "manual"),
        ("paper", "Buy", "200", "robot", "robot"),
        ("paper", "Sell", "203", "robot", "robot"),
        ("bybit-main", "Buy", "999", "terminal_manual", "manual"),
    ), start=1):
        add_fill(paper, account=account, exec_id=f"e{i}", order_id=f"o{i}",
                 side=side, price=price, occurred=i * 1000,
                 origin=owner, controller=controller)
    fingerprint = hashlib.sha256(paper.read_bytes()).hexdigest()
    archive_path = tmp_path / "diary" / "scoped_diary_statistics.sqlite3"
    first = refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive_path)
    assert first["MANUAL"]["statistics"]["sample"]["total"] == 1
    assert first["ROBOT"]["statistics"]["sample"]["total"] == 1
    assert first["MANUAL"]["source_revision"] == 5
    assert first["ROBOT"]["source_revision"] == 5
    assert refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive_path) == first
    assert hashlib.sha256(paper.read_bytes()).hexdigest() == fingerprint
    assert not (tmp_path / "diary" / "scoped_factors_unavailable.sqlite3").exists()
    assert load_latest_scoped_statistics_read_only(
        archive_path, account_id="paper", owner="MANUAL",
    ) == first["MANUAL"]
    assert load_latest_scoped_statistics_read_only(
        archive_path, account_id="paper", owner="ROBOT",
    ) == first["ROBOT"]
    assert load_latest_scoped_statistics_read_only(
        archive_path, account_id="bybit-main", owner="MANUAL",
    ) is None
    a = ScopedStatisticsArchive(archive_path)
    try:
        assert a.latest(account_id="paper", owner="ROBOT") == first["ROBOT"]
        assert a.latest(account_id="paper", owner="MANUAL") == first["MANUAL"]
        assert a.latest(account_id="bybit-main", owner="MANUAL") is None
    finally:
        a.close()
    add_fill(paper, account="paper", exec_id="e6", order_id="o6",
             side="Buy", price="300", occurred=6000, origin="robot", controller="robot")
    updated = refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive_path)
    assert updated["ROBOT"]["source_revision"] == 6
    assert updated["ROBOT"]["statistics"]["sample"]["total"] == 2


def test_unknown_origin_blocks_both_scopes_without_creating_archive(tmp_path: Path):
    paper = tmp_path / "paper.sqlite3"
    source_db(paper)
    add_fill(paper, account="paper", exec_id="e1", order_id="o1",
             side="Buy", price="100", occurred=1000,
             origin="external", controller="external")
    archive = tmp_path / "separate" / "scoped_diary_statistics.sqlite3"
    with pytest.raises(StatisticsScopeError, match="unattributed"):
        refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive)
    assert not archive.exists()


def test_mixed_manual_robot_episode_blocks_publication(tmp_path: Path):
    paper = tmp_path / "paper.sqlite3"
    source_db(paper)
    add_fill(paper, account="paper", exec_id="e1", order_id="o1",
             side="Buy", price="100", occurred=1000, origin="terminal_manual", controller="manual")
    add_fill(paper, account="paper", exec_id="e2", order_id="o2",
             side="Sell", price="110", occurred=2000, origin="robot", controller="robot")
    archive = tmp_path / "separate" / "scoped_diary_statistics.sqlite3"
    with pytest.raises(StatisticsScopeError, match="mixed_controller"):
        refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive)
    assert not archive.exists()


def test_unproven_source_never_creates_fake_zero_statistics(tmp_path: Path):
    paper = tmp_path / "paper.sqlite3"
    archive = tmp_path / "separate" / "scoped_diary_statistics.sqlite3"
    with pytest.raises(StatisticsScopeError, match="paper_source_db_required"):
        refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive)
    assert not paper.exists()
    assert not archive.exists()
    source_db(paper)
    sqlite3.connect(paper).execute("DELETE FROM paper_accounts").connection.commit()
    with pytest.raises(StatisticsScopeError, match="paper_account_not_proven"):
        refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive)
    assert not archive.exists()


def test_source_and_archive_cannot_share_directory(tmp_path: Path):
    paper = tmp_path / "paper.sqlite3"
    source_db(paper)
    with pytest.raises(StatisticsScopeError, match="independent"):
        refresh_paper_scoped_statistics(
            paper_db_path=paper, archive_path=tmp_path / "scoped_diary_statistics.sqlite3",
        )


def test_source_reconstruction_and_origins_share_snapshot(tmp_path: Path, monkeypatch):
    paper = tmp_path / "paper.sqlite3"
    source_db(paper)
    original = sqlite3.connect(paper)
    original.execute("PRAGMA journal_mode=WAL")
    original.close()
    add_fill(paper, account="paper", exec_id="e1", order_id="o1",
             side="Buy", price="100", occurred=1000,
             origin="terminal_manual", controller="manual")
    import terminal.diary.scoped_statistics_reporter as reporter
    resolver = reporter.load_order_origins_from_connection

    def concurrent_write(conn, *, account_id):
        # First SELECT has already established a read snapshot; writer commits
        # another fill before the resolver SELECT, but the resolver must not see it.
        add_fill(paper, account="paper", exec_id="e2", order_id="o2",
                 side="Sell", price="110", occurred=2000,
                 origin="terminal_manual", controller="manual")
        return resolver(conn, account_id=account_id)

    monkeypatch.setattr(reporter, "load_order_origins_from_connection", concurrent_write)
    snapshot = load_paper_source_snapshot(paper)
    assert snapshot.source_revision == 2
    assert len(snapshot.origins) == 1
    assert len(snapshot.episodes) == 1
    monkeypatch.setattr(reporter, "load_order_origins_from_connection", resolver)
    newer = load_paper_source_snapshot(paper)
    assert newer.source_revision == 3
    assert len(newer.origins) == 2


def test_read_only_archive_loader_fails_closed_without_creating_any_database(tmp_path: Path):
    path = tmp_path / "scoped_diary_statistics.sqlite3"
    with pytest.raises(StatisticsScopeError, match="unavailable"):
        load_latest_scoped_statistics_read_only(path, account_id="paper", owner="MANUAL")
    assert not path.exists()
    assert not (tmp_path / "scoped_diary_statistics.sqlite3-journal").exists()


def test_read_only_archive_loader_rejects_corrupted_digest(tmp_path: Path):
    paper = tmp_path / "source" / "paper.sqlite3"
    paper.parent.mkdir()
    source_db(paper)
    archive = tmp_path / "diary" / "scoped_diary_statistics.sqlite3"
    refresh_paper_scoped_statistics(paper_db_path=paper, archive_path=archive)
    con = sqlite3.connect(archive)
    con.execute("UPDATE scoped_statistics SET report_sha256='0' WHERE owner='ROBOT'")
    con.commit()
    con.close()
    with pytest.raises(StatisticsScopeError, match="corrupt"):
        load_latest_scoped_statistics_read_only(
            archive, account_id="paper", owner="ROBOT",
        )
    # The unrelated MANUAL report is still accessible.
    assert load_latest_scoped_statistics_read_only(
        archive, account_id="paper", owner="MANUAL",
    ) is not None
