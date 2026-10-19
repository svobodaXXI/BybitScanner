"""
geometry.naked_retest

Offline research prototype (MIRROR RETEST-1) for the owner-defined H-016
mechanics in DOCUMENTS/TRADING_STRATEGY_SPEC.md and
DOCUMENTS/RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md section 2-3:

    frozen boundary -> naked breakout candle -> RETEST CAMPAIGN -> first retest

Naked breakout (owner rule, plan 2.1): one closed candle whose real body fully
crosses the boundary. UP: ``open < boundary(t_open)`` and
``close > boundary(t_close)``; DOWN mirrors it. Equality, wick-only crossings
and a candle that already opened beyond the level do not qualify. No extra
acceptance candle is required. A horizontal level has zero slope; a sloped
line is evaluated at the candle's own open and close times.

RETEST CAMPAIGN direction is opposite to the breakout (toward the broken
boundary): UP breakout -> SHORT campaign, DOWN breakout -> LONG campaign.
The first proven contact with ``boundary(t)`` after the breakout candle closes
is terminal for the campaign; later taps never re-arm it (plan 2.5).

Owner decisions 2026-10-19 (MIRROR RETEST-2): prior compression is allowed
(no accumulation filter); the retest is a wick touch or entry into a small
dynamic ATR zone passed by the caller; the campaign has no fixed horizon.

Owner decisions MIRROR RETEST-3: ATR period and coefficient are chosen by
historical trials without look-ahead (``retest_calibration``); the mirror level
stays valid until the first confirmed retest regardless of later market
structure, so nothing but a retest ends a campaign; unreliable data blocks.
A candle that does not continue the processed history (gap) is not consumed:
the state is flagged ``data_blocked`` until the missing candle arrives, and
``retest_campaign.entry_gate`` admits nothing while it is set.

Contact proof from closed OHLC only. For an UP breakout (price above the line)
a candle proves contact when its open or close is at/below the line (plus
tolerance) at that time, or its low is at/below it at every instant of the
candle (``low <= min(boundary(t_open), boundary(t_close)) + tolerance``). When
the low lies only between the two values the touch time is unknown: the
campaign ends fail-closed as ``RETEST_UNPROVEN`` instead of being counted or
ignored. A horizontal level can never be ambiguous. DOWN mirrors with highs.

Responsibility:
- pure transition over one authoritative closed candle at a time;
- stale/replayed candles are ignored idempotently; terminal states never move.

Not responsible for (owned elsewhere or still owner-undecided):
- detecting the boundary itself (existing geometry detectors);
- entries, confirmations, orders, STOP/TAKE, Robot or Scanner wiring; no
  runtime module imports this file;
- choosing the ATR period/coefficient (``retest_calibration``); campaign risk
  and exit intents live in ``retest_campaign``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
import math
from typing import Any, Mapping


STATE_VERSION = "naked-retest-1"

BREAKOUT_UP = "UP"
BREAKOUT_DOWN = "DOWN"
CAMPAIGN_LONG = "LONG"
CAMPAIGN_SHORT = "SHORT"

PHASE_WAITING_BREAKOUT = "WAITING_NAKED_BREAKOUT"
PHASE_CAMPAIGN_ACTIVE = "RETEST_CAMPAIGN_ACTIVE"
PHASE_RETEST_PROVEN = "RETEST_PROVEN"
PHASE_RETEST_UNPROVEN = "RETEST_UNPROVEN"

EVENT_INITIALIZED = "INITIALIZED"
EVENT_NO_TRANSITION = "NO_TRANSITION"
EVENT_BEFORE_AS_OF = "IGNORED_BEFORE_BOUNDARY_AS_OF"
EVENT_IGNORED_STALE = "IGNORED_STALE_CANDLE"
EVENT_NAKED_BREAKOUT = "NAKED_BREAKOUT"
EVENT_RETEST_PROVEN = "RETEST_PROVEN"
EVENT_RETEST_UNPROVEN = "RETEST_UNPROVEN"
EVENT_DATA_GAP = "DATA_GAP_BLOCKED"
EVENT_TERMINAL = "TERMINAL_STATE"

TERMINAL_PHASES = frozenset({PHASE_RETEST_PROVEN, PHASE_RETEST_UNPROVEN})
_PHASES = frozenset({PHASE_WAITING_BREAKOUT, PHASE_CAMPAIGN_ACTIVE}) | TERMINAL_PHASES
_CAMPAIGN_FOR_BREAKOUT = {BREAKOUT_UP: CAMPAIGN_SHORT, BREAKOUT_DOWN: CAMPAIGN_LONG}


class NakedRetestError(ValueError):
    """Raised when boundary, state or candle input cannot be trusted."""


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise NakedRetestError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise NakedRetestError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise NakedRetestError(f"{field} must be finite")
    return number


def _time_ms(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NakedRetestError(f"{field} must be integer milliseconds")
    return value


@dataclass(frozen=True)
class Boundary:
    """One frozen level: ``price(t) = anchor_price + slope_per_ms * (t - anchor_time_ms)``.

    ``as_of_time_ms`` is when the geometry became known; candles opening
    earlier can never be its breakout (no retroactive levels).
    """

    boundary_id: str
    anchor_time_ms: int
    anchor_price: float
    slope_per_ms: float
    as_of_time_ms: int

    def __post_init__(self) -> None:
        if not str(self.boundary_id or "").strip():
            raise NakedRetestError("boundary_id is required")
        _time_ms(self.anchor_time_ms, "anchor_time_ms")
        _time_ms(self.as_of_time_ms, "as_of_time_ms")
        _finite(self.anchor_price, "anchor_price")
        _finite(self.slope_per_ms, "slope_per_ms")

    @classmethod
    def horizontal(cls, boundary_id: str, price: float, *, as_of_time_ms: int) -> "Boundary":
        return cls(boundary_id, as_of_time_ms, price, 0.0, as_of_time_ms)

    @property
    def is_horizontal(self) -> bool:
        return self.slope_per_ms == 0.0

    def price_at(self, time_ms: int) -> float:
        return self.anchor_price + self.slope_per_ms * (time_ms - self.anchor_time_ms)


def _candle(candle: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(candle, Mapping):
        raise NakedRetestError("candle must be a mapping")
    if candle.get("closed") is not True:
        raise NakedRetestError("only authoritative closed candles are accepted")
    open_time = _time_ms(candle.get("open_time_ms"), "candle.open_time_ms")
    close_time = _time_ms(candle.get("close_time_ms"), "candle.close_time_ms")
    if close_time <= open_time:
        raise NakedRetestError("candle close_time_ms must follow open_time_ms")
    o, h, l, c = (
        _finite(candle.get(key), f"candle.{key}") for key in ("open", "high", "low", "close")
    )
    if l > min(o, c) or h < max(o, c):
        raise NakedRetestError("candle OHLC is inconsistent")
    return {"open_time_ms": open_time, "close_time_ms": close_time,
            "open": o, "high": h, "low": l, "close": c}


def naked_breakout_direction(boundary: Boundary, candle: Mapping[str, Any]) -> str | None:
    """Strict full-body crossing of the boundary by one closed candle, else None."""

    row = _candle(candle)
    at_open = boundary.price_at(row["open_time_ms"])
    at_close = boundary.price_at(row["close_time_ms"])
    if row["open"] < at_open and row["close"] > at_close:
        return BREAKOUT_UP
    if row["open"] > at_open and row["close"] < at_close:
        return BREAKOUT_DOWN
    return None


def atr_tolerance(atr: Any, multiplier: Any) -> float:
    """Owner rule 2026-10-19: retest zone = ``multiplier * ATR``.

    Neither value has an approved default: the coefficient is still owner
    pending and the ATR (period, source candles) is supplied by the caller from
    closed history up to and including the evaluated candle only.
    """

    atr_value = _finite(atr, "atr")
    factor = _finite(multiplier, "tolerance multiplier")
    if atr_value < 0 or factor < 0:
        raise NakedRetestError("ATR and tolerance multiplier must be non-negative")
    return atr_value * factor


def retest_contact(
    boundary: Boundary,
    breakout_direction: str,
    candle: Mapping[str, Any],
    tolerance: float = 0.0,
) -> str | None:
    """``"PROVEN"``, ``"AMBIGUOUS"`` or None for one closed post-breakout candle.

    ``tolerance`` widens the boundary toward the breakout side by a price
    distance (``atr_tolerance``); ``0.0`` is exact contact.
    """

    row = _candle(candle)
    tolerance = _finite(tolerance, "tolerance")
    if tolerance < 0:
        raise NakedRetestError("tolerance must be non-negative")
    if breakout_direction not in (BREAKOUT_UP, BREAKOUT_DOWN):
        raise NakedRetestError(f"unknown breakout direction: {breakout_direction!r}")
    shift = tolerance if breakout_direction == BREAKOUT_UP else -tolerance
    at_open = boundary.price_at(row["open_time_ms"]) + shift
    at_close = boundary.price_at(row["close_time_ms"]) + shift
    if breakout_direction == BREAKOUT_UP:
        if row["open"] <= at_open or row["close"] <= at_close or row["low"] <= min(at_open, at_close):
            return "PROVEN"
        return "AMBIGUOUS" if row["low"] <= max(at_open, at_close) else None
    if row["open"] >= at_open or row["close"] >= at_close or row["high"] >= max(at_open, at_close):
        return "PROVEN"
    return "AMBIGUOUS" if row["high"] >= min(at_open, at_close) else None


def initialize_state(boundary: Boundary) -> tuple[dict[str, Any], str]:
    return {
        "state_version": STATE_VERSION,
        "boundary_id": boundary.boundary_id,
        "phase": PHASE_WAITING_BREAKOUT,
        "cursor_close_time_ms": None,
        "breakout": None,
        "retest": None,
        "data_blocked": False,
        "last_event": EVENT_INITIALIZED,
    }, EVENT_INITIALIZED


def _validate_state(boundary: Boundary, state: Mapping[str, Any]) -> None:
    if not isinstance(state, Mapping) or state.get("state_version") != STATE_VERSION:
        raise NakedRetestError("unsupported naked-retest state")
    if state.get("boundary_id") != boundary.boundary_id:
        raise NakedRetestError("state belongs to a different boundary")
    if state.get("phase") not in _PHASES:
        raise NakedRetestError("invalid naked-retest phase")


def process_closed_candle(
    boundary: Boundary,
    state: Mapping[str, Any],
    candle: Mapping[str, Any],
    *,
    retest_tolerance: float = 0.0,
) -> tuple[dict[str, Any], str]:
    """Advance by exactly one closed candle; reads nothing beyond it.

    ``retest_tolerance`` (price distance, see ``atr_tolerance``) applies only
    to the retest zone, never to the strict naked-breakout test.
    """

    _validate_state(boundary, state)
    row = _candle(candle)
    new_state = deepcopy(dict(state))
    if new_state["phase"] in TERMINAL_PHASES:
        return new_state, EVENT_TERMINAL

    cursor = new_state.get("cursor_close_time_ms")
    if cursor is not None and row["close_time_ms"] <= cursor:
        return new_state, EVENT_IGNORED_STALE
    if row["open_time_ms"] < boundary.as_of_time_ms:
        return new_state, EVENT_BEFORE_AS_OF
    if cursor is not None:
        if row["open_time_ms"] < cursor:
            raise NakedRetestError("candle overlaps already processed history")
        # Accept both close = next open and close = next open - 1 ms conventions.
        if row["open_time_ms"] > cursor + 1:
            new_state["data_blocked"] = True
            new_state["last_event"] = EVENT_DATA_GAP
            return new_state, EVENT_DATA_GAP
    new_state["data_blocked"] = False
    new_state["cursor_close_time_ms"] = row["close_time_ms"]

    if new_state["phase"] == PHASE_WAITING_BREAKOUT:
        direction = naked_breakout_direction(boundary, row | {"closed": True})
        if direction is None:
            new_state["last_event"] = EVENT_NO_TRANSITION
            return new_state, EVENT_NO_TRANSITION
        new_state["phase"] = PHASE_CAMPAIGN_ACTIVE
        new_state["breakout"] = {
            "direction": direction,
            "campaign_direction": _CAMPAIGN_FOR_BREAKOUT[direction],
            "open_time_ms": row["open_time_ms"],
            "close_time_ms": row["close_time_ms"],
            "open": row["open"],
            "close": row["close"],
            "boundary_at_open": boundary.price_at(row["open_time_ms"]),
            "boundary_at_close": boundary.price_at(row["close_time_ms"]),
        }
        new_state["last_event"] = EVENT_NAKED_BREAKOUT
        return new_state, EVENT_NAKED_BREAKOUT

    contact = retest_contact(
        boundary, new_state["breakout"]["direction"], row | {"closed": True}, retest_tolerance
    )
    if contact is None:
        new_state["last_event"] = EVENT_NO_TRANSITION
        return new_state, EVENT_NO_TRANSITION
    proven = contact == "PROVEN"
    new_state["phase"] = PHASE_RETEST_PROVEN if proven else PHASE_RETEST_UNPROVEN
    new_state["retest"] = {
        "contact": contact,
        "tolerance": float(retest_tolerance),
        "open_time_ms": row["open_time_ms"],
        "close_time_ms": row["close_time_ms"],
        "boundary_at_open": boundary.price_at(row["open_time_ms"]),
        "boundary_at_close": boundary.price_at(row["close_time_ms"]),
    }
    new_state["last_event"] = EVENT_RETEST_PROVEN if proven else EVENT_RETEST_UNPROVEN
    return new_state, new_state["last_event"]


def replay_closed_candles(
    boundary: Boundary,
    state: Mapping[str, Any],
    candles: Iterable[Mapping[str, Any]],
    *,
    retest_tolerance_for: Callable[[Mapping[str, Any]], float] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Feed candles through ``process_closed_candle``; stop at a terminal phase or data gap.

    ``retest_tolerance_for(candle)`` supplies the per-candle dynamic (ATR)
    tolerance from closed history up to that candle; omitted means exact contact.
    """

    new_state = deepcopy(dict(state))
    events: list[str] = []
    for candle in candles:
        tolerance = 0.0 if retest_tolerance_for is None else retest_tolerance_for(candle)
        new_state, event = process_closed_candle(
            boundary, new_state, candle, retest_tolerance=tolerance
        )
        events.append(event)
        if new_state["phase"] in TERMINAL_PHASES or event == EVENT_DATA_GAP:
            break
    return new_state, tuple(events)
