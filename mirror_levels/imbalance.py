"""
mirror_levels.imbalance

M3 of #613: three-candle fair value gaps (FVG), clusters and their fill /
inversion lifecycle -- a *quality factor* next to a mirror level, never a
precondition of a mirror retest.

Definition (bullish; bearish mirrors it): candles 1-2-3 consecutive, closed;
``low[3] > high[1]``; zone ``[high[1], low[3]]``. It is known only at the close
of candle 3 (``formed_at_ms``) -- the middle (displacement) candle never reveals
a gap by itself, so nothing here can see candle 3 before it closed.

Lifecycle over later closed candles (bullish gap lies *below* price):
``FORMED_UNTOUCHED -> EDGE_TOUCHED -> PARTIAL_FILL -> FULL_FILL``, wick and close
depth tracked separately (depth 1.0 = whole gap, 0.5 = midpoint). A close below
the bottom marks ``INVERTED`` (closed through: the zone flips role, IFVG); the
first later candle reaching the zone again from the new (lower) side is the
``IFVG_RETEST``. Stale candles are ignored and a gap in the candle sequence
blocks the state (``data_blocked``), like ``geometry.naked_retest``.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence


BULLISH = "BULLISH"
BEARISH = "BEARISH"

PHASE_UNTOUCHED = "FORMED_UNTOUCHED"
PHASE_EDGE = "EDGE_TOUCHED"
PHASE_PARTIAL = "PARTIAL_FILL"
PHASE_FULL = "FULL_FILL"
_PHASE_ORDER = {PHASE_UNTOUCHED: 0, PHASE_EDGE: 1, PHASE_PARTIAL: 2, PHASE_FULL: 3}

STATE_VERSION = "fvg-1"


@dataclass(frozen=True)
class FairValueGap:
    fvg_id: str
    symbol: str
    timeframe: str
    direction: str
    bottom: float
    top: float
    first_open_ms: int      # candle 1 open
    middle_open_ms: int     # displacement candle open
    formed_at_ms: int       # candle 3 close: the earliest moment the gap is known
    middle_body: float
    middle_range: float

    @property
    def height(self) -> float:
        return self.top - self.bottom

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _gap_id(symbol: str, timeframe: str, direction: str, middle_open_ms: int) -> str:
    raw = f"{symbol}|{timeframe}|{direction}|{middle_open_ms}".encode()
    return "fvg-" + hashlib.sha256(raw).hexdigest()[:20]


def detect_fvgs(candles: Sequence[Mapping], *, symbol: str, timeframe: str) -> tuple[FairValueGap, ...]:
    """All FVGs whose third candle is inside ``candles`` (closed, contiguous)."""

    out = []
    for i in range(2, len(candles)):
        c1, c2, c3 = candles[i - 2], candles[i - 1], candles[i]
        if not (c1["close_time_ms"] <= c2["open_time_ms"] + 1 and c2["close_time_ms"] <= c3["open_time_ms"] + 1):
            continue
        h1, l1 = float(c1["high"]), float(c1["low"])
        h3, l3 = float(c3["high"]), float(c3["low"])
        if l3 > h1:
            direction, bottom, top = BULLISH, h1, l3
        elif h3 < l1:
            direction, bottom, top = BEARISH, h3, l1
        else:
            continue
        out.append(FairValueGap(
            _gap_id(symbol, timeframe, direction, int(c2["open_time_ms"])), symbol, str(timeframe),
            direction, bottom, top, int(c1["open_time_ms"]), int(c2["open_time_ms"]),
            int(c3["close_time_ms"]), abs(float(c2["close"]) - float(c2["open"])),
            float(c2["high"]) - float(c2["low"]),
        ))
    return tuple(out)


def cluster_fvgs(gaps: Sequence[FairValueGap], *, timeframe_ms: int) -> tuple[dict[str, Any], ...]:
    """Consecutive same-direction gaps (adjacent displacement candles) as one void.

    Components keep their own ids and lifecycle; the cluster only reports the union.
    """

    clusters: list[dict[str, Any]] = []
    for gap in sorted(gaps, key=lambda g: g.middle_open_ms):
        last = clusters[-1] if clusters else None
        if (last is not None and last["direction"] == gap.direction
                and gap.middle_open_ms - last["last_middle_open_ms"] == timeframe_ms):
            last["components"].append(gap.fvg_id)
            last["bottom"] = min(last["bottom"], gap.bottom)
            last["top"] = max(last["top"], gap.top)
            last["last_middle_open_ms"] = gap.middle_open_ms
            last["formed_at_ms"] = gap.formed_at_ms
        else:
            clusters.append({"direction": gap.direction, "components": [gap.fvg_id],
                             "bottom": gap.bottom, "top": gap.top,
                             "first_middle_open_ms": gap.middle_open_ms,
                             "last_middle_open_ms": gap.middle_open_ms,
                             "formed_at_ms": gap.formed_at_ms})
    return tuple(clusters)


def initial_state(gap: FairValueGap) -> dict[str, Any]:
    return {
        "state_version": STATE_VERSION, "fvg_id": gap.fvg_id, "phase": PHASE_UNTOUCHED,
        "cursor_close_time_ms": gap.formed_at_ms, "data_blocked": False,
        "first_touch_ms": None, "midpoint_touch_ms": None, "full_fill_ms": None,
        "max_wick_depth": 0.0, "max_close_depth": 0.0,
        "unfilled_bottom": gap.bottom, "unfilled_top": gap.top,
        "inverted_ms": None, "ifvg_retest_ms": None,
    }


def _depth(gap: FairValueGap, price: float) -> float:
    """Share of the gap filled when price reaches ``price`` from the gap's open side."""

    if gap.height <= 0:
        return 1.0
    raw = (gap.top - price) / gap.height if gap.direction == BULLISH else (price - gap.bottom) / gap.height
    return max(0.0, min(1.0, raw))


def advance(gap: FairValueGap, state: Mapping[str, Any], candle: Mapping) -> dict[str, Any]:
    """Advance the gap lifecycle by one closed candle; reads nothing beyond it."""

    if state.get("state_version") != STATE_VERSION or state.get("fvg_id") != gap.fvg_id:
        raise ValueError("state belongs to another gap or version")
    new = deepcopy(dict(state))
    open_ms, close_ms = int(candle["open_time_ms"]), int(candle["close_time_ms"])
    cursor = int(new["cursor_close_time_ms"])
    if close_ms <= cursor:
        return new                                     # stale / replayed candle
    if open_ms > cursor + 1:
        new["data_blocked"] = True                     # missing candle: no verdict from a hole
        return new
    new["data_blocked"] = False
    new["cursor_close_time_ms"] = close_ms
    o, h, l, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
    bullish = gap.direction == BULLISH

    if new["inverted_ms"] is not None:
        # IFVG: the first later return to the zone from the new side.
        if new["ifvg_retest_ms"] is None and ((h >= gap.bottom) if bullish else (l <= gap.top)):
            new["ifvg_retest_ms"] = open_ms
        return new

    reach = l if bullish else h
    touched = (reach <= gap.top) if bullish else (reach >= gap.bottom)
    if touched:
        wick_depth = _depth(gap, reach)
        close_depth = _depth(gap, c)
        if new["first_touch_ms"] is None:
            new["first_touch_ms"] = open_ms
        new["max_wick_depth"] = max(new["max_wick_depth"], wick_depth)
        new["max_close_depth"] = max(new["max_close_depth"], close_depth)
        if new["midpoint_touch_ms"] is None and wick_depth >= 0.5:
            new["midpoint_touch_ms"] = open_ms
        if bullish:
            new["unfilled_top"] = max(gap.bottom, min(new["unfilled_top"], reach))
        else:
            new["unfilled_bottom"] = min(gap.top, max(new["unfilled_bottom"], reach))
        phase = PHASE_FULL if wick_depth >= 1.0 else PHASE_PARTIAL if wick_depth > 0 else PHASE_EDGE
        if _PHASE_ORDER[phase] > _PHASE_ORDER[new["phase"]]:
            new["phase"] = phase
        if phase == PHASE_FULL and new["full_fill_ms"] is None:
            new["full_fill_ms"] = open_ms
        if (c < gap.bottom) if bullish else (c > gap.top):
            new["inverted_ms"] = open_ms               # closed through the whole zone
    return new


def replay(gap: FairValueGap, candles: Sequence[Mapping], state: Mapping[str, Any] | None = None
           ) -> dict[str, Any]:
    current = dict(state) if state is not None else initial_state(gap)
    for candle in candles:
        if int(candle["open_time_ms"]) < gap.formed_at_ms:
            continue
        current = advance(gap, current, candle)
        if current["data_blocked"]:
            break
    return current
