"""Verified M5 visual projection from the SAME committed Wedge SIMULATION M1.

The recorder observes only the existing session after each committed M1,
never decides trades, imports PAPER, fetches market data or guesses a fill.
Incomplete 5m groups are not shown as completed M5 candles.
"""
from __future__ import annotations

from typing import Callable

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession

FIVE_MIN_MS = 300_000


class WedgeVisualReplay:
    def __init__(
        self, *, run_id: str, symbol: str, start_ms: int, end_ms: int,
        on_events: Callable[[list[dict[str, object]]], None] | None = None,
    ):
        self.run_id = run_id
        self.symbol = symbol
        self.start_ms = start_ms
        self.end_ms = end_ms
        self._bar: list[Candle] = []
        self._items: list[dict[str, object]] = []
        self._order_count = 0
        self._decision_count = 0
        self._entry_receipts: dict[str, object] = {}
        self._fills = 0
        self._m5 = 0
        self._last_released_trade_events = 0
        self._on_events = on_events
        self._emitted = 0
        self._event_order = {
            "CANDLE_CLOSED": 0, "WEDGE_ACCEPTED": 1, "WEDGE_BREAKOUT": 2,
            "WEDGE_RETEST": 3, "ENTRY_SIGNAL": 4,
            "ENTRY_FILLED": 5, "EXIT_FILLED": 6,
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

    def record(self, session: VirtualReplaySession, minute: Candle) -> None:
        if not self.start_ms <= minute.start_ms < self.end_ms:
            return
        if session.account.symbol != self.symbol or (
            session.account.simulation_run_id != self.run_id
        ):
            raise ValueError("visual replay changed SIMULATION identity")
        robot = session.wedge_robot
        if robot is None:
            raise ValueError("visual replay requires the original Wedge Robot")
        decisions = robot.decisions
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
        for order in orders[self._order_count:]:
            if order.kind != "SUBMITTED" or order.order_type != "LIMIT":
                continue
            robot = session.wedge_robot
            if robot is None:
                raise ValueError("visual replay requires original Wedge Robot")
            preview = next((
                p for p in robot.risk_previews
                if p.request.order_id == order.order_id
            ), None)
            if preview is None:
                raise ValueError("unproved LIMIT submitted without Robot risk preview")
            self._items.append({
                "kind": "ENTRY_SIGNAL", "time_ms": order.virtual_time_ms,
                "side": "LONG" if preview.request.side == "BUY" else "SHORT",
                "price": float(preview.request.limit_price),
                "stop": float(preview.stop_price), "take": float(preview.take_price),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
            })
        self._order_count = len(orders)

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
                    "net_usdt": str(net),
                    "pnl_percent": str(net * 100 / entry_notional),
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
                self._items.append({
                    "kind": "CANDLE_CLOSED", "time_ms": bars[-1].end_ms,
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
            "market_data_source": "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
            "source_id": source_id,
            "events": events,
        }
