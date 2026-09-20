"""Presentation-only trade overlay for one Ikigai Box formation.

Pure planning arithmetic for the chart/card: stage, whether F(1.618) was
reached, a PLANNED four-LIMIT grid, a PLANNED STOP and the F(1.0) target.
Nothing here places orders, creates candidates or touches Robot admission;
see DOCUMENTS/IKIGAI_BOX_STRATEGY_SPEC.md section 3 (approved intent only).

Only candles up to ``formation.as_of_index`` are read.

Deliberately NOT decided here (spec: user decisions pending):
- the real grid spacing / zone width -- ``GRID_STEP_FRACTION`` is a
  visualisation placeholder, never an execution parameter;
- the partial-profit trigger, fraction and the breakeven buffer;
- the second attempt (F(2.618)) lifecycle. ``build_entry_grid`` accepts any
  anchor level so a later slice can reuse it without changing this contract.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Optional, Tuple

GRID_ORDERS = 4
ORDER_FRACTION = 1 / GRID_ORDERS            # each LIMIT is 1/4 РО
# Visualisation placeholder: step as a fraction of |F(2.618) - F(1.618)|.
GRID_STEP_FRACTION = 0.05
# Grid = one step on the approach side of the level, the level itself, and two
# steps beyond it, so the furthest LIMIT is always past the level.
GRID_OFFSET_STEPS = (1, 0, -1, -2)         # in the direction of the leg-two move
FALLBACK_STOP_FRACTION = 0.015             # -1.5% from (planned) average entry
# Textbook candle shapes; named so they are never mistaken for tuned values.
PIN_BAR_MIN_WICK_TO_BODY = 2.0
PIN_BAR_MAX_OPPOSITE_WICK_TO_BODY = 1.0


@dataclass(frozen=True)
class EntryGrid:
    anchor_level: float                    # 1.618 now, 2.618 for a later attempt
    anchor_price: float
    prices: Tuple[float, ...]              # ordered from nearest to furthest
    size_fraction_each: float              # 1/4 РО
    furthest_beyond_anchor: bool
    step: float
    spacing_is_placeholder: bool = True


@dataclass(frozen=True)
class StopPlan:
    price: float
    basis: str                             # "REVERSAL_CANDLE" | "FALLBACK_-1.5%"
    anchor_index: Optional[int]
    anchor_kind: Optional[str]
    reference_entry: float                 # planned quantity-weighted entry


@dataclass(frozen=True)
class IkigaiBoxTradeOverlay:
    direction: str
    stage: str                             # WATCH | BOX_READY | BOX_BREAK_OBSERVED | CONFIRMED
    level_1_618_reached: bool
    first_reach_index: Optional[int]
    entry_zone_active: bool
    grid: Optional[EntryGrid]              # None while only observing
    stop: Optional[StopPlan]
    target_price: float                    # F(1.0)
    partial_take_note: str
    unapproved: Tuple[str, ...]


def stage_of(formation) -> str:
    phase = getattr(formation, "phase", None)
    return phase if phase in ("BOX_READY", "BOX_BREAK_OBSERVED") else "CONFIRMED"


def _sign(formation) -> int:
    """+1 when leg two moves UP (SHORT setup), -1 when it moves DOWN (LONG)."""
    return 1 if formation.direction == "SHORT" else -1


def first_reach_index(candles, formation, level_price: float) -> Optional[int]:
    """First closed candle after B whose extreme touched ``level_price``."""
    sign = _sign(formation)
    column = "high" if sign == 1 else "low"
    values = candles[column].to_numpy(dtype=float)
    for index in range(formation.anchor_end_index + 1, formation.as_of_index + 1):
        if (sign == 1 and values[index] >= level_price) or (
            sign == -1 and values[index] <= level_price
        ):
            return index
    return None


def build_entry_grid(
    formation, *, anchor_level: float = 1.618,
) -> EntryGrid:
    """Four equally spaced PLANNED LIMITs around ``anchor_level``."""
    sign = _sign(formation)
    anchor = formation.fibonacci_price(anchor_level)
    gap = abs(formation.fibonacci_2_618 - formation.fibonacci_1_618)
    step = gap * GRID_STEP_FRACTION
    if not (isfinite(anchor) and isfinite(step) and step > 0):
        raise ValueError("Invalid Ikigai grid geometry")
    prices = tuple(anchor - sign * offset * step for offset in GRID_OFFSET_STEPS)
    # Ordered nearest -> furthest along the leg-two direction.
    return EntryGrid(
        anchor_level=anchor_level,
        anchor_price=anchor,
        prices=prices,
        size_fraction_each=ORDER_FRACTION,
        furthest_beyond_anchor=(prices[-1] - anchor) * sign > 0,
        step=step,
    )


def _reversal_kind(row, previous, sign: int) -> Optional[str]:
    """Bearish reversal for SHORT (leg two up); bullish for LONG (leg two down)."""
    o, h, l, c = row
    body = abs(c - o)
    if sign == 1:
        upper, lower = h - max(o, c), min(o, c) - l
        if previous is not None:
            po, pc = previous[0], previous[3]
            if pc > po and c < o and o >= pc and c <= po:
                return "BEARISH_ENGULFING"
        if body > 0 and upper >= PIN_BAR_MIN_WICK_TO_BODY * body and (
            lower <= PIN_BAR_MAX_OPPOSITE_WICK_TO_BODY * body
        ):
            return "SHOOTING_STAR"
    else:
        upper, lower = h - max(o, c), min(o, c) - l
        if previous is not None:
            po, pc = previous[0], previous[3]
            if pc < po and c > o and o <= pc and c >= po:
                return "BULLISH_ENGULFING"
        if body > 0 and lower >= PIN_BAR_MIN_WICK_TO_BODY * body and (
            upper <= PIN_BAR_MAX_OPPOSITE_WICK_TO_BODY * body
        ):
            return "HAMMER"
    return None


def find_reversal_stop_anchor(candles, formation, from_index: int):
    """Latest closed reversal candle in [from_index, as_of], or None."""
    sign = _sign(formation)
    rows = candles[["open", "high", "low", "close"]].to_numpy(dtype=float)
    for index in range(formation.as_of_index, max(from_index, 1) - 1, -1):
        previous = tuple(rows[index - 1]) if index > 0 else None
        kind = _reversal_kind(tuple(rows[index]), previous, sign)
        if kind is not None:
            extreme = rows[index][1] if sign == 1 else rows[index][2]
            return index, float(extreme), kind
    return None


def build_stop_plan(candles, formation, grid: EntryGrid, reach_index: int) -> StopPlan:
    sign = _sign(formation)
    reference = sum(grid.prices) / len(grid.prices)    # equal 1/4 weights
    anchor = find_reversal_stop_anchor(candles, formation, reach_index)
    if anchor is not None:
        index, extreme, kind = anchor
        # Valid only if it protects the planned entry (beyond it, adverse side).
        if (extreme - reference) * sign > 0:
            return StopPlan(extreme, "REVERSAL_CANDLE", index, kind, reference)
    fallback = reference * (1 + sign * FALLBACK_STOP_FRACTION)
    return StopPlan(fallback, "FALLBACK_-1.5%", None, None, reference)


def build_trade_overlay(candles, formation) -> IkigaiBoxTradeOverlay:
    """Stage-aware planning overlay; only candles through ``as_of`` are read."""
    reach = first_reach_index(candles, formation, formation.fibonacci_1_618)
    grid = stop = None
    if reach is not None:
        grid = build_entry_grid(formation)
        stop = build_stop_plan(candles, formation, grid, reach)
    return IkigaiBoxTradeOverlay(
        direction=formation.direction,
        stage=stage_of(formation),
        level_1_618_reached=reach is not None,
        first_reach_index=reach,
        entry_zone_active=reach is not None,
        grid=grid,
        stop=stop,
        target_price=formation.fibonacci_1_0,
        partial_take_note="фиксацию начинать до 1.0 (уровень не утверждён)",
        unapproved=(
            "grid spacing/zone width",
            "partial-take trigger and fraction",
            "breakeven buffer",
            "attempt 2 at F(2.618)",
        ),
    )
