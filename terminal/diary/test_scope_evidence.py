from __future__ import annotations

import sqlite3

import pytest

from terminal.diary.scope_evidence import load_order_origins_read_only
from terminal.diary.scoped_statistics_archive import StatisticsScopeError
from terminal.domain.models import Origin


def make_source(path):
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE executions (
            trading_account_id TEXT, category TEXT, exec_id TEXT,
            order_id TEXT
        );
        CREATE TABLE trading_commands (
            command_id TEXT, trading_account_id TEXT, exchange_order_id TEXT,
            origin TEXT, controller TEXT
        );
    """)
    return con


def test_only_proven_per_account_command_ownership_is_exported(tmp_path):
    source = tmp_path / "source.sqlite3"
    con = make_source(source)
    con.executemany(
        "INSERT INTO executions VALUES (?, 'linear', ?, ?)",
        [
            ("paper", "exec-m", "order-m"),
            ("paper", "exec-r", "order-r"),
            ("paper", "exec-unknown", "order-orphan"),
            ("bybit-main", "exec-main", "order-main"),
        ],
    )
    con.executemany(
        "INSERT INTO trading_commands VALUES (?,?,?,?,?)",
        [
            ("cmd-m", "paper", "order-m", "terminal_manual", "manual"),
            ("cmd-r", "paper", "order-r", "robot", "robot"),
            ("cmd-main", "bybit-main", "order-main", "terminal_manual", "manual"),
        ],
    )
    con.commit()
    con.close()
    paper = load_order_origins_read_only(source, account_id="paper")
    main = load_order_origins_read_only(source, account_id="bybit-main")
    assert {k.exec_id.value: origin for k, origin in paper.items()} == {
        "exec-m": Origin.TERMINAL_MANUAL, "exec-r": Origin.ROBOT,
    }
    assert {k.exec_id.value: origin for k, origin in main.items()} == {
        "exec-main": Origin.TERMINAL_MANUAL,
    }
    assert {k.trading_account_id.value for k in paper} == {"paper"}
    assert {k.trading_account_id.value for k in main} == {"bybit-main"}


def test_wrong_controller_is_not_auto_classified(tmp_path):
    source = tmp_path / "source.sqlite3"
    con = make_source(source)
    con.execute("INSERT INTO executions VALUES ('paper','linear','exec-1','order-1')")
    con.execute("INSERT INTO trading_commands VALUES ('c1','paper','order-1','robot','manual')")
    con.commit()
    con.close()
    assert load_order_origins_read_only(source, account_id="paper") == {}


def test_conflicting_order_claims_fail_closed(tmp_path):
    source = tmp_path / "source.sqlite3"
    con = make_source(source)
    con.execute("INSERT INTO executions VALUES ('paper','linear','exec-1','order-1')")
    con.execute("INSERT INTO trading_commands VALUES ('c1','paper','order-1','robot','robot')")
    con.execute("INSERT INTO trading_commands VALUES ('c2','paper','order-1','terminal_manual','manual')")
    con.commit()
    con.close()
    with pytest.raises(StatisticsScopeError, match="ambiguous"):
        load_order_origins_read_only(source, account_id="paper")


def test_no_source_database_is_created(tmp_path):
    missing = tmp_path / "paper.sqlite3"
    with pytest.raises(StatisticsScopeError, match="unavailable"):
        load_order_origins_read_only(missing, account_id="paper")
    assert not missing.exists()
