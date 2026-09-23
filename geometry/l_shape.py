"""
geometry.l_shape

Autonomous offline detector for the L-shaped formation (BACKLOG.md G6, owner
definition from the B2USDT 5m chart, 2026-09-23):

    impulse -> local HIGH -> trough ("впадина") -> breakout of that HIGH

LONG  : a rising impulse prints the local HIGH H; the following trough candles
        never trade above H; the first closed candle whose high exceeds H is the
        breakout and the decision candle.
SHORT : the exact mirror around a local LOW.

The impulse starts at the nearest confirmed reversal LOW before H (the
nearest reversal HIGH for SHORT), never at a mere window minimum.

There is no narrow-consolidation condition: the trough may be any shape as
long as it stays strictly below H (LONG) and above the impulse origin.

Target (LONG): U is the body top, max(open, close), of the trough candle with
the lowest low (the earliest such candle on a tie); D = H - U; T = H + D;
potential = 100 * (T / H - 1). SHORT mirrors it with the body bottom of the
trough candle with the highest high and T = L - D.

Responsibility:
- read already loaded closed candles and report one formation or nothing;
- Scanner signal eligibility for a detected formation: potential of at least
  0.8% from the breakout level and a reference STOP with reward/risk of at
  least 2:1 (``l_shape_signal_plan``), separate from the geometry.

Not responsible for:
- trading decisions, Robot admission, orders, Telegram, Scanner wiring;
- a generic pattern engine, ranking or scoring.

Only candles up to ``as_of_index`` (the breakout candle) are read, so a later
bar can never change an earlier verdict and a confirmed historical anchor is
never re-derived from future data.
"""

from __future__ import annotations

from dataclasses import dataclass

from confirmation import calculate_atr

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"


@dataclass(frozen=True)
class LShapeParameters:
    """Named, tunable thresholds. Deliberately coarse: no per-ticker fitting.

    atr_period
        Period of the existing project ATR (``confirmation.calculate_atr``).
    impulse_min_bars / impulse_max_bars
        Bounded search window for the impulse leg into the local extreme.
    pivot_left_bars / pivot_right_bars
        The impulse origin is the nearest reversal LOW (HIGH for SHORT) before
        the extreme, strictly beyond this many candles on each side: the same
        rule and defaults as ``pivots.find_pivots``.
    impulse_min_atr_multiple
        The impulse range (origin extreme to local HIGH/LOW) must be at least
        this many ATR: the vertical stroke of the L.
    impulse_min_bar_progress_atr
        Average impulse range per bar, in ATR units. This is what stops a long
        flat prelude from being absorbed into the impulse.
    trough_min_bars / trough_max_bars
        Bounded number of trough candles strictly between the local extreme
        and the breakout candle.
    """

    atr_period: int = 14
    impulse_min_bars: int = 3
    impulse_max_bars: int = 30
    impulse_min_atr_multiple: float = 3.0
    impulse_min_bar_progress_atr: float = 0.5
    pivot_left_bars: int = 3
    pivot_right_bars: int = 3
    trough_min_bars: int = 3
    trough_max_bars: int = 30


DEFAULT_PARAMETERS = LShapeParameters()


@dataclass(frozen=True)
class LShapeFormation:
    """One detected formation, in source candle indices."""

    direction: str
    start_index: int              # the impulse origin: the figure starts here
    impulse_start_index: int
    extreme_index: int            # the local HIGH (LONG) / LOW (SHORT) candle
    trough_start_index: int
    trough_end_index: int
    trough_index: int             # the candle whose body edge gives U
    breakout_index: int
    breakout_level: float         # H (LONG) / L (SHORT)
    trough_edge: float            # U
    trough_extreme: float         # the trough's actual low (LONG) / high (SHORT)
    depth: float                  # D = |H - U|
    target_level: float           # T = H + D (LONG) / L - D (SHORT)
    potential_percent: float      # measured from the breakout level
    impulse_origin_price: float
    impulse_range: float
    atr: float
    impulse_atr_multiple: float
    impulse_bar_progress_atr_multiple: float
    as_of_index: int              # == breakout_index


def _series(candles):
    """Accept a DataFrame or any sequence of OHLC mappings, read-only."""
    if candles is None:
        return None
    if hasattr(candles, "to_dict"):
        rows = candles.to_dict("records")
    else:
        rows = list(candles)
    if not rows:
        return None
    try:
        return [
            (
                float(row["open"]),
                float(row["high"]),
                float(row["low"]),
                float(row["close"]),
            )
            for row in rows
        ]
    except (KeyError, TypeError, ValueError):
        return None


def _atr_values(candles, period):
    """The project ATR is a trailing rolling mean: value i reads rows <= i."""
    try:
        values = calculate_atr(candles, period=period)
        return [float(value) for value in values]
    except Exception:
        return None


def _valid_atr(atr_values, index):
    value = atr_values[index]
    if value != value or value <= 0:       # NaN or non-positive
        return None
    return value


def detect_l_shape(
    candles,
    *,
    as_of_index=None,
    parameters: LShapeParameters = DEFAULT_PARAMETERS,
):
    """Return the L-shape whose breakout candle is ``as_of_index``, or None.

    ``as_of_index`` defaults to the last supplied candle. Nothing after it is
    read, so calling this on a longer frame with the same ``as_of_index``
    produces the same answer as calling it on the truncated prefix.
    """
    rows = _series(candles)
    if rows is None:
        return None
    last = len(rows) - 1 if as_of_index is None else int(as_of_index)
    if last < 0 or last >= len(rows):
        return None
    atr_values = _atr_values(candles, parameters.atr_period)
    if atr_values is None:
        return None
    return _detect_at(rows, atr_values, last, parameters)


def find_latest_l_shape(
    candles,
    *,
    parameters: LShapeParameters = DEFAULT_PARAMETERS,
):
    """Return the most recent formation whose breakout lies in ``candles``.

    Every breakout candidate is evaluated exactly as ``detect_l_shape`` would
    at that breakout candle, so a later bar never alters it; a breakout a few
    candles before the scan is therefore not missed.
    """
    return next(iter_l_shapes(candles, parameters=parameters), None)


def iter_l_shapes(
    candles,
    *,
    parameters: LShapeParameters = DEFAULT_PARAMETERS,
):
    """Yield every formation in ``candles``, most recent breakout first.

    Structural detection only; signal admission is ``l_shape_signal_plan``.
    """
    rows = _series(candles)
    if rows is None:
        return
    atr_values = _atr_values(candles, parameters.atr_period)
    if atr_values is None:
        return
    for as_of in range(len(rows) - 1, -1, -1):
        formation = _detect_at(rows, atr_values, as_of, parameters)
        if formation is not None:
            yield formation


# --- Scanner signal eligibility (owner decision 2026-09-23) -----------------
# Separate trade-plan geometry: it never moves the formation anchors or target
# and never rejects a structure; it only decides whether a detected formation
# is a deliverable Scanner signal. L-shape only; no Robot/order semantics.

SIGNAL_MIN_POTENTIAL_PERCENT = 0.8
SIGNAL_MIN_REWARD_RISK = 2.0

STOP_STRUCTURAL = "STRUCTURAL"
STOP_RATIO_FALLBACK = "RATIO_FALLBACK"


@dataclass(frozen=True)
class LShapeSignalPlan:
    """Reference STOP and admission verdict for one formation.

    ``reference`` is the breakout level H (L for SHORT) for both target and
    STOP distances. The structural STOP sits at the trough's actual extreme;
    no tick/fee buffer is known on the Scanner side, so this plan is an
    indication only and never an executable order.
    """

    reference: float
    target: float
    stop: float
    stop_kind: str
    structural_stop: float
    reward: float
    risk: float
    reward_risk: float
    potential_percent: float
    eligible: bool
    rejection: str | None


def l_shape_signal_plan(formation):
    """Compute the reference STOP and whether the formation may be signalled."""
    reference = formation.breakout_level
    target = formation.target_level
    structural_stop = formation.trough_extreme
    reward = abs(target - reference)
    structural_risk = abs(reference - structural_stop)
    adverse = -1.0 if formation.direction == DIRECTION_LONG else 1.0
    if 0 < structural_risk <= reward / 2:
        stop, stop_kind, risk = structural_stop, STOP_STRUCTURAL, structural_risk
    else:
        # Default ratio-based STOP: half the target distance, adverse side.
        risk = reward / 2
        stop, stop_kind = reference + adverse * risk, STOP_RATIO_FALLBACK
    reward_risk = reward / risk if risk > 0 else 0.0
    potential = abs(formation.potential_percent)

    rejection = None
    if potential < SIGNAL_MIN_POTENTIAL_PERCENT:
        rejection = "potential_below_minimum"
    elif risk <= 0 or stop <= 0:
        rejection = "stop_not_viable"
    elif reward_risk < SIGNAL_MIN_REWARD_RISK:
        rejection = "reward_risk_below_minimum"
    return LShapeSignalPlan(
        reference=reference,
        target=target,
        stop=stop,
        stop_kind=stop_kind,
        structural_stop=structural_stop,
        reward=reward,
        risk=risk,
        reward_risk=reward_risk,
        potential_percent=potential,
        eligible=rejection is None,
        rejection=rejection,
    )


def _detect_at(rows, atr_values, breakout, parameters):
    atr = _valid_atr(atr_values, breakout)
    if atr is None:
        return None
    # The highest local HIGH (lowest local LOW) the breakout candle clears is
    # the most prominent one; it is tried first and the first valid one wins.
    for direction in (DIRECTION_LONG, DIRECTION_SHORT):
        candidates = _extreme_candidates(rows, breakout, direction, parameters)
        for extreme in candidates:
            formation = _qualify(rows, atr, parameters, direction, extreme, breakout)
            if formation is not None:
                return formation
    return None


def _extreme_candidates(rows, breakout, direction, parameters):
    """Candles the breakout clears while every candle in between stays inside.

    LONG: high[extreme] < high[breakout] and every trough high <= high[extreme].
    Ordered most prominent first (highest HIGH / lowest LOW).
    """
    sign = 1.0 if direction == DIRECTION_LONG else -1.0
    edge = 1 if direction == DIRECTION_LONG else 2      # high / low column

    def value(index):
        return sign * rows[index][edge]

    breakout_value = value(breakout)
    found = []
    inner_max = float("-inf")    # most extreme trough value seen so far
    first = max(0, breakout - parameters.trough_max_bars - 1)
    for extreme in range(breakout - 1, first - 1, -1):
        trough_bars = breakout - extreme - 1
        level = value(extreme)
        if (
            trough_bars >= parameters.trough_min_bars
            and level < breakout_value
            and inner_max <= level
        ):
            found.append(extreme)
        inner_max = max(inner_max, level)
    found.sort(key=lambda index: (-value(index), index))
    return found


def _qualify(rows, atr, parameters, direction, extreme, breakout):
    long_side = direction == DIRECTION_LONG
    opens = [row[0] for row in rows]
    highs = [row[1] for row in rows]
    lows = [row[2] for row in rows]
    closes = [row[3] for row in rows]

    origin = _reversal_origin(
        lows if long_side else [-value for value in highs], extreme, parameters,
    )
    if origin is None:
        return None
    if long_side:
        level = highs[extreme]
        origin_price = lows[origin]
        # The local HIGH must be the impulse extreme, printed at its end.
        if _last_index_of_max(highs, origin, extreme) != extreme:
            return None
    else:
        level = lows[extreme]
        origin_price = highs[origin]
        if _last_index_of_min(lows, origin, extreme) != extreme:
            return None

    impulse_bars = extreme - origin + 1
    if impulse_bars < parameters.impulse_min_bars:
        return None
    impulse_range = abs(level - origin_price)
    if impulse_range <= 0:
        return None
    if impulse_range < parameters.impulse_min_atr_multiple * atr:
        return None
    bar_progress = impulse_range / impulse_bars
    if bar_progress < parameters.impulse_min_bar_progress_atr * atr:
        return None

    trough_start = extreme + 1
    trough_end = breakout - 1
    trough = range(trough_start, trough_end + 1)
    if long_side:
        trough_index = min(trough, key=lambda index: (lows[index], index))
        # The trough must not erase the impulse: otherwise it is a reversal.
        if lows[trough_index] <= origin_price:
            return None
        trough_edge = max(opens[trough_index], closes[trough_index])
        depth = level - trough_edge
        target = level + depth
    else:
        trough_index = min(trough, key=lambda index: (-highs[index], index))
        if highs[trough_index] >= origin_price:
            return None
        trough_edge = min(opens[trough_index], closes[trough_index])
        depth = trough_edge - level
        target = level - depth
    if depth <= 0 or target <= 0:
        return None

    return LShapeFormation(
        direction=direction,
        start_index=origin,
        impulse_start_index=origin,
        extreme_index=extreme,
        trough_start_index=trough_start,
        trough_end_index=trough_end,
        trough_index=trough_index,
        breakout_index=breakout,
        breakout_level=level,
        trough_edge=trough_edge,
        trough_extreme=lows[trough_index] if long_side else highs[trough_index],
        depth=depth,
        target_level=target,
        potential_percent=100.0 * (target / level - 1.0),
        impulse_origin_price=origin_price,
        impulse_range=impulse_range,
        atr=atr,
        impulse_atr_multiple=impulse_range / atr,
        impulse_bar_progress_atr_multiple=bar_progress / atr,
        as_of_index=breakout,
    )


def _reversal_origin(lows, extreme, parameters):
    """Nearest confirmed reversal LOW before the extreme, or None.

    Same pivot rule as ``pivots.find_pivots``: the low is strictly below the
    ``pivot_left_bars`` lows before it and the ``pivot_right_bars`` lows after
    it, all confirmed no later than the extreme. It must also stay the lowest
    low up to the extreme, so the rise into the HIGH starts there. SHORT
    passes negated highs. There is no fallback to a window minimum.
    """
    left = parameters.pivot_left_bars
    right = parameters.pivot_right_bars
    first = max(left, extreme - parameters.impulse_max_bars + 1)
    for origin in range(extreme - right, first - 1, -1):
        low = lows[origin]
        if (
            low < min(lows[origin - left:origin])
            and low < min(lows[origin + 1:extreme + 1])
        ):
            return origin
    return None


def _last_index_of_min(values, start, end):
    """Most recent bar printing the window minimum: the origin of a rise."""
    best_index = start
    best_value = values[start]
    for index in range(start, end + 1):
        if values[index] <= best_value:
            best_value = values[index]
            best_index = index
    return best_index


def _last_index_of_max(values, start, end):
    """Most recent bar printing the window maximum: the origin of a drop."""
    best_index = start
    best_value = values[start]
    for index in range(start, end + 1):
        if values[index] >= best_value:
            best_value = values[index]
            best_index = index
    return best_index
