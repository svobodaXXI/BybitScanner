"""Real Scanner L-shape recognition after a proven STOP, no guessed signal.

This complements tests/test_stop_reentry_paper_e2e.py (real order matcher):
an independently detected *latest closed* L-shape produces the same
immutable risk/lineage proposal in canonical Robot admission. No fake
L-shape scanner or hand-typed strategy geometry is used here.
"""
from __future__ import annotations

import pandas as pd

# Reuse the project's existing offline Scanner/Telegram test stubs, including
# the intentionally absent production-only config.py. Do not invent config.
import tests.test_telegram_delivery
import l_shape_scanner
from terminal.application.robot_reentry_adapter import automatic_reentry_proposal
from terminal.domain.models import Symbol, TradingAccountId
from tests.test_l_shape_detector import STEP_MS, _long_shape
from tests.test_stop_reentry_reservation import prepared


def _snapshot_from_closed(closed):
    # Bybit Scanner returns one newest potentially still-open candle.
    current = closed.iloc[-1:].copy()
    current["time"] += STEP_MS
    current[["open", "high", "low", "close"]] = 9999.0
    return pd.concat([closed, current], ignore_index=True)


def test_real_lshape_detector_signal_qualifies_as_new_stop_attempt(prepared, tmp_path):
    store, _ = prepared
    closed = _long_shape()
    observation = l_shape_scanner.observe_l_shape(
        "LABUSDT", _snapshot_from_closed(closed),
        timeframe="5", chart_dir=tmp_path,
    )
    assert observation is not None
    assert observation["source_candle_time_ms"] == int(closed.time.iloc[-1])
    snapshot = l_shape_scanner._robot_signal_snapshot("LABUSDT", "5", observation)
    assert snapshot["pattern"] == "L-shape"
    assert snapshot["robot_handoff_ready"] is True
    end_ms = int(closed.time.iloc[-1]) + STEP_MS

    with store.robot_admission_transaction():
        proposal = automatic_reentry_proposal(
            store, TradingAccountId("paper"), candidate_id="second",
            symbol=Symbol("LABUSDT"), snapshot=snapshot, now_ms=end_ms,
        )
    assert proposal is not None
    assert proposal.previous_stop_exec_id == "stop-exec-1"
    assert proposal.confirmed_at_ms == end_ms
    assert proposal.strategy_confirmation_proven is True


def test_old_lshape_breakout_is_not_a_new_signal_after_another_closed_bar(
    prepared, tmp_path,
):
    closed = _long_shape()
    next_candle = closed.iloc[-1:].copy()
    next_candle["time"] += STEP_MS
    next_candle[["open", "high", "low", "close"]] = 107.0
    history = pd.concat([closed, next_candle], ignore_index=True)
    observation = l_shape_scanner.observe_l_shape(
        "LABUSDT", _snapshot_from_closed(history),
        timeframe="5", chart_dir=tmp_path,
    )
    assert observation is None
