"""
mirror_levels.tracker

Fresh untested mirror levels and their first retest, per ``MirrorLevel``.

The transition itself is ``geometry.naked_retest.process_closed_candle`` (strict
naked breakout, first proven contact terminal, stale/gap handling) with the
optional 5m->1m ``retest_calibration.fine_resolver``. This module adds only the
observation record around it:

- ``status``: ``WAITING_BREAKOUT`` / ``BROKEN_UNTESTED`` / ``RETESTED`` /
  ``RETEST_UNPROVEN`` (or ``DATA_BLOCKED``) -- the #613 vocabulary over the
  existing phases;
- ``breakout_evidence``: ``mirror_levels.breakout.classify_crossing`` of the
  breakout candle;
- ``imbalance``: FVGs whose displacement window contains the breakout candle,
  with the level's position ``inside`` / ``edge`` / ``outside`` the gap. An FVG is
  a recorded quality factor only: a level without any gap is tracked the same way.

The whole record is JSON-serialisable; resuming from it with only new candles
gives the same result as one replay (restart equivalence).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from geometry.naked_retest import (
    EVENT_NAKED_BREAKOUT,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
    PHASE_RETEST_UNPROVEN,
    PHASE_WAITING_BREAKOUT,
    initialize_state,
    process_closed_candle,
)
from mirror_levels.breakout import classify_crossing
from mirror_levels.imbalance import FairValueGap
from mirror_levels.levels import MirrorLevel


STATUS_WAITING = "WAITING_BREAKOUT"
STATUS_UNTESTED = "BROKEN_UNTESTED"
STATUS_RETESTED = "RETESTED"
STATUS_UNPROVEN = "RETEST_UNPROVEN"
STATUS_DATA_BLOCKED = "DATA_BLOCKED"
_STATUS = {PHASE_WAITING_BREAKOUT: STATUS_WAITING, PHASE_CAMPAIGN_ACTIVE: STATUS_UNTESTED,
           PHASE_RETEST_PROVEN: STATUS_RETESTED, PHASE_RETEST_UNPROVEN: STATUS_UNPROVEN}


def level_position(level_price: float, gap: FairValueGap, *, edge_tolerance: float) -> str:
    if gap.bottom - edge_tolerance <= level_price <= gap.bottom + edge_tolerance or \
            gap.top - edge_tolerance <= level_price <= gap.top + edge_tolerance:
        return "edge"
    if gap.bottom < level_price < gap.top:
        return "inside"
    return "outside"


def new_record(level: MirrorLevel) -> dict[str, Any]:
    state, _ = initialize_state(level.boundary)
    return {"level_id": level.level_id, "naked_retest": state, "status": STATUS_WAITING,
            "breakout_evidence": None, "imbalance": [], "previous_close": None}


def track(level: MirrorLevel, candles: Sequence[Mapping], *, record: Mapping[str, Any] | None = None,
          retest_tolerance: float = 0.0, atr_at: Callable[[int], float | None] | None = None,
          gaps: Sequence[FairValueGap] = (), edge_tolerance: float = 0.0,
          ambiguity_resolver: Callable[[Mapping, float], str | None] | None = None,
          ) -> dict[str, Any]:
    """Advance one level over closed candles; ``atr_at(close_time_ms)`` must be causal."""

    out = dict(record) if record is not None else new_record(level)
    if out["level_id"] != level.level_id:
        raise ValueError("record belongs to another level")
    state = out["naked_retest"]
    previous_close = out.get("previous_close")
    for candle in candles:
        row = dict(candle, closed=True)
        resolver = ambiguity_resolver if state["phase"] == PHASE_CAMPAIGN_ACTIVE else None
        state, event = process_closed_candle(level.boundary, state, row,
                                             retest_tolerance=retest_tolerance,
                                             ambiguity_resolver=resolver)
        if event == EVENT_NAKED_BREAKOUT:
            atr = atr_at(int(row["close_time_ms"])) if atr_at is not None else None
            evidence = classify_crossing(level.boundary, row, atr=atr, previous_close=previous_close)
            out["breakout_evidence"] = None if evidence is None else dict(evidence.__dict__)
        breakout = state.get("breakout")
        if breakout is not None:
            # Link a gap only once it is known (candle 3 closed), never earlier.
            breakout_open = int(breakout["open_time_ms"])
            price = level.price_at(int(breakout["close_time_ms"]))
            linked = {item["fvg_id"] for item in out["imbalance"]}
            for gap in gaps:
                step = gap.middle_open_ms - gap.first_open_ms
                if (gap.fvg_id not in linked and gap.formed_at_ms <= int(row["close_time_ms"])
                        and gap.first_open_ms <= breakout_open <= gap.middle_open_ms + step):
                    out["imbalance"] = [*out["imbalance"], {
                        "fvg_id": gap.fvg_id, "direction": gap.direction, "bottom": gap.bottom,
                        "top": gap.top, "formed_at_ms": gap.formed_at_ms,
                        "position": level_position(price, gap, edge_tolerance=edge_tolerance)}]
        if state.get("cursor_close_time_ms") == int(row["close_time_ms"]):
            previous_close = float(row["close"])  # only a candle the state actually consumed
        if state.get("data_blocked"):
            break
    out["naked_retest"] = state
    out["previous_close"] = previous_close
    out["status"] = STATUS_DATA_BLOCKED if state.get("data_blocked") else _STATUS[state["phase"]]
    return out
