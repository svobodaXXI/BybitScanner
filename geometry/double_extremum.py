"""Closed-candle double TOP/BOTTOM neckline confirmation, PAPER pattern primitive.

No orders and no alternative Robot engine. Signal only on the *last* fully
closed bar crossing a neck established by two distinct pivot extrema.
Both pivots and neckline must be formed strictly before the confirming bar.
A wick beyond the neck, an old confirmation, or unequal peaks cannot trigger.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class DoubleExtremum:
    pattern: str
    direction: str
    first_pivot_index: int
    neck_index: int
    second_pivot_index: int
    confirmed_index: int
    neckline: Decimal
    extreme: Decimal
    target: Decimal
    stop: Decimal


def _price(candle: Mapping[str, object], key: str) -> Decimal:
    try:
        value = candle[key]
        if isinstance(value, bool):
            raise ValueError
        number = Decimal(str(value))
        if number <= 0 or not number.is_finite():
            raise ValueError
        return number
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("invalid closed OHLC bar") from exc


def detect_confirmed_double_extremum(
    closed_candles: Sequence[Mapping[str, object]], *,
    pivot_span: int = 1,
    max_extreme_difference_fraction: Decimal = Decimal("0.005"),
    min_neck_depth_fraction: Decimal = Decimal("0.003"),
) -> DoubleExtremum | None:
    """Use only CLOSED candle records; the caller excludes a forming bar.

    Two nonadjacent pivot peaks/troughs, an intervening opposite pivot and
    an independently closed neckline break constitute confirmation.
    A confirming close must cross the neck from its preceding close, not
    merely still be below/above it after an earlier break.
    """
    if not isinstance(pivot_span, int) or isinstance(pivot_span, bool) or pivot_span < 1:
        return None
    if (not max_extreme_difference_fraction.is_finite()
            or not min_neck_depth_fraction.is_finite()
            or not (Decimal("0") < max_extreme_difference_fraction < Decimal("0.1"))
            or not (Decimal("0") < min_neck_depth_fraction < Decimal("0.1"))):
        return None
    n = len(closed_candles)
    if n < 2 * pivot_span + 6:
        return None
    try:
        highs = [_price(c, "high") for c in closed_candles]
        lows = [_price(c, "low") for c in closed_candles]
        closes = [_price(c, "close") for c in closed_candles]
        if any(lo > hi or not lo <= close <= hi
               for lo, hi, close in zip(lows, highs, closes)):
            return None
    except (ValueError, TypeError):
        return None
    confirm = n - 1
    # A second extremum must be a proven pivot BEFORE the confirming candle.
    for direction in ("SHORT", "LONG"):
        prices = highs if direction == "SHORT" else lows
        opposite = lows if direction == "SHORT" else highs
        cmp_pivot = max if direction == "SHORT" else min
        pivots = [
            i for i in range(pivot_span, n - pivot_span - 1)
            if prices[i] == cmp_pivot(prices[i - pivot_span:i + pivot_span + 1])
            and all(prices[i] != prices[j] for j in range(i - pivot_span, i + pivot_span + 1) if j != i)
        ]
        for second in reversed(pivots):
            if second + pivot_span >= confirm:
                continue
            for first in reversed([i for i in pivots if i + pivot_span + 1 < second]):
                extreme_a, extreme_b = prices[first], prices[second]
                if abs(extreme_a - extreme_b) / max(extreme_a, extreme_b) > max_extreme_difference_fraction:
                    continue
                interior = range(first + 1, second)
                if not interior:
                    continue
                neck_index = (min(interior, key=lambda j: lows[j])
                              if direction == "SHORT" else max(interior, key=lambda j: highs[j]))
                neck = opposite[neck_index]
                extreme = max(extreme_a, extreme_b) if direction == "SHORT" else min(extreme_a, extreme_b)
                depth = extreme - neck if direction == "SHORT" else neck - extreme
                if depth <= 0 or depth / extreme < min_neck_depth_fraction:
                    continue
                if direction == "SHORT":
                    if not (closes[-2] >= neck and closes[-1] < neck):
                        continue
                    stop = extreme
                    target = neck - depth
                else:
                    if not (closes[-2] <= neck and closes[-1] > neck):
                        continue
                    stop = extreme
                    target = neck + depth
                if target <= 0:
                    continue
                return DoubleExtremum(
                    pattern="Double Top" if direction == "SHORT" else "Double Bottom",
                    direction=direction,
                    first_pivot_index=first, neck_index=neck_index,
                    second_pivot_index=second, confirmed_index=confirm,
                    neckline=neck, extreme=extreme, target=target, stop=stop,
                )
    return None
