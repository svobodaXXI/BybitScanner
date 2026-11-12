"""Causal market-flow features and optional PAPER entry gate for shared Robot.

Simulation and Robot reuse the same pure entry rule; only the existing PAPER
or virtual-exchange executor may create orders after its own risk/admission.
No numeric thresholds are calibrated from a single historical winner.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
ONE_THOUSAND = Decimal("1000")
BPS = Decimal("10000")


@dataclass(frozen=True, slots=True)
class FlowWindow:
    start_ms: int
    end_ms: int
    start_price: Decimal
    end_price: Decimal
    buy_notional_usdt: Decimal
    sell_notional_usdt: Decimal
    price_source: str = "TRADE"
    book_valid: bool = False
    bid_refill_ratio: Decimal | None = None
    ask_refill_ratio: Decimal | None = None

    def __post_init__(self) -> None:
        if (type(self.start_ms) is not int or type(self.end_ms) is not int
                or self.start_ms < 0 or self.start_ms >= self.end_ms):
            raise ValueError("invalid causal flow-window timestamps")
        if self.price_source not in ("TRADE", "MID"):
            raise ValueError("price source must be TRADE or MID")
        for name in ("start_price", "end_price", "buy_notional_usdt",
                     "sell_notional_usdt"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be finite Decimal")
            if value <= ZERO if name.endswith("price") else value < ZERO:
                raise ValueError(f"{name} out of range")
        if not isinstance(self.book_valid, bool):
            raise ValueError("book_valid must be boolean")
        for name in ("bid_refill_ratio", "ask_refill_ratio"):
            ratio = getattr(self, name)
            if ratio is not None:
                if not self.book_valid:
                    raise ValueError("refill requires integrity-checked L2 events")
                if not isinstance(ratio, Decimal) or not ratio.is_finite() or ratio < ZERO:
                    raise ValueError(f"{name} must be non-negative finite Decimal")

    @property
    def total_notional(self) -> Decimal:
        return self.buy_notional_usdt + self.sell_notional_usdt

    @property
    def delta_notional(self) -> Decimal:
        return self.buy_notional_usdt - self.sell_notional_usdt

    @property
    def delta_fraction(self) -> Decimal | None:
        total = self.total_notional
        return self.delta_notional / total if total > ZERO else None

    @property
    def price_change_bps(self) -> Decimal:
        return BPS * (self.end_price - self.start_price) / self.start_price

    @property
    def buy_impact_per_1000_usdt(self) -> Decimal | None:
        if self.buy_notional_usdt == ZERO:
            return None
        return max(ZERO, self.price_change_bps) * ONE_THOUSAND / self.buy_notional_usdt

    @property
    def sell_impact_per_1000_usdt(self) -> Decimal | None:
        if self.sell_notional_usdt == ZERO:
            return None
        return max(ZERO, -self.price_change_bps) * ONE_THOUSAND / self.sell_notional_usdt


@dataclass(frozen=True, slots=True)
class FlowTransition:
    known_at_ms: int
    current_delta_fraction: Decimal | None
    current_price_change_bps: Decimal
    buy_wave_accelerating: bool
    sell_wave_accelerating: bool
    sell_impact_fading: bool
    buy_impact_fading: bool
    bid_refill_observed: bool | None
    ask_refill_observed: bool | None
    sell_absorption_candidate: bool | None
    buy_absorption_candidate: bool | None


def compare_flow_windows(
    previous: FlowWindow, current: FlowWindow, *, decision_ms: int,
) -> FlowTransition:
    """Compare two equal-duration consecutive finished windows, never future data.

    All booleans are descriptive observations, not buy/sell authorization.
    "Absorption candidate" requires actual book-delta refill evidence, not
    inferred changes in aggregated depth or liquidation counts.
    """
    if not isinstance(previous, FlowWindow) or not isinstance(current, FlowWindow):
        raise TypeError("FlowWindow inputs required")
    if (type(decision_ms) is not int or decision_ms < current.end_ms
            or previous.end_ms != current.start_ms
            or previous.end_ms - previous.start_ms != current.end_ms - current.start_ms
            or previous.price_source != current.price_source):
        raise ValueError("non-causal, non-contiguous or mixed-source flow windows")
    before, now = previous.delta_fraction, current.delta_fraction

    buy_wave = (
        before is not None and now is not None and now > ZERO
        and now > before and current.buy_notional_usdt > previous.buy_notional_usdt
        and current.price_change_bps > ZERO
    )
    sell_wave = (
        before is not None and now is not None and now < ZERO
        and now < before and current.sell_notional_usdt > previous.sell_notional_usdt
        and current.price_change_bps < ZERO
    )
    sell_fading = (
        before is not None and now is not None and before < ZERO and now < ZERO
        and current.sell_notional_usdt >= previous.sell_notional_usdt
        and current.sell_impact_per_1000_usdt is not None
        and previous.sell_impact_per_1000_usdt is not None
        and current.sell_impact_per_1000_usdt < previous.sell_impact_per_1000_usdt
    )
    buy_fading = (
        before is not None and now is not None and before > ZERO and now > ZERO
        and current.buy_notional_usdt >= previous.buy_notional_usdt
        and current.buy_impact_per_1000_usdt is not None
        and previous.buy_impact_per_1000_usdt is not None
        and current.buy_impact_per_1000_usdt < previous.buy_impact_per_1000_usdt
    )

    bid_refill = (current.bid_refill_ratio > ZERO
                  if current.book_valid and current.bid_refill_ratio is not None else None)
    ask_refill = (current.ask_refill_ratio > ZERO
                  if current.book_valid and current.ask_refill_ratio is not None else None)
    return FlowTransition(
        known_at_ms=decision_ms,
        current_delta_fraction=now,
        current_price_change_bps=current.price_change_bps,
        buy_wave_accelerating=buy_wave,
        sell_wave_accelerating=sell_wave,
        sell_impact_fading=sell_fading,
        buy_impact_fading=buy_fading,
        bid_refill_observed=bid_refill,
        ask_refill_observed=ask_refill,
        sell_absorption_candidate=(sell_fading and bid_refill) if bid_refill is not None else None,
        buy_absorption_candidate=(buy_fading and ask_refill) if ask_refill is not None else None,
    )


def permits_paper_entry(direction: str, transition: FlowTransition | None) -> bool:
    """Research option for existing protected PAPER/virtual Robot entries.

    A completed, source-validated flow transition is required: no history,
    opposite pressure or unsupported direction cannot authorize an entry.
    This pure policy produces no trade, bypass, stop or alternate executor.
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError("known Robot entry direction required")
    if transition is None:
        return False
    if not isinstance(transition, FlowTransition):
        raise TypeError("completed shared Robot flow transition required")
    return (
        transition.buy_wave_accelerating if direction == "LONG"
        else transition.sell_wave_accelerating
    )


@dataclass(frozen=True, slots=True)
class TakerPrint:
    """One exchange execution; NOT evidence of one independent market order."""

    symbol: str
    trade_id: str
    event_ms: int
    side: str
    price: Decimal
    size_base: Decimal

    def __post_init__(self) -> None:
        if (not isinstance(self.symbol, str) or not self.symbol.endswith("USDT")
                or not self.symbol.isalnum() or not isinstance(self.trade_id, str)
                or not self.trade_id or type(self.event_ms) is not int
                or self.event_ms < 0 or self.side not in ("Buy", "Sell")):
            raise ValueError("invalid Bybit public execution identity/time/side")
        for field in ("price", "size_base"):
            value = getattr(self, field)
            if not isinstance(value, Decimal) or not value.is_finite() or value <= ZERO:
                raise ValueError(f"{field} must be positive finite Decimal")

    @property
    def notional_usdt(self) -> Decimal:
        return self.price * self.size_base


def normalize_bybit_taker_print(raw: dict, *, layout: str) -> TakerPrint:
    """Normalize native Bybit publicTrade or daily public trade CSV, preserving taker side.

    The caller owns snapshot/reconnect integrity and authoritative provenance.
    History without a side cannot be used to infer buy/sell activity.
    """
    from decimal import InvalidOperation, ROUND_FLOOR

    if not isinstance(raw, dict) or layout not in ("WS_PUBLIC_TRADE", "PUBLIC_TRADE_ARCHIVE"):
        raise ValueError("explicit Bybit public-trade layout required")
    if layout == "WS_PUBLIC_TRADE":
        fields = ("s", "i", "T", "S", "p", "v")
        if any(field not in raw for field in fields) or type(raw["T"]) is not int:
            raise ValueError("malformed Bybit WebSocket public trade")
        event_ms = raw["T"]
        values = (raw["s"], raw["i"], raw["S"], raw["p"], raw["v"])
    else:
        fields = ("symbol", "trdMatchID", "timestamp", "side", "price", "size")
        if any(field not in raw for field in fields):
            raise ValueError("public archive lacks required execution side")
        try:
            stamp = Decimal(str(raw["timestamp"]))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError("invalid Bybit archive execution timestamp") from exc
        if not stamp.is_finite() or stamp < ZERO:
            raise ValueError("invalid Bybit archive execution timestamp")
        event_ms = int((stamp * 1000).to_integral_value(rounding=ROUND_FLOOR))
        values = (raw["symbol"], raw["trdMatchID"], raw["side"], raw["price"], raw["size"])
    try:
        price, size = (Decimal(str(value)) for value in values[3:])
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid Bybit execution price or quantity") from exc
    return TakerPrint(str(values[0]), str(values[1]), event_ms, str(values[2]), price, size)


def aggregate_taker_prints(
    prints: tuple[TakerPrint, ...], *, symbol: str, start_ms: int, end_ms: int,
) -> FlowWindow | None:
    """Aggregate only already available, verified, time-ordered prints into one window.

    Empty intervals yield UNKNOWN (None), not synthetic zero flow or prices.
    The caller must establish that the exchange subscription/archive has no gaps.
    """
    if (type(start_ms) is not int or type(end_ms) is not int
            or start_ms < 0 or end_ms <= start_ms or not symbol):
        raise ValueError("invalid symbol or causal observation interval")
    if not isinstance(prints, tuple) or any(not isinstance(p, TakerPrint) for p in prints):
        raise TypeError("normalized tuple of public executions required")
    if not prints:
        return None
    seen: set[str] = set()
    last_ms = -1
    buy, sell = ZERO, ZERO
    for trade in prints:
        if (trade.symbol != symbol or trade.trade_id in seen
                or not start_ms <= trade.event_ms < end_ms
                or trade.event_ms < last_ms):
            raise ValueError("foreign, duplicate, unordered or future execution")
        seen.add(trade.trade_id)
        last_ms = trade.event_ms
        if trade.side == "Buy":
            buy += trade.notional_usdt
        else:
            sell += trade.notional_usdt
    return FlowWindow(
        start_ms=start_ms, end_ms=end_ms,
        start_price=prints[0].price, end_price=prints[-1].price,
        buy_notional_usdt=buy, sell_notional_usdt=sell,
    )


class CompletedFlowObserver:
    """One bounded causal flow cursor used by Robot and historical SIMULATION.

    The source adapter must prove that all prints in each completed window were
    available before observation; a source label alone is not that proof.
    No order authority, background polling or full-tape memory is retained.
    """

    def __init__(self, *, symbol: str, window_ms: int) -> None:
        if (not isinstance(symbol, str) or not symbol.isalnum()
                or not symbol.endswith("USDT") or type(window_ms) is not int
                or window_ms <= 0):
            raise ValueError("invalid flow observer symbol/window")
        self.symbol = symbol
        self.window_ms = window_ms
        self._previous: FlowWindow | None = None
        self._source_id: str | None = None
        self._last_end_ms: int | None = None
        self.last_transition: FlowTransition | None = None

    def observe_closed(
        self, prints: tuple[TakerPrint, ...], *, start_ms: int, end_ms: int,
        observed_at_ms: int, source_id: str,
    ) -> FlowTransition | None:
        """Advance exactly one finished trade window; missing trades stay unknown.

        A gap or changed source resets comparisons. Invalid inputs do not
        advance the cursor. Caller must independently prove data completeness.
        """
        if (type(start_ms) is not int or type(end_ms) is not int
                or type(observed_at_ms) is not int or start_ms < 0
                or end_ms - start_ms != self.window_ms
                or start_ms % self.window_ms or observed_at_ms < end_ms
                or (self._last_end_ms is not None and start_ms < self._last_end_ms)):
            raise ValueError("incomplete, overlapping or future flow window")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("nonempty source identity required")
        current = aggregate_taker_prints(
            prints, symbol=self.symbol, start_ms=start_ms, end_ms=end_ms,
        )
        previous = (
            self._previous if self._source_id == source_id
            and self._last_end_ms == start_ms else None
        )
        transition = (
            compare_flow_windows(previous, current, decision_ms=observed_at_ms)
            if previous is not None and current is not None else None
        )
        self._previous = current
        self._source_id = source_id
        self._last_end_ms = end_ms
        self.last_transition = transition
        return transition
