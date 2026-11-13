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
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from geometry.naked_retest import CAMPAIGN_LONG, CAMPAIGN_SHORT
from retest_campaign import STOP_NET_BREAK_EVEN, net_break_even_remainder_stop

from research.historical_market_replay import Candle
from robot_entry_flow_evidence import TakerPrint
from research.simulator_v2.historical_orderbook import BookState
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
class L2PartialTakePolicy:
    """Explicit research-only potential threshold; disabled unless supplied."""
    potential_fraction: Decimal
    quantity_fraction: Decimal
    quantity_step: Decimal
    tick_size: Decimal
    stop_slippage_fraction: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        for name in ("potential_fraction", "quantity_fraction", "quantity_step",
                     "tick_size", "stop_slippage_fraction"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"invalid L2 partial policy {name}")
        if (not 0 < self.potential_fraction < 1
                or not 0 < self.quantity_fraction < 1
                or self.quantity_step <= 0 or self.tick_size <= 0
                or not 0 <= self.stop_slippage_fraction < 1):
            raise ValueError("invalid bounded L2 partial TAKE/BE terms")


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
        execution_mode: str = "OHLC_M1",
        l2_partial_take_policy: L2PartialTakePolicy | None = None,
    ) -> None:
        if execution_mode not in ("OHLC_M1", "HISTORICAL_L2"):
            raise ValueError("explicit OHLC_M1 or HISTORICAL_L2 virtual execution required")
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
        if l2_partial_take_policy is not None and (
            execution_mode != "HISTORICAL_L2"
            or not isinstance(l2_partial_take_policy, L2PartialTakePolicy)
        ):
            raise ValueError("partial TAKE/BE is SIMULATION HISTORICAL_L2 only")
        self.account = account
        self._l2_partial_policy = l2_partial_take_policy
        self._l2_partial_entry: VirtualFill | None = None
        self._l2_partial_qty: Decimal | None = None
        self._l2_partial_target: Decimal | None = None
        self._l2_partial_fill: VirtualFill | None = None
        self._l2_be_stop: Decimal | None = None
        self._l2_partial_underdepth_ids: set[str] = set()
        self.taker_fee_rate = taker_fee_rate
        self.maker_fee_rate = maker_fee_rate
        self._last_close_ms: int | None = None
        self._pending: tuple[MarketRequest | LimitRequest, int] | None = None
        self._seen_order_ids: set[str] = set()
        self._events: list[OrderEvent] = []
        self._pending_protection: ProtectedLimitRequest | None = None
        self._active_protection: ProtectedLimitRequest | None = None
        self.execution_mode = execution_mode
        self._l2_book: BookState | None = None
        self._l2_event_at_ms: int | None = None
        self._l2_event_kind: str | None = None
        self._l2_underdepth_order_ids: set[str] = set()
        self._l2_pending_stop: tuple[int, Decimal] | None = None
        self._l2_deferred_stop_count = 0
        self._last_minute_fills: tuple[VirtualFill, ...] = ()
        self._last_minute_order_events: tuple[OrderEvent, ...] = ()
        self._robot_limits: dict[str, tuple[RobotLimitRequest, int]] = {}
        self._robot_markets: dict[str, tuple[MarketRequest, int]] = {}
        self._robot_stop: RobotStopRequest | None = None

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
    def l2_unproven_entry_depth_count(self) -> int:
        """Protected LIMIT requests encountering unprovable full-size book depth."""
        return len(self._l2_underdepth_order_ids)

    @property
    def l2_deferred_stop_count(self) -> int:
        return self._l2_deferred_stop_count

    @property
    def l2_stop_pending(self) -> bool:
        return self._l2_pending_stop is not None

    @property
    def l2_partial_take_fills(self) -> int:
        return sum(event.kind == "PARTIAL_TAKE_FILLED" for event in self._events)

    @property
    def l2_be_stop_amendments(self) -> int:
        return sum(event.kind == "STOP_AMENDED_BE" for event in self._events)

    @property
    def l2_partial_depth_unproven_count(self) -> int:
        return len(self._l2_partial_underdepth_ids)

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

    def _require_l2_event(self, at_ms: int, *, kind: str) -> None:
        if self.execution_mode != "HISTORICAL_L2":
            raise ValueError("historical L2 events require explicit HISTORICAL_L2 mode")
        if type(at_ms) is not int or at_ms < 0:
            raise ValueError("invalid historical event time")
        if self._last_close_ms is not None and at_ms < self._last_close_ms:
            raise ValueError("historical event precedes committed virtual M1")
        if self._l2_event_at_ms is not None and at_ms < self._l2_event_at_ms:
            raise ValueError("historical market event time reversed")
        if (self._l2_event_at_ms == at_ms and self._l2_event_kind != kind):
            raise ValueError("cross-channel trade/book order ambiguous at same millisecond")
        if (kind == "TRADE" and self._l2_event_at_ms == at_ms):
            raise ValueError("same-millisecond taker print order is unproven")

    def on_historical_same_ms_inert_bucket(
        self, *, books: tuple[BookState, ...], trades: tuple[TakerPrint, ...],
    ) -> None:
        """Commit a mixed-timestamp bucket ONLY if neither ordering can fill.

        Trade and book archives do not establish an exchange-level order for
        equal millisecond timestamps. A non-triggering trade needs no virtual
        execution action; it still reaches the Scanner through the original
        pinned taker tape at the M1 close. Never skip a potential fill.
        """
        if (not isinstance(books, tuple) or not isinstance(trades, tuple)
                or not books or not trades or len(books) > 2000
                or len(trades) > 2000):
            raise ValueError("bounded mixed L2/taker group required")
        stamp = books[0].available_at_ms
        if (any(not isinstance(book, BookState)
                or book.available_at_ms != stamp or book.symbol != self.account.symbol
                for book in books)
                or any(not isinstance(trade, TakerPrint)
                       or trade.event_ms != stamp or trade.symbol != self.account.symbol
                       for trade in trades)
                or len({trade.trade_id for trade in trades}) != len(trades)):
            raise ValueError("invalid original mixed-millisecond L2/taker events")
        self._require_l2_event(stamp, kind="BOOK")
        if self._l2_pending_stop is not None:
            raise ValueError(f"same-ms L2/taker deferred STOP chronology unproven at {stamp}")
        if self._active_protection is not None and self._l2_partial_policy is not None:
            if self._l2_partial_fill is not None and self._l2_be_stop is None:
                raise ValueError(f"same-ms L2/taker potential BE amendment chronology unproven at {stamp}")
            if self._l2_partial_fill is None and any(
                (book.best_bid[0] >= self._l2_partial_target
                 if self._active_protection.entry.side == "BUY"
                 else book.best_ask[0] <= self._l2_partial_target)
                for book in books
            ):
                raise ValueError(f"same-ms L2/taker partial TAKE chronology unproven at {stamp}")
        if self._robot_limits or self._robot_markets or self._robot_stop is not None:
            raise ValueError(f"same-ms L2/taker native Robot chronology unproven at {stamp}")
        exposure = self.account.snapshot(
            as_of_ms=stamp, mark_price=trades[0].price,
        ).position_quantity
        if exposure and self._active_protection is None:
            raise ValueError(f"same-ms L2/taker unprotected exposure at {stamp}")
        if self._active_protection is not None:
            plan = self._active_protection
            long = plan.entry.side == "BUY"
            stop_price = self._l2_current_stop(plan)
            if any(
                (t.price <= stop_price if long else t.price >= stop_price)
                or ((t.side == "Buy" and t.price > plan.take_price) if long
                    else (t.side == "Sell" and t.price < plan.take_price))
                for t in trades
            ):
                raise ValueError(f"same-ms L2/taker protected exit chronology unproven at {stamp}")
        if self._pending is not None:
            request, submitted = self._pending
            if not isinstance(request, LimitRequest):
                raise ValueError("historical L2 requires protected LIMIT")
            if stamp > submitted:
                if any(
                    (book.best_ask[0] <= request.limit_price if request.side == "BUY"
                     else book.best_bid[0] >= request.limit_price)
                    for book in books
                ):
                    raise ValueError(f"same-ms L2/taker marketable entry chronology unproven at {stamp}")
                if any(
                    ((t.side == "Sell" and t.price < request.limit_price)
                     if request.side == "BUY"
                     else (t.side == "Buy" and t.price > request.limit_price))
                    for t in trades
                ):
                    raise ValueError(f"same-ms L2/taker passive entry chronology unproven at {stamp}")
        # Both possible channel orders leave the virtual account unchanged.
        # Apply only original book deltas; the same trades are independently
        # observed by the Scanner at the committed M1 close, not discarded.
        for book in books:
            if self.on_historical_book(book) is not None:
                raise ValueError("inert mixed-millisecond preflight invariant broken")

    def _l2_remaining_quantity(self, plan: ProtectedLimitRequest) -> Decimal:
        partial = self._l2_partial_fill
        return plan.entry.quantity if partial is None else plan.entry.quantity - partial.quantity

    def _l2_current_stop(self, plan: ProtectedLimitRequest) -> Decimal:
        return self._l2_be_stop if self._l2_be_stop is not None else plan.stop_price

    def _l2_arm_partial(self, entry: VirtualFill, plan: ProtectedLimitRequest) -> None:
        policy = self._l2_partial_policy
        if policy is None:
            return
        if self._l2_partial_entry is not None:
            raise ValueError("historical partial management already owns a position")
        quantity = (plan.entry.quantity * policy.quantity_fraction
                    // policy.quantity_step) * policy.quantity_step
        if not 0 < quantity < plan.entry.quantity:
            raise ValueError("25 percent partial quantity does not fit instrument step")
        is_long = plan.entry.side == "BUY"
        target = entry.price + (plan.take_price - entry.price) * policy.potential_fraction
        rounding = ROUND_CEILING if is_long else ROUND_FLOOR
        target = (target / policy.tick_size).to_integral_value(
            rounding=rounding,
        ) * policy.tick_size
        if not ((entry.price < target < plan.take_price) if is_long
                else (plan.take_price < target < entry.price)):
            raise ValueError("partial threshold must remain inside original target")
        self._l2_partial_entry = entry
        self._l2_partial_qty = quantity
        self._l2_partial_target = target
        self._l2_partial_fill = None
        self._l2_be_stop = None

    def _l2_clear_partial(self) -> None:
        self._l2_partial_entry = None
        self._l2_partial_qty = None
        self._l2_partial_target = None
        self._l2_partial_fill = None
        self._l2_be_stop = None

    def _l2_manage_partial_book(self, book: BookState) -> VirtualFill | None:
        """Marketable reduce-only virtual LIMIT; BE never before confirmed partial."""
        entry = self._l2_partial_entry
        plan = self._active_protection
        policy = self._l2_partial_policy
        if entry is None or plan is None or policy is None:
            return None
        if book.available_at_ms <= entry.virtual_time_ms:
            return None
        is_long = plan.entry.side == "BUY"
        if self._l2_partial_fill is None:
            target = self._l2_partial_target
            eligible = book.best_bid[0] >= target if is_long else book.best_ask[0] <= target
            if not eligible:
                return None
            # Strict full-depth requirement, not maker queue priority.
            candidate = self._l2_sweep(
                side="SELL" if is_long else "BUY",
                quantity=self._l2_partial_qty,
                limit_price=target, allow_unfilled_limit=True,
            )
            if candidate is None:
                if plan.entry.order_id not in self._l2_partial_underdepth_ids:
                    self._l2_partial_underdepth_ids.add(plan.entry.order_id)
                    self._events.append(OrderEvent(
                        plan.entry.order_id, "PARTIAL_DEPTH_UNPROVEN",
                        book.available_at_ms, order_type="LIMIT",
                    ))
                return None
            # Take no price improvement: LIMIT threshold, conservative taker fees.
            partial = self._l2_receipt(
                plan.entry.order_id, event_at_ms=book.available_at_ms,
                side="SELL" if is_long else "BUY",
                quantity=self._l2_partial_qty, price=target,
                fee_rate=self.taker_fee_rate, suffix="_partial_fill",
            )
            self.account.append(partial)
            self._l2_partial_fill = partial
            self._events.append(OrderEvent(
                plan.entry.order_id, "PARTIAL_TAKE_FILLED",
                book.available_at_ms, order_type="LIMIT",
            ))
            return partial

        if self._l2_be_stop is None:
            mark = book.best_bid[0] if is_long else book.best_ask[0]
            partial = self._l2_partial_fill
            proposed = net_break_even_remainder_stop(
                campaign_direction=CAMPAIGN_LONG if is_long else CAMPAIGN_SHORT,
                partial_take_confirmed=True, protection_preserved=True,
                current_stop_price=plan.stop_price, mark_price=mark,
                entry_qty=plan.entry.quantity, entry_avg_price=entry.price,
                entry_fees_usdt=entry.fee,
                partial_qty=partial.quantity, partial_avg_price=partial.price,
                partial_fees_usdt=partial.fee,
                funding_usdt=Decimal(0),
                remainder_exit_fee_rate=self.taker_fee_rate,
                slippage_price=mark * policy.stop_slippage_fraction,
                tick_size=policy.tick_size,
            )
            if proposed.decision == STOP_NET_BREAK_EVEN:
                self._l2_be_stop = proposed.stop_price
                self._events.append(OrderEvent(
                    plan.entry.order_id, "STOP_AMENDED_BE",
                    book.available_at_ms, order_type="STOP",
                ))
        return None

    def _l2_hold_triggered_stop(self, trade: TakerPrint) -> None:
        """Preserve the original first trigger and worst subsequent print."""
        if self._l2_pending_stop is None or self._active_protection is None:
            raise ValueError("no triggered historical STOP to hold")
        start, worst = self._l2_pending_stop
        is_long = self._active_protection.entry.side == "BUY"
        self._l2_pending_stop = (
            start, min(worst, trade.price) if is_long else max(worst, trade.price),
        )
        self._l2_event_at_ms = trade.event_ms
        self._l2_event_kind = "TRADE"

    def _l2_settle_triggered_stop(self, book: BookState) -> VirtualFill | None:
        """One post-trigger book may settle STOP, never using a future candle.

        Only a quote no later than 250ms after the original trigger and no
        better than its worst recorded trade can settle. Otherwise keep
        waiting or fail closed. Settlement is conditional simulated execution.
        """
        if self._l2_pending_stop is None or self._active_protection is None:
            raise ValueError("no historical STOP settlement pending")
        trigger_ms, worst_print = self._l2_pending_stop
        elapsed = book.available_at_ms - trigger_ms
        if elapsed <= 0 or elapsed > 250:
            raise ValueError("deferred L2 STOP has no fresh post-trigger book within 250ms")
        plan = self._active_protection
        is_long = plan.entry.side == "BUY"
        if ((is_long and book.best_bid[0] > worst_print)
                or (not is_long and book.best_ask[0] < worst_print)):
            return None
        prior = self._l2_book
        self._l2_book = book
        try:
            price = self._l2_sweep(
                side="SELL" if is_long else "BUY",
                quantity=plan.entry.quantity, limit_price=None,
            )
        finally:
            self._l2_book = prior
        receipt = self._l2_receipt(
            plan.entry.order_id, event_at_ms=book.available_at_ms,
            side="SELL" if is_long else "BUY",
            quantity=self._l2_remaining_quantity(plan),
            price=price, fee_rate=self.taker_fee_rate,
            suffix="_stop_fill",
        )
        self.account.append(receipt)
        self._active_protection = None
        self._l2_pending_stop = None
        self._l2_clear_partial()
        self._events.append(OrderEvent(
            plan.entry.order_id, "STOP_FILLED",
            book.available_at_ms, order_type="STOP",
        ))
        return receipt

    def _l2_sweep(
        self, *, side: str, quantity: Decimal, limit_price: Decimal | None,
        allow_unfilled_limit: bool = False,
    ) -> Decimal | None:
        """Full-size-only research model; market STOP remains strictly fail-closed.

        A GTC LIMIT may partially fill in reality. If available depth within
        its price cannot prove a *full* fill, this virtual model leaves it
        pending and records uncertainty; it must never invent a partial fill.
        """
        book = self._l2_book
        if book is None:
            raise ValueError("no historical L2 snapshot for virtual execution")
        levels = book.asks if side == "BUY" else book.bids
        remaining = quantity
        cost = Decimal(0)
        for price, available in levels:
            if (limit_price is not None and
                    ((side == "BUY" and price > limit_price)
                     or (side == "SELL" and price < limit_price))):
                break
            used = min(remaining, available)
            cost += used * price
            remaining -= used
            if remaining == 0:
                return cost / quantity
        if limit_price is not None and (
            (side == "BUY" and book.best_ask[0] > limit_price)
            or (side == "SELL" and book.best_bid[0] < limit_price)
        ):
            return None
        if allow_unfilled_limit and limit_price is not None:
            return None
        raise ValueError("historical L2 does not prove sufficient executable depth")

    def _l2_receipt(
        self, order_id: str, *, event_at_ms: int, side: str,
        quantity: Decimal, price: Decimal, fee_rate: Decimal, suffix: str,
    ) -> VirtualFill:
        return VirtualFill(
            self.account.simulation_run_id, self.account.symbol,
            order_id + suffix, event_at_ms, side, quantity, price,
            price * quantity * fee_rate,
        )

    def on_historical_book(self, book: BookState) -> VirtualFill | None:
        """Marketable protected LIMIT only after authenticated, time-ordered L2.

        This does not claim resting queue priority. Book events never fill a
        passive LIMIT merely because the best bid/ask touches its price.
        """
        if not isinstance(book, BookState) or book.symbol != self.account.symbol:
            raise ValueError("original same-symbol L2 book state required")
        self._require_l2_event(book.available_at_ms, kind="BOOK")
        if self._robot_limits or self._robot_markets or self._robot_stop is not None:
            raise ValueError("native multi-order matching not implemented for L2")
        if self._pending is not None and not isinstance(self._pending[0], LimitRequest):
            raise ValueError("historical L2 does not support OHLC MARKET fill")
        if self._l2_pending_stop is not None:
            receipt = self._l2_settle_triggered_stop(book)
            self._l2_book = book
            self._l2_event_at_ms = book.available_at_ms
            self._l2_event_kind = "BOOK"
            return receipt
        receipt = None
        next_pending = self._pending
        next_pending_protection = self._pending_protection
        next_protection = self._active_protection
        if next_pending is not None:
            request, submitted_at_ms = next_pending
            if book.available_at_ms > submitted_at_ms:
                previous = self._l2_book
                self._l2_book = book
                try:
                    price = self._l2_sweep(
                        side=request.side, quantity=request.quantity,
                        limit_price=request.limit_price,
                        allow_unfilled_limit=True,
                    )
                    if price is None and (
                        (request.side == "BUY"
                         and book.best_ask[0] <= request.limit_price)
                        or (request.side == "SELL"
                            and book.best_bid[0] >= request.limit_price)
                    ):
                        if request.order_id not in self._l2_underdepth_order_ids:
                            self._l2_underdepth_order_ids.add(request.order_id)
                            self._events.append(OrderEvent(
                                request.order_id, "DEPTH_UNPROVEN",
                                book.available_at_ms, order_type="LIMIT",
                            ))
                finally:
                    self._l2_book = previous
                if price is not None:
                    receipt = self._l2_receipt(
                        request.order_id, event_at_ms=book.available_at_ms,
                        side=request.side, quantity=request.quantity,
                        price=price, fee_rate=self.taker_fee_rate, suffix="_fill",
                    )
                    if next_pending_protection is None:
                        raise ValueError("unprotected L2 LIMIT entry is forbidden")
                    self.account.append(receipt)
                    self._l2_arm_partial(receipt, next_pending_protection)
                    next_protection = next_pending_protection
                    next_pending = None
                    next_pending_protection = None
        self._l2_book = book
        self._l2_event_at_ms = book.available_at_ms
        self._l2_event_kind = "BOOK"
        self._pending = next_pending
        self._pending_protection = next_pending_protection
        self._active_protection = next_protection
        if receipt is not None:
            self._events.append(OrderEvent(
                receipt.fill_id.removesuffix("_fill"), "FILLED",
                book.available_at_ms, order_type="LIMIT",
            ))
        elif self._active_protection is not None:
            receipt = self._l2_manage_partial_book(book)
        return receipt

    def on_historical_trade_batch(
        self, trades: tuple[TakerPrint, ...],
    ) -> VirtualFill | None:
        """Treat same-millisecond public executions as an unordered group.

        Bybit archive rows can share exact exchange timestamps. Trade IDs and
        CSV row order do NOT establish the sequence of those fills. Commit
        only an outcome which is independent of the group's internal order;
        otherwise fail closed without mutating the account.
        """
        if (not isinstance(trades, tuple) or not 0 < len(trades) <= 2000
                or any(not isinstance(t, TakerPrint) for t in trades)):
            raise ValueError("bounded original taker-print batch required")
        stamp = trades[0].event_ms
        if (any(t.event_ms != stamp or t.symbol != self.account.symbol
                for t in trades)
                or len({t.trade_id for t in trades}) != len(trades)):
            raise ValueError("mixed or duplicate same-millisecond taker prints")
        if len(trades) == 1:
            return self.on_historical_trade(trades[0])
        self._require_l2_event(stamp, kind="TRADE")
        if self._l2_book is None or stamp < self._l2_book.available_at_ms:
            raise ValueError("book state unavailable at historical trade time")
        if self._robot_limits or self._robot_markets or self._robot_stop is not None:
            raise ValueError("native multi-order matching not implemented for L2")
        if self._l2_pending_stop is not None:
            is_long = self._active_protection.entry.side == "BUY"
            worst = (
                min(trades, key=lambda t: t.price) if is_long
                else max(trades, key=lambda t: t.price)
            )
            self._l2_hold_triggered_stop(worst)
            return None
        qualifying: list[TakerPrint] = []
        if self._active_protection is not None:
            plan = self._active_protection
            is_long = plan.entry.side == "BUY"
            stop_price = self._l2_current_stop(plan)
            stops = [
                t for t in trades if
                (t.price <= stop_price if is_long else t.price >= stop_price)
            ]
            takes = [
                t for t in trades if (
                    (t.side == "Buy" and t.price > plan.take_price) if is_long else
                    (t.side == "Sell" and t.price < plan.take_price)
                )
            ]
            if stops and takes:
                raise ValueError("same-millisecond STOP/TAKE order is unproven")
            qualifying = stops or takes
            # For a STOP, select the most adverse observed trade. The virtual
            # book still determines executable price (or blocks stale depth).
            if stops:
                qualifying = [
                    min(stops, key=lambda t: t.price) if is_long
                    else max(stops, key=lambda t: t.price)
                ]
        elif self._pending is not None:
            request, submitted_at = self._pending
            if not isinstance(request, LimitRequest):
                raise ValueError("historical L2 requires protected LIMIT")
            if stamp > submitted_at:
                qualifying = [
                    t for t in trades
                    if ((request.side == "BUY" and t.side == "Sell"
                         and t.price < request.limit_price)
                        or (request.side == "SELL" and t.side == "Buy"
                            and t.price > request.limit_price))
                ]
            if qualifying:
                if self._pending_protection is None:
                    raise ValueError("unprotected L2 LIMIT entry is forbidden")
                plan = self._pending_protection
                is_long = request.side == "BUY"
                if any(
                    ((t.price <= plan.stop_price or t.price >= plan.take_price)
                     if is_long else
                     (t.price >= plan.stop_price or t.price <= plan.take_price))
                    for t in trades
                ):
                    raise ValueError("same-millisecond entry/exit order is unproven")
        if qualifying:
            return self.on_historical_trade(qualifying[0])
        # No price in this unordered batch can change the virtual account.
        # The batch is nevertheless consumed as one timestamped event.
        self._l2_event_at_ms = stamp
        self._l2_event_kind = "TRADE"
        return None

    def on_historical_trade(self, trade: TakerPrint) -> VirtualFill | None:
        """Trade-through of resting LIMIT, or trade-triggered protected exit.

        No trade/bar HIGH/LOW touch can fill a resting LIMIT; price must be
        strictly through, on the actual aggressive side, after submission.
        STOP is a trade-price trigger and fills by fresh opposite book depth.
        TAKE is conservative maker trade-through; no OHLC STOP-first shortcut.
        """
        if not isinstance(trade, TakerPrint) or trade.symbol != self.account.symbol:
            raise ValueError("original same-symbol taker execution required")
        self._require_l2_event(trade.event_ms, kind="TRADE")
        if self._l2_book is None or trade.event_ms < self._l2_book.available_at_ms:
            raise ValueError("book state unavailable at historical trade time")
        if self._robot_limits or self._robot_markets or self._robot_stop is not None:
            raise ValueError("native multi-order matching not implemented for L2")
        if self._l2_pending_stop is not None:
            self._l2_hold_triggered_stop(trade)
            return None
        receipt = None
        event = None
        next_pending = self._pending
        next_pending_protection = self._pending_protection
        next_protection = self._active_protection
        if next_protection is not None:
            plan = next_protection
            is_long = plan.entry.side == "BUY"
            stop_price = self._l2_current_stop(plan)
            stop_hit = trade.price <= stop_price if is_long else trade.price >= stop_price
            take_through = (
                (trade.side == "Buy" and trade.price > plan.take_price) if is_long
                else (trade.side == "Sell" and trade.price < plan.take_price)
            )
            if stop_hit:
                # A last trade can precede dissemination of the corresponding
                # book delta. Never fill from a contradictory/stale PRE-trade
                # book; wait for a fresh POST-trigger book with proven depth.
                if (trade.event_ms - self._l2_book.available_at_ms > 250
                        or (is_long and self._l2_book.best_bid[0] > trade.price)
                        or (not is_long and self._l2_book.best_ask[0] < trade.price)):
                    self._l2_pending_stop = (trade.event_ms, trade.price)
                    self._l2_deferred_stop_count += 1
                    self._events.append(OrderEvent(
                        plan.entry.order_id, "STOP_TRIGGER_DEFERRED",
                        trade.event_ms, order_type="STOP",
                    ))
                    self._l2_event_at_ms = trade.event_ms
                    self._l2_event_kind = "TRADE"
                    return None
                side = "SELL" if is_long else "BUY"
                price = self._l2_sweep(
                    side=side, quantity=self._l2_remaining_quantity(plan), limit_price=None,
                )
                fee_rate = self.taker_fee_rate
                reason = "STOP"
            elif take_through:
                side = "SELL" if is_long else "BUY"
                price = plan.take_price
                fee_rate = self.maker_fee_rate
                reason = "TAKE"
            else:
                price = None
            if price is not None:
                receipt = self._l2_receipt(
                    plan.entry.order_id, event_at_ms=trade.event_ms,
                    side=side, quantity=self._l2_remaining_quantity(plan), price=price,
                    fee_rate=fee_rate, suffix="_" + reason.lower() + "_fill",
                )
                event = OrderEvent(
                    plan.entry.order_id, reason + "_FILLED", trade.event_ms,
                    order_type=reason,
                )
                self.account.append(receipt)
                self._l2_clear_partial()
                next_protection = None
        elif next_pending is not None:
            request, submitted_at_ms = next_pending
            if not isinstance(request, LimitRequest):
                raise ValueError("historical L2 requires protected LIMIT")
            if (trade.event_ms > submitted_at_ms and
                    ((request.side == "BUY" and trade.side == "Sell"
                      and trade.price < request.limit_price)
                     or (request.side == "SELL" and trade.side == "Buy"
                         and trade.price > request.limit_price))):
                if next_pending_protection is None:
                    raise ValueError("unprotected L2 LIMIT entry is forbidden")
                receipt = self._l2_receipt(
                    request.order_id, event_at_ms=trade.event_ms,
                    side=request.side, quantity=request.quantity,
                    price=request.limit_price, fee_rate=self.maker_fee_rate,
                    suffix="_fill",
                )
                event = OrderEvent(
                    request.order_id, "FILLED", trade.event_ms, order_type="LIMIT",
                )
                self.account.append(receipt)
                self._l2_arm_partial(receipt, next_pending_protection)
                next_protection = next_pending_protection
                next_pending_protection = None
                next_pending = None
        self._l2_event_at_ms = trade.event_ms
        self._l2_event_kind = "TRADE"
        self._pending = next_pending
        self._pending_protection = next_pending_protection
        self._active_protection = next_protection
        if event is not None:
            self._events.append(event)
        return receipt

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

        if self.execution_mode == "HISTORICAL_L2":
            if (self._l2_pending_stop is not None
                    and minute.end_ms - self._l2_pending_stop[0] > 250):
                raise ValueError("deferred historical STOP remained unfilled past 250ms")
            # M1 drives only chart/Scanner time; fills already happened at
            # original trade/book event timestamps. Never call OHLC matching.
            if (self._l2_event_at_ms is not None
                    and self._l2_event_at_ms >= minute.end_ms):
                raise ValueError("historical L2 event exceeds current M1 close")
            self._last_close_ms = minute.end_ms
            self._last_minute_fills = ()
            self._last_minute_order_events = ()
            return None

        receipts: list[VirtualFill] = []
        new_events: list[OrderEvent] = []
        next_pending = self._pending
        next_pending_protection = self._pending_protection
        next_active_protection = self._active_protection

        if self._robot_limits or self._robot_markets or self._robot_stop is not None:
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
