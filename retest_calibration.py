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
    PHASE_RETEST_PROVEN,
    TERMINAL_PHASES,
    Boundary,
    atr_tolerance,
    initialize_state,
    process_closed_candle,
    retest_contact,
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


REF_TOUCH = "TOUCH"
REF_NO_TOUCH = "NO_TOUCH"
REF_AMBIGUOUS = "AMBIGUOUS"
REF_DATA_GAP = "DATA_GAP"

LABEL_TP = "TP"
LABEL_FP_LATE = "FP_LATE"
LABEL_UNLABELED_NEAR_MISS = "UNLABELED_NEAR_MISS"
LABEL_FN = "FN"
LABEL_TN = "TN"
LABEL_EXCLUDED = "EXCLUDED"


def reference_touch(
    boundary: Boundary,
    breakout_direction: str,
    breakout_close_time_ms: int,
    fine_candles: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Physical-touch reference from finer closed candles (e.g. 1m under 5m).

    Exact contact only (zero tolerance), first proven contact after the coarse
    breakout candle closed. It measures whether price reached the line; it is
    NOT an owner judgement of which near-misses count as a retest.
    """

    previous_close = None
    for candle in fine_candles:
        if candle["open_time_ms"] < breakout_close_time_ms:
            continue
        if previous_close is not None and candle["open_time_ms"] > previous_close + 1:
            return {"status": REF_DATA_GAP, "touch_close_time_ms": None}
        previous_close = candle["close_time_ms"]
        contact = retest_contact(boundary, breakout_direction, candle, 0.0)
        if contact == "PROVEN":
            return {"status": REF_TOUCH, "touch_open_time_ms": candle["open_time_ms"],
                    "touch_close_time_ms": candle["close_time_ms"]}
        if contact == "AMBIGUOUS":
            return {"status": REF_AMBIGUOUS, "touch_close_time_ms": None}
    return {"status": REF_NO_TOUCH, "touch_close_time_ms": None}


def label_detection(outcome: Mapping[str, Any], reference: Mapping[str, Any],
                    coarse_ms: int) -> tuple[str, int | None]:
    """Compare one coarse detection with the fine physical-touch reference.

    Returns ``(label, delay_ms)``; delay = detection close - reference touch
    close (negative: detected before price physically reached the line).
    An earlier detection, or one without any reference touch, is a near-miss
    detection whose correctness needs an independent owner label.
    """

    if reference["status"] in (REF_AMBIGUOUS, REF_DATA_GAP) or outcome["outcome"] in (
        OUTCOME_ATR_UNAVAILABLE, OUTCOME_DATA_GAP
    ):
        return LABEL_EXCLUDED, None
    detected = outcome["outcome"] == PHASE_RETEST_PROVEN
    touched = reference["status"] == REF_TOUCH
    if not detected:
        return (LABEL_FN if touched else LABEL_TN), None
    if not touched:
        return LABEL_UNLABELED_NEAR_MISS, None
    detection_close = outcome["retest_close_time_ms"]
    delay = detection_close - reference["touch_close_time_ms"]
    detection_open = detection_close - coarse_ms
    if reference["touch_open_time_ms"] >= detection_open and reference["touch_close_time_ms"] <= detection_close:
        return LABEL_TP, delay
    return (LABEL_UNLABELED_NEAR_MISS if delay < 0 else LABEL_FP_LATE), delay


def summarize_labels(labels: Sequence[tuple[str, int | None]]) -> dict[str, Any]:
    """Counts, precision bounds (near-miss as FP / as TP), touch recall, delays."""

    counts = {name: 0 for name in (LABEL_TP, LABEL_FP_LATE, LABEL_UNLABELED_NEAR_MISS,
                                   LABEL_FN, LABEL_TN, LABEL_EXCLUDED)}
    delays = []
    early_with_touch = 0
    for label, delay in labels:
        counts[label] += 1
        if delay is not None:
            delays.append(delay)
            if label == LABEL_UNLABELED_NEAR_MISS:
                early_with_touch += 1
    tp, late, near = counts[LABEL_TP], counts[LABEL_FP_LATE], counts[LABEL_UNLABELED_NEAR_MISS]
    detections = tp + late + near
    touches = tp + late + early_with_touch + counts[LABEL_FN]
    delays.sort()
    return {
        **counts,
        "detections": detections,
        "precision_lower": tp / detections if detections else None,
        "precision_upper": (tp + near) / detections if detections else None,
        "touch_recall": (tp + early_with_touch) / touches if touches else None,
        "median_delay_ms": delays[len(delays) // 2] if delays else None,
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
