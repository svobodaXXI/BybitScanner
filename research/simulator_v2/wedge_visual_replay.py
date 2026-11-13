"""Verified M5 visual projection from the SAME committed Wedge SIMULATION M1.

The recorder observes only the existing session after each committed M1,
never decides trades, imports PAPER, fetches market data or guesses a fill.
Incomplete 5m groups are not shown as completed M5 candles.
"""
from __future__ import annotations

from typing import Callable

from research.historical_market_replay import Candle
from robot_entry_flow_evidence import ImpulseProtectedPlan
from research.wilder_dmi import WilderDmi
from research.simulator_v2.session import VirtualReplaySession

FIVE_MIN_MS = 300_000


class WedgeVisualReplay:
    def __init__(
        self, *, run_id: str, symbol: str, start_ms: int, end_ms: int,
        on_events: Callable[[list[dict[str, object]]], None] | None = None,
        impulse_plans: dict[str, ImpulseProtectedPlan] | None = None,
        historical_l2: bool = False,
    ):
        self.run_id = run_id
        self.symbol = symbol
        self.start_ms = start_ms
        self.end_ms = end_ms
        self._bar: list[Candle] = []
        self._dmi = WilderDmi(timeframe_ms=FIVE_MIN_MS)
        self._items: list[dict[str, object]] = []
        self._order_count = 0
        self._decision_count = 0
        self._entry_receipts: dict[str, object] = {}
        self._fills = 0
        self._m5 = 0
        self._last_released_trade_events = 0
        self._on_events = on_events
        self._impulse_plans = impulse_plans
        if type(historical_l2) is not bool:
            raise TypeError("explicit historical L2 visual flag required")
        self._historical_l2 = historical_l2
        self._partial_receipts: dict[str, object] = {}
        self._emitted = 0
        self._event_order = {
            "CANDLE_CLOSED": 0, "WEDGE_ACCEPTED": 1, "WEDGE_BREAKOUT": 2,
            "WEDGE_RETEST": 3, "ENTRY_SIGNAL": 4,
            "ENTRY_FILLED": 5, "PARTIAL_FILLED": 6,
            "STOP_AMENDED": 7, "EXIT_FILLED": 8,
        }

    def _publish(self) -> None:
        """Only committed events, with the same ordering/IDs as final replay.

        The first M5 is sent immediately. Subsequent batches contain at
        most one hour of additional M5 bars to avoid excessive UI renders.
        """
        if self._on_events is None or self._emitted == len(self._items):
            return
        pending = sorted(
            self._items[self._emitted:],
            key=lambda x: (x["time_ms"], self._event_order[x["kind"]]),
        )
        frame = [
            {"source": "SIMULATION", "simulation_run_id": self.run_id,
             "sequence": self._emitted + i + 1, **item}
            for i, item in enumerate(pending)
        ]
        self._on_events(frame)
        self._emitted += len(frame)
        self._last_released_trade_events += sum(
            item["kind"] != "CANDLE_CLOSED" for item in pending
        )

    def _record_l2_fills(
        self, session: VirtualReplaySession, minute: Candle,
        events: tuple,
    ) -> None:
        """Project only original event-time virtual journal, never M1 OHLC fills.

        Cross-check each receipt against the immutable account and matching
        order event. Mixed/partial chronology must not be guessed or reordered.
        """
        if session.exchange.execution_mode != "HISTORICAL_L2":
            raise ValueError("L2 visual journal requires original L2 exchange")
        fresh = session.account.fills[self._fills:]
        receipts = {fill.fill_id: fill for fill in fresh}
        if len(receipts) != len(fresh):
            raise ValueError("duplicate L2 virtual receipt ID in replay")
        matched: set[str] = set()
        suffix = {
            "FILLED": "_fill",
            "PARTIAL_TAKE_FILLED": "_partial_fill",
            "STOP_FILLED": "_stop_fill",
            "TAKE_FILLED": "_take_fill",
        }
        for order in events:
            if order.kind == "STOP_AMENDED_BE":
                if order.order_id not in self._partial_receipts:
                    raise ValueError("L2 BE amendment without a preceding partial fill")
                if not minute.start_ms <= order.virtual_time_ms < minute.end_ms:
                    raise ValueError("L2 amended STOP escaped its original minute")
                if order.stop_price is None or order.stop_price <= 0:
                    raise ValueError("BE STOP amendment lacks original virtual stop price")
                self._items.append({
                    "kind": "STOP_AMENDED", "time_ms": order.virtual_time_ms,
                    "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
                    "reason": "NET_BREAK_EVEN_AFTER_PARTIAL",
                    "stop": float(order.stop_price),
                })
                continue
            if order.kind not in suffix:
                continue
            identity = order.order_id + suffix[order.kind]
            receipt = receipts.get(identity)
            if (identity in matched or receipt is None
                    or receipt.virtual_time_ms != order.virtual_time_ms
                    or not minute.start_ms <= receipt.virtual_time_ms < minute.end_ms):
                raise ValueError("L2 fill has no corresponding event-time ledger receipt")
            matched.add(identity)
            entry = order.kind == "FILLED"
            side = "LONG" if (receipt.side == "BUY") == entry else "SHORT"
            financials = {}
            if entry:
                if order.order_id in self._entry_receipts:
                    raise ValueError("duplicate L2 entry visual receipt")
                self._entry_receipts[order.order_id] = receipt
            elif order.kind == "PARTIAL_TAKE_FILLED":
                original = self._entry_receipts.get(order.order_id)
                if (original is None or order.order_id in self._partial_receipts
                        or original.side == receipt.side
                        or not 0 < receipt.quantity < original.quantity):
                    raise ValueError("unproven L2 partial quantity or identity")
                self._partial_receipts[order.order_id] = receipt
                financials = {
                    "reason": "PARTIAL_TAKE",
                    "quantity": format(receipt.quantity, "f"),
                    "fee_usdt": format(receipt.fee, "f"),
                }
            else:
                original = self._entry_receipts.pop(order.order_id, None)
                partial = self._partial_receipts.pop(order.order_id, None)
                if (original is None or original.side == receipt.side
                        or receipt.quantity + (partial.quantity if partial else 0)
                        != original.quantity):
                    raise ValueError("L2 final exit does not reconcile position quantity")
                direction = 1 if original.side == "BUY" else -1
                gross = ((receipt.price - original.price) * receipt.quantity
                         + ((partial.price - original.price) * partial.quantity
                            if partial else 0)) * direction
                net = gross - original.fee - receipt.fee - (partial.fee if partial else 0)
                basis = original.price * original.quantity
                financials = {
                    "reason": order.kind.removesuffix("_FILLED"),
                    "quantity": format(receipt.quantity, "f"),
                    "net_usdt": format(net, "f"),
                    "pnl_percent": format(net * 100 / basis, "f"),
                }
            self._items.append({
                "kind": ("ENTRY_FILLED" if entry else
                         "PARTIAL_FILLED" if order.kind == "PARTIAL_TAKE_FILLED"
                         else "EXIT_FILLED"),
                "time_ms": receipt.virtual_time_ms,
                "side": side,
                "price": float(receipt.price),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
                "quantity": format(receipt.quantity, "f"),
                "fee_usdt": format(receipt.fee, "f"),
                **financials,
            })
            self._fills += 1
        if matched != set(receipts):
            raise ValueError("orphan L2 account receipt cannot be visualized")

    def record(self, session: VirtualReplaySession, minute: Candle) -> None:
        if not self.start_ms <= minute.start_ms < self.end_ms:
            return
        if session.account.symbol != self.symbol or (
            session.account.simulation_run_id != self.run_id
        ):
            raise ValueError("visual replay changed SIMULATION identity")
        if (session.exchange.execution_mode == "HISTORICAL_L2") != self._historical_l2:
            raise ValueError("legacy M1 visual cannot mislabel L2 event-time fills")
        robot = session.wedge_robot
        if robot is None and self._impulse_plans is None:
            raise ValueError("visual replay requires committed Wedge or impulse Robot")
        decisions = robot.decisions if robot is not None else ()
        if len(decisions) < self._decision_count:
            raise ValueError("Robot decisions went backwards")
        for decision in decisions[self._decision_count:]:
            if decision.virtual_time_ms != minute.end_ms:
                continue
            kind = {
                "INITIALIZED": "WEDGE_ACCEPTED",
                "BREAKOUT": "WEDGE_BREAKOUT",
                "RETEST": "WEDGE_RETEST",
            }.get(decision.event)
            if kind is not None:
                self._items.append({
                    "kind": kind, "time_ms": decision.virtual_time_ms,
                    "pattern": decision.pattern,
                    "candidate_id": decision.candidate_id,
                })
        self._decision_count = len(decisions)
        orders = session.exchange.events
        if len(orders) < self._order_count:
            raise ValueError("virtual order journal went backwards")
        # The existing Robot created every protected LIMIT. Expose the actual
        # submission, never an unapproved candidate as a trade entry.
        fresh_orders = orders[self._order_count:]
        for order in fresh_orders:
            if order.kind != "SUBMITTED" or order.order_type != "LIMIT":
                continue
            if robot is None:
                # Impulse order must match a committed shared Robot plan.
                plan = (self._impulse_plans or {}).get(order.order_id)
                if plan is None or plan.signal.known_at_ms != order.virtual_time_ms:
                    raise ValueError("impulse LIMIT lacks committed Robot risk plan")
                side, price, stop, take = (
                    plan.signal.direction, plan.entry_price,
                    plan.stop_price, plan.take_price,
                )
            else:
                preview = next((
                    p for p in robot.risk_previews
                    if p.request.order_id == order.order_id
                ), None)
                if preview is None:
                    raise ValueError("unproved LIMIT submitted without Robot risk preview")
                side = "LONG" if preview.request.side == "BUY" else "SHORT"
                price, stop, take = (
                    preview.request.limit_price, preview.stop_price,
                    preview.take_price,
                )
            self._items.append({
                "kind": "ENTRY_SIGNAL", "time_ms": order.virtual_time_ms,
                "side": side,
                "price": float(price),
                "stop": float(stop), "take": float(take),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
            })
        self._order_count = len(orders)

        if self._historical_l2:
            self._record_l2_fills(session, minute, fresh_orders)
            receipts = ()
            fill_events = ()
        else:
            if session.exchange.execution_mode != "OHLC_M1":
                raise ValueError("legacy M1 visual cannot mislabel L2 event-time fills")
            receipts = session.exchange.last_minute_fills
            fill_events = session.exchange.last_minute_order_events
        if len(receipts) != len(fill_events):
            raise ValueError("virtual fills and exchange events diverged")
        for receipt, order in zip(receipts, fill_events):
            if receipt.virtual_time_ms != minute.end_ms or (
                order.virtual_time_ms != minute.end_ms
            ):
                raise ValueError("visual fill escaped its committed M1")
            entry = order.kind == "FILLED"
            if not entry and order.kind not in ("STOP_FILLED", "TAKE_FILLED"):
                raise ValueError("unclassified virtual exit")
            # Only original immutable virtual exchange receipts define PnL.
            # Percent is net profit divided by entry notional, not deposit ROI.
            financials: dict[str, str] = {}
            if entry:
                self._entry_receipts[order.order_id] = receipt
            else:
                original = self._entry_receipts.pop(order.order_id, None)
                if original is None or original.quantity != receipt.quantity:
                    raise ValueError("virtual exit lacks a matching entry receipt")
                gross = (receipt.price - original.price) * receipt.quantity * (
                    1 if original.side == "BUY" else -1
                )
                net = gross - original.fee - receipt.fee
                entry_notional = original.price * original.quantity
                financials = {
                    "net_usdt": format(net, "f"),
                    "pnl_percent": format(net * 100 / entry_notional, "f"),
                }
            self._items.append({
                "kind": "ENTRY_FILLED" if entry else "EXIT_FILLED",
                "time_ms": receipt.virtual_time_ms,
                "side": ("LONG" if receipt.side == "BUY" else "SHORT")
                    if entry else ("LONG" if receipt.side == "SELL" else "SHORT"),
                "price": float(receipt.price),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
                **({} if entry else {"reason": order.kind.replace("_FILLED", "")}),
                **financials,
            })
            self._fills += 1

        # The viewport is explicitly M5: never render an incomplete M5 bar.
        # Partial first/last M1 remain in the PnL but are not false M5 OHLC.
        if minute.start_ms % FIVE_MIN_MS == 0:
            self._bar.clear()
        if minute.start_ms % FIVE_MIN_MS == 0 or self._bar:
            if self._bar and minute.start_ms != self._bar[-1].end_ms:
                raise ValueError("gap in visual M5 input")
            self._bar.append(minute)
            if len(self._bar) == 5:
                bars = self._bar
                completed = Candle(
                    start_ms=bars[0].start_ms, interval_ms=FIVE_MIN_MS,
                    open=bars[0].open, high=max(c.high for c in bars),
                    low=min(c.low for c in bars), close=bars[-1].close,
                    volume=sum((c.volume for c in bars), 0),
                )
                dmi = self._dmi.observe_closed(completed)
                self._items.append({
                    "kind": "CANDLE_CLOSED", "time_ms": bars[-1].end_ms,
                    "dmi": {
                        "time_ms": dmi.time_ms,
                        "plus_di": float(dmi.plus_di) if dmi.plus_di is not None else None,
                        "minus_di": float(dmi.minus_di) if dmi.minus_di is not None else None,
                        "adx": float(dmi.adx) if dmi.adx is not None else None,
                    },
                    "candle": {
                        "start_ms": bars[0].start_ms, "end_ms": bars[-1].end_ms,
                        "open": float(bars[0].open),
                        "high": float(max(c.high for c in bars)),
                        "low": float(min(c.low for c in bars)),
                        "close": float(bars[-1].close),
                        "volume": float(sum((c.volume for c in bars), 0)),
                    },
                })
                self._m5 += 1
                self._bar = []
                # A newly verified trade action must not wait for an hourly
                # candle batch: release after its CLOSED M5 alongside the bar.
                new_actions = sum(
                    item["kind"] != "CANDLE_CLOSED"
                    for item in self._items[self._emitted:]
                )
                if self._m5 == 1 or self._m5 % 3 == 0 or new_actions:
                    self._publish()

    def document(self, *, source_id: str, expected_fills: int) -> dict[str, object]:
        if self._fills != expected_fills:
            raise ValueError("replay marker count disagrees with virtual account")
        if self._m5 < 1:
            raise ValueError("Период не содержит завершённых M5-свечей для графика")
        self._publish()  # Last partial hour can contain executed orders.
        items = sorted(self._items, key=lambda x: (x["time_ms"], self._event_order[x["kind"]]))
        if len(items) > 100_000:
            raise ValueError("visual replay event count exceeds viewer limit")
        events = [
            {"source": "SIMULATION", "simulation_run_id": self.run_id,
             "sequence": index, **item}
            for index, item in enumerate(items, 1)
        ]
        return {
            "source": "SIMULATION", "simulation_run_id": self.run_id,
            "mode": "STRATEGY", "demo": False, "timeframe": "5m",
            "symbol": self.symbol,
            "market_data_source": (
                "PINNED_BYBIT_PUBLIC_TRADES_PLUS_L2_EVENT_TIME_SIMULATION"
                if self._historical_l2 else "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M"
            ),
            **({"execution_certainty": "CONDITIONAL_L2_NOT_REAL_EXCHANGE_FILLS",
                "execution_clock": "ORIGINAL_EVENT_TIME_NOT_OHLC_M1",
                "partial_and_be_markers": "EVENTS_ONLY_CONDITIONAL"
                } if self._historical_l2 else {}),
            "source_id": source_id,
            "events": events,
        }
