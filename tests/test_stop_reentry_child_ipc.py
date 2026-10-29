"""A real spawned Scanner L-shape relays an immutable post-STOP signal over IPC.

Exercises the existing multiprocessing scanner_process pipe. Canonical
STOP/protection/trade evidence stays in the parent PAPER DB; the child
cannot write to that DB or issue orders. The separate protected matcher
E2E covers LIMIT/STOP/TAKE and Diary restart.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pandas as pd

import tests.test_telegram_delivery  # offline Scanner config, also in child
from terminal.application.robot_reentry_adapter import automatic_reentry_proposal
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.scanner_process import run_scan_pass_in_child_process
from tests.test_l_shape_detector import _long_shape, STEP_MS
from tests.test_stop_reentry_reservation import prepared

SYMBOL = "LABUSDT"
ACCOUNT = TradingAccountId("paper")


def _child_scan_lshape(*, box_plan_preparer=None, control_checkpoint=None,
                       robot_candidate_observer=None, progress_observer=None):
    import tests.test_telegram_delivery
    import l_shape_scanner
    import robot_candidate_store
    from pattern_robot_integration import (
        prepare_robot_handoff, robot_candidate_observer as observing,
    )

    robot_candidate_store.DEFAULT_STORE_DIR = Path(os.environ["REENTRY_CHILD_CANDIDATES"])
    symbol = os.environ.get("REENTRY_CHILD_SYMBOL", SYMBOL)
    closed = _long_shape()
    if "REENTRY_CHILD_BREAKOUT" in os.environ:
        breakout_open = int(os.environ["REENTRY_CHILD_BREAKOUT"])
        closed["time"] = [
            breakout_open - STEP_MS * (len(closed) - 1 - i)
            for i in range(len(closed))
        ]
    open_bar = closed.iloc[-1:].copy()
    open_bar["time"] += STEP_MS
    open_bar[["open", "high", "low", "close"]] = 9999.0
    observation = l_shape_scanner.observe_l_shape(
        symbol, pd.concat([closed, open_bar], ignore_index=True),
        timeframe="5", chart_dir=os.environ["REENTRY_CHILD_CHARTS"],
    )
    if observation is None:
        raise AssertionError("no fresh confirmed Scanner L-shape")
    with observing(robot_candidate_observer):
        result = prepare_robot_handoff(
            l_shape_scanner._robot_signal_snapshot(symbol, "5", observation),
            timeframe="5", enabled=True,
        )
    if not result.candidate_id:
        raise AssertionError("child failed to persist L-shape candidate")
    if progress_observer is not None:
        progress_observer({"symbols_done": 1, "symbols_total": 1, "symbol": SYMBOL})


def test_spawned_lshape_scanner_pipe_then_canonical_post_stop_lineage(prepared, tmp_path):
    import robot_candidate_store

    store, _ = prepared
    candidates = tmp_path / "candidates"
    delivered = []

    def parent_backend_observer(candidate_id):
        # The real backend pipe hands a persisted candidate ID to the parent.
        # Admission and all durable STOP evidence remain in its PAPER SQLite.
        envelope = robot_candidate_store.load_candidate(candidate_id, store_dir=candidates)
        with store.robot_admission_transaction():
            proposal = automatic_reentry_proposal(
                store, ACCOUNT, candidate_id=candidate_id,
                symbol=Symbol(SYMBOL),
                snapshot=envelope["signal_snapshot"],
                now_ms=int(envelope["signal_snapshot"]["l_shape"]["breakout_time_ms"]) + STEP_MS,
            )
        delivered.append((candidate_id, proposal))

    with mock.patch.dict(os.environ, {
        "REENTRY_CHILD_CANDIDATES": str(candidates),
        "REENTRY_CHILD_CHARTS": str(tmp_path / "charts"),
    }):
        run_scan_pass_in_child_process(
            target="tests.test_stop_reentry_child_ipc:_child_scan_lshape",
            robot_candidate_observer=parent_backend_observer,
        )

    assert len(delivered) == 1
    candidate_id, proposal = delivered[0]
    assert candidate_id
    assert proposal is not None
    assert proposal.previous_stop_exec_id == "stop-exec-1"
    assert proposal.strategy_confirmation_proven is True
