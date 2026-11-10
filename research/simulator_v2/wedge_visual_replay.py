"""Verified M5 visual projection from the SAME committed Wedge SIMULATION M1.

The recorder observes only the existing session after each committed M1,
never decides trades, imports PAPER, fetches market data or guesses a fill.
Incomplete 5m groups are not shown as completed M5 candles.
"""
from __future__ import annotations

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession

FIVE_MIN_MS = 300_000


class WedgeVisualReplay:
    def __init__(self, *, run_id: str, symbol: str, start_ms: int, end_ms: int):
        self.run_id = run_id
        self.symbol = symbol
        self.start_ms = start_ms
        self.end_ms = end_ms
        self._bar: list[Candle] = []
        self._items: list[dict[str, object]] = []
        self._order_count = 0
        self._fills = 0
        self._m5 = 0

    def record(self, session: VirtualReplaySession, minute: Candle) -> None:
        if not self.start_ms <= minute.start_ms < self.end_ms:
            return
        if session.account.symbol != self.symbol or (
            session.account.simulation_run_id != self.run_id
        ):
            raise ValueError("visual replay changed SIMULATION identity")
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
            self._items.append({
                "kind": "ENTRY_FILLED" if entry else "EXIT_FILLED",
                "time_ms": receipt.virtual_time_ms,
                "side": ("LONG" if receipt.side == "BUY" else "SHORT")
                    if entry else ("LONG" if receipt.side == "SELL" else "SHORT"),
                "price": float(receipt.price),
                "trade_id": f"SIMULATION:{self.run_id}:{order.order_id}",
                **({} if entry else {"reason": order.kind.replace("_FILLED", "")}),
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

    def document(self, *, source_id: str, expected_fills: int) -> dict[str, object]:
        if self._fills != expected_fills:
            raise ValueError("replay marker count disagrees with virtual account")
        if self._m5 < 1:
            raise ValueError("Период не содержит завершённых M5-свечей для графика")
        order = {"CANDLE_CLOSED": 0, "ENTRY_SIGNAL": 1,
                 "ENTRY_FILLED": 2, "EXIT_FILLED": 3}
        items = sorted(self._items, key=lambda x: (x["time_ms"], order[x["kind"]]))
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
