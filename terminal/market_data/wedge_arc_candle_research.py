"""Closed-OHLC / frozen-wedge arc confluence for Impulse Hunt research only.

Reuses existing Geometry bullish engulfing, Morning Star and smooth-arc
recognizers. Opposite-side versions are exact price mirrors of those rules.
No REST, L2 subscribe, order/STOP/TAKE, admission or runtime mutation.
Candles and frozen geometry are caller-provided *research* inputs; neither
their source completeness nor L2 absorption is certified here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Mapping

from geometry.reversal_patterns import (
    ARC_MAX_RUN, is_bullish_engulfing, is_morning_star, is_smooth_arc,
)
from robot_state_machine import (
    STATE_VERSION, RobotStateMachineError, boundary_price,
)
from scanner_geometry_cursor import (
    ScannerGeometryCursorError, project_latest_geometry_index,
)
from robot_entry_flow_evidence import CandidateBoundFlowEvidence, FlowTransition
from .wedge_candle_exhaustion_research import (
    ClosedCandlePatternObservation, WedgeCandleExhaustionResearch,
    observe_wedge_candle_exhaustion,
)

ONE_MINUTE_MS = 60_000


@dataclass(frozen=True, slots=True)
class WedgeArcCandleResearch:
    candidate_id: str
    state_revision: int
    symbol: str
    direction: str
    evaluated_at_ms: int
    outcome: str
    arc_shape_observed: bool
    near_frozen_edge: bool
    candle_patterns: tuple[str, ...]
    confluence: WedgeCandleExhaustionResearch | None
    # Exact native archive/WS receipt parity and immutable arc provenance
    # are separate prerequisites for any future trading proposal.
    source_complete: bool = False
    trading_authorized: bool = False
    tape_receipt_metadata_matched: bool = False


def _price(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("invalid OHLC value")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("invalid OHLC value") from exc
    if not isfinite(number) or number <= 0:
        raise ValueError("invalid OHLC price")
    return number


def _checked_candles(
    rows: tuple[Mapping[str, object], ...], *, decision_ms: int,
) -> tuple[list[dict[str, float]], int] | None:
    """Validate a bounded consecutive, finished M1 history; never add a live bar."""
    if not isinstance(rows, tuple) or not 4 <= len(rows) <= ARC_MAX_RUN + 3:
        return None
    checked: list[dict[str, float]] = []
    previous_time: int | None = None
    for row in rows:
        if not isinstance(row, Mapping):
            return None
        stamp = row.get("time")
        if (type(stamp) is not int or stamp <= 0 or stamp % ONE_MINUTE_MS
                or (previous_time is not None
                    and stamp - previous_time != ONE_MINUTE_MS)):
            return None
        try:
            o, h, l, c = (_price(row.get(k)) for k in ("open", "high", "low", "close"))
        except ValueError:
            return None
        if not l <= min(o, c) <= max(o, c) <= h:
            return None
        checked.append({"open": o, "high": h, "low": l, "close": c})
        previous_time = stamp
    assert previous_time is not None
    if previous_time + ONE_MINUTE_MS > decision_ms:
        return None
    return checked, previous_time


def _hammer_shape(current: Mapping[str, float]) -> bool:
    """One long-lower-shadow candle; direction requires preceding price context."""
    body = abs(current["close"] - current["open"])
    spread = current["high"] - current["low"]
    if body <= 0 or spread <= 0:
        return False
    lower = min(current["open"], current["close"]) - current["low"]
    upper = current["high"] - max(current["open"], current["close"])
    # Initial *research* anatomy only, not production/calibrated thresholds.
    return lower >= 2 * body and upper <= body


def _doji_shape(current: Mapping[str, float], limit: Decimal) -> bool:
    spread = current["high"] - current["low"]
    return (spread > 0
            and Decimal(str(abs(current["close"] - current["open"]))) /
            Decimal(str(spread)) <= limit)


def _mirror_rows(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    """Mirror OHLC around zero, so existing bullish recognizers are reused."""
    return [
        {
            "open": -row["open"], "high": -row["low"],
            "low": -row["high"], "close": -row["close"],
        }
        for row in rows
    ]


def observe_closed_wedge_arc_candles(
    record,
    closed_m1: tuple[Mapping[str, object], ...],
    flow: FlowTransition | None,
    *,
    decision_ms: int,
    atr: Decimal,
    max_boundary_distance_atr: Decimal,
    doji_body_fraction: Decimal,
    source_id: str,
) -> WedgeArcCandleResearch | None:
    """As-of M1 candlestick labels at a frozen final wedge arc (non-trading).

    Geometry and source timestamps are validated against original candidate
    and frozen Scanner cursor. A smooth turning arc + edge distance is
    required before candle observations can be joined to the flow observer.
    Numeric tolerances are explicit uncalibrated RESEARCH inputs.
    """
    if (type(decision_ms) is not int or decision_ms <= 0
            or not isinstance(source_id, str) or not source_id
            or not all(isinstance(v, Decimal) and v.is_finite()
                       for v in (atr, max_boundary_distance_atr, doji_body_fraction))
            or atr <= 0 or max_boundary_distance_atr <= 0
            or not Decimal("0") <= doji_body_fraction <= Decimal("0.5")):
        return None

    checked = _checked_candles(closed_m1, decision_ms=decision_ms)
    if checked is None:
        return None
    rows, last_stamp = checked

    try:
        snapshot, state = record.signal_snapshot, record.robot_state
        pattern = snapshot.get("pattern")
        direction = {"Falling Wedge": "LONG", "Rising Wedge": "SHORT"}.get(pattern)
        if (record.status != "APPROVED"
                or direction is None
                or state.get("phase") != "WAITING_BREAKOUT"
                or state.get("pattern") != pattern
                or state.get("direction") != direction
                or state.get("state_version") != STATE_VERSION):
            return None
        candidate_id, revision, symbol = (
            record.candidate_id, record.state_revision, record.symbol.value,
        )
        if (not isinstance(candidate_id, str) or not candidate_id
                or type(revision) is not int or revision < 0
                or not isinstance(symbol, str) or not symbol.endswith("USDT")):
            return None
        index = project_latest_geometry_index(
            snapshot, latest_closed_candle_time_ms=last_stamp,
        )
        if (type(state.get("geometry_cursor")) is not int
                or index != state["geometry_cursor"]):
            return None
        geometry = snapshot.get("robot_geometry", snapshot.get("geometry"))
        apex = geometry.get("apex")
        if (not isinstance(apex, Mapping)
                or not isfinite(float(apex.get("index")))
                or index >= float(apex["index"])):
            return None
        side = "lower" if direction == "LONG" else "upper"
        boundary = boundary_price(snapshot, side=side, geometry_index=index)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError,
            RobotStateMachineError, ScannerGeometryCursorError):
        return None

    # Reuse the existing Geometry helpers. For Rising Wedge the signed price
    # mirror yields the exact bearish analogues without altering Geometry.
    import pandas as pd
    mirror = direction == "SHORT"
    checked_rows = _mirror_rows(rows) if mirror else rows
    frame = pd.DataFrame(checked_rows)
    last = len(frame) - 1
    arc = is_smooth_arc(frame, last, atr_value=float(atr))
    extreme = rows[-1]["low"] if direction == "LONG" else rows[-1]["high"]
    near = (Decimal(str(abs(extreme - boundary))) <=
            atr * max_boundary_distance_atr)

    labels: list[str] = []
    confluence = None
    if arc and near:
        if is_bullish_engulfing(frame, last):
            labels.append("BEARISH_ENGULFING" if mirror else "BULLISH_ENGULFING")
        if is_morning_star(frame, last):
            labels.append("EVENING_STAR" if mirror else "MORNING_STAR")
        # Hanging Man is a long lower shadow AFTER a rise, not a
        # shooting-star / long upper-shadow candle.
        prior = rows[-2]
        if _hammer_shape(rows[-1]):
            if direction == "LONG" and prior["close"] < prior["open"]:
                labels.append("HAMMER")
            elif direction == "SHORT" and prior["close"] > prior["open"]:
                labels.append("HANGING_MAN")
        if _doji_shape(rows[-1], doji_body_fraction):
            labels.append("DOJI")

        # Same terminal candle == one underlying price-reversal event. Do not
        # count multiple candle names as independent support.
        event_group = f"PRICE_REVERSAL:{symbol}:{last_stamp}"
        observations = tuple(
            ClosedCandlePatternObservation(
                name=name, candidate_id=candidate_id, state_revision=revision,
                symbol=symbol, source_id=source_id,
                pattern_version="WEDGE_ARC_OHLC_RESEARCH_V1",
                event_group=event_group, closed_at_ms=last_stamp + ONE_MINUTE_MS,
                available_at_ms=last_stamp + ONE_MINUTE_MS,
            )
            for name in labels
        )
        confluence = observe_wedge_candle_exhaustion(
            record, flow, observations, decision_ms=decision_ms,
        )

    outcome = (
        "ARC_NOT_OBSERVED" if not arc else
        "OUTSIDE_FROZEN_EDGE_ZONE" if not near else
        "ARC_CANDLE_CONTEXT_RESEARCH" if labels else
        "ARC_WITHOUT_RECOGNIZED_CANDLE"
    )
    return WedgeArcCandleResearch(
        candidate_id, revision, symbol, direction, decision_ms,
        outcome, arc, near, tuple(labels), confluence,
    )


def observe_wedge_arc_with_certified_tape_receipt(
    record,
    closed_m1: tuple[Mapping[str, object], ...],
    receipt: CandidateBoundFlowEvidence | None,
    *,
    decision_ms: int,
    atr: Decimal,
    max_boundary_distance_atr: Decimal,
    doji_body_fraction: Decimal,
    source_id: str,
) -> WedgeArcCandleResearch | None:
    """Research-only join of a *producer-certified* exact M1 trade receipt.

    Independently produced publicTrade WS/REST/closed-kline parity is required.
    These metadata guards do NOT certify the underlying data themselves.
    The OHLC source, location-specific arc and L2 history are not verified by
    this join, so source_complete/trading_authorized remain False.
    """
    if (not isinstance(receipt, CandidateBoundFlowEvidence)
            or type(decision_ms) is not int
            or not isinstance(closed_m1, tuple) or not closed_m1
            or not isinstance(closed_m1[-1], Mapping)):
        return None
    latest = closed_m1[-1].get("time")
    if (type(latest) is not int
            or latest + ONE_MINUTE_MS != receipt.closed_at_ms):
        return None
    try:
        direction = record.robot_state.get("direction")
        candidate_id, symbol, revision = (
            record.candidate_id, record.symbol.value, record.state_revision,
        )
    except (AttributeError, TypeError):
        return None
    digest = receipt.print_facts_sha256
    if (receipt.candidate_id != candidate_id
            or receipt.symbol != symbol or receipt.direction != direction
            or type(receipt.state_revision) is not int
            or receipt.state_revision != revision
            or receipt.source_kind != "BYBIT_TRIPLE_CLOSED_M1_CERTIFIED"
            or receipt.source_complete is not True
            or receipt.receipt_cutoff_proven is not True
            or receipt.transport_generation_proven is not True
            or not isinstance(digest, str) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)
            or type(receipt.closed_at_ms) is not int
            or receipt.closed_at_ms <= 0
            or receipt.closed_at_ms % ONE_MINUTE_MS != 0
            or type(receipt.decision_ms) is not int
            or not receipt.closed_at_ms <= receipt.decision_ms <= decision_ms
            or decision_ms - receipt.closed_at_ms > 120_000
            or not isinstance(receipt.transition, FlowTransition)
            or receipt.transition.known_at_ms != receipt.decision_ms):
        return None
    result = observe_closed_wedge_arc_candles(
        record, closed_m1, receipt.transition,
        decision_ms=decision_ms, atr=atr,
        max_boundary_distance_atr=max_boundary_distance_atr,
        doji_body_fraction=doji_body_fraction, source_id=source_id,
    )
    if result is None:
        return None
    return replace(result, tape_receipt_metadata_matched=True)
