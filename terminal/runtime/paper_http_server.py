"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections import deque
from decimal import Decimal, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

import websocket
import requests

from terminal.api.models import (
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
LIMIT_FIELDS = {
    "client_action_id", "symbol", "side", "volume", "sizing_reference_price",
    "limit_price", "time_in_force",
}
LIMIT_CANCEL_FIELDS = {"client_action_id", "symbol", "order_id"}
LIMIT_AMEND_FIELDS = {"client_action_id", "symbol", "order_id", "limit_price"}


class PublicTradeBuffer:
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        maxlen: int = 500,
        *,
        tick_size: Decimal = Decimal("0.00001"),
        aggregation_window_ms: int = 50,
        book_descriptor_provider: Callable[[], dict | None] | None = None,
    ) -> None:
        if tick_size <= 0 or aggregation_window_ms < 0:
            raise ValueError("invalid public-trade aggregation settings")
        self.symbol = symbol
        self._trades: deque[dict] = deque(maxlen=maxlen)
        self._active: dict | None = None
        self._tick_size = tick_size
        self._aggregation_window_ms = aggregation_window_ms
        self._book_descriptor_provider = book_descriptor_provider
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
        with self._lock:
            for trade in sorted(
                trades,
                key=lambda item: (int(item["timestamp"]), int(item["seq"])),
            ):
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
            self._condition.notify_all()
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


class LiveOrderBookProvider:
    def __init__(self, buffer: PublicOrderBookBuffer) -> None:
        self._buffer = buffer

    def get_book(self, symbol: Symbol) -> NormalizedOrderBook | None:
        payload = self._buffer.snapshot()
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
        return NormalizedOrderBook(
            symbol=symbol,
            bids=bids,
            asks=asks,
            health=BookHealth.READY,
            received_at_ms=int(payload["receivedAt"]),
            available_depth=min(len(bids), len(asks)),
        )


class SerializedPaperRuntime:
    def __init__(self, factory) -> None:
        self._requests: queue.Queue = queue.Queue()
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
                operation, completed, response = self._requests.get()
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


def load_public_instrument(symbol: str):
    response = requests.get(
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

        if parsed.path == "/api/public-trades/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]

            if symbol != self.server.public_trades.symbol:
                self._json_response(
                    400,
                    {"ok": False, "error": "unsupported_symbol"},
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            seen_ids: set[str] = set()

            try:
                while True:
                    trades = self.server.public_trades.snapshot_after(0)

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

            if symbol != self.server.public_orderbook.symbol:
                self._json_response(
                    400,
                    {"ok": False, "error": "unsupported_symbol"},
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()

            version = -1
            try:
                while True:
                    payload = self.server.public_orderbook.snapshot_after(version)
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

            if symbol != self.server.public_trades.symbol:
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

            trades = self.server.public_trades.snapshot_after(after)

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

            try:
                state = self.server.runtime.call(
                    lambda runtime: runtime.paper_state(symbols[0])
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

        self._json_response(
            404,
            {
                "ok": False,
                "error": "not_found",
            },
        )

    def do_POST(self) -> None:
        if self.path == "/api/limit/amend":
            try:
                payload = self._payload(LIMIT_AMEND_FIELDS)
                request = PaperLimitAmendRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"], _decimal(payload["limit_price"]),
                )
                result = self.server.runtime.call(
                    lambda runtime: runtime.amend_limit(request)
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
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
                result = self.server.runtime.call(
                    lambda runtime: runtime.create_limit(request)
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
            return

        if self.path == "/api/limit/cancel":
            try:
                payload = self._payload(LIMIT_CANCEL_FIELDS)
                request = PaperLimitCancelRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    payload["order_id"],
                )
                result = self.server.runtime.call(
                    lambda runtime: runtime.cancel_limit(request)
                )
            except Exception:
                self._json_response(400, to_primitive(_validation_error()))
                return
            self._json_response(200, to_primitive(result))
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
            result = self.server.runtime.call(
                lambda runtime: runtime.api.full_close(request)
            )
            self._json_response(200, to_primitive(result))
            return

        if self.path != "/api/market":
            self._json_response(404, {"ok": False, "error": "not_found"})
            return

        try:
            request = self._market_request()
        except Exception:
            self._json_response(400, to_primitive(_validation_error()))
            return

        result = self.server.runtime.call(
            lambda runtime: runtime.api.market(request)
        )
        self._json_response(200, to_primitive(result))

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
    instrument_snapshot = load_public_instrument("ONGUSDT")
    public_orderbook = PublicOrderBookBuffer("ONGUSDT", depth=1000)
    public_trades = PublicTradeBuffer(
        "ONGUSDT",
        tick_size=instrument_snapshot.tick_size,
        aggregation_window_ms=50,
        book_descriptor_provider=public_orderbook.latest_descriptor,
    )
    public_trades.start()
    public_orderbook.start()

    book_provider = LiveOrderBookProvider(public_orderbook)
    runtime = SerializedPaperRuntime(lambda: PaperRuntime(
        database_path,
        book_provider=book_provider,
        instrument_snapshot=instrument_snapshot,
    ))

    server = ThreadingHTTPServer((HOST, port), PaperHttpHandler)
    server.runtime = runtime
    server.public_trades = public_trades
    server.public_orderbook = public_orderbook

    try:
        print(f"PAPER HTTP runtime listening on http://{HOST}:{port}")
        print("Bybit public market data streams: ONGUSDT")
        server.serve_forever()
    finally:
        runtime.close()
        public_trades.close()
        public_orderbook.close()
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
