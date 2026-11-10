"""Isolated MARKET and GTC LIMIT fill adapter for historical SIMULATION only.

Market fills use the following M1 OPEN after submission. Limit orders remain
pending until the next closed M1 proves *strict trade-through* (or the next
OPEN is already marketable). A trade-through is an explicit deterministic
OHLC fill assumption, NOT proof of venue queue priority or real execution.
LIMIT fills occur at their stated limit price, never a fictitious improvement.
A marketable opening uses taker fees; intrabar limit fill uses maker fees.

Only one pending virtual order, full fills, one-way position, no leverage,
margin, depth, partial fills, STOP/TAKE or real trading endpoints. Robot owns
entry eligibility and protection; this module owns only execution assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MINUTE_MS
from research.simulator_v2.virtual_account import VirtualAccount, VirtualFill, IDENTITY


@dataclass(frozen=True)
class MarketRequest:
    """Already-admitted instruction; this adapter makes no trading decision."""

    order_id: str
    side: str
    quantity: Decimal
    namespace: str = "SIMULATION"

    def __post_init__(self) -> None:
        if self.namespace != "SIMULATION":
            raise ValueError("only internal SIMULATION orders are permitted")
        if not isinstance(self.order_id, str) or not IDENTITY.fullmatch(self.order_id):
            raise ValueError("invalid virtual order identity")
        if self.side not in ("BUY", "SELL"):
            raise ValueError("invalid virtual side")
        if (
            not isinstance(self.quantity, Decimal)
            or not self.quantity.is_finite()
            or self.quantity <= 0
        ):
            raise ValueError("positive finite Decimal quantity required")


@dataclass(frozen=True)
class LimitRequest:
    """Already-admitted SIMULATION-only full-size GTC LIMIT, not Robot policy."""

    order_id: str
    side: str
    quantity: Decimal
    limit_price: Decimal
    namespace: str = "SIMULATION"

    def __post_init__(self) -> None:
        # Reuse MarketRequest identity, side, size and namespace validation.
        MarketRequest(self.order_id, self.side, self.quantity, self.namespace)
        if (not isinstance(self.limit_price, Decimal)
                or not self.limit_price.is_finite()
                or self.limit_price <= 0):
            raise ValueError("positive finite Decimal LIMIT price required")


@dataclass(frozen=True)
class OrderEvent:
    order_id: str
    kind: str  # SUBMITTED, AMENDED, CANCELLED, FILLED
    virtual_time_ms: int
    namespace: str = "SIMULATION"
    order_type: str = "MARKET"


class VirtualExchange:
    """Single-run local exchange adapter, with no network or filesystem IO.

    Treat on_closed_minute() as the first step for each newly closed candle,
    then allow Robot to submit() using that candle's virtual close timestamp.
    A new order cannot fill on that same candle. A failed account append leaves
    the exchange's minute cursor and pending order unchanged, so the exact
    failed minute may be retried after the cause is fixed.
    """

    def __init__(
        self, *, account: VirtualAccount,
        taker_fee_rate: Decimal = Decimal("0.0006"),
        maker_fee_rate: Decimal = Decimal("0.0002"),
    ) -> None:
        if not isinstance(account, VirtualAccount):
            raise TypeError("a dedicated SIMULATION VirtualAccount is required")
        if (
            not isinstance(taker_fee_rate, Decimal)
            or not taker_fee_rate.is_finite()
            or taker_fee_rate < 0
            or taker_fee_rate >= 1
        ):
            raise ValueError("invalid virtual taker fee rate")
        if (not isinstance(maker_fee_rate, Decimal)
                or not maker_fee_rate.is_finite()
                or maker_fee_rate < 0 or maker_fee_rate >= 1):
            raise ValueError("invalid virtual maker fee rate")
        self.account = account
        self.taker_fee_rate = taker_fee_rate
        self.maker_fee_rate = maker_fee_rate
        self._last_close_ms: int | None = None
        self._pending: tuple[MarketRequest | LimitRequest, int] | None = None
        self._seen_order_ids: set[str] = set()
        self._events: list[OrderEvent] = []

    @property
    def virtual_time_ms(self) -> int | None:
        return self._last_close_ms

    @property
    def pending(self) -> MarketRequest | LimitRequest | None:
        return self._pending[0] if self._pending is not None else None

    @property
    def events(self) -> tuple[OrderEvent, ...]:
        return tuple(self._events)

    def submit(self, request: MarketRequest, *, submitted_at_ms: int) -> None:
        if not isinstance(request, MarketRequest):
            raise TypeError("MarketRequest required")
        self._submit(request, submitted_at_ms=submitted_at_ms)

    def submit_limit(self, request: LimitRequest, *, submitted_at_ms: int) -> None:
        if not isinstance(request, LimitRequest):
            raise TypeError("LimitRequest required")
        self._submit(request, submitted_at_ms=submitted_at_ms)

    def _submit(
        self, request: MarketRequest | LimitRequest, *, submitted_at_ms: int,
    ) -> None:
        if self._last_close_ms is None or submitted_at_ms != self._last_close_ms:
            raise ValueError("submit requires the latest fully closed M1 time")
        if self._pending is not None:
            raise ValueError("another virtual order is already pending")
        if request.order_id in self._seen_order_ids:
            raise ValueError("virtual order ID already used")
        self._pending = (request, submitted_at_ms)
        self._seen_order_ids.add(request.order_id)
        kind = "LIMIT" if isinstance(request, LimitRequest) else "MARKET"
        self._events.append(OrderEvent(
            request.order_id, "SUBMITTED", submitted_at_ms, order_type=kind,
        ))

    def amend_limit(
        self, request: LimitRequest, *, amended_at_ms: int,
    ) -> None:
        """Change only price of a currently pending GTC LIMIT, not ownership."""
        if not isinstance(request, LimitRequest):
            raise TypeError("LimitRequest required")
        if (self._last_close_ms is None or amended_at_ms != self._last_close_ms
                or self._pending is None
                or not isinstance(self._pending[0], LimitRequest)):
            raise ValueError("only a pending LIMIT may be amended at a closed M1")
        old, submitted_at_ms = self._pending
        if ((request.order_id, request.side, request.quantity, request.namespace)
                != (old.order_id, old.side, old.quantity, old.namespace)):
            raise ValueError("LIMIT amendment must preserve identity, side and quantity")
        if request.limit_price == old.limit_price:
            return
        self._pending = (request, submitted_at_ms)
        self._events.append(OrderEvent(
            request.order_id, "AMENDED", amended_at_ms, order_type="LIMIT",
        ))

    def cancel_pending(self, order_id: str, *, cancelled_at_ms: int) -> None:
        if (
            self._pending is None or self._pending[0].order_id != order_id
            or self._last_close_ms is None or cancelled_at_ms != self._last_close_ms
        ):
            raise ValueError("only the current pending virtual order may be cancelled")
        prior = self._pending[0]
        self._pending = None
        self._events.append(OrderEvent(
            order_id, "CANCELLED", cancelled_at_ms,
            order_type="LIMIT" if isinstance(prior, LimitRequest) else "MARKET",
        ))

    def on_closed_minute(self, minute: Candle) -> VirtualFill | None:
        """Process an M1 only after closure, with explicit fill assumptions.

        MARKET: next M1 OPEN. LIMIT: first future M1 with opening marketable
        or strict penetration beyond limit. Intrabar LIMIT fill assumed at
        limit price; equality-only touches are never considered guaranteed.
        No unclosed/future OHLC is visible to the strategy at decision time.
        """
        if not isinstance(minute, Candle) or minute.interval_ms != MINUTE_MS:
            raise ValueError("only closed M1 Candle is supported")
        if minute.start_ms % MINUTE_MS:
            raise ValueError("M1 candle must use UTC minute boundaries")
        if self._last_close_ms is not None and minute.start_ms != self._last_close_ms:
            raise ValueError("M1 gap, overlap or duplicate at virtual exchange")

        receipt = None
        filled_kind: str | None = None
        if self._pending is not None:
            request, submitted_at_ms = self._pending
            if isinstance(request, MarketRequest):
                if submitted_at_ms != minute.start_ms:
                    raise ValueError("pending MARKET cannot skip its next M1 opening")
                price = minute.open
                fee_rate = self.taker_fee_rate
                filled_kind = "MARKET"
            else:
                if submitted_at_ms > minute.start_ms:
                    raise ValueError("LIMIT cannot execute before submission")
                buy = request.side == "BUY"
                marketable_open = (
                    minute.open <= request.limit_price if buy
                    else minute.open >= request.limit_price
                )
                trade_through = (
                    minute.low < request.limit_price if buy
                    else minute.high > request.limit_price
                )
                if marketable_open or trade_through:
                    price = request.limit_price
                    fee_rate = (
                        self.taker_fee_rate if marketable_open
                        else self.maker_fee_rate
                    )
                    filled_kind = "LIMIT"
            if filled_kind is not None:
                fee = price * request.quantity * fee_rate
                receipt = VirtualFill(
                    simulation_run_id=self.account.simulation_run_id,
                    symbol=self.account.symbol,
                    fill_id=f"{request.order_id}_fill",
                    virtual_time_ms=minute.end_ms,
                    side=request.side,
                    quantity=request.quantity,
                    price=price,
                    fee=fee,
                )
                # Account validates atomically; failed append leaves minute
                # cursor, pending LIMIT and event stream unchanged.
                self.account.append(receipt)

        self._last_close_ms = minute.end_ms
        if receipt is not None:
            self._pending = None
            self._events.append(
                OrderEvent(
                    request.order_id, "FILLED", minute.end_ms,
                    order_type=filled_kind,
                )
            )
        return receipt
