"""Pattern-specific closed-candle freshness evidence for PAPER_AUTO admission.

The Wedge proof (``scanner_geometry_cursor`` + ``robot_state_machine``) replays
closed 1m candles against a frozen cursor and apex. IKIGAI_BOX and L-shape have
neither: their frozen terms are a TAKE price (Box) or a target/stop pair
(L-shape), and their lifecycle ends when price reaches them. This module proves
that, and only that, from authoritative closed candles of the pattern's own
source timeframe. Nothing is synthesised: a missing candle, a gap, an
unreadable term or a signal too old to cover fails closed (an exception here,
``None`` for the policy, which turns it into WAIT).

* IKIGAI_BOX (``DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md``, owner correction
  2026-09-29): stale/completed once a closed candle after the frozen decision
  time printed ``high >= take`` (LONG) / ``low <= take`` (SHORT).
* L-shape (``robot_l_shape.invalidation_event``): stale once a closed candle
  after the breakout candle touched the frozen target or stop.
"""

from __future__ import annotations

import math
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

import robot_l_shape
from scanner_geometry_cursor import load_scanner_catchup_closed_candles

KIND_BOX = "IKIGAI_BOX"
KIND_L_SHAPE = "L-shape"

# A kline request is bounded; a signal older than this cannot be proven fresh.
MAX_LOOKBACK_CANDLES = 600
_MINUTE_MS = 60_000


class PatternFreshnessError(RuntimeError):
    """Freshness cannot be proven from the frozen terms or the candle evidence."""


def freshness_kind(signal_snapshot: Any) -> str | None:
    """The pattern kind handled here, or None (Wedge keeps the cursor/apex proof)."""
    if not isinstance(signal_snapshot, Mapping):
        return None
    if str(signal_snapshot.get("pattern", "")).strip() == KIND_BOX:
        return KIND_BOX
    if robot_l_shape.is_l_shape_snapshot(signal_snapshot):
        return KIND_L_SHAPE
    return None


def _decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise PatternFreshnessError(f"{name} is invalid")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PatternFreshnessError(f"{name} is invalid") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise PatternFreshnessError(f"{name} must be positive and finite")
    return parsed


def _timestamp(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PatternFreshnessError(f"{name} is invalid")
    return value


def _interval_ms(timeframe: Any) -> int:
    text = str(timeframe).strip()
    if not text.isdecimal() or int(text) <= 0:
        raise PatternFreshnessError("source timeframe must be a positive minute interval")
    return int(text) * _MINUTE_MS


class _Terms:
    """What the freshness proof needs: the timeline anchor and the end condition."""

    __slots__ = ("kind", "timeframe", "interval_ms", "first_open_ms", "direction", "levels")

    def __init__(self, kind, timeframe, interval_ms, first_open_ms, direction, levels):
        self.kind = kind
        self.timeframe = timeframe
        self.interval_ms = interval_ms
        # Open time of the first candle that counts as "after the signal".
        self.first_open_ms = first_open_ms
        self.direction = direction
        # Box: (take,). L-shape: (target, stop).
        self.levels = levels


def _box_terms(snapshot: Mapping[str, Any]) -> _Terms:
    identity = snapshot.get("identity")
    plan = snapshot.get("plan")
    if not isinstance(identity, Mapping) or not isinstance(plan, Mapping):
        raise PatternFreshnessError("Box identity and plan are required")
    direction = str(plan.get("direction", "")).strip().upper()
    if direction not in ("LONG", "SHORT") or direction != str(identity.get("direction", "")).strip().upper():
        raise PatternFreshnessError("Box direction is invalid")
    timeframe = str(identity.get("timeframe", "")).strip()
    interval = _interval_ms(timeframe)
    decision_time = _timestamp(snapshot.get("decision_time_ms"), "decision_time_ms")
    if decision_time % interval:
        raise PatternFreshnessError("Box decision time is not aligned to its candle grid")
    take = _decimal(plan.get("take_price"), "plan.take_price")
    return _Terms(KIND_BOX, timeframe, interval, decision_time, direction, (take,))


def _l_shape_terms(snapshot: Mapping[str, Any]) -> _Terms:
    try:
        frozen = robot_l_shape.frozen_terms(snapshot)
    except robot_l_shape.RobotLShapeError as exc:
        raise PatternFreshnessError("L-shape frozen terms are invalid") from exc
    interval = _interval_ms(frozen.source_timeframe)
    if frozen.breakout_time_ms % interval:
        raise PatternFreshnessError("L-shape breakout time is not aligned to its candle grid")
    return _Terms(
        KIND_L_SHAPE, frozen.source_timeframe, interval, frozen.breakout_time_ms + interval,
        frozen.direction, (frozen.target, frozen.stop),
    )


def _terms(snapshot: Mapping[str, Any]) -> _Terms:
    kind = freshness_kind(snapshot)
    if kind == KIND_BOX:
        return _box_terms(snapshot)
    if kind == KIND_L_SHAPE:
        return _l_shape_terms(snapshot)
    raise PatternFreshnessError("pattern has no closed-candle freshness proof here")


def _closed_row(row: Any, terms: _Terms) -> dict[str, object]:
    try:
        time_ms = int(row["time"])
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise PatternFreshnessError("closed candle evidence is invalid") from exc
    if time_ms <= 0 or not all(math.isfinite(v) for v in (high, low, close)) or low > high:
        raise PatternFreshnessError("closed candle evidence is invalid")
    return {
        "closed": True, "timeframe": terms.timeframe, "time_ms": time_ms,
        "high": high, "low": low, "close": close,
    }


def load_pattern_closed_candles(
    symbol: str,
    signal_snapshot: Mapping[str, Any],
    *,
    candle_loader: Callable[..., Any] | None = None,
    now_ms: int | None = None,
) -> tuple[dict[str, object], ...]:
    """Closed candles of the source timeframe strictly after the signal, contiguous.

    One bounded request. The newest returned kline is treated as still forming
    (the Scanner recovery convention) and dropped. An empty tuple means the load
    succeeded and no candle has closed since the signal: not a completion.
    """
    symbol_value = str(symbol).strip()
    if not symbol_value:
        raise PatternFreshnessError("symbol is required")
    terms = _terms(signal_snapshot)
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    if now < terms.first_open_ms:
        raise PatternFreshnessError("signal is in the future")
    wanted = (now - terms.first_open_ms) // terms.interval_ms + 3
    if wanted > MAX_LOOKBACK_CANDLES:
        raise PatternFreshnessError("signal is too old to prove freshness in one request")

    if candle_loader is None:
        from analyzer.candles import load_candles

        candle_loader = load_candles
    frame = candle_loader(symbol_value, terms.timeframe, max(3, wanted), minimum=2)
    if frame is None or len(frame) < 2 or not {"time", "high", "low", "close"}.issubset(frame.columns):
        raise PatternFreshnessError("closed candle evidence is unavailable")

    closed = [_closed_row(frame.iloc[position], terms) for position in range(len(frame) - 1)]
    times = [candle["time_ms"] for candle in closed]
    if times != sorted(set(times)):
        raise PatternFreshnessError("closed candle evidence is unordered or duplicated")
    # The evidence must reach the signal: the newest closed bar cannot predate the bar before it.
    if times[-1] < terms.first_open_ms - terms.interval_ms:
        raise PatternFreshnessError("closed candle evidence does not reach the signal time")
    after = [candle for candle in closed if candle["time_ms"] >= terms.first_open_ms]
    expected = list(range(terms.first_open_ms, terms.first_open_ms + len(after) * terms.interval_ms,
                          terms.interval_ms))
    if [candle["time_ms"] for candle in after] != expected:
        raise PatternFreshnessError("closed candle range after the signal is incomplete")
    return tuple(after)


def pattern_candidate_fresh(
    signal_snapshot: Mapping[str, Any], candles: tuple[Mapping[str, Any], ...],
) -> bool:
    """False once the frozen end condition was reached, True if it provably was not.

    Raises ``PatternFreshnessError`` for an unsupported pattern, unreadable frozen
    terms or candles that are not the contiguous post-signal range.
    """
    terms = _terms(signal_snapshot)
    expected_time = terms.first_open_ms
    for candle in candles:
        if (not isinstance(candle, Mapping) or candle.get("closed") is not True
                or str(candle.get("timeframe", "")).strip() != terms.timeframe
                or candle.get("time_ms") != expected_time):
            raise PatternFreshnessError("candles are not the contiguous post-signal range")
        expected_time += terms.interval_ms
        high = _decimal(candle.get("high"), "candle.high")
        low = _decimal(candle.get("low"), "candle.low")
        if low > high:
            raise PatternFreshnessError("candle low exceeds high")
        if terms.kind == KIND_BOX:
            (take,) = terms.levels
            if (high >= take) if terms.direction == "LONG" else (low <= take):
                return False
        elif robot_l_shape.invalidation_event(signal_snapshot, candle) is not None:
            return False
    return True


def freshness_fetch(
    wedge_fetch: Callable[[str, Mapping[str, Any]], tuple],
    *,
    pattern_fetch: Callable[[str, Mapping[str, Any]], tuple] = load_pattern_closed_candles,
) -> Callable[[str, Mapping[str, Any]], tuple]:
    """Route Box / L-shape to their own evidence; Wedge keeps its existing fetch."""

    def fetch(symbol: str, signal_snapshot: Mapping[str, Any]) -> tuple:
        if freshness_kind(signal_snapshot) is None:
            return wedge_fetch(symbol, signal_snapshot)
        return pattern_fetch(symbol, signal_snapshot)

    return fetch
