"""Read-only M5 projection of the committed native Box SIMULATION journal."""
from __future__ import annotations

from typing import Callable

from research.historical_market_replay import Candle
from research.simulator_v2.robot_sandbox import ConnectedSimulationRobot
from research.simulator_v2.session import VirtualReplaySession

M5 = 300_000


class BoxVisualReplay:
    def __init__(
        self, *, run_id: str, symbol: str, start_ms: int, end_ms: int,
        on_events: Callable[[list[dict[str, object]]], None] | None = None,
    ) -> None:
        self.run_id = run_id
        self.symbol = symbol
        self.start_ms = start_ms
        self.end_ms = end_ms
        self._on_events = on_events
        self._items: list[dict[str, object]] = []
        self._bar: list[Candle] = []
        self._seen_exchange_events = 0
        self._emitted = 0
        self._fills = 0
        self._trade_id = f"SIMULATION:{run_id}:IKIGAI_BOX"
        self._event_order = {
            "CANDLE_CLOSED": 0, "ENTRY_SIGNAL": 1,
            "ENTRY_FILLED": 2, "EXIT_FILLED": 3,
        }

    def _roles(self, robot: ConnectedSimulationRobot) -> dict[str, str]:
        return robot.ownership_roles()

    def _publish(self) -> None:
        if self._on_events is None or self._emitted == len(self._items):
            return
        pending = sorted(
            self._items[self._emitted:],
            key=lambda item: (item["time_ms"], self._event_order[item["kind"]]),
        )
        frame = [
            {"source": "SIMULATION", "simulation_run_id": self.run_id,
             "sequence": self._emitted + index + 1, **item}
            for index, item in enumerate(pending)
        ]
        self._on_events(frame)
        self._emitted += len(frame)

    def record(
        self, session: VirtualReplaySession, robot: ConnectedSimulationRobot | None,
        minute: Candle,
    ) -> None:
        if not self.start_ms <= minute.start_ms < self.end_ms:
            return
        roles = self._roles(robot) if robot is not None else {}
        events = session.exchange.events
        for event in events[self._seen_exchange_events:]:
            if event.kind == "SUBMITTED" and roles.get(event.order_id) == "ENTRY":
                request = next((
                    item.entry for item in session.exchange.robot_limits
                    if item.entry.order_id == event.order_id
                ), None)
                if request is not None:
                    self._items.append({
                        "kind": "ENTRY_SIGNAL", "time_ms": event.virtual_time_ms,
                        "side": "LONG" if request.side == "BUY" else "SHORT",
                        "price": float(request.limit_price), "trade_id": self._trade_id,
                    })
        self._seen_exchange_events = len(events)

        for fill, event in zip(
            session.exchange.last_minute_fills,
            session.exchange.last_minute_order_events,
        ):
            is_entry = roles.get(event.order_id) == "ENTRY"
            self._items.append({
                "kind": "ENTRY_FILLED" if is_entry else "EXIT_FILLED",
                "time_ms": event.virtual_time_ms,
                "side": (
                    "LONG" if fill.side == "BUY" else "SHORT"
                ) if is_entry else (
                    "LONG" if fill.side == "SELL" else "SHORT"
                ),
                "price": float(fill.price), "trade_id": self._trade_id,
                **({} if is_entry else {
                    "reason": "STOP" if event.kind == "STOP_FILLED" else "TAKE",
                }),
            })
            self._fills += 1

        if minute.start_ms % M5 == 0:
            self._bar.clear()
        if minute.start_ms % M5 == 0 or self._bar:
            self._bar.append(minute)
            if len(self._bar) == 5:
                bars = self._bar
                self._items.append({
                    "kind": "CANDLE_CLOSED", "time_ms": bars[-1].end_ms,
                    "candle": {
                        "start_ms": bars[0].start_ms, "end_ms": bars[-1].end_ms,
                        "open": float(bars[0].open),
                        "high": float(max(item.high for item in bars)),
                        "low": float(min(item.low for item in bars)),
                        "close": float(bars[-1].close),
                        "volume": float(sum((item.volume for item in bars), 0)),
                    },
                })
                self._bar = []
                self._publish()

    def document(self, *, source_id: str, expected_fills: int) -> dict[str, object]:
        if self._fills != expected_fills:
            raise ValueError(
                f"Box replay marker count {self._fills} disagrees with "
                f"virtual account {expected_fills}"
            )
        self._publish()
        items = sorted(
            self._items,
            key=lambda item: (item["time_ms"], self._event_order[item["kind"]]),
        )
        return {
            "source": "SIMULATION", "simulation_run_id": self.run_id,
            "mode": "STRATEGY", "demo": False, "timeframe": "5m",
            "symbol": self.symbol,
            "market_data_source": "BYBIT_OFFICIAL_PUBLIC_TRADES_DERIVED_5M",
            "source_id": source_id,
            "events": [
                {"source": "SIMULATION", "simulation_run_id": self.run_id,
                 "sequence": index, **item}
                for index, item in enumerate(items, 1)
            ],
        }
