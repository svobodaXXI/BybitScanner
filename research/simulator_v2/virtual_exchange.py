"""Isolated MARKET and GTC LIMIT fill adapter for historical SIMULATION only.

Market fills use the following M1 OPEN after submission. Limit orders remain
pending until the next closed M1 proves *strict trade-through* (or the next
OPEN is already marketable). A trade-through is an explicit deterministic
OHLC fill assumption, NOT proof of venue queue priority or real execution.
LIMIT fills occur at their stated limit price, never a fictitious improvement.
A marketable opening uses taker fees; intrabar limit fill uses maker fees.

The legacy single-order seam remains for Wedge.  The native Robot seam may
hold several already-owned GTC LIMITs for one symbol (Box P1..P4 and their
paired exits); it still makes no strategy, sizing or protection decision.
Full fills, one-way position, no leverage, depth, partial fills or real
trading endpoints.
Protected STOP/TAKE execute pessimistically on ambiguous closed M1 candles:
STOP takes precedence over TAKE and gap STOP executes at OPEN. When entry and
STOP hit in one bar, both receipts commit atomically. Intrabar TAKE on an
entry candle is deferred (its order relative to entry is unprovable).
Robot owns entry eligibility and price policy; exchange owns fill assumptions.
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
class ProtectedLimitRequest:
    """Explicit research-only STOP/TAKE bracket bound to one GTC entry.

    Robot controls the price calculations before constructing this request.
    No strategy or RR logic belongs in the virtual exchange.
    """
    entry: LimitRequest
    stop_price: Decimal
    take_price: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.entry, LimitRequest):
            raise TypeError("exact virtual LIMIT request required")
        for price in (self.stop_price, self.take_price):
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
                raise ValueError("finite positive protective prices required")
        entry = self.entry.limit_price
        if self.entry.side == "BUY":
            valid = self.stop_price < entry < self.take_price
        else:
            valid = self.take_price < entry < self.stop_price
        if not valid:
            raise ValueError("STOP/TAKE must straddle entry on protective sides")


@dataclass(frozen=True)
class RobotLimitRequest:
    """One native Robot-owned GTC LIMIT projected into the virtual venue."""

    entry: LimitRequest
    reduce_only: bool

    def __post_init__(self) -> None:
        if not isinstance(self.entry, LimitRequest) or type(self.reduce_only) is not bool:
            raise TypeError("exact Robot LIMIT and reduce-only flag required")


@dataclass(frozen=True)
class RobotStopRequest:
    """Current native Robot STOP projection; quantity follows actual position."""

    order_id: str
    position_side: str
    stop_price: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not IDENTITY.fullmatch(self.order_id):
            raise ValueError("invalid virtual STOP identity")
        if self.position_side not in ("LONG", "SHORT"):
            raise ValueError("virtual STOP needs LONG or SHORT position side")
        if (not isinstance(self.stop_price, Decimal)
                or not self.stop_price.is_finite() or self.stop_price <= 0):
            raise ValueError("positive finite virtual STOP required")


@dataclass(frozen=True)
class RobotTakeRequest:
    """Current Robot TAKE projection: trigger price and actual position side."""

    order_id: str
    position_side: str
    take_price: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not IDENTITY.fullmatch(self.order_id):
            raise ValueError("invalid virtual TAKE identity")
        if self.position_side not in ("LONG", "SHORT"):
            raise ValueError("virtual TAKE needs LONG or SHORT position side")
        if (not isinstance(self.take_price, Decimal)
                or not self.take_price.is_finite() or self.take_price <= 0):
            raise ValueError("positive finite virtual TAKE required")


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
        self._pending_protection: ProtectedLimitRequest | None = None
        self._active_protection: ProtectedLimitRequest | None = None
        self._last_minute_fills: tuple[VirtualFill, ...] = ()
        self._last_minute_order_events: tuple[OrderEvent, ...] = ()
        self._robot_limits: dict[str, tuple[RobotLimitRequest, int]] = {}
        self._robot_markets: dict[str, tuple[MarketRequest, int]] = {}
        self._robot_stop: RobotStopRequest | None = None
        self._robot_take: RobotTakeRequest | None = None

    @property
    def virtual_time_ms(self) -> int | None:
        return self._last_close_ms

    @property
    def pending(self) -> MarketRequest | LimitRequest | None:
        if self._pending is not None:
            return self._pending[0]
        if self._robot_markets:
            return next(iter(self._robot_markets.values()))[0]
        if self._robot_limits:
            return next(iter(self._robot_limits.values()))[0].entry
        return None

    @property
    def events(self) -> tuple[OrderEvent, ...]:
        return tuple(self._events)

    @property
    def active_protection(self) -> ProtectedLimitRequest | None:
        return self._active_protection

    @property
    def last_minute_fills(self) -> tuple[VirtualFill, ...]:
        return self._last_minute_fills

    @property
    def last_minute_order_events(self) -> tuple[OrderEvent, ...]:
        return self._last_minute_order_events

    @property
    def robot_limits(self) -> tuple[RobotLimitRequest, ...]:
        return tuple(item[0] for item in self._robot_limits.values())

    @property
    def robot_markets(self) -> tuple[MarketRequest, ...]:
        return tuple(item[0] for item in self._robot_markets.values())

    @property
    def robot_stop(self) -> RobotStopRequest | None:
        return self._robot_stop

    @property
    def robot_take(self) -> RobotTakeRequest | None:
        return self._robot_take

    def submit_robot_market(
        self, request: MarketRequest, *, submitted_at_ms: int,
    ) -> None:
        """Queue a native Robot MARKET for the next historical M1 OPEN."""
        if not isinstance(request, MarketRequest):
            raise TypeError("MarketRequest required")
        if (self._last_close_ms is None or submitted_at_ms != self._last_close_ms
                or self._pending is not None or self._active_protection is not None):
            raise ValueError("Robot MARKET requires latest committed native-Robot M1")
        if request.order_id in self._seen_order_ids:
            if request.order_id in self._robot_markets:
                return
            raise ValueError("native Robot MARKET identity already retired")
        self._seen_order_ids.add(request.order_id)
        self._robot_markets[request.order_id] = (request, submitted_at_ms)
        self._events.append(OrderEvent(
            request.order_id, "SUBMITTED", submitted_at_ms, order_type="MARKET",
        ))

    def synchronize_robot_limits(
        self, requests: tuple[RobotLimitRequest, ...], *, synchronized_at_ms: int,
    ) -> None:
        """Mirror the native Robot's durable active-order projection.

        Orders absent from the new projection are cancelled; unchanged orders
        retain their original submission minute and therefore cannot be made
        artificially younger or older by repeated Robot reconciliation.
        """
        if self._pending is not None or self._active_protection is not None:
            raise ValueError("legacy and native Robot exchange modes cannot mix")
        if (self._last_close_ms is None or synchronized_at_ms != self._last_close_ms
                or not isinstance(requests, tuple)):
            raise ValueError("Robot LIMIT sync requires latest committed M1")
        incoming: dict[str, RobotLimitRequest] = {}
        for item in requests:
            if not isinstance(item, RobotLimitRequest):
                raise TypeError("RobotLimitRequest tuple required")
            if item.entry.order_id in incoming:
                raise ValueError("duplicate native Robot LIMIT identity")
            incoming[item.entry.order_id] = item
        for order_id, (prior, _submitted) in self._robot_limits.items():
            current = incoming.get(order_id)
            if current is not None and current != prior:
                raise ValueError("native Robot LIMIT changed without durable amendment")
        next_limits: dict[str, tuple[RobotLimitRequest, int]] = {}
        for order_id, item in incoming.items():
            if order_id in self._robot_limits:
                next_limits[order_id] = self._robot_limits[order_id]
            else:
                if order_id in self._seen_order_ids:
                    raise ValueError("native Robot order identity already retired")
                next_limits[order_id] = (item, synchronized_at_ms)
                self._seen_order_ids.add(order_id)
                self._events.append(OrderEvent(
                    order_id, "SUBMITTED", synchronized_at_ms, order_type="LIMIT",
                ))
        for order_id in self._robot_limits.keys() - next_limits.keys():
            self._events.append(OrderEvent(
                order_id, "CANCELLED", synchronized_at_ms, order_type="LIMIT",
            ))
        self._robot_limits = next_limits

    def synchronize_robot_stop(
        self, request: RobotStopRequest | None, *, synchronized_at_ms: int,
    ) -> None:
        if self._pending is not None or self._active_protection is not None:
            raise ValueError("legacy and native Robot exchange modes cannot mix")
        if self._last_close_ms is None or synchronized_at_ms != self._last_close_ms:
            raise ValueError("Robot STOP sync requires latest committed M1")
        self._robot_stop = request

    def synchronize_robot_take(
        self, request: RobotTakeRequest | None, *, synchronized_at_ms: int,
    ) -> None:
        if self._pending is not None or self._active_protection is not None:
            raise ValueError("legacy and native Robot exchange modes cannot mix")
        if self._last_close_ms is None or synchronized_at_ms != self._last_close_ms:
            raise ValueError("Robot TAKE sync requires latest committed M1")
        self._robot_take = request

    @staticmethod
    def _limit_resolution(request: LimitRequest, minute: Candle) -> tuple[Decimal, Decimal] | None:
        buy = request.side == "BUY"
        marketable = minute.open <= request.limit_price if buy else minute.open >= request.limit_price
        through = minute.low < request.limit_price if buy else minute.high > request.limit_price
        if not (marketable or through):
            return None
        return request.limit_price, Decimal(1 if marketable else 0)

    def _match_native_robot(
        self, minute: Candle,
    ) -> tuple[list[VirtualFill], list[OrderEvent]]:
        receipts: list[VirtualFill] = []
        events: list[OrderEvent] = []
        snapshot = self.account.snapshot(
            as_of_ms=minute.start_ms, mark_price=minute.open,
        )
        position = snapshot.position_quantity
        stop = self._robot_stop
        if position and stop is not None:
            is_long = position > 0
            if (stop.position_side == "LONG") != is_long:
                raise ValueError("native Robot STOP side conflicts with virtual position")
            hit = minute.low <= stop.stop_price if is_long else minute.high >= stop.stop_price
            if hit:
                gap = minute.open <= stop.stop_price if is_long else minute.open >= stop.stop_price
                price = minute.open if gap else stop.stop_price
                receipts.append(VirtualFill(
                    self.account.simulation_run_id, self.account.symbol,
                    stop.order_id + "_fill", minute.end_ms,
                    "SELL" if is_long else "BUY", abs(position), price,
                    price * abs(position) * self.taker_fee_rate,
                ))
                events.append(OrderEvent(
                    stop.order_id, "STOP_FILLED", minute.end_ms, order_type="STOP",
                ))
                self._robot_stop = None
                self._robot_take = None
                self._robot_limits = {}
                self._robot_markets = {}
                return receipts, events

        take = self._robot_take
        if position and take is not None:
            is_long = position > 0
            if (take.position_side == "LONG") != is_long:
                raise ValueError("native Robot TAKE side conflicts with virtual position")
            hit = minute.high >= take.take_price if is_long else minute.low <= take.take_price
            if hit:
                # A TAKE is a triggered market exit in the Robot, not a maker
                # LIMIT. The proven boundary is the conservative fill price:
                # do not invent positive gap improvement from OHLC.
                price = take.take_price
                quantity = abs(position)
                receipts.append(VirtualFill(
                    self.account.simulation_run_id, self.account.symbol,
                    take.order_id + "_fill", minute.end_ms,
                    "SELL" if is_long else "BUY", quantity, price,
                    price * quantity * self.taker_fee_rate,
                ))
                events.append(OrderEvent(
                    take.order_id, "TAKE_FILLED", minute.end_ms, order_type="TAKE",
                ))
                self._robot_stop = None
                self._robot_take = None
                self._robot_limits = {}
                self._robot_markets = {}
                return receipts, events

        if self._robot_markets:
            order_id, (request, submitted_at) = next(iter(self._robot_markets.items()))
            if submitted_at > minute.start_ms:
                raise ValueError("native Robot MARKET cannot fill before submission")
            receipts.append(VirtualFill(
                self.account.simulation_run_id, self.account.symbol,
                order_id + "_fill", minute.end_ms, request.side, request.quantity,
                minute.open, minute.open * request.quantity * self.taker_fee_rate,
            ))
            events.append(OrderEvent(
                order_id, "FILLED", minute.end_ms, order_type="MARKET",
            ))
            self._robot_markets.pop(order_id)
            # Closed OHLC cannot prove a chronology for several queued Robot
            # actions.  As with crossed grid LIMITs, commit only one fill per
            # M1 and leave the rest pending for a later historical OPEN.
            return receipts, events

        eligible_entries: list[tuple[str, RobotLimitRequest, Decimal, Decimal]] = []
        eligible_exits: list[tuple[str, RobotLimitRequest, Decimal, Decimal]] = []
        for order_id, (owned, submitted_at) in self._robot_limits.items():
            if submitted_at > minute.start_ms:
                raise ValueError("native Robot LIMIT cannot execute before submission")
            resolution = self._limit_resolution(owned.entry, minute)
            if resolution is None:
                continue
            price, marketable = resolution
            target = eligible_exits if owned.reduce_only else eligible_entries
            target.append((order_id, owned, price, marketable))

        # P1..P4 are adverse layers: a LONG buys high-to-low, a SHORT sells
        # low-to-high.  This is venue ordering only; prices came from Robot.
        eligible_entries.sort(
            key=lambda item: item[2], reverse=(eligible_entries[0][1].entry.side == "BUY")
            if eligible_entries else False,
        )
        # A closed OHLC bar proves that every crossed level was visited, but
        # not a venue fill chronology for several resting orders.  Commit at
        # most the first adverse grid layer per M1 and leave the rest GTC.
        # This is conservative, causal, and gives the native ownership journal
        # one strictly later closed-market event for every subsequent layer.
        selected = eligible_entries[:1]
        if not selected:
            # Never award a TAKE on a candle that also established/top-upped
            # exposure: OHLC cannot prove TAKE happened after that entry.
            eligible_exits.sort(key=lambda item: item[0])
            selected = eligible_exits[:1]
        projected = position
        for order_id, owned, price, marketable in selected:
            request = owned.entry
            quantity = request.quantity
            signed = quantity if request.side == "BUY" else -quantity
            if owned.reduce_only:
                if not projected or projected * signed >= 0:
                    raise ValueError("reduce-only Robot LIMIT cannot add exposure")
                quantity = min(quantity, abs(projected))
                signed = quantity if request.side == "BUY" else -quantity
            projected += signed
            fee_rate = self.taker_fee_rate if marketable else self.maker_fee_rate
            receipts.append(VirtualFill(
                self.account.simulation_run_id, self.account.symbol,
                order_id + "_fill", minute.end_ms, request.side, quantity, price,
                price * quantity * fee_rate,
            ))
            events.append(OrderEvent(
                order_id, "FILLED", minute.end_ms, order_type="LIMIT",
            ))
            self._robot_limits.pop(order_id, None)
            if owned.reduce_only and projected == 0:
                break
        return receipts, events

    def submit(self, request: MarketRequest, *, submitted_at_ms: int) -> None:
        if not isinstance(request, MarketRequest):
            raise TypeError("MarketRequest required")
        self._submit(request, submitted_at_ms=submitted_at_ms)

    def submit_limit(self, request: LimitRequest, *, submitted_at_ms: int) -> None:
        if not isinstance(request, LimitRequest):
            raise TypeError("LimitRequest required")
        self._submit(request, submitted_at_ms=submitted_at_ms)

    def submit_protected_limit(
        self, request: ProtectedLimitRequest, *, submitted_at_ms: int,
    ) -> None:
        """Bind STOP+TAKE to the GTC entry before the first possible fill."""
        if not isinstance(request, ProtectedLimitRequest):
            raise TypeError("ProtectedLimitRequest required")
        if self._last_close_ms is None:
            raise ValueError("a closed virtual M1 is required before protected entry")
        position = self.account.snapshot(
            as_of_ms=self._last_close_ms,
            mark_price=request.entry.limit_price,
        ).position_quantity
        if position != 0:
            raise ValueError("cannot submit protected entry while a virtual position is open")
        self._submit(request.entry, submitted_at_ms=submitted_at_ms)
        self._pending_protection = request

    def _submit(
        self, request: MarketRequest | LimitRequest, *, submitted_at_ms: int,
    ) -> None:
        if self._last_close_ms is None or submitted_at_ms != self._last_close_ms:
            raise ValueError("submit requires the latest fully closed M1 time")
        if self._pending is not None or self._active_protection is not None:
            raise ValueError("pending order or protected position already owns virtual symbol")
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
        if self._pending_protection is not None:
            raise ValueError("protected LIMIT reprice requires new native Robot risk proof")
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
        self._pending_protection = None
        self._events.append(OrderEvent(
            order_id, "CANCELLED", cancelled_at_ms,
            order_type="LIMIT" if isinstance(prior, LimitRequest) else "MARKET",
        ))

    @staticmethod
    def _protective_exit(
        request: ProtectedLimitRequest, minute: Candle, *, entry_candle: bool,
    ) -> tuple[str, Decimal] | None:
        """Pessimistic OHLC resolution with STOP priority, never false TAKE.

        A same-bar intrabar TAKE might have occurred before the LIMIT entry,
        so do NOT award it. STOP is considered hit even during entry candle.
        """
        is_long = request.entry.side == "BUY"
        stop_gap = (
            minute.open <= request.stop_price if is_long
            else minute.open >= request.stop_price
        )
        stop_hit = (
            minute.low <= request.stop_price if is_long
            else minute.high >= request.stop_price
        )
        if stop_hit:
            return "STOP", minute.open if stop_gap else request.stop_price
        if entry_candle:
            return None
        take_hit = (
            minute.high >= request.take_price if is_long
            else minute.low <= request.take_price
        )
        if take_hit:
            return "TAKE", request.take_price
        return None

    def _exit_fill(
        self, request: ProtectedLimitRequest, minute: Candle,
        reason: str, price: Decimal,
    ) -> VirtualFill:
        return VirtualFill(
            simulation_run_id=self.account.simulation_run_id,
            symbol=self.account.symbol,
            fill_id=request.entry.order_id + "_" + reason.lower() + "_fill",
            virtual_time_ms=minute.end_ms,
            side="SELL" if request.entry.side == "BUY" else "BUY",
            quantity=request.entry.quantity,
            price=price,
            fee=price * request.entry.quantity * self.taker_fee_rate,
        )

    def on_closed_minute(self, minute: Candle) -> VirtualFill | None:
        """Atomically match a closed M1 without reading future minutes.

        Protected positions use STOP-first matching. A same-candle entry+STOP
        is an atomic batch in the existing VirtualAccount, never a naked fill.
        """
        if not isinstance(minute, Candle) or minute.interval_ms != MINUTE_MS:
            raise ValueError("only closed M1 Candle is supported")
        if minute.start_ms % MINUTE_MS:
            raise ValueError("M1 candle must use UTC minute boundaries")
        if self._last_close_ms is not None and minute.start_ms != self._last_close_ms:
            raise ValueError("M1 gap, overlap or duplicate at virtual exchange")

        receipts: list[VirtualFill] = []
        new_events: list[OrderEvent] = []
        next_pending = self._pending
        next_pending_protection = self._pending_protection
        next_active_protection = self._active_protection

        if (self._robot_limits or self._robot_markets
                or self._robot_stop is not None or self._robot_take is not None):
            if next_pending is not None or next_active_protection is not None:
                raise ValueError("legacy and native Robot exchange modes cannot mix")
            receipts, new_events = self._match_native_robot(minute)
        elif next_active_protection is not None:
            if next_pending is not None:
                raise ValueError("protected position and pending entry cannot coexist")
            resolution = self._protective_exit(
                next_active_protection, minute, entry_candle=False,
            )
            if resolution is not None:
                reason, price = resolution
                receipts.append(
                    self._exit_fill(next_active_protection, minute, reason, price)
                )
                new_events.append(OrderEvent(
                    next_active_protection.entry.order_id,
                    reason + "_FILLED", minute.end_ms, order_type=reason,
                ))
                next_active_protection = None
        elif next_pending is not None:
            request, submitted_at_ms = next_pending
            kind: str | None = None
            price: Decimal | None = None
            fee_rate = self.taker_fee_rate
            if isinstance(request, MarketRequest):
                if submitted_at_ms != minute.start_ms:
                    raise ValueError("pending MARKET cannot skip its next M1 opening")
                price, kind = minute.open, "MARKET"
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
                    price, kind = request.limit_price, "LIMIT"
                    fee_rate = (
                        self.taker_fee_rate if marketable_open
                        else self.maker_fee_rate
                    )
            if kind is not None:
                assert price is not None
                receipts.append(VirtualFill(
                    simulation_run_id=self.account.simulation_run_id,
                    symbol=self.account.symbol,
                    fill_id=f"{request.order_id}_fill",
                    virtual_time_ms=minute.end_ms,
                    side=request.side, quantity=request.quantity,
                    price=price, fee=price * request.quantity * fee_rate,
                ))
                new_events.append(OrderEvent(
                    request.order_id, "FILLED", minute.end_ms, order_type=kind,
                ))
                if next_pending_protection is not None:
                    if not isinstance(request, LimitRequest) or next_pending_protection.entry != request:
                        raise ValueError("STOP/TAKE bracket differs from pending LIMIT")
                    resolution = self._protective_exit(
                        next_pending_protection, minute, entry_candle=True,
                    )
                    if resolution is not None:
                        reason, exit_price = resolution
                        receipts.append(self._exit_fill(
                            next_pending_protection, minute, reason, exit_price,
                        ))
                        new_events.append(OrderEvent(
                            request.order_id, reason + "_FILLED", minute.end_ms,
                            order_type=reason,
                        ))
                    else:
                        next_active_protection = next_pending_protection
                    next_pending_protection = None
                next_pending = None

        if receipts:
            # If both the entry and its STOP trigger in the same M1, either
            # both are accounted for, or the entire minute remains uncommitted.
            self.account.append_many(tuple(receipts))
        self._last_close_ms = minute.end_ms
        self._pending = next_pending
        self._pending_protection = next_pending_protection
        self._active_protection = next_active_protection
        self._events.extend(new_events)
        self._last_minute_fills = tuple(receipts)
        self._last_minute_order_events = tuple(new_events)
        return receipts[-1] if receipts else None
