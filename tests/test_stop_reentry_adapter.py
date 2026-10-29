"""Real frozen-snapshot adapter: next closed candle, risk, STOP ancestry.

No API orders, external data or VPS. Wedge/Box cannot bypass an unproven
pattern-specific entry-ready/risk mapping.
"""
from dataclasses import replace
from decimal import Decimal

import pytest

from terminal.application.robot_reentry_adapter import (
    proven_pattern_entry, automatic_reentry_proposal,
)
from terminal.domain.models import TradingAccountId, Symbol
from tests.test_stop_reentry_reservation import prepared


def lshape(*, breakout_ms=1_000_000, symbol="LABUSDT"):
    return {
        "symbol": symbol, "pattern": "L-shape", "robot_handoff_ready": True,
        "l_shape": {
            "direction": "LONG", "source_timeframe": "1",
            "breakout_time_ms": breakout_ms,
            "reference": "100", "target": "110", "stop": "99",
            "structural_stop": "99", "stop_kind": "STRUCTURAL",
            "potential_percent": "10", "reward_risk": "5",
        },
    }


def mirror(*, confirmation_close=1_060_000, symbol="LABUSDT"):
    snap = lshape(breakout_ms=confirmation_close - 60_000, symbol=symbol)
    snap["pattern"] = "MIRROR"
    snap["mirror_entry"] = snap.pop("l_shape") | {
        "confirmation": {
            "close_time_ms": confirmation_close,
            "timeframe": "1",
            "kind": "ENGULFING",
        },
    }
    return snap


def test_lshape_must_finish_new_breakout_candle_before_it_is_eligible():
    assert proven_pattern_entry(lshape(), now_ms=1_059_999) is None
    proof = proven_pattern_entry(lshape(), now_ms=1_060_000)
    assert proof.direction == "LONG"
    assert proof.confirmed_at_ms == 1_060_000
    assert proof.risk_reservation_usdt > Decimal("0")


def test_mirror_requires_next_completed_candle_of_correct_type():
    proof = proven_pattern_entry(mirror(), now_ms=1_060_000)
    assert proof.pattern == "MIRROR"
    assert proof.confirmed_at_ms == 1_060_000
    assert proven_pattern_entry(mirror(confirmation_close=1_060_000), now_ms=1_059_999) is None
    wrong = mirror()
    wrong["mirror_entry"]["confirmation"]["kind"] = "DOJI"
    assert proven_pattern_entry(wrong, now_ms=1_060_000) is None
    wrong = mirror()
    wrong["mirror_entry"]["confirmation"]["timeframe"] = "5"
    assert proven_pattern_entry(wrong, now_ms=1_060_000) is None


def test_ordinary_wedge_and_box_do_not_forge_stop_or_confirmation_proof():
    for name in ("Falling Wedge", "Rising Wedge", "IKIGAI_BOX"):
        snap = lshape()
        snap["pattern"] = name
        assert proven_pattern_entry(snap, now_ms=2_000_000) is None


def test_original_mirror_registers_new_campaign_without_any_risk_reset(prepared):
    store, _ = prepared
    with store.robot_admission_transaction():
        original = automatic_reentry_proposal(
            store, TradingAccountId("paper"), candidate_id="new-mirror",
            symbol=Symbol("TESTUSDT"),
            snapshot=mirror(symbol="TESTUSDT"), now_ms=1_060_000,
        )
    assert original.previous_stop_exec_id is None
    assert original.original_risk_budget_usdt == original.reserved_risk_usdt * 3


def test_existing_mirror_stopped_campaign_can_accept_fresh_lshape(prepared):
    store, path = prepared
    store._connection.execute(
        "UPDATE robot_candidates SET approved_at_ms=100000, updated_at_ms=100000 WHERE candidate_id='second'"
    )
    new_signal = lshape(breakout_ms=59_000)
    with store.robot_admission_transaction():
        plan = automatic_reentry_proposal(
            store, TradingAccountId("paper"), candidate_id="second",
            symbol=Symbol("LABUSDT"), snapshot=new_signal, now_ms=120_000,
        )
        assert plan.previous_stop_exec_id == "stop-exec-1"
        assert plan.confirmed_at_ms == 119_000


def test_paper_auto_mirror_opt_in_creates_real_candidate_and_diary_link_atomically(
    tmp_path, monkeypatch,
):
    from robot_candidate_store import create_signal_snapshot
    from terminal.application.robot_autopilot_shadow import (
        SOURCE_SCANNER, admit_arrived_auto_candidate,
    )
    from terminal.persistence.sqlite_store import SQLiteStore

    monkeypatch.setenv("BYBITSCANNER_STOP_REENTRY_AUTO", "1")
    monkeypatch.setenv("BYBITSCANNER_MIRROR_STANDALONE_ROBOT", "1")
    db_path = tmp_path / "paper.sqlite3"
    directory = tmp_path / "candidates"
    account = TradingAccountId("paper")
    with SQLiteStore.open(db_path) as store:
        store.initialize_paper_account(account, Decimal("5000"), updated_at_ms=1)
        robot = store.initialize_robot_runtime_state(account, updated_at_ms=1000)
        store.update_robot_runtime_state(
            account, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=robot.version, updated_at_ms=1001,
        )
        ap = store.initialize_robot_autopilot_state(account, updated_at_ms=1000)
        store.update_robot_autopilot_state(
            account, mode="PAPER_AUTO", expected_version=ap.version,
            updated_at_ms=1001,
        )
        create_signal_snapshot(
            mirror(), timeframe="1", store_dir=directory,
            candidate_id="mirror-auto-initial",
            created_at="2026-10-29T12:00:00+00:00",
        )
        admitted = admit_arrived_auto_candidate(
            store, account, source=SOURCE_SCANNER,
            candidate_ref="mirror-auto-initial",
            protection_healthy=lambda: True,
            candidate_fresh=lambda *_: True,
            candidate_store_dir=directory,
            clock_ms=lambda: 1_200_000,
            daily_loss_gate_enabled=False,
        )
        assert admitted is not None
        assert admitted.result.outcome == "ALLOW", admitted.result
        assert admitted.candidate.candidate_id == "mirror-auto-initial"
        assert store._connection.execute(
            "SELECT COUNT(*) FROM robot_reentry_campaigns"
        ).fetchone()[0] == 1
        assert store._connection.execute(
            "SELECT COUNT(*) FROM robot_reentry_attempts"
        ).fetchone()[0] == 1
        assert store._connection.execute(
            "SELECT COUNT(*) FROM robot_trades"
        ).fetchone()[0] == 0  # Admission does NOT place or fill an order


def test_actual_paper_auto_stop_then_fresh_lshape_reserves_second_attempt(
    prepared, tmp_path, monkeypatch,
):
    """The old trade has a real canonical STOP; no order is issued by admission."""
    from robot_candidate_store import create_signal_snapshot
    from terminal.application.robot_autopilot_shadow import (
        SOURCE_SCANNER, admit_arrived_auto_candidate,
    )
    account = TradingAccountId("paper")
    store, path = prepared
    # The simple STOP fixture prepared a waiting candidate for store-level tests;
    # this end-to-end test admits it through the actual Scanner handoff instead.
    store._connection.execute("DELETE FROM robot_candidates WHERE candidate_id='second'")
    # Portfolio Admission requires exact reconstructed position lots. The
    # STOP-level fixture has only an exit fill; add its real earlier entry
    # counterpart so the canonical collector proves net FLAT (10 - 10 = 0).
    store._connection.execute(
        """INSERT INTO executions (
           trading_account_id,category,exec_id,order_id,symbol,side,
           price,quantity,fee,exchange_timestamp_ms)
           VALUES ('paper','linear','entry-exec-1','entry-order-1',
                   'LABUSDT','Buy','1','10','0.1',200)"""
    )
    store.initialize_paper_account(account, Decimal("5000"), updated_at_ms=10)
    ap = store.initialize_robot_autopilot_state(account, updated_at_ms=10)
    store.update_robot_autopilot_state(
        account, mode="PAPER_AUTO", expected_version=ap.version,
        updated_at_ms=11,
    )
    monkeypatch.setenv("BYBITSCANNER_STOP_REENTRY_AUTO", "1")
    monkeypatch.setenv("BYBITSCANNER_MIRROR_STANDALONE_ROBOT", "1")
    directory = tmp_path / "candidates"
    create_signal_snapshot(
        lshape(breakout_ms=59_000), timeframe="1", store_dir=directory,
        candidate_id="second", created_at="2026-10-29T12:00:00+00:00",
    )
    admission = admit_arrived_auto_candidate(
        store, account, source=SOURCE_SCANNER, candidate_ref="second",
        protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
        candidate_store_dir=directory, clock_ms=lambda: 120_000,
        daily_loss_gate_enabled=False,
    )
    assert admission is not None
    assert admission.result.outcome == "ALLOW", admission.result
    assert admission.candidate_created
    rows = store._connection.execute(
        "SELECT attempt_index, candidate_id, previous_stop_exec_id "
        "FROM robot_reentry_attempts ORDER BY attempt_index"
    ).fetchall()
    assert [(row[0], row[1], row[2]) for row in rows] == [
        (1, "first", None), (2, "second", "stop-exec-1")
    ]
    assert store._connection.execute(
        "SELECT COUNT(*) FROM robot_trades"
    ).fetchone()[0] == 1  # No new position added before independent LIMIT fill
