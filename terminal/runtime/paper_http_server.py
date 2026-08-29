"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import websocket
import requests

from terminal.api.models import (
    CloseAllCommandRequest,
    ClientActionId,
    CommandResult,
    CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest,
    MarketCommandRequest,
    PaperLimitCancelRequest,
    PaperLimitAmendRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
    to_primitive,
)
from terminal.domain.models import OrderSide
from terminal.domain.models import Price, Quantity, Symbol
from terminal.exchange.normalization import normalize_instrument
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime


LOGGER = logging.getLogger(__name__)


HOST = "127.0.0.1"
PORT = 8765
MARKET_FIELDS = {
    "client_action_id",
    "symbol",
    "side",
    "volume",
    "sizing_reference_price",
    "slippage_type",
    "slippage_value",
}
VOLUME_FIELDS = {"unit", "amount"}
FULL_CLOSE_FIELDS = {"client_action_id", "symbol"}
CLOSE_ALL_FIELDS = {"client_action_id"}
LIMIT_FIELDS = {
    "client_action_id", "symbol", "side", "volume", "sizing_reference_price",
    "limit_price", "time_in_force",
}
LIMIT_CANCEL_FIELDS = {"client_action_id", "symbol", "order_id"}
LIMIT_AMEND_FIELDS = {"client_action_id", "symbol", "order_id", "limit_price"}
NATIVE_KLINE_INTERVALS = ("1", "5", "15", "60", "D")
SUPPORTED_KLINE_INTERVALS = ("15s", *NATIVE_KLINE_INTERVALS)


class PublicTradeBuffer:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        maxlen: int = 500,
        *,
        tick_size: Decimal = Decimal("0.00001"),
        aggregation_window_ms: int = 50,
        book_descriptor_provider: Callable[[], dict | None] | None = None,
        raw_trade_consumer: Callable[[list[dict]], None] | None = None,
    ) -> None:
        if tick_size <= 0 or aggregation_window_ms < 0:
            raise ValueError("invalid public-trade aggregation settings")
        self.symbol = symbol
        self._trades: deque[dict] = deque(maxlen=maxlen)
        self._active: dict | None = None
        self._tick_size = tick_size
        self._aggregation_window_ms = aggregation_window_ms
        self._book_descriptor_provider = book_descriptor_provider
        self._raw_trade_consumer = raw_trade_consumer
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="bybit-public-trades",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()

    def snapshot_after(self, after: int) -> list[dict]:
        with self._lock:
            self._flush_expired_locked(int(time.time() * 1000))
            return [
                trade.copy()
                for trade in self._trades
                if int(trade["seq"]) > after
            ]

    def add_trades(self, trades: list[dict]) -> None:
        ordered = sorted(
            trades,
            key=lambda item: (int(item["timestamp"]), int(item["seq"])),
        )
        if self._raw_trade_consumer is not None:
            self._raw_trade_consumer(ordered)
        with self._lock:
            for trade in ordered:
                self._add_trade_locked(trade)

    def flush(self) -> None:
        with self._lock:
            self._flush_active_locked()

    def _add_trade_locked(self, trade: dict) -> None:
        timestamp = int(trade["timestamp"])
        received_at_ms = int(trade.get("received_at_ms") or time.time() * 1000)
        trade_seq = int(trade["seq"])
        side = str(trade["side"])
        price = Decimal(str(trade["price"]))
        quantity = Decimal(str(trade["quantity"]))
        if side not in ("BUY", "SELL") or price <= 0 or quantity <= 0:
            return

        active = self._active
        if active is not None and (
            active["side"] != side
            or timestamp - int(active["ended_at_ms"]) > self._aggregation_window_ms
        ):
            self._flush_active_locked()
            active = None

        if active is None:
            self._active = {
                "id": f"cumulative-{side.lower()}-{trade['id']}",
                "seq": int(trade["seq"]),
                "symbol": self.symbol,
                "side": side,
                "started_at_ms": timestamp,
                "ended_at_ms": timestamp,
                "first_trade_seq": trade_seq,
                "last_trade_seq": trade_seq,
                "backend_first_received_at_ms": received_at_ms,
                "backend_last_received_at_ms": received_at_ms,
                "trade_count": 0,
                "total_quantity": Decimal("0"),
                "total_notional_usdt": Decimal("0"),
                "first_execution_price": price,
                "last_execution_price": price,
                "min_execution_price": price,
                "max_execution_price": price,
                "trade_ids": [],
            }
            active = self._active

        active["seq"] = max(int(active["seq"]), int(trade["seq"]))
        active["ended_at_ms"] = timestamp
        active["last_trade_seq"] = trade_seq
        active["backend_last_received_at_ms"] = received_at_ms
        active["trade_count"] += 1
        active["total_quantity"] += quantity
        active["total_notional_usdt"] += price * quantity
        active["last_execution_price"] = price
        active["min_execution_price"] = min(active["min_execution_price"], price)
        active["max_execution_price"] = max(active["max_execution_price"], price)
        active["trade_ids"].append(str(trade["id"]))

    def _flush_expired_locked(self, now_ms: int) -> None:
        if self._active is not None and (
            now_ms - int(self._active["ended_at_ms"])
            >= self._aggregation_window_ms
        ):
            self._flush_active_locked()

    def _flush_active_locked(self) -> None:
        if self._active is None:
            return
        active = self._active
        finalized_at_ms = int(time.time() * 1000)
        book_correlation = None
        if self._book_descriptor_provider is not None:
            book_descriptor = self._book_descriptor_provider()
            if book_descriptor is not None:
                book_correlation = {
                    "basis": "LATEST_BACKEND_KNOWN_AT_FINALIZATION",
                    **book_descriptor,
                }
        low = active["min_execution_price"]
        high = active["max_execution_price"]
        swept_ticks = int(
            ((high - low) / self._tick_size).to_integral_value(
                rounding=ROUND_CEILING,
            )
        ) + 1
        self._trades.append({
            **active,
            "total_quantity": str(active["total_quantity"]),
            "total_notional_usdt": str(active["total_notional_usdt"]),
            "first_execution_price": str(active["first_execution_price"]),
            "last_execution_price": str(active["last_execution_price"]),
            "min_execution_price": str(low),
            "max_execution_price": str(high),
            "sweep_low_price": str(low),
            "sweep_high_price": str(high),
            "swept_price_range": str(high - low),
            "swept_ticks": swept_ticks,
            "tick_size": str(self._tick_size),
            "aggregation_window_ms": self._aggregation_window_ms,
            "finalized_at_ms": finalized_at_ms,
            "book_correlation": book_correlation,
        })
        self._active = None

    def _run(self) -> None:
        while not self._stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(
                    "wss://stream.bybit.com/v5/public/linear",
                    timeout=10,
                )

                ws.send(json.dumps({
                    "op": "subscribe",
                    "args": [f"publicTrade.{self.symbol}"],
                }))

                while not self._stop.is_set():
                    raw = ws.recv()
                    message = json.loads(raw)

                    if message.get("topic") != f"publicTrade.{self.symbol}":
                        continue

                    data = message.get("data")
                    if not isinstance(data, list):
                        continue

                    normalized = []
                    received_at_ms = int(time.time() * 1000)

                    for index, trade in enumerate(data):
                        if not isinstance(trade, dict):
                            continue

                        side = trade.get("S")
                        price = trade.get("p")
                        quantity = trade.get("v")

                        if side not in ("Buy", "Sell"):
                            continue
                        if price is None or quantity is None:
                            continue

                        timestamp = int(trade.get("T") or time.time() * 1000)
                        seq = int(trade.get("seq") or timestamp * 1000 + index)

                        normalized.append({
                            "id": str(
                                trade.get("i")
                                or f"{timestamp}-{seq}-{index}"
                            ),
                            "seq": seq,
                            "timestamp": timestamp,
                            "symbol": self.symbol,
                            "side": "BUY" if side == "Buy" else "SELL",
                            "price": str(price),
                            "quantity": str(quantity),
                            "received_at_ms": received_at_ms,
                        })

                    if normalized:
                        self.add_trades(normalized)

            except Exception:
                if not self._stop.is_set():
                    time.sleep(1.5)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass


class PublicOrderBookBuffer:
    def __init__(self, symbol: str = "BTCUSDT", depth: int = 50) -> None:
        self.symbol = symbol
        self.depth = depth
        self._bids: dict[str, str] = {}
        self._asks: dict[str, str] = {}
        self._state = "DISCONNECTED"
        self._timestamp = 0
        self._matching_engine_cts = None
        self._received_at = 0
        self._update_id = 0
        self._sequence = 0
        self._version = 0
        self._update_consumer: Callable[[str], None] | None = None
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="bybit-public-orderbook",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()

    def snapshot_after(
        self,
        after_version: int,
        timeout: float = 15.0,
    ) -> dict:
        with self._condition:
            self._condition.wait_for(
                lambda: self._version > after_version or self._stop.is_set(),
                timeout=timeout,
            )
            return self._snapshot_locked()

    def snapshot(self) -> dict:
        with self._condition:
            return self._snapshot_locked()

    def set_update_consumer(self, consumer: Callable[[str], None] | None) -> None:
        with self._condition:
            self._update_consumer = consumer

    def apply_message(self, message: dict) -> str:
        if message.get("topic") != f"orderbook.{self.depth}.{self.symbol}":
            return "IGNORED"

        message_type = message.get("type")
        data = message.get("data")
        if message_type not in ("snapshot", "delta") or not isinstance(data, dict):
            return "IGNORED"

        try:
            update_id = int(data["u"])
            sequence = int(data.get("seq") or 0)
            timestamp = int(message.get("ts") or time.time() * 1000)
            raw_cts = data.get("cts", message.get("cts"))
            matching_engine_cts = int(raw_cts) if raw_cts is not None else None
            bids = self._levels(data.get("b"))
            asks = self._levels(data.get("a"))
        except (KeyError, TypeError, ValueError):
            return "IGNORED"

        with self._condition:
            if message_type == "snapshot":
                self._bids = bids
                self._asks = asks
            else:
                if self._state != "READY":
                    return "IGNORED"
                if update_id <= self._update_id:
                    return "IGNORED"
                self._apply_delta(self._bids, bids)
                self._apply_delta(self._asks, asks)

            self._trim_locked()
            self._state = "READY"
            self._timestamp = timestamp
            self._matching_engine_cts = matching_engine_cts
            self._received_at = int(time.time() * 1000)
            self._update_id = update_id
            self._sequence = sequence
            self._version += 1
            book_update_id = f"{self.symbol}:{sequence}:{update_id}"
            update_consumer = self._update_consumer
            self._condition.notify_all()

        if update_consumer is not None:
            try:
                update_consumer(book_update_id)
            except Exception:
                LOGGER.exception(
                    "PAPER order-book notification failed; book_update_id=%s",
                    book_update_id,
                )
        return "APPLIED"

    @staticmethod
    def _levels(raw_levels: object) -> dict[str, str]:
        if not isinstance(raw_levels, list):
            raise ValueError("order-book levels must be a list")

        levels: dict[str, str] = {}
        for raw_level in raw_levels:
            if not isinstance(raw_level, list) or len(raw_level) != 2:
                raise ValueError("invalid order-book level")
            price = str(raw_level[0])
            size = str(raw_level[1])
            parsed_price = Decimal(price)
            parsed_size = Decimal(size)
            if not parsed_price.is_finite() or parsed_price <= 0:
                raise ValueError("invalid order-book price")
            if not parsed_size.is_finite() or parsed_size < 0:
                raise ValueError("invalid order-book size")
            levels[price] = size
        return levels

    @staticmethod
    def _apply_delta(target: dict[str, str], updates: dict[str, str]) -> None:
        for price, size in updates.items():
            if Decimal(size) == 0:
                target.pop(price, None)
            else:
                target[price] = size

    def _trim_locked(self) -> None:
        self._bids = dict(sorted(
            self._bids.items(),
            key=lambda item: Decimal(item[0]),
            reverse=True,
        )[:self.depth])
        self._asks = dict(sorted(
            self._asks.items(),
            key=lambda item: Decimal(item[0]),
        )[:self.depth])

    def _clear(self, state: str) -> None:
        with self._condition:
            self._clear_locked(state)

    def _clear_locked(self, state: str) -> None:
        self._bids.clear()
        self._asks.clear()
        self._state = state
        self._timestamp = int(time.time() * 1000)
        self._received_at = self._timestamp
        self._matching_engine_cts = None
        self._update_id = 0
        self._sequence = 0
        self._version += 1
        self._condition.notify_all()

    def _snapshot_locked(self) -> dict:
        return {
            "symbol": self.symbol,
            "bids": [
                {"price": price, "size": size}
                for price, size in self._bids.items()
            ],
            "asks": [
                {"price": price, "size": size}
                for price, size in self._asks.items()
            ],
            "timestamp": self._timestamp,
            "matchingEngineCts": self._matching_engine_cts,
            "receivedAt": self._received_at,
            "updateId": self._update_id,
            "sequence": self._sequence,
            "state": self._state,
            "source": "BYBIT_LINEAR_WS",
            "version": self._version,
            "bestBid": next(iter(self._bids), None),
            "bestAsk": next(iter(self._asks), None),
        }

    def latest_descriptor(self) -> dict | None:
        """Return an immutable scalar descriptor of the latest READY book."""
        with self._condition:
            if self._state != "READY" or not self._bids or not self._asks:
                return None
            return {
                "book_version": self._version,
                "update_id": self._update_id,
                "sequence": self._sequence,
                "exchange_ts_ms": self._timestamp,
                "matching_engine_cts_ms": self._matching_engine_cts,
                "backend_received_at_ms": self._received_at,
                "best_bid": next(iter(self._bids)),
                "best_ask": next(iter(self._asks)),
            }

    def _run(self) -> None:
        topic = f"orderbook.{self.depth}.{self.symbol}"
        while not self._stop.is_set():
            ws = None
            self._clear("CONNECTING")
            try:
                ws = websocket.create_connection(
                    "wss://stream.bybit.com/v5/public/linear",
                    timeout=10,
                )
                ws.send(json.dumps({"op": "subscribe", "args": [topic]}))

                while not self._stop.is_set():
                    message = json.loads(ws.recv())
                    self.apply_message(message)
            except Exception:
                if not self._stop.is_set():
                    snapshot = self.snapshot()
                    LOGGER.exception(
                        "Bybit order-book worker failed; symbol=%s state=%s "
                        "update_id=%s sequence=%s",
                        self.symbol,
                        snapshot["state"],
                        snapshot["updateId"],
                        snapshot["sequence"],
                    )
                    self._clear("DISCONNECTED")
                    time.sleep(1.5)
            finally:
                if ws is not None:
                    try:
                        ws.close()
                    except Exception:
                        pass


class PublicTradeKlineBuffer:
    """Build bounded UTC-aligned 15-second OHLC from raw executions."""

    def __init__(self, symbol: str, *, history_limit: int = 1000,
                 tick_size: Decimal = Decimal("0.00001")) -> None:
        self.symbol = symbol
        self.interval = "15s"
        self.history_limit = history_limit
        self.tick_size = tick_size
        self._candles: deque[dict] = deque(maxlen=history_limit)
        self._version = 0
        self._received_at = 0
        self._condition = threading.Condition()
        self._stop = threading.Event()

    def add_trades(self, trades: list[dict]) -> None:
        with self._condition:
            changed = False
            for trade in sorted(trades, key=lambda item: int(item["timestamp"])):
                timestamp = int(trade["timestamp"])
                price = Decimal(str(trade["price"]))
                if timestamp <= 0 or not price.is_finite() or price <= 0:
                    continue
                start_time = timestamp // 15000 * 15000
                current = self._candles[-1] if self._candles else None
                if current is None or start_time > current["startTime"]:
                    self._candles.append({
                        "startTime": start_time, "open": str(price),
                        "high": str(price), "low": str(price),
                        "close": str(price),
                    })
                elif start_time == current["startTime"]:
                    current["high"] = str(max(Decimal(current["high"]), price))
                    current["low"] = str(min(Decimal(current["low"]), price))
                    current["close"] = str(price)
                else:
                    continue
                changed = True
                self._received_at = max(self._received_at, timestamp)
            if changed:
                self._version += 1
                self._condition.notify_all()

    def start(self) -> None:
        return

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()

    def snapshot_after(self, after_version: int, timeout: float = 15.0) -> dict:
        with self._condition:
            self._condition.wait_for(
                lambda: self._version > after_version or self._stop.is_set(),
                timeout=timeout,
            )
            return self._snapshot_locked()

    def snapshot(self) -> dict:
        with self._condition:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "tickSize": str(self.tick_size),
            "candles": [item.copy() for item in self._candles],
            "receivedAt": self._received_at,
            "state": "READY" if self._candles else "CONNECTING",
            "source": "BYBIT_PUBLIC_TRADES", "version": self._version,
        }


class PublicKlineBuffer:
    """Poll one native Bybit kline interval and expose live snapshots."""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        *,
        interval: str = "5",
        history_limit: int = 1000,
        tick_size: Decimal = Decimal("0.00001"),
        poll_interval: float = 1.0,
        session: requests.Session | None = None,
    ) -> None:
        if (
            interval not in NATIVE_KLINE_INTERVALS
            or not 1 <= history_limit <= 1000
            or not tick_size.is_finite()
            or tick_size <= 0
        ):
            raise ValueError("invalid public-kline settings")
        self.symbol = symbol
        self.interval = interval
        self.history_limit = history_limit
        self.tick_size = tick_size
        self._poll_interval = poll_interval
        self._session = session or create_bybit_rest_session()
        self._candles: list[dict] = []
        self._state = "CONNECTING"
        self._received_at = 0
        self._version = 0
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="bybit-public-klines", daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()

    def snapshot_after(self, after_version: int, timeout: float = 15.0) -> dict:
        with self._condition:
            self._condition.wait_for(
                lambda: self._version > after_version or self._stop.is_set(),
                timeout=timeout,
            )
            return self._snapshot_locked()

    def snapshot(self) -> dict:
        with self._condition:
            return self._snapshot_locked()

    def refresh(self) -> None:
        response = self._session.get(
            "https://api.bybit.com/v5/market/kline",
            params={
                "category": "linear", "symbol": self.symbol,
                "interval": self.interval, "limit": self.history_limit,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("retCode") != 0:
            raise RuntimeError("Bybit kline request failed")
        result = payload.get("result")
        raw_candles = result.get("list") if isinstance(result, dict) else None
        if not isinstance(raw_candles, list) or not raw_candles:
            raise RuntimeError("Bybit kline response is invalid")
        candles = [self._normalize_candle(item) for item in raw_candles]
        candles.sort(key=lambda item: item["startTime"])
        if len({item["startTime"] for item in candles}) != len(candles):
            raise RuntimeError("Bybit kline response contains duplicate intervals")
        with self._condition:
            self._candles = candles[-self.history_limit:]
            self._state = "READY"
            self._received_at = int(time.time() * 1000)
            self._version += 1
            self._condition.notify_all()

    @staticmethod
    def _normalize_candle(raw: object) -> dict:
        if not isinstance(raw, list) or len(raw) < 5:
            raise RuntimeError("Bybit kline item is invalid")
        try:
            start_time = int(raw[0])
            prices = tuple(Decimal(str(value)) for value in raw[1:5])
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise RuntimeError("Bybit kline item is invalid") from exc
        open_price, high_price, low_price, close_price = prices
        if (
            start_time <= 0
            or any(not price.is_finite() or price <= 0 for price in prices)
            or high_price < max(open_price, close_price)
            or low_price > min(open_price, close_price)
        ):
            raise RuntimeError("Bybit kline item is invalid")
        return {
            "startTime": start_time, "open": str(open_price),
            "high": str(high_price), "low": str(low_price),
            "close": str(close_price),
        }

    def _snapshot_locked(self) -> dict:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "tickSize": str(self.tick_size),
            "candles": [candle.copy() for candle in self._candles],
            "receivedAt": self._received_at, "state": self._state,
            "source": "BYBIT_LINEAR_REST", "version": self._version,
        }

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception:
                if not self._stop.is_set():
                    LOGGER.exception(
                        "Bybit kline worker failed; symbol=%s interval=%s",
                        self.symbol, self.interval,
                    )
                    with self._condition:
                        self._state = "DEGRADED"
                        self._version += 1
                        self._condition.notify_all()
            self._stop.wait(self._poll_interval)


class LiveOrderBookProvider:
    def __init__(
        self,
        buffer: PublicOrderBookBuffer,
        *,
        rest_session: requests.Session | None = None,
    ) -> None:
        self._buffer = buffer
        self._lock = threading.RLock()
        self._rest_session = rest_session

    def set_buffer(self, buffer: PublicOrderBookBuffer) -> None:
        with self._lock:
            self._buffer = buffer

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        current = self.get_current_book_update(symbol)
        if current is not None:
            return current[1]
        if self._rest_session is None:
            return None
        return self._load_rest_book(symbol)

    def _load_rest_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        try:
            response = self._rest_session.get(
                "https://api.bybit.com/v5/market/orderbook",
                params={"category": "linear", "symbol": symbol.value, "limit": 50},
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") if payload.get("retCode") == 0 else None
            if not isinstance(result, dict) or result.get("s") != symbol.value:
                return None
            bids = tuple(
                PriceLevel(Price(Decimal(level[0])), Quantity(Decimal(level[1])))
                for level in result.get("b", [])
            )
            asks = tuple(
                PriceLevel(Price(Decimal(level[0])), Quantity(Decimal(level[1])))
                for level in result.get("a", [])
            )
            if not bids or not asks:
                return None
            return NormalizedOrderBook(
                symbol=symbol,
                bids=bids,
                asks=asks,
                health=BookHealth.READY,
                received_at_ms=int(time.time() * 1000),
                available_depth=min(len(bids), len(asks)),
            )
        except (
            IndexError, InvalidOperation, KeyError, TypeError, ValueError,
            requests.RequestException,
        ):
            return None

    def get_current_book_update(
        self, symbol: Symbol,
    ) -> tuple[str, NormalizedOrderBook] | None:
        with self._lock:
            buffer = self._buffer
        payload = buffer.snapshot()
        if payload["state"] != "READY" or payload["symbol"] != symbol.value:
            return None
        try:
            bids = tuple(
                PriceLevel(
                    Price(Decimal(level["price"])),
                    Quantity(Decimal(level["size"])),
                )
                for level in payload["bids"]
            )
            asks = tuple(
                PriceLevel(
                    Price(Decimal(level["price"])),
                    Quantity(Decimal(level["size"])),
                )
                for level in payload["asks"]
            )
        except (KeyError, TypeError, ValueError):
            return None
        if not bids or not asks:
            return None
        book = NormalizedOrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            health=BookHealth.READY,
            received_at_ms=int(payload["receivedAt"]),
            available_depth=min(len(bids), len(asks)),
        )
        return (
            f"{symbol.value}:{int(payload['sequence'])}:{int(payload['updateId'])}",
            book,
        )


@dataclass(frozen=True)
class _BookUpdateNotification:
    book_update_id: str


class SerializedPaperRuntime:
    def __init__(self, factory) -> None:
        self._requests: queue.Queue = queue.Queue()
        self._book_update_lock = threading.Lock()
        self._latest_book_update_id: str | None = None
        self._book_update_pending = False
        self._ready = threading.Event()
        self._initialization_error: BaseException | None = None
        self._thread = threading.Thread(
            target=self._run,
            args=(factory,),
            name="paper-runtime-owner",
            daemon=True,
        )
        self._thread.start()
        self._ready.wait()
        if self._initialization_error is not None:
            raise RuntimeError("PAPER runtime initialization failed") from self._initialization_error

    def call(self, operation, timeout: float = 15.0):
        if not self._thread.is_alive():
            raise RuntimeError("PAPER runtime owner is unavailable")
        completed = threading.Event()
        response: dict[str, object] = {}
        self._requests.put((operation, completed, response))
        if not completed.wait(timeout):
            raise TimeoutError("PAPER runtime operation timed out")
        error = response.get("error")
        if isinstance(error, BaseException):
            raise error
        return response.get("result")

    def enqueue_book_update(self, book_update_id: str) -> None:
        if not book_update_id:
            raise ValueError("book_update_id must be non-empty")
        if not self._thread.is_alive():
            raise RuntimeError("PAPER runtime owner is unavailable")
        with self._book_update_lock:
            self._latest_book_update_id = book_update_id
            if self._book_update_pending:
                return
            self._book_update_pending = True
        self._requests.put(_BookUpdateNotification(book_update_id))

    def close(self) -> None:
        if not self._thread.is_alive():
            return
        completed = threading.Event()
        self._requests.put((None, completed, {}))
        completed.wait(15)
        self._thread.join(timeout=15)

    def _run(self, factory) -> None:
        runtime = None
        try:
            runtime = factory()
        except BaseException as exc:
            self._initialization_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                request = self._requests.get()
                if isinstance(request, _BookUpdateNotification):
                    with self._book_update_lock:
                        book_update_id = (
                            self._latest_book_update_id or request.book_update_id
                        )
                        self._book_update_pending = False
                    try:
                        runtime.process_orderbook_update(book_update_id)
                    except BaseException:
                        LOGGER.exception(
                            "PAPER Limit update processing failed; book_update_id=%s",
                            book_update_id,
                        )
                    continue
                operation, completed, response = request
                if operation is None:
                    completed.set()
                    return
                try:
                    response["result"] = operation(runtime)
                except BaseException as exc:
                    response["error"] = exc
                finally:
                    completed.set()
        finally:
            runtime.close()


def create_bybit_rest_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    proxy = os.environ.get(
        "BYBITSCANNER_BYBIT_PROXY", "socks5h://127.0.0.1:10808",
    )
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


def load_public_instrument(
    symbol: str,
    session: requests.Session | None = None,
):
    response = (session or create_bybit_rest_session()).get(
        "https://api.bybit.com/v5/market/instruments-info",
        params={"category": "linear", "symbol": symbol},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("retCode") != 0:
        raise RuntimeError("Bybit instrument request failed")
    result = payload.get("result")
    items = result.get("list") if isinstance(result, dict) else None
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise RuntimeError("Bybit instrument response is invalid")
    normalized = dict(items[0])
    normalized["category"] = "linear"
    return normalize_instrument(normalized)


def load_public_instruments(session: requests.Session | None = None) -> list[dict[str, str]]:
    rest = session or create_bybit_rest_session()
    cursor = ""
    instruments: list[dict[str, str]] = []
    while True:
        params = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        response = rest.get(
            "https://api.bybit.com/v5/market/instruments-info",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("result") if payload.get("retCode") == 0 else None
        items = result.get("list") if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise RuntimeError("Bybit instrument universe response is invalid")
        for item in items:
            price_filter = item.get("priceFilter") if isinstance(item, dict) else None
            symbol = item.get("symbol") if isinstance(item, dict) else None
            tick_size = price_filter.get("tickSize") if isinstance(price_filter, dict) else None
            if (
                isinstance(symbol, str) and isinstance(tick_size, str)
                and item.get("status") == "Trading" and item.get("settleCoin") == "USDT"
            ):
                instruments.append({"symbol": symbol, "tick_size": tick_size})
        cursor = result.get("nextPageCursor", "") if isinstance(result, dict) else ""
        if not cursor:
            break
    return sorted(instruments, key=lambda item: item["symbol"])


@dataclass
class MarketDataSession:
    symbol: str
    public_orderbook: PublicOrderBookBuffer
    public_trades: PublicTradeBuffer
    public_klines: dict[str, object]

    def close(self) -> None:
        self.public_orderbook.set_update_consumer(None)
        self.public_orderbook.close()
        self.public_trades.close()
        for buffer in self.public_klines.values():
            buffer.close()


class WorkspaceMarketDataManager:
    def __init__(self, instruments: list[dict[str, str]], provider: LiveOrderBookProvider,
                 runtime: SerializedPaperRuntime, initial: MarketDataSession) -> None:
        self.instruments = instruments
        self._tick_sizes = {item["symbol"]: Decimal(item["tick_size"]) for item in instruments}
        self._provider = provider
        self._runtime = runtime
        self._active = initial
        self._lock = threading.RLock()

    def activate(self, symbol: str) -> MarketDataSession:
        normalized = symbol.strip().upper()
        with self._lock:
            if normalized == self._active.symbol:
                return self._active
            tick_size = self._tick_sizes.get(normalized)
            if tick_size is None:
                raise ValueError("unsupported symbol")
            replacement = create_market_data_session(normalized, tick_size, self._runtime)
            previous = self._active
            self._active = replacement
            self._provider.set_buffer(replacement.public_orderbook)
        previous.close()
        return replacement

    def close(self) -> None:
        with self._lock:
            active = self._active
        active.close()


def create_market_data_session(symbol: str, tick_size: Decimal,
                               runtime: SerializedPaperRuntime | None = None) -> MarketDataSession:
    public_orderbook = PublicOrderBookBuffer(symbol, depth=1000)
    trade_klines = PublicTradeKlineBuffer(symbol, history_limit=1000, tick_size=tick_size)
    public_klines = {
        interval: PublicKlineBuffer(
            symbol, interval=interval, history_limit=1000,
            tick_size=tick_size, session=create_bybit_rest_session(),
        )
        for interval in NATIVE_KLINE_INTERVALS
    }
    public_klines["15s"] = trade_klines
    public_trades = PublicTradeBuffer(
        symbol, tick_size=tick_size, aggregation_window_ms=50,
        book_descriptor_provider=public_orderbook.latest_descriptor,
        raw_trade_consumer=trade_klines.add_trades,
    )
    public_trades.start()
    for public_kline in public_klines.values():
        public_kline.start()
    if runtime is not None:
        public_orderbook.set_update_consumer(runtime.enqueue_book_update)
    public_orderbook.start()
    return MarketDataSession(symbol, public_orderbook, public_trades, public_klines)


class PaperHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path == "/api/health":
            self._json_response(
                200,
                {
                    "ok": True,
                    "mode": "paper",
                },
            )
            return

        if parsed.path == "/api/instruments":
            self._json_response(200, {"ok": True, "instruments": self.server.market_data.instruments})
            return

        if parsed.path == "/api/public-trades/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]

            try:
                market = self.server.market_data.activate(symbol)
            except ValueError:
                self._json_response(
                    400,
                    {"ok": False, "error": "unsupported_symbol"},
                )
                return
            public_trades = market.public_trades

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            seen_ids: set[str] = set()

            try:
                while True:
                    trades = public_trades.snapshot_after(0)

                    fresh = [
                        trade
                        for trade in trades
                        if trade["id"] not in seen_ids
                    ]

                    if fresh:
                        for trade in fresh:
                            seen_ids.add(trade["id"])

                        if len(seen_ids) > 1000:
                            current_ids = {
                                trade["id"]
                                for trade in trades
                            }
                            seen_ids.intersection_update(current_ids)

                        payload = json.dumps(
                            {"trades": fresh},
                            separators=(",", ":"),
                        )

                        self.wfile.write(
                            f"data:{payload}\n\n".encode("utf-8")
                        )
                        self.wfile.flush()

                    time.sleep(0.03)

            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
            ):
                return

        if parsed.path == "/api/public-orderbook/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]

            try:
                market = self.server.market_data.activate(symbol)
            except ValueError:
                self._json_response(
                    400,
                    {"ok": False, "error": "unsupported_symbol"},
                )
                return
            public_orderbook = market.public_orderbook

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            version = -1
            try:
                while True:
                    payload = public_orderbook.snapshot_after(version)
                    next_version = int(payload["version"])
                    if next_version > version:
                        version = next_version
                        body = json.dumps(payload, separators=(",", ":"))
                        self.wfile.write(f"data:{body}\n\n".encode("utf-8"))
                    else:
                        self.wfile.write(b":keepalive\n\n")
                    self.wfile.flush()
            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
            ):
                return

        if parsed.path == "/api/public-klines/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]
            interval = query.get("interval", ["5"])[0]
            try:
                market = self.server.market_data.activate(symbol)
            except ValueError:
                market = None
            if market is None or interval not in SUPPORTED_KLINE_INTERVALS or interval not in market.public_klines:
                self._json_response(
                    400, {"ok": False, "error": "unsupported_kline_stream"},
                )
                return
            public_kline = market.public_klines[interval]

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            version = -1
            try:
                while True:
                    payload = public_kline.snapshot_after(version)
                    next_version = int(payload["version"])
                    if next_version > version:
                        version = next_version
                        body = json.dumps(payload, separators=(",", ":"))
                        self.wfile.write(f"data:{body}\n\n".encode("utf-8"))
                    else:
                        self.wfile.write(b":keepalive\n\n")
                    self.wfile.flush()
            except (
                BrokenPipeError,
                ConnectionResetError,
                ConnectionAbortedError,
            ):
                return

        if parsed.path == "/api/public-trades":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]

            try:
                market = self.server.market_data.activate(symbol)
            except ValueError:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "unsupported_symbol",
                    },
                )
                return

            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "invalid_after",
                    },
                )
                return

            trades = market.public_trades.snapshot_after(after)

            self._json_response(
                200,
                {
                    "ok": True,
                    "symbol": symbol,
                    "trades": trades,
                },
            )
            return

        if parsed.path == "/api/paper-state":
            query = parse_qs(parsed.query)
            symbols = query.get("symbol", [])
            if len(symbols) != 1:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "symbol_required",
                    },
                )
                return

            symbol = symbols[0]
            try:
                state = self.server.runtime.call(
                    lambda runtime: runtime.paper_state(symbol)
                )
            except Exception:
                self._json_response(
                    400,
                    {
                        "ok": False,
                        "error": "invalid_paper_state_request",
                    },
                )
                return

            self._json_response(
                200,
                {
                    "ok": True,
                    **state,
                },
            )
            return

        if parsed.path == "/api/open-positions":
            try:
                inventory = self.server.runtime.call(
                    lambda runtime: runtime.open_positions()
                )
            except Exception:
                self._json_response(
                    503,
                    {"ok": False, "error": "open_positions_unavailable"},
                )
                return
            self._json_response(
                200,
                {"ok": True, **to_primitive(inventory)},
            )
            return

        self._json_response(
            404,
            {
                "ok": False,
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if self.path == "/api/close-all":
            try:
                payload = self._payload(CLOSE_ALL_FIELDS)
                request = CloseAllCommandRequest(ClientActionId(payload["client_action_id"]))
                result = self.server.runtime.call(lambda runtime: runtime.close_all(request))
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, {"ok": True, **to_primitive(result)})
            return

        if self.path == "/api/limit/amend":
            try:
                payload = self._payload(LIMIT_AMEND_FIELDS)
                request = PaperLimitAmendRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"], _decimal(payload["limit_price"]),
                )
                result, state = self.server.runtime.call(
                    lambda runtime: (
                        runtime.amend_limit(request),
                        runtime.paper_state(request.symbol),
                    )
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, {
                **to_primitive(result),
                "paper_state": {"ok": True, **state},
            })
            return

        if self.path == "/api/limit":
            try:
                payload = self._payload(LIMIT_FIELDS)
                volume = payload["volume"]
                if not isinstance(volume, dict) or set(volume) != VOLUME_FIELDS:
                    raise ValueError("invalid volume fields")
                request = LimitCommandRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    OrderSide(payload["side"]),
                    VolumeRequest(VolumeUnit(volume["unit"]), _decimal(volume["amount"])),
                    _decimal(payload["sizing_reference_price"]),
                    _decimal(payload["limit_price"]), TimeInForce(payload["time_in_force"]),
                )
                result, state = self.server.runtime.call(
                    lambda runtime: (
                        runtime.create_limit(request),
                        runtime.paper_state(request.symbol),
                    )
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, {
                **to_primitive(result),
                "paper_state": {"ok": True, **state},
            })
            return

        if self.path == "/api/limit/cancel":
            try:
                payload = self._payload(LIMIT_CANCEL_FIELDS)
                request = PaperLimitCancelRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"],
                )
                result, state = self.server.runtime.call(
                    lambda runtime: (
                        runtime.cancel_limit(request),
                        runtime.paper_state(request.symbol),
                    )
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, {
                **to_primitive(result),
                "paper_state": {"ok": True, **state},
            })
            return

        if self.path == "/api/full-close":
            try:
                payload = self._payload(FULL_CLOSE_FIELDS)
                request = FullCloseCommandRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"]
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            result, state = self.server.runtime.call(
                lambda runtime: (
                    runtime.api.full_close(request),
                    runtime.paper_state(request.symbol),
                )
            )
            self._json_response(200, {
                **to_primitive(result),
                "paper_state": {"ok": True, **state},
            })
            return

        if self.path != "/api/market":
            self._json_response(404, {"ok": False, "error": "not_found"})
            return

        try:
            request = self._market_request()
        except Exception:
            self._json_response(400, to_primitive(_validation_error()))
            return

        result, state = self.server.runtime.call(
            lambda runtime: (
                runtime.api.market(request),
                runtime.paper_state(request.symbol),
            )
        )
        self._json_response(200, {
            **to_primitive(result),
            "paper_state": {"ok": True, **state},
        })

    def _market_request(self) -> MarketCommandRequest:
        payload = self._payload(MARKET_FIELDS)
        volume = payload["volume"]
        if not isinstance(volume, dict) or set(volume) != VOLUME_FIELDS:
            raise ValueError("invalid volume fields")
        return MarketCommandRequest(
            ClientActionId(payload["client_action_id"]),
            payload["symbol"],
            OrderSide(payload["side"]),
            VolumeRequest(VolumeUnit(volume["unit"]), _decimal(volume["amount"])),
            _decimal(payload["sizing_reference_price"]),
            payload["slippage_type"],
            _decimal(payload["slippage_value"]),
        )

    def _payload(self, fields: set[str]) -> dict:
        content_length = int(self.headers.get("Content-Length", ""))
        if content_length <= 0:
            raise ValueError("request body is required")
        payload = json.loads(
            self.rfile.read(content_length).decode("utf-8"),
            parse_float=Decimal,
        )
        if not isinstance(payload, dict) or set(payload) != fields:
            raise ValueError("invalid request fields")
        return payload

    def _json_response(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BYBITSCANNER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_path = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))
    port = int(os.environ.get("BYBITSCANNER_PAPER_PORT", str(PORT)))
    rest_session = create_bybit_rest_session()
    instruments = load_public_instruments(rest_session)
    instrument_snapshot = load_public_instrument("ONGUSDT", rest_session)
    initial_market = create_market_data_session("ONGUSDT", instrument_snapshot.tick_size)
    book_provider = LiveOrderBookProvider(
        initial_market.public_orderbook,
        rest_session=rest_session,
    )
    runtime = SerializedPaperRuntime(lambda: PaperRuntime(
        database_path,
        book_provider=book_provider,
        instrument_snapshot=instrument_snapshot,
        instrument_provider=lambda symbol: load_public_instrument(symbol, rest_session),
    ))
    initial_market.public_orderbook.set_update_consumer(runtime.enqueue_book_update)
    market_data = WorkspaceMarketDataManager(instruments, book_provider, runtime, initial_market)

    server = ThreadingHTTPServer((HOST, port), PaperHttpHandler)
    server.runtime = runtime
    server.market_data = market_data

    try:
        print(f"PAPER HTTP runtime listening on http://{HOST}:{port}")
        print("Bybit public market data streams: active workspace symbol (initial ONGUSDT)")
        server.serve_forever()
    finally:
        market_data.close()
        runtime.close()
        server.server_close()


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("decimal value is invalid")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("decimal value must be finite")
    return result


def _validation_error() -> CommandResult:
    return CommandResult(
        "",
        CommandResultStatus.VALIDATION_ERROR,
        "validation_error",
        "command request is invalid",
    )


if __name__ == "__main__":
    main()
