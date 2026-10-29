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


def wedge(*, close_open_ms=1_020_000, direction="LONG"):
    from scanner_geometry_cursor import CURSOR_VERSION

    pattern = "Falling Wedge" if direction == "LONG" else "Rising Wedge"
    return {
        "symbol": "LABUSDT", "pattern": pattern,
        "geometry": {
            "current_index": 10, "apex": {"index": 30},
            "upper_line": {"slope": -0.1, "intercept": 20},
            "lower_line": {"slope": 0.1, "intercept": 10},
        },
        "scanner_geometry_cursor": {
            "version": CURSOR_VERSION, "timeframe": "1",
            "geometry_index": 10, "source_candle_time_ms": close_open_ms,
        },
    }


def test_wedge_1m_uses_real_frozen_candle_cursor_and_own_robot_geometry():
    assert proven_pattern_entry(wedge(), now_ms=1_079_999) is None
    valid = proven_pattern_entry(wedge(), now_ms=1_080_000)
    assert valid is not None
    assert valid.pattern == "Falling Wedge"
    assert valid.direction == "LONG"
    assert valid.confirmed_at_ms == 1_080_000
    assert proven_pattern_entry(wedge(direction="SHORT"), now_ms=1_080_000).direction == "SHORT"


def test_wedge_cursor_must_not_be_guessed_from_candle_age_or_candidate_arrival():
    assert proven_pattern_entry({"pattern": "Falling Wedge"}, now_ms=10**15) is None
    snap = wedge()
    snap["scanner_geometry_cursor"]["geometry_index"] = 9
    assert proven_pattern_entry(snap, now_ms=1_200_000) is None
    snap = wedge()
    snap["scanner_geometry_cursor"]["timeframe"] = "5"
    assert proven_pattern_entry(snap, now_ms=1_200_000) is None
    snap = wedge()
    snap["geometry"]["apex"]["valid_intersection"] = False
    assert proven_pattern_entry(snap, now_ms=1_200_000) is None


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
    parent = store.get_robot_candidate("first")
    new_signal = lshape(breakout_ms=360_000)
    new_signal["reentry_parent"] = {
        "candidate_id": parent.candidate_id,
        "snapshot_sha256": parent.snapshot_sha256,
    }
    with store.robot_admission_transaction():
        plan = automatic_reentry_proposal(
            store, TradingAccountId("paper"), candidate_id="second",
            symbol=Symbol("LABUSDT"), snapshot=new_signal, now_ms=420_000,
        )
        assert plan.previous_stop_exec_id == "stop-exec-1"
        assert plan.confirmed_at_ms == 420_000


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


@pytest.mark.parametrize("structure_compatible", [True, False])
def test_actual_paper_auto_stop_then_fresh_lshape_reserves_second_attempt(
    prepared, tmp_path, monkeypatch, structure_compatible,
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
    parent = store.get_robot_candidate("first")
    # The integration fixture uses real 1m-scale chronology, unlike the
    # deliberately tiny millisecond counters in low-level storage tests.
    store._connection.execute(
        """UPDATE robot_trades SET signal_time_ms=120000,
           entry_time_ms=180000, exit_time_ms=300000, created_at_ms=180000,
           updated_at_ms=300100 WHERE trade_id='trade-1'"""
    )
    store._connection.execute(
        "UPDATE executions SET exchange_timestamp_ms=300000 WHERE exec_id='stop-exec-1'"
    )
    # Portfolio Admission requires exact reconstructed position lots. The
    # STOP-level fixture has only an exit fill; add its real earlier entry
    # counterpart so the canonical collector proves net FLAT (10 - 10 = 0).
    store._connection.execute(
        """INSERT INTO executions (
           trading_account_id,category,exec_id,order_id,symbol,side,
           price,quantity,fee,exchange_timestamp_ms)
           VALUES ('paper','linear','entry-exec-1','entry-order-1',
                   'LABUSDT','Buy','1','10','0.1',180000)"""
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
    fresh = lshape(breakout_ms=360_000)
    if not structure_compatible:
        # Correct symbol, direction, and post-STOP candle are NOT enough:
        # the new structure is 10x farther away than the previous thesis.
        fresh["l_shape"].update(
            reference="1000", target="1100",
            stop="990", structural_stop="990",
        )
    create_signal_snapshot(
        fresh, timeframe="1", store_dir=directory,
        candidate_id="second", created_at="2026-10-29T12:00:00+00:00",
    )
    admission = admit_arrived_auto_candidate(
        store, account, source=SOURCE_SCANNER, candidate_ref="second",
        protection_healthy=lambda: True, candidate_fresh=lambda *_: True,
        candidate_store_dir=directory, clock_ms=lambda: 480_000,
        daily_loss_gate_enabled=False,
    )
    assert admission is not None
    if not structure_compatible:
        assert admission.result.outcome == "WAIT", admission.result
        assert admission.result.reason_code == "REENTRY_THESIS_UNPROVEN"
        assert admission.candidate is None
        assert not admission.candidate_created
        assert store.get_robot_candidate("second") is None
        assert store._connection.execute(
            "SELECT COUNT(*) FROM robot_reentry_attempts"
        ).fetchone()[0] == 1
        return
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


def box(*, decision_ms=300_000):
    """Frozen Box plan economics are not a fixed Robot 250-USDT RO."""
    return {
        "pattern": "IKIGAI_BOX", "contract_version": 1,
        "environment": "PAPER", "execution_authorized": False, "attempt": 1,
        "identity": {"symbol": "LABUSDT", "timeframe": "5", "direction": "LONG"},
        "decision_time_ms": decision_ms,
        "plan": {
            "direction": "LONG",
            "full_position": {
                "quantity": "8", "average_entry": "92.8", "net_stop_loss": "25.6",
            },
            "partial_fill_loss_upper_bound": "25.6",
            "minimum_partial_fill_rr": "1.18",
        },
    }


def test_box_uses_frozen_grid_worst_loss_not_small_nonbox_budget():
    snap = box()
    assert proven_pattern_entry(snap, now_ms=599_999) is None
    evidence = proven_pattern_entry(snap, now_ms=600_000)
    assert evidence.pattern == "IKIGAI_BOX"
    assert evidence.direction == "LONG"
    assert evidence.confirmed_at_ms == 600_000
    assert evidence.risk_reservation_usdt == (
        Decimal("25.6") + Decimal("8") * Decimal("92.8") * Decimal("0.002")
    )
    corrupt = box()
    corrupt["plan"]["partial_fill_loss_upper_bound"] = "-1"
    assert proven_pattern_entry(corrupt, now_ms=600_000) is None
    corrupt = box()
    corrupt["environment"] = "LIVE"
    assert proven_pattern_entry(corrupt, now_ms=600_000) is None
    corrupt = box()
    corrupt["decision_time_ms"] += 1
    assert proven_pattern_entry(corrupt, now_ms=600_000) is None


def test_5m_wedge_reuses_proven_affine_1m_handoff_geometry():
    from scanner_geometry_cursor import project_frozen_geometry_to_robot_1m

    snap = wedge()
    source_geometry = snap["geometry"]
    snap["scanner_source_timeframe"] = "5"
    snap["robot_handoff_ready"] = True
    snap["robot_geometry"] = project_frozen_geometry_to_robot_1m(
        source_geometry, source_timeframe="5",
    )
    assert proven_pattern_entry(snap, now_ms=1_079_999) is None
    qualified = proven_pattern_entry(snap, now_ms=1_080_000)
    assert qualified is not None
    assert qualified.direction == "LONG"
    assert qualified.confirmed_at_ms == 1_080_000
    broken = dict(snap)
    broken["robot_geometry"] = dict(snap["robot_geometry"])
    broken["robot_geometry"]["scanner_source_timeframe"] = "1"
    assert proven_pattern_entry(broken, now_ms=1_080_000) is None
    broken = dict(snap)
    broken.pop("robot_geometry")
    assert proven_pattern_entry(broken, now_ms=1_080_000) is None


def test_optin_dispatch_never_silently_falls_back_to_old_untracked_admission(
    prepared, monkeypatch,
):
    from terminal.application.robot_autopilot_shadow import (
        _auto_reentry_proposal_for_candidate, _Candidate, SOURCE_SCANNER,
    )
    from terminal.persistence.sqlite_store import PersistenceError

    store, _ = prepared
    monkeypatch.setenv("BYBITSCANNER_STOP_REENTRY_AUTO", "1")
    candidate = _Candidate(
        ref="unproven", pattern="Falling Wedge", symbol=Symbol("LABUSDT"),
        timeframe="1", source_identity="unproven:hash", snapshot_sha256=None,
        valid=True, executable=True, invalidated=False, already_admitted=False,
        own_ids=frozenset({"unproven"}),
        snapshot={"symbol": "LABUSDT", "pattern": "Falling Wedge"},
    )
    with pytest.raises(PersistenceError, match="no verified"):
        with store.robot_admission_transaction():
            _auto_reentry_proposal_for_candidate(
                store, TradingAccountId("paper"), source=SOURCE_SCANNER,
                candidate=candidate, now_ms=1_200_000,
            )
