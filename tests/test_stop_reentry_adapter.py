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
