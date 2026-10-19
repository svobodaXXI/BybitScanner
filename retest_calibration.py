"""Offline walk-forward harness for the H-016 retest ATR zone (MIRROR RETEST-3).

Owner decision: the ATR period and tolerance coefficient are chosen by
historical trials without look-ahead. This module only provides the trial
mechanics; it ships no candidate grid, no objective and no chosen values.

- ATR is the existing project ATR (``confirmation.calculate_atr``), a
  trailing rolling mean: the value at candle i reads candles <= i only, and the
  retest test for candle i runs after that candle has closed.
- A case is one frozen boundary with its own chronological closed candles
  (warm-up history before ``as_of`` is allowed and feeds only the ATR).
- ``walk_forward_select`` scores every caller candidate on cases that closed
  completely before ``split_time_ms``, picks the best by the caller objective,
  and only then evaluates that single choice on cases that open at/after the
  split. Cases straddling the split are excluded and reported.

Read-only and offline: no market data transport, no Scanner/Robot wiring.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

import pandas as pd

from confirmation import calculate_atr
from geometry.naked_retest import (
    EVENT_DATA_GAP,
    PHASE_CAMPAIGN_ACTIVE,
    TERMINAL_PHASES,
    Boundary,
    atr_tolerance,
    initialize_state,
    process_closed_candle,
)


OUTCOME_ATR_UNAVAILABLE = "ATR_UNAVAILABLE"
OUTCOME_DATA_GAP = "DATA_GAP"


class RetestCalibrationError(ValueError):
    """Raised when a case, candidate or objective result cannot be trusted."""


@dataclass(frozen=True)
class CalibrationCase:
    boundary: Boundary
    candles: tuple[Mapping[str, Any], ...]


@dataclass(frozen=True)
class Candidate:
    atr_period: int
    multiplier: float

    def __post_init__(self) -> None:
        if isinstance(self.atr_period, bool) or not isinstance(self.atr_period, int) or self.atr_period < 1:
            raise RetestCalibrationError("atr_period must be a positive integer")
        atr_tolerance(1.0, self.multiplier)  # validates the coefficient


def causal_atr_series(candles: Sequence[Mapping[str, Any]], period: int) -> list[float | None]:
    """Project ATR per candle; None where history is still too short."""

    frame = pd.DataFrame({key: [float(c[key]) for c in candles] for key in ("high", "low", "close")})
    values = calculate_atr(frame, period=period) if len(frame) else []
    return [None if value is None or not math.isfinite(float(value)) else float(value)
            for value in values]


def evaluate_case(case: CalibrationCase, candidate: Candidate) -> dict[str, Any]:
    """Run one boundary with ``multiplier * ATR(period)`` as the retest zone."""

    atr = causal_atr_series(case.candles, candidate.atr_period)
    state, _ = initialize_state(case.boundary)
    outcome = None
    for index, candle in enumerate(case.candles):
        tolerance = 0.0
        if state["phase"] == PHASE_CAMPAIGN_ACTIVE:
            if atr[index] is None:
                outcome = OUTCOME_ATR_UNAVAILABLE
                break
            tolerance = atr_tolerance(atr[index], candidate.multiplier)
        state, event = process_closed_candle(case.boundary, state, candle, retest_tolerance=tolerance)
        if event == EVENT_DATA_GAP:
            outcome = OUTCOME_DATA_GAP
            break
        if state["phase"] in TERMINAL_PHASES:
            break
    breakout = state["breakout"] or {}
    retest = state["retest"] or {}
    return {
        "boundary_id": case.boundary.boundary_id,
        "candidate": candidate,
        "outcome": outcome or state["phase"],
        "breakout_direction": breakout.get("direction"),
        "breakout_close_time_ms": breakout.get("close_time_ms"),
        "retest_close_time_ms": retest.get("close_time_ms"),
        "retest_tolerance": retest.get("tolerance"),
    }


def _span(case: CalibrationCase) -> tuple[int, int]:
    if not case.candles:
        raise RetestCalibrationError(f"case {case.boundary.boundary_id!r} has no candles")
    return case.candles[0]["open_time_ms"], case.candles[-1]["close_time_ms"]


def walk_forward_select(
    cases: Sequence[CalibrationCase],
    candidates: Sequence[Candidate],
    *,
    split_time_ms: int,
    objective: Callable[[list[dict[str, Any]]], float],
) -> dict[str, Any]:
    """Choose a candidate on pre-split cases only; report it on post-split cases.

    Ties keep the earliest candidate in caller order (deterministic). A
    non-finite objective score disqualifies that candidate.
    """

    if not candidates:
        raise RetestCalibrationError("at least one candidate is required")
    train, test, straddling = [], [], []
    for case in cases:
        start, end = _span(case)
        if end <= split_time_ms:
            train.append(case)
        elif start >= split_time_ms:
            test.append(case)
        else:
            straddling.append(case.boundary.boundary_id)
    if not train:
        raise RetestCalibrationError("no case closes before the split")

    scores: dict[Candidate, float | None] = {}
    best = None
    for candidate in candidates:
        score = float(objective([evaluate_case(case, candidate) for case in train]))
        scores[candidate] = score if math.isfinite(score) else None
        if scores[candidate] is not None and (best is None or score > scores[best]):
            best = candidate
    if best is None:
        raise RetestCalibrationError("no candidate produced a finite objective score")
    return {
        "selected": best,
        "train_scores": scores,
        "train_boundary_ids": [case.boundary.boundary_id for case in train],
        "test_outcomes": [evaluate_case(case, best) for case in test],
        "excluded_straddling": straddling,
    }
