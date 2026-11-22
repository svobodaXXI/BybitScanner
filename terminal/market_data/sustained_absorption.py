"""Generic fixed-level liquidity persistence research (Box/Wedge).

Input is a caller-reconstructed stream of complete displayed book states
from ONE archive/connection generation with genuinely consecutive normalized
update IDs. Do not translate exchange seq gaps into invented consecutive IDs.
This module cannot establish that the caller's source is complete, cross-
stream clock order is accurate, or that a revision corresponds to a fill.
It never creates a signal, order, or Robot admission decision.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from robot_entry_flow_evidence import TakerPrint

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ReconstructedBook:
    symbol: str
    generation: int
    update_id: int
    event_ms: int
    available_at_ms: int
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]


@dataclass(frozen=True, slots=True)
class AvailablePrint:
    print: TakerPrint
    generation: int
    available_at_ms: int


@dataclass(frozen=True, slots=True)
class RecoveryWindow:
    start_ms: int
    end_ms: int
    opposing_notional: Decimal
    compatible_print_notional: Decimal
    compatible_recovery_notional: Decimal

    @property
    def recovery_fraction(self) -> Decimal | None:
        if self.opposing_notional == ZERO:
            return None
        return self.compatible_recovery_notional / self.opposing_notional


@dataclass(frozen=True, slots=True)
class AbsorptionObservation:
    symbol: str
    direction: str
    generation: int
    decision_ms: int
    frozen_levels: tuple[Decimal, ...]
    initial_depth_notional: Decimal
    minimum_depth_notional: Decimal
    final_depth_notional: Decimal
    adverse_quote_break: bool
    windows: tuple[RecoveryWindow, ...]
    source_complete: bool = field(default=False, init=False)
    trading_authorized: bool = field(default=False, init=False)

    @property
    def minimum_depth_fraction(self) -> Decimal:
        return self.minimum_depth_notional / self.initial_depth_notional

    @property
    def repeated_recovery_observed(self) -> bool:
        return sum(w.compatible_recovery_notional > ZERO for w in self.windows) >= 2


def _levels(values):
    if not isinstance(values, tuple) or not values:
        raise ValueError("missing displayed side")
    result = {}
    for p, q in values:
        if (not isinstance(p, Decimal) or not isinstance(q, Decimal)
                or not p.is_finite() or not q.is_finite() or p <= ZERO or q <= ZERO
                or p in result):
            raise ValueError("invalid or duplicate displayed level")
        result[p] = q
    return result


def observe_sustained_absorption(
    books: tuple[ReconstructedBook, ...],
    prints: tuple[AvailablePrint, ...],
    *,
    symbol: str,
    direction: str,
    generation: int,
    start_ms: int,
    end_ms: int,
    decision_ms: int,
    window_ms: int,
    max_quote_age_ms: int,
    level_count: int = 5,
) -> AbsorptionObservation | None:
    """Describe fixed-band persistence under observed contra-side trades.

    Books contain the last complete pre-start state and subsequent complete
    states through the interval (not orphan deltas). Both streams are supplied
    in event-time order with explicit availability. Historical archives can
    use a declared simulated availability policy, never a real receipt claim.
    Equal-millisecond cross-stream ordering is ambiguous: those prints count
    in total pressure, but get no matching credit. Credit follows a strictly
    ordered same-level print -> displayed decrease -> displayed increase.
    No credit is reused across levels or subwindows. Counts measure compatible
    aggregate revisions, NOT passive executions or guaranteed replenishment.
    No default trading thresholds: all fractions, breaks, missing pressure and
    repeated windows stay descriptive.
    """
    if (direction not in ("LONG", "SHORT") or not isinstance(symbol, str)
            or not symbol.endswith("USDT") or not symbol.isalnum()
            or any(type(v) is not int for v in (
                generation, start_ms, end_ms, decision_ms, window_ms,
                max_quote_age_ms, level_count,
            )) or generation < 0 or not 0 <= start_ms < end_ms <= decision_ms
            or window_ms <= 0 or (end_ms-start_ms) % window_ms
            or (end_ms-start_ms) // window_ms < 2 or max_quote_age_ms < 0
            or level_count < 1 or not isinstance(books, tuple) or len(books) < 2
            or not isinstance(prints, tuple)):
        return None
    try:
        states = []
        previous = None
        for b in books:
            if (not isinstance(b, ReconstructedBook) or b.symbol != symbol
                    or type(b.generation) is not int or b.generation != generation
                    or type(b.update_id) is not int or b.update_id < 0
                    or type(b.event_ms) is not int
                    or type(b.available_at_ms) is not int
                    or not 0 <= b.event_ms < end_ms
                    or not b.event_ms <= b.available_at_ms <= decision_ms):
                return None
            if previous is not None and (
                b.update_id != previous.update_id + 1
                or b.event_ms < previous.event_ms
                or b.available_at_ms < previous.available_at_ms
                or b.event_ms - previous.event_ms > max_quote_age_ms
            ):
                return None
            bids, asks = _levels(b.bids), _levels(b.asks)
            if max(bids) >= min(asks):
                return None
            states.append(bids if direction == "LONG" else asks)
            previous = b
        if (not books[0].event_ms < start_ms <= books[1].event_ms
                or books[0].available_at_ms > start_ms
                or start_ms-books[0].event_ms > max_quote_age_ms
                or end_ms-books[-1].event_ms > max_quote_age_ms):
            return None
        seen = set()
        last = -1
        for item in prints:
            if not isinstance(item, AvailablePrint) or not isinstance(item.print, TakerPrint):
                return None
            p = item.print
            if (p.symbol != symbol or type(item.generation) is not int
                    or item.generation != generation or p.trade_id in seen
                    or not start_ms <= p.event_ms < end_ms
                    or p.event_ms < last or type(item.available_at_ms) is not int
                    or not p.event_ms <= item.available_at_ms <= decision_ms):
                return None
            seen.add(p.trade_id)
            last = p.event_ms
        initial = states[0]
        levels = tuple(sorted(initial, reverse=direction == "LONG")[:level_count])
        if len(levels) != level_count:
            return None
        sign = 1 if direction == "LONG" else -1
        edge = levels[-1]
        def depth(state):
            return sum((p*state.get(p, ZERO) for p in levels), ZERO)
        initial_depth = depth(initial)
        minimum_depth = initial_depth
        broke = False
        n = (end_ms-start_ms)//window_ms
        totals = [[ZERO, ZERO, ZERO] for _ in range(n)]
        # Sort only within a bounded caller-supplied interval. Equal-time
        # prints on book update times receive no credit (order unproven).
        book_times = {b.event_ms for b in books}
        events = [(b.event_ms, 0, j) for j,b in enumerate(books) if j]
        events.extend((p.print.event_ms, 1, j) for j,p in enumerate(prints))
        events.sort()
        prior = 0
        last_available = books[0].available_at_ms
        current_slice = -1
        pending = {}
        depleted = {}
        for time, kind, j in events:
            available = books[j].available_at_ms if kind == 0 else prints[j].available_at_ms
            if available < last_available:
                return None  # source event and availability order disagree
            last_available = available
            k = min((time-start_ms)//window_ms, n-1)
            if k != current_slice:
                pending.clear()
                depleted.clear()
                current_slice = k
            if kind == 1:
                p = prints[j].print
                if p.side != ("Sell" if direction == "LONG" else "Buy"):
                    continue
                totals[k][0] += p.notional_usdt
                state = states[prior]
                best = max(state) if direction == "LONG" else min(state)
                if (time not in book_times and time-books[prior].event_ms <= max_quote_age_ms
                        and books[prior].available_at_ms <= prints[j].available_at_ms
                        and p.price == best and p.price in levels):
                    totals[k][1] += p.notional_usdt
                    # Store unmatched print quantity once by price. Book
                    # revisions at the same price can consume it only once.
                    pending[p.price] = pending.get(p.price, ZERO) + p.size_base
                continue
            old, new = states[prior], states[j]
            for p in levels:
                change = new.get(p, ZERO)-old.get(p, ZERO)
                if change < ZERO:
                    match = min(-change, pending.get(p, ZERO))
                    pending[p] = pending.get(p, ZERO)-match
                    depleted[p] = depleted.get(p, ZERO)+match
                elif change > ZERO and books[j].event_ms > books[prior].event_ms:
                    match = min(change, depleted.get(p, ZERO))
                    depleted[p] = depleted.get(p, ZERO)-match
                    totals[k][2] += p*match
            prior = j
            minimum_depth = min(minimum_depth, depth(new))
            best = max(new) if direction == "LONG" else min(new)
            if sign*(best-edge) < ZERO:
                broke = True
        windows = tuple(RecoveryWindow(
            start_ms+i*window_ms, start_ms+(i+1)*window_ms, *t
        ) for i,t in enumerate(totals))
        return AbsorptionObservation(
            symbol, direction, generation, decision_ms, levels,
            initial_depth, minimum_depth, depth(states[prior]), broke, windows
        )
    except (ValueError, TypeError, ArithmeticError, AttributeError):
        return None
