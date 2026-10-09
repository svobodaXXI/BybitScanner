"""Conservative closed-candle completion gate for a frozen Ikigai Box setup.

Do not infer completion from age. A setup is spent only once its first-grid
entry area was reached and its common TAKE was subsequently crossed.
All comparisons use the unrounded geometric levels, avoiding a false claim
of having reached an exchange-tick price before the planner runs.
"""
from decimal import Decimal, InvalidOperation


def box_first_grid_already_completed(closed, formation):
    """Return True for completed or unprovable history (fail closed).

    Never use the still-forming exchange candle. A same-bar P1 and TAKE is
    ambiguous in OHLC; reject rather than guess intrabar event order.
    """
    try:
        direction = formation.direction
        f1 = Decimal(str(formation.fibonacci_1_0))
        f1618 = Decimal(str(formation.fibonacci_1_618))
        b = int(formation.anchor_end_index)
        end = int(formation.as_of_index)
        if direction not in ("LONG", "SHORT") or not 0 <= b < end < len(closed):
            return True
        if not f1.is_finite() or not f1618.is_finite() or f1 <= 0 or f1618 <= 0:
            return True
        displacement = f1618 - f1
        if (direction == "LONG" and displacement >= 0) or (
            direction == "SHORT" and displacement <= 0
        ):
            return True
        p1 = f1 + Decimal("0.75") * displacement
        take = f1 + Decimal("0.10") * displacement
        if p1 <= 0 or take <= 0:
            return True
        entered = False
        for i in range(b + 1, end + 1):
            candle = closed.iloc[i]
            high = Decimal(str(candle["high"]))
            low = Decimal(str(candle["low"]))
            if not high.is_finite() or not low.is_finite() or high < low or low <= 0:
                return True
            touched = low <= p1 if direction == "LONG" else high >= p1
            returned = high >= take if direction == "LONG" else low <= take
            if entered and returned:
                return True
            if touched:
                # Either this bar contained both events (unknown ordering) or
                # an earlier bar crossed the entry area.
                if returned:
                    return True
                entered = True
        return False
    except (AttributeError, KeyError, IndexError, TypeError, ValueError, InvalidOperation, OverflowError):
        return True
