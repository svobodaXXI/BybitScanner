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


def replay_research_mirror_level(
    level: MirrorLevel, closed_candles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Read-only historical boundary observation for a local Simulator caller.

    Reuses the native MIRROR tracker and source/direction gates. The caller
    supplies a previously confirmed native level and complete CLOSED candles
    starting at its first usable candle; this does not detect patterns,
    assign Scanner candidate eligibility, authorize trades or submit orders.
    Missing initial coverage, gaps and incomplete candles fail closed.
    """
    from mirror_levels.levels import (
        mirror_breakout_allowed, mirror_level_allowed, timeframe_ms,
    )

    if not mirror_level_allowed(level):
        return {"level_id": getattr(level, "level_id", None),
                "status": "SOURCE_POLICY_REJECTED", "breakout": None,
                "first_retest": None, "observation_only": True}
    if not isinstance(closed_candles, Sequence) or not closed_candles:
        raise ValueError("MIRROR research requires closed candle history")
    step = timeframe_ms(level.timeframe)
    cursor = None
    record = new_record(level)
    for row in closed_candles:
        if not isinstance(row, Mapping) or row.get("closed") is not True:
            raise ValueError("MIRROR research requires authoritative closed candles")
        opened, closed = row.get("open_time_ms"), row.get("close_time_ms")
        if (type(opened) is not int or type(closed) is not int
                or opened < 0 or opened % step != 0 or closed - opened != step):
            raise ValueError("MIRROR research requires aligned native-timeframe candles")
        if cursor is None:
            if opened < level.confirmed_at_ms or opened - level.confirmed_at_ms >= step:
                raise ValueError("MIRROR research missing first usable candle")
        elif opened != cursor:
            raise ValueError("MIRROR research candle gap or overlap")
        record = track(level, (row,), record=record)
        if record["status"] == STATUS_DATA_BLOCKED:
            raise ValueError("MIRROR research history gap")
        cursor = closed
    breakout = record["naked_retest"].get("breakout")
    if breakout is not None and not mirror_breakout_allowed(level, breakout):
        return {"level_id": level.level_id, "status": "BREAKOUT_POLICY_REJECTED",
                "breakout": None, "first_retest": None, "observation_only": True}
    return {
        "level_id": level.level_id, "status": record["status"],
        "breakout": breakout,
        "first_retest": record["naked_retest"].get("retest"),
        "observation_only": True,
    }


def replay_local_simulation_mirror(
    *, simulation_run_id: str, symbol: str, level: MirrorLevel,
    closed_bars: Sequence[Any],
) -> dict[str, Any]:
    """Native Mirror observation on the existing local Simulator's closed Candles.

    Accepts its verified closed-M5/M1 Candle value objects, not arbitrary OHLC
    snapshots or prefilled Robot candidates. The caller must obtain the bars
    from an independently verified, committed SIMULATION history feed.
    No order, sizing, position or PAPER/Robot runtime is accessed here.
    """
    from research.historical_market_replay import Candle
    from research.simulator_v2.timeline import RUN_ID_RE, SYMBOL_RE
    from mirror_levels.levels import timeframe_ms

    if (not isinstance(simulation_run_id, str)
            or RUN_ID_RE.fullmatch(simulation_run_id) is None
            or not isinstance(symbol, str) or SYMBOL_RE.fullmatch(symbol) is None
            or not symbol.endswith("USDT") or level.symbol != symbol):
        raise ValueError("MIRROR SIMULATION identity mismatch")
    if not isinstance(closed_bars, (tuple, list)) or not closed_bars:
        raise ValueError("MIRROR SIMULATION requires committed closed bars")
    step = timeframe_ms(level.timeframe)
    if any(type(bar) is not Candle or bar.interval_ms != step for bar in closed_bars):
        raise ValueError("MIRROR SIMULATION requires native closed timeframe Candles")
    rows = tuple({
        "open_time_ms": bar.start_ms, "close_time_ms": bar.end_ms,
        "open": float(bar.open), "high": float(bar.high),
        "low": float(bar.low), "close": float(bar.close), "closed": True,
    } for bar in closed_bars)
    observed = replay_research_mirror_level(level, rows)
    return {
        "namespace": "SIMULATION", "simulation_run_id": simulation_run_id,
        "symbol": symbol, **observed,
    }
