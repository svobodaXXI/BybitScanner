from __future__ import annotations

import json
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


def test_proven_robot_limit_entry_is_attributed_but_legacy_is_not(tmp_path):
    db = tmp_path / "source.sqlite3"
    con = make_source(db)
    con.executescript("""
        CREATE TABLE robot_entry_orders (
            order_id TEXT, trading_account_id TEXT, admission_version INTEGER, origin TEXT
        );
        CREATE TABLE paper_limit_orders (order_id TEXT, trading_account_id TEXT);
    """)
    rows = [
        ("e-robot", "o-robot", "ROBOT", 5),
        ("e-legacy", "o-legacy", "LEGACY", None),
        ("e-null", "o-null", "ROBOT", None),
    ]
    for eid, oid, origin, version in rows:
        con.execute("INSERT INTO executions VALUES ('paper','linear',?,?)", (eid, oid))
        con.execute("INSERT INTO paper_limit_orders VALUES (?, 'paper')", (oid,))
        con.execute("INSERT INTO robot_entry_orders VALUES (?, 'paper', ?, ?)", (oid, version, origin))
    con.commit()
    con.close()
    attributed = load_order_origins_read_only(db, account_id="paper")
    assert {key.exec_id.value: origin for key, origin in attributed.items()} == {
        "e-robot": Origin.ROBOT,
    }


def test_resolved_protection_obligation_requires_exact_order_and_exec_identity(tmp_path):
    db = tmp_path / "source.sqlite3"
    con = make_source(db)
    con.executescript("""
        CREATE TABLE robot_trades (trade_id TEXT, trading_account_id TEXT);
        CREATE TABLE paper_protection_obligations (
            trade_id TEXT, trading_account_id TEXT, order_id TEXT, exec_id TEXT, status TEXT
        );
        INSERT INTO robot_trades VALUES ('t1','paper');
    """)
    for eid, oid in [("e1", "o1"), ("e2", "o2"), ("e3", "o3")]:
        con.execute("INSERT INTO executions VALUES ('paper','linear',?,?)", (eid, oid))
    con.executemany("INSERT INTO paper_protection_obligations VALUES (?,?,?,?,?)", [
        ("t1", "paper", "o1", "e1", "RESOLVED"),
        ("t1", "paper", "o2", "e2", "DISPATCHING"),
        ("t1", "paper", "o3", "wrong-exec", "RESOLVED"),
    ])
    con.commit()
    con.close()
    attributed = load_order_origins_read_only(db, account_id="paper")
    assert {key.exec_id.value: origin for key, origin in attributed.items()} == {
        "e1": Origin.ROBOT,
    }


def test_conflicting_manual_command_and_robot_attestation_blocks_origin(tmp_path):
    db = tmp_path / "source.sqlite3"
    con = make_source(db)
    con.executescript("""
        CREATE TABLE robot_entry_orders (
            order_id TEXT, trading_account_id TEXT, admission_version INTEGER, origin TEXT
        );
        CREATE TABLE paper_limit_orders (order_id TEXT, trading_account_id TEXT);
        INSERT INTO executions VALUES ('paper','linear','e1','o1');
        INSERT INTO trading_commands VALUES ('cmd-1','paper','o1','terminal_manual','manual');
        INSERT INTO robot_entry_orders VALUES ('o1','paper',3,'ROBOT');
        INSERT INTO paper_limit_orders VALUES ('o1','paper');
    """)
    con.commit()
    con.close()
    with pytest.raises(StatisticsScopeError, match="conflicting"):
        load_order_origins_read_only(db, account_id="paper")


def _box_exit_source(path):
    """One exact Robot Box TAKE fill; no trading command/entry/STOP evidence."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE executions (
            trading_account_id TEXT, category TEXT, exec_id TEXT, order_id TEXT,
            symbol TEXT, side TEXT, exchange_timestamp_ms INTEGER
        );
        CREATE TABLE trading_commands (
            command_id TEXT, trading_account_id TEXT, exchange_order_id TEXT,
            origin TEXT, controller TEXT
        );
        CREATE TABLE paper_limit_orders (
            order_id TEXT, trading_account_id TEXT, symbol TEXT, side TEXT,
            created_at_ms INTEGER
        );
        CREATE TABLE paper_limit_actions (order_id TEXT, operation TEXT);
        CREATE TABLE box_order_ownership (
            trading_account_id TEXT, order_id TEXT, candidate_id TEXT,
            role TEXT, slot INTEGER
        );
        CREATE TABLE box_attempt_ownership (
            candidate_id TEXT, trading_account_id TEXT, symbol TEXT
        );
        CREATE TABLE robot_candidates (
            candidate_id TEXT, trading_account_id TEXT, symbol TEXT,
            status TEXT, signal_snapshot_json TEXT
        );
        CREATE TABLE robot_trades (
            candidate_id TEXT, trading_account_id TEXT, symbol TEXT,
            pattern TEXT, direction TEXT, entry_time_ms INTEGER, exit_time_ms INTEGER
        );
        INSERT INTO executions VALUES ('paper','linear','box-exec','box-exit-order',
            'BTCUSDT','Sell',2000);
        INSERT INTO paper_limit_orders VALUES ('box-exit-order','paper','BTCUSDT','Sell',1500);
        INSERT INTO paper_limit_actions VALUES ('box-exit-order','create');
        INSERT INTO box_order_ownership VALUES (
            'paper','box-exit-order','box-plan-a','EXIT',1);
        INSERT INTO box_attempt_ownership VALUES ('box-plan-a','paper','BTCUSDT');
        INSERT INTO robot_trades VALUES (
            'box-robot-a','paper','BTCUSDT','IKIGAI_BOX','LONG',1000,2100);
    """)
    con.executemany(
        "INSERT INTO robot_candidates VALUES (?,?,?,?,?)",
        [
            ("box-plan-a", "paper", "BTCUSDT", "BOX_PLAN_ONLY", json.dumps({
                "pattern": "IKIGAI_BOX", "environment": "PAPER",
                "identity": {"direction": "LONG"},
            })),
            ("box-robot-a", "paper", "BTCUSDT", "CLOSED", json.dumps({
                "source_box_candidate_id": "box-plan-a",
            })),
        ],
    )
    con.commit()
    return con


def test_exact_box_exit_handoff_trade_and_immutable_order_prove_robot(tmp_path):
    db = tmp_path / "source.sqlite3"
    con = _box_exit_source(db)
    con.close()
    origins = load_order_origins_read_only(db, account_id="paper")
    assert {key.exec_id.value: value for key, value in origins.items()} == {
        "box-exec": Origin.ROBOT,
    }
    assert load_order_origins_read_only(db, account_id="bybit-main") == {}


@pytest.mark.parametrize("mutation", [
    "DELETE FROM box_order_ownership",
    "UPDATE box_order_ownership SET role='ENTRY'",
    "UPDATE box_order_ownership SET slot=0",
    "UPDATE box_order_ownership SET candidate_id='unrelated'",
    "DELETE FROM box_attempt_ownership",
    "UPDATE box_attempt_ownership SET symbol='ETHUSDT'",
    "DELETE FROM robot_trades",
    "UPDATE robot_trades SET symbol='ETHUSDT'",
    "UPDATE robot_trades SET direction='SHORT'",
    "UPDATE robot_trades SET entry_time_ms=2500",
    "UPDATE paper_limit_orders SET side='Buy'",
    "DELETE FROM paper_limit_actions",
    "INSERT INTO paper_limit_actions VALUES ('box-exit-order','create')",
    "UPDATE robot_candidates SET signal_snapshot_json='{}' WHERE candidate_id='box-robot-a'",
    "UPDATE robot_candidates SET status='BOX_PLAN_ONLY' WHERE candidate_id='box-robot-a'",
])
def test_box_exit_missing_or_conflicting_link_never_guesses_robot(tmp_path, mutation):
    db = tmp_path / "source.sqlite3"
    con = _box_exit_source(db)
    con.execute(mutation)
    con.commit()
    con.close()
    assert load_order_origins_read_only(db, account_id="paper") == {}


def test_box_exit_conflicting_manual_command_blocks_attribution(tmp_path):
    db = tmp_path / "source.sqlite3"
    con = _box_exit_source(db)
    con.execute(
        "INSERT INTO trading_commands VALUES (?,?,?,?,?)",
        ("manual", "paper", "box-exit-order", "terminal_manual", "manual"),
    )
    con.commit()
    con.close()
    with pytest.raises(StatisticsScopeError, match="conflicting_robot_execution_ownership"):
        load_order_origins_read_only(db, account_id="paper")
