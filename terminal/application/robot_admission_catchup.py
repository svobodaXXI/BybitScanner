"""Pure admission catch-up orchestration for Robot v0.1.

This module does not load candles or submit orders.  It replays already-validated
closed 1m evidence through the existing Robot state machine and adds the single
durable execution marker needed to distinguish a retest discovered during
late admission from a retest observed by the ordinary live monitor path.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

import robot_state_machine


LATE_ADMISSION_MARKET = "LATE_ADMISSION_MARKET"


def replay_admission_catchup(
    signal_snapshot: Mapping[str, Any],
    initial_state: Mapping[str, Any],
    candles: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Replay missed closed candles and mark only replay-discovered retests.

    Geometry and phase semantics remain owned by ``robot_state_machine``.  The
    marker is added only when THIS replay observes ``EVENT_RETEST`` and ends in
    ``RETEST_DETECTED``; ordinary realtime retests therefore keep the existing
    LIMIT entry path.  Existing execution diagnostics are preserved.
    """

    new_state, events = robot_state_machine.replay_closed_candles(
        signal_snapshot,
        initial_state,
        candles,
    )
    if (
        robot_state_machine.EVENT_RETEST in events
        and new_state.get("phase") == robot_state_machine.PHASE_RETEST_DETECTED
    ):
        execution = dict(new_state.get("execution") or {})
        execution["entry_mode"] = LATE_ADMISSION_MARKET
        new_state = dict(new_state)
        new_state["execution"] = execution
    return new_state, events
