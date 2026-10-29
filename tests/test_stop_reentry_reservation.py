"""Atomic Robot STOP reentry lineage in the *existing* PAPER SQLite/Dairy.

No runtime, exchange or VPS is started. The same BEGIN IMMEDIATE Robot
admission transaction owns candidate+attempt; original trade/STOP evidence is
read from canonical robot_trades, executions and protection obligations.
"""
import sqlite3
from decimal import Decimal

import pytest

from terminal.diary.reentry import ReentryDiaryReader
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import PersistenceError, SQLiteStore


ACCOUNT = TradingAccountId("paper")
THESIS = "f" * 64


@pytest.fixture
def prepared(tmp_path):
    path = tmp_path / "paper.sqlite3"
    store = SQLiteStore.open(path)
    state = store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=0)
    store.update_robot_runtime_state(
        ACCOUNT, mode="ROBOT_RUNNING", recovery_status="READY",
        reason=None, expected_version=state.version, updated_at_ms=1,
    )
    store.create_robot_candidate(
        candidate_id="first", trading_account_id=ACCOUNT,
        symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={
            "symbol": "LABUSDT", "pattern": "MIRROR",
            "robot_handoff_ready": True,
            "mirror_entry": {
                "direction": "LONG", "source_timeframe": "1",
                "breakout_time_ms": 60_000,
                "reference": "100", "stop": "99", "target": "110",
                "structural_stop": "99", "stop_kind": "STRUCTURAL",
                "potential_percent": "10", "reward_risk": "5",
                "confirmation": {
                    "close_time_ms": 120_000, "timeframe": "1",
                    "kind": "ENGULFING",
                },
            },
        },
        approved_at_ms=100, updated_at_ms=100,
    )
    with store.robot_admission_transaction():
        assert store.create_robot_reentry_campaign(
            account=ACCOUNT, campaign_id="thesis-lab-long",
            first_candidate_id="first", frozen_thesis_sha256=THESIS,
            direction="LONG", original_risk_budget_usdt=Decimal("10"),
            reserved_risk_usdt=Decimal("4"), reserved_at_ms=110,
        )
    with sqlite3.connect(path) as con:
        con.execute("UPDATE robot_candidates SET status='CLOSED', updated_at_ms=310 WHERE candidate_id='first'")
        con.execute(
            """INSERT INTO robot_trades (
               trade_id,trading_account_id,candidate_id,symbol,direction,
               pattern,source_timeframe,signal_time_ms,entry_time_ms,entry_path,
               actual_wv,average_entry,stop_price,take_price,
               exit_time_ms,exit_price,exit_reason,realized_pnl_usdt,
               realized_pnl_pct,fees_costs_usdt,version,created_at_ms,
               updated_at_ms,entry_quantity,entry_position_version
            ) VALUES ('trade-1','paper','first','LABUSDT','LONG',
              'MIRROR','1',120,180,'LIMIT','1','1','0.9','1.2',
              300,'0.9','STOP','-2','-2','0.5',2,180,310,'10',2)"""
        )
        con.execute(
            """INSERT INTO paper_protection_obligations (
              obligation_id,trade_id,trading_account_id,symbol,protection_version,
              winning_leg,trigger_price,observed_exit_price,observed_quantity,
              market_event_id,source_received_at_ms,latched_at_ms,order_id,
              exec_id,status,version,updated_at_ms
            ) VALUES ('obligation-1','trade-1','paper','LABUSDT',1,'STOP',
                      '0.9','0.9','10','tick-1',390,395,'stop-order-1',
                      'stop-exec-1','RESOLVED',1,400)"""
        )
        con.execute(
            """INSERT INTO executions (
               trading_account_id,category,exec_id,order_id,symbol,side,
               price,quantity,fee,exchange_timestamp_ms)
               VALUES ('paper','linear','stop-exec-1','stop-order-1',
                       'LABUSDT','Sell','0.9','10','0.1',300)"""
        )
        con.execute(
            """INSERT INTO position_projections (
              trading_account_id,category,symbol,position_idx,side,quantity,
              average_entry,realized_pnl,accumulated_fee,engaged_notional,
              sync_state,version,updated_at_ms)
              VALUES ('paper','linear','LABUSDT',0,'Flat','0',NULL,
                      '-2','0.5','0','synced',3,400)"""
        )
    store.create_robot_candidate(
        candidate_id="second", trading_account_id=ACCOUNT,
        symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "L-shape", "test": "second"},
        approved_at_ms=450, updated_at_ms=450,
    )
    try:
        yield store, path
    finally:
        store.close()


def reserve(store, **override):
    args = dict(
        account=ACCOUNT, campaign_id="thesis-lab-long",
        candidate_id="second", frozen_thesis_sha256=THESIS,
        direction="LONG", previous_stop_exec_id="stop-exec-1",
        confirmed_at_ms=420, reserved_risk_usdt=Decimal("4"),
        reserved_at_ms=460, strategy_confirmation_proven=True,
    )
    args.update(override)
    return store.reserve_robot_stop_reentry(**args)


def count(path):
    with sqlite3.connect(path) as con:
        return con.execute("SELECT count(*) FROM robot_reentry_attempts").fetchone()[0]


def test_new_pattern_reserves_once_and_diary_reuses_canonical_statistical_facts(prepared):
    store, path = prepared
    with store.robot_admission_transaction():
        assert reserve(store) is True
    with store.robot_admission_transaction():
        assert reserve(store) is False
    assert count(path) == 2
    diary = ReentryDiaryReader(path).load()[0]
    assert [a.candidate_id for a in diary.attempts] == ["first", "second"]
    assert diary.attempts[0].exit_reason == "STOP"
    assert diary.attempts[0].known_net_pnl_usdt == Decimal("-2.5")
    assert diary.attempts[1].status == "RESERVED_OR_UNFILLED"
    assert diary.known_net_pnl_usdt is None


def test_reservation_requires_existing_robot_admission_transaction(prepared):
    store, path = prepared
    with pytest.raises(PersistenceError, match="transaction"):
        reserve(store)
    assert count(path) == 1


@pytest.mark.parametrize("mutate", [
    {"previous_stop_exec_id": "fake-stop"},
    {"confirmed_at_ms": 300},
    {"strategy_confirmation_proven": False},
    {"frozen_thesis_sha256": "a" * 64},
    {"direction": "SHORT"},
    {"reserved_risk_usdt": Decimal("8")},
    {"reserved_risk_usdt": Decimal("NaN")},
])
def test_unproven_stop_frozen_thesis_risk_or_confirmation_blocks(prepared, mutate):
    store, path = prepared
    with pytest.raises(PersistenceError), store.robot_admission_transaction():
        reserve(store, **mutate)
    assert count(path) == 1


def test_rollback_protects_candidate_attempt_slot(prepared):
    store, path = prepared
    with pytest.raises(RuntimeError), store.robot_admission_transaction():
        assert reserve(store)
        raise RuntimeError("crash before commit")
    assert count(path) == 1
    with store.robot_admission_transaction():
        assert reserve(store)
    assert count(path) == 2


def test_active_position_or_pending_limit_disallows_retry(prepared):
    store, path = prepared
    with sqlite3.connect(path) as con:
        con.execute("UPDATE position_projections SET side='Long',quantity='1' WHERE symbol='LABUSDT'")
    with pytest.raises(PersistenceError, match="FLAT"), store.robot_admission_transaction():
        reserve(store)
    with sqlite3.connect(path) as con:
        con.execute("UPDATE position_projections SET side='Flat',quantity='0' WHERE symbol='LABUSDT'")
        con.execute(
            """INSERT INTO paper_limit_orders (
               order_id,order_link_id,trading_account_id,symbol,side,price,
               quantity,filled_quantity,time_in_force,status,created_at_ms,updated_at_ms)
               VALUES ('pending','pending-link','paper','LABUSDT','Buy','1',
                       '1','0','GTC','open',410,410)"""
        )
    with pytest.raises(PersistenceError, match="exposure"), store.robot_admission_transaction():
        reserve(store)
    assert count(path) == 1


def test_pending_protection_command_blocks_new_entry(prepared):
    store, path = prepared
    with sqlite3.connect(path) as con:
        con.execute(
            """INSERT INTO protection_projections (
              trading_account_id,category,symbol,position_idx,status,
              take_profit,stop_loss,trailing_stop,pending_command_id,
              version,evidence_at_ms,updated_at_ms)
              VALUES ('paper','linear','LABUSDT',0,'pending',
                      NULL,NULL,NULL,'pending-protection',1,400,400)"""
        )
    with pytest.raises(PersistenceError, match="pending STOP/TAKE"), store.robot_admission_transaction():
        reserve(store)
    assert count(path) == 1


def test_missing_actual_fill_or_resolved_stop_never_reserves(prepared):
    store, path = prepared
    with sqlite3.connect(path) as con:
        con.execute("DELETE FROM executions WHERE exec_id='stop-exec-1'")
    with pytest.raises(PersistenceError, match="execution"), store.robot_admission_transaction():
        reserve(store)
    assert count(path) == 1


def test_missing_fee_never_grants_unlimited_retries(prepared):
    store, path = prepared
    with sqlite3.connect(path) as con:
        con.execute("UPDATE robot_trades SET fees_costs_usdt=NULL WHERE trade_id='trade-1'")
    with pytest.raises(PersistenceError, match="STOP"), store.robot_admission_transaction():
        reserve(store)
    assert count(path) == 1


def test_conflicting_original_reservation_is_not_silently_reset(prepared):
    store, path = prepared
    # Initial candidate is closed; future init must not silently overwrite it.
    with pytest.raises(PersistenceError), store.robot_admission_transaction():
        store.create_robot_reentry_campaign(
            account=ACCOUNT, campaign_id="thesis-lab-long",
            first_candidate_id="second", frozen_thesis_sha256=THESIS,
            direction="LONG", original_risk_budget_usdt=Decimal("10"),
            reserved_risk_usdt=Decimal("4"), reserved_at_ms=460,
        )
    assert count(path) == 1


def test_same_frozen_thesis_cannot_restart_as_new_campaign_to_reset_budget(prepared):
    store, path = prepared
    with pytest.raises(PersistenceError, match="already reserved"), store.robot_admission_transaction():
        store.create_robot_reentry_campaign(
            account=ACCOUNT, campaign_id="new-budget-reset",
            first_candidate_id="second", frozen_thesis_sha256=THESIS,
            direction="LONG", original_risk_budget_usdt=Decimal("1000"),
            reserved_risk_usdt=Decimal("1"), reserved_at_ms=460,
        )
    assert count(path) == 1


def test_third_fresh_pattern_allowed_fourth_denied_without_new_budget(prepared):
    store, path = prepared
    with store.robot_admission_transaction():
        assert reserve(store)
    with sqlite3.connect(path) as con:
        con.execute("UPDATE robot_candidates SET status='CLOSED',updated_at_ms=610 WHERE candidate_id='second'")
        con.execute(
            """INSERT INTO robot_trades (
               trade_id,trading_account_id,candidate_id,symbol,direction,
               pattern,source_timeframe,signal_time_ms,entry_time_ms,entry_path,
               actual_wv,average_entry,stop_price,take_price,
               exit_time_ms,exit_price,exit_reason,realized_pnl_usdt,
               realized_pnl_pct,fees_costs_usdt,version,created_at_ms,
               updated_at_ms,entry_quantity,entry_position_version)
              VALUES ('trade-2','paper','second','LABUSDT','LONG',
                      'L-shape','1',420,470,'LIMIT','1','1','0.9','1.2',
                      600,'0.9','STOP','-1.5','-1.5','0.2',2,470,610,'10',4)"""
        )
        con.execute(
            """INSERT INTO paper_protection_obligations (
              obligation_id,trade_id,trading_account_id,symbol,protection_version,
              winning_leg,trigger_price,observed_exit_price,observed_quantity,
              market_event_id,source_received_at_ms,latched_at_ms,order_id,
              exec_id,status,version,updated_at_ms)
              VALUES ('obligation-2','trade-2','paper','LABUSDT',1,'STOP',
                      '0.9','0.9','10','tick-2',620,630,'stop-order-2',
                      'stop-exec-2','RESOLVED',1,640)"""
        )
        con.execute(
            """INSERT INTO executions (
               trading_account_id,category,exec_id,order_id,symbol,side,
               price,quantity,fee,exchange_timestamp_ms)
               VALUES ('paper','linear','stop-exec-2','stop-order-2',
                       'LABUSDT','Sell','0.9','10','0.1',600)"""
        )
    store.create_robot_candidate(
        candidate_id="third", trading_account_id=ACCOUNT,
        symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "Falling Wedge", "test": "third"},
        approved_at_ms=750, updated_at_ms=750,
    )
    with store.robot_admission_transaction():
        assert reserve(
            store, candidate_id="third", previous_stop_exec_id="stop-exec-2",
            confirmed_at_ms=700, reserved_at_ms=760,
            reserved_risk_usdt=Decimal("5"),
        )
    assert count(path) == 3
    store.create_robot_candidate(
        candidate_id="fourth", trading_account_id=ACCOUNT,
        symbol=Symbol("LABUSDT"), status="APPROVED",
        signal_snapshot={"pattern": "MIRROR", "test": "fourth"},
        approved_at_ms=850, updated_at_ms=850,
    )
    with pytest.raises(PersistenceError, match="maximum"), store.robot_admission_transaction():
        reserve(
            store, candidate_id="fourth", previous_stop_exec_id="stop-exec-3",
            confirmed_at_ms=800, reserved_at_ms=860,
            reserved_risk_usdt=Decimal("1"),
        )
    assert count(path) == 3
