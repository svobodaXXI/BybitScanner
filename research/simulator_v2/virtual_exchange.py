"""Isolated, deterministic MARKET fill adapter for historical SIMULATION only.

An admitted virtual order submitted after a CLOSED M1 bar is eligible only
at the *next* M1 opening price. No exchange API, network, order policy, STOP/
TAKE strategy, leverage or production runtime is imported. Fills are passed
to the existing VirtualAccount; the adapter does not calculate PnL.

Model limits: one pending market order, one-way net position, no slippage,
fully filled at the next bar's open with configured taker fee. This model is
not a claim of realistic live execution or a complete Robot lifecycle.
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
class OrderEvent:
    order_id: str
    kind: str  # SUBMITTED, CANCELLED, FILLED
    virtual_time_ms: int
    namespace: str = "SIMULATION"


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
        self.account = account
        self.taker_fee_rate = taker_fee_rate
        self._last_close_ms: int | None = None
        self._pending: tuple[MarketRequest, int] | None = None
        self._seen_order_ids: set[str] = set()
        self._events: list[OrderEvent] = []

    @property
    def virtual_time_ms(self) -> int | None:
        return self._last_close_ms

    @property
    def pending(self) -> MarketRequest | None:
        return self._pending[0] if self._pending is not None else None

    @property
    def events(self) -> tuple[OrderEvent, ...]:
        return tuple(self._events)

    def submit(self, request: MarketRequest, *, submitted_at_ms: int) -> None:
        if not isinstance(request, MarketRequest):
            raise TypeError("MarketRequest required")
        if self._last_close_ms is None or submitted_at_ms != self._last_close_ms:
            raise ValueError("submit requires the latest fully closed M1 time")
        if self._pending is not None:
            raise ValueError("another virtual market order is already pending")
        if request.order_id in self._seen_order_ids:
            raise ValueError("virtual order ID already used")
        self._pending = (request, submitted_at_ms)
        self._seen_order_ids.add(request.order_id)
        self._events.append(OrderEvent(request.order_id, "SUBMITTED", submitted_at_ms))

    def cancel_pending(self, order_id: str, *, cancelled_at_ms: int) -> None:
        if (
            self._pending is None or self._pending[0].order_id != order_id
            or self._last_close_ms is None or cancelled_at_ms != self._last_close_ms
        ):
            raise ValueError("only the current pending virtual order may be cancelled")
        self._pending = None
        self._events.append(OrderEvent(order_id, "CANCELLED", cancelled_at_ms))

    def on_closed_minute(self, minute: Candle) -> VirtualFill | None:
        """Process a just-completed M1; next-open fill is a modeling assumption.

        Processing waits until the bar is closed, but it uses ONLY its opening
        price for an older pending MARKET order. This never reads a future bar
        or uses the current candle's high/low to grant a favorable execution.
        """
        if not isinstance(minute, Candle) or minute.interval_ms != MINUTE_MS:
            raise ValueError("only closed M1 Candle is supported")
        if minute.start_ms % MINUTE_MS:
            raise ValueError("M1 candle must use UTC minute boundaries")
        if self._last_close_ms is not None and minute.start_ms != self._last_close_ms:
            raise ValueError("M1 gap, overlap or duplicate at virtual exchange")

        receipt = None
        if self._pending is not None:
            request, submitted_at_ms = self._pending
            if submitted_at_ms != minute.start_ms:
                raise ValueError("pending order cannot skip its next M1 opening")
            fee = minute.open * request.quantity * self.taker_fee_rate
            receipt = VirtualFill(
                simulation_run_id=self.account.simulation_run_id,
                symbol=self.account.symbol,
                fill_id=f"{request.order_id}_fill",
                virtual_time_ms=minute.end_ms,
                side=request.side,
                quantity=request.quantity,
                price=minute.open,
                fee=fee,
            )
            # Account is the only fill ledger and validates the receipt
            # before accepting it; don't advance this clock on a failure.
            self.account.append(receipt)

        self._last_close_ms = minute.end_ms
        if receipt is not None:
            self._pending = None
            self._events.append(
                OrderEvent(request.order_id, "FILLED", minute.end_ms)
            )
        return receipt
