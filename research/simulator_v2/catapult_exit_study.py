"""Research-only, causally fenced exit-policy *proposals* for Simulator V2.

No Robot, exchange, persistent store, order API, market subscription or writer.
A proposal is NOT permission to trade, a fill, or a profitability claim.
Prices/stops are unrounded previews: native tick, qty, protection reconciliation,
fees and slippage must be checked by an authorized execution owner later.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Regime = Literal["PROBE", "TREND_RETEST", "EXHAUSTION"]
Action = Literal[
    "INSUFFICIENT", "HOLD", "FULL_EXIT_PREVIEW", "PARTIAL_EXIT_PREVIEW",
    "TRAIL_TIGHTEN_PREVIEW",
]


def _decimal(value: Decimal, name: str, *, positive: bool = False) -> None:
    if (not isinstance(value, Decimal) or not value.is_finite()
            or (value <= 0 if positive else False)):
        raise ValueError("invalid " + name)


@dataclass(frozen=True)
class FrozenTrade:
    trade_id: str
    direction: Literal["LONG", "SHORT"]
    regime: Regime
    filled_at_ms: int
    entry_price: Decimal
    protective_stop: Decimal
    remaining_qty: Decimal
    entry_fee_for_remaining: Decimal
    protection_confirmed: bool

    def __post_init__(self) -> None:
        if (not self.trade_id or self.direction not in ("LONG", "SHORT")
                or self.regime not in ("PROBE", "TREND_RETEST", "EXHAUSTION")
                or type(self.filled_at_ms) is not int or self.filled_at_ms < 0):
            raise ValueError("invalid frozen trade identity or regime")
        for name in ("entry_price", "protective_stop", "remaining_qty"):
            _decimal(getattr(self, name), name, positive=True)
        _decimal(self.entry_fee_for_remaining, "entry_fee_for_remaining")
        if self.entry_fee_for_remaining < 0:
            raise ValueError("negative entry fee")
        if ((self.direction == "LONG" and self.protective_stop >= self.entry_price)
                or (self.direction == "SHORT" and self.protective_stop <= self.entry_price)):
            raise ValueError("original STOP must be risk-reducing relative to entry")


@dataclass(frozen=True)
class MarketReceipt:
    """Every timestamp is an actual observed event or host receipt, not fabricated OHLC."""

    trade_id: str
    decision_at_ms: int
    book_event_ms: int
    book_received_ms: int
    print_event_ms: int
    print_received_ms: int
    book_snapshot_delta_continuous: bool
    prints_covered: bool
    mark_price: Decimal
    best_price_since_fill: Decimal
    directional_print_delta_usdt: Decimal
    structure_invalidated: bool = False


@dataclass(frozen=True)
class StudySettings:
    """All thresholds are experiment inputs, never production settings."""

    timeouts_by_regime_ms: tuple[tuple[str, int], ...]
    minimum_followthrough_r: Decimal
    opposition_notional_usdt: Decimal
    start_trailing_at_r: Decimal
    trailing_gap_r: Decimal
    partial_fraction: Decimal
    exit_fee_rate: Decimal
    adverse_slippage_rate: Decimal
    max_data_age_ms: int

    def __post_init__(self) -> None:
        regimes = dict(self.timeouts_by_regime_ms)
        if (len(self.timeouts_by_regime_ms) != 3
                or set(regimes) != {"PROBE", "TREND_RETEST", "EXHAUSTION"}
                or any(type(v) is not int or v <= 0 for v in regimes.values())):
            raise ValueError("three explicit regime-specific timeouts required")
        for name in (
            "minimum_followthrough_r", "opposition_notional_usdt",
            "start_trailing_at_r", "trailing_gap_r", "partial_fraction",
            "exit_fee_rate", "adverse_slippage_rate",
        ):
            _decimal(getattr(self, name), name)
        if (self.minimum_followthrough_r <= 0 or self.opposition_notional_usdt <= 0
                or self.start_trailing_at_r <= 0 or self.trailing_gap_r <= 0
                or not 0 < self.partial_fraction < 1
                or not 0 <= self.exit_fee_rate < 1
                or not 0 <= self.adverse_slippage_rate < 1
                or type(self.max_data_age_ms) is not int or self.max_data_age_ms <= 0):
            raise ValueError("invalid research thresholds or cost assumptions")


@dataclass(frozen=True)
class ExitProposal:
    action: Action
    reason: str
    estimated_net_if_exited: Decimal | None = None
    fraction_to_close: Decimal | None = None
    unrounded_stop_preview: Decimal | None = None
    namespace: Literal["SIMULATION_RESEARCH_ONLY"] = "SIMULATION_RESEARCH_ONLY"
    trading_authorized: bool = False


def evaluate_exit(
    trade: FrozenTrade, receipt: MarketReceipt, settings: StudySettings,
) -> ExitProposal:
    """One immutable, no-side-effect decision preview at a declared host time.

    This does not simulate execution or guarantee receipt completeness. An
    upstream independent source attestor must provide the two continuity flags.
    In particular source-time-only historical exchange archives fail this gate.
    """
    def insufficient(why: str) -> ExitProposal:
        return ExitProposal("INSUFFICIENT", why)

    if not trade.protection_confirmed:
        return insufficient("no confirmed original STOP")
    if not receipt.trade_id or receipt.trade_id != trade.trade_id:
        return insufficient("trade identity mismatch")
    if (not receipt.book_snapshot_delta_continuous or not receipt.prints_covered):
        return insufficient("book or print receipt continuity unproven")
    times = (
        receipt.decision_at_ms, receipt.book_event_ms, receipt.book_received_ms,
        receipt.print_event_ms, receipt.print_received_ms,
    )
    if any(type(t) is not int or t < 0 for t in times):
        return insufficient("invalid receipt time")
    if (receipt.decision_at_ms < trade.filled_at_ms
            or receipt.book_event_ms < trade.filled_at_ms
            or receipt.print_event_ms < trade.filled_at_ms
            or receipt.book_received_ms < receipt.book_event_ms
            or receipt.print_received_ms < receipt.print_event_ms
            or receipt.book_received_ms > receipt.decision_at_ms
            or receipt.print_received_ms > receipt.decision_at_ms
            or receipt.decision_at_ms - receipt.book_received_ms > settings.max_data_age_ms
            or receipt.decision_at_ms - receipt.print_received_ms > settings.max_data_age_ms):
        return insufficient("future, pre-fill, stale or inconsistent host receipt")
    for name in ("mark_price", "best_price_since_fill"):
        value = getattr(receipt, name)
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            return insufficient("missing price evidence")
    if (not isinstance(receipt.directional_print_delta_usdt, Decimal)
            or not receipt.directional_print_delta_usdt.is_finite()
            or type(receipt.structure_invalidated) is not bool):
        return insufficient("invalid flow or structure evidence")

    sign = Decimal(1 if trade.direction == "LONG" else -1)
    if sign * (receipt.best_price_since_fill - trade.entry_price) < 0:
        return insufficient("no causal favorable-price history")
    if sign * (receipt.best_price_since_fill - receipt.mark_price) < 0:
        return insufficient("favorable-price history excludes current price")
    risk = abs(trade.entry_price - trade.protective_stop)
    favorable_r = sign * (receipt.best_price_since_fill - trade.entry_price) / risk
    qty = trade.remaining_qty
    projected_net = (
        sign * (receipt.mark_price - trade.entry_price) * qty
        - trade.entry_fee_for_remaining
        - receipt.mark_price * qty * (
            settings.exit_fee_rate + settings.adverse_slippage_rate
        )
    )
    elapsed = receipt.decision_at_ms - trade.filled_at_ms
    timed_out = (
        elapsed >= dict(settings.timeouts_by_regime_ms)[trade.regime]
        and favorable_r < settings.minimum_followthrough_r
    )
    opposed = (
        receipt.directional_print_delta_usdt <= -settings.opposition_notional_usdt
    )
    if receipt.structure_invalidated:
        return ExitProposal("FULL_EXIT_PREVIEW", "frozen structure invalidated",
                            estimated_net_if_exited=projected_net)
    if opposed or timed_out:
        if projected_net > 0:
            return ExitProposal("PARTIAL_EXIT_PREVIEW",
                                "fading but projected net-positive",
                                estimated_net_if_exited=projected_net,
                                fraction_to_close=settings.partial_fraction)
        return ExitProposal("FULL_EXIT_PREVIEW",
                            "adverse flow or no timely followthrough",
                            estimated_net_if_exited=projected_net)

    if (receipt.directional_print_delta_usdt > 0
            and favorable_r >= settings.start_trailing_at_r
            and projected_net > 0):
        distance = settings.trailing_gap_r * risk
        candidate = receipt.mark_price - sign * distance
        tightens = sign * (candidate - trade.protective_stop) > 0
        behind_market = sign * (receipt.mark_price - candidate) > 0
        if tightens and behind_market and candidate > 0:
            return ExitProposal("TRAIL_TIGHTEN_PREVIEW", "impulse persists",
                                estimated_net_if_exited=projected_net,
                                unrounded_stop_preview=candidate)
    return ExitProposal("HOLD", "no supported exit or tightening proposal",
                        estimated_net_if_exited=projected_net)
