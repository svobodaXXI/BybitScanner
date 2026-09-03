"""Minimal local HTTP runtime for PAPER Trading Workspace development."""

from __future__ import annotations

import json
import logging
import os
import queue
import socket
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

import requests
import socks
import websocket

from terminal.api.models import (
    CloseAllCommandRequest,
    AmendCommandRequest,
    CancelCommandRequest,
    ClientActionId,
    CommandResult,
    CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest,
    LiveMarketCommandRequest,
    MarketCommandRequest,
    PaperLimitCancelRequest,
    PaperLimitAmendRequest,
    PaperStopDeleteRequest,
    PaperStopMutationRequest,
    ProtectionCommandRequest,
    TimeInForce,
    VolumeRequest,
    VolumeUnit,
    to_primitive,
)
from terminal.domain.models import OrderSide
from terminal.domain.models import Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.market_data.hub import MarketDataHub, SymbolContext
from terminal.market_data.client_projection import ClientMarketProjection, StaleProjectionError
from terminal.market_data.instrument_registry import InstrumentRegistry
from terminal.market_data.workspace_stream import (
    WorkspaceStreamBackpressure, WorkspaceStreamBroker, WorkspaceStreamError,
    websocket_accept, websocket_text_frame,
)
from terminal.market_data.workspace_controller import WorkspaceController
from terminal.market_data.workspace_errors import (
    InactiveWorkspace,
    UnsupportedWorkspaceInstrument,
    WorkspaceCandidateNotReady,
    WorkspaceInstrumentBootstrapFailure,
    WorkspaceSemanticError,
    UpstreamWorkspaceMarketDataFailure,
)
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.exchange.bybit_account_validation import AccountValidationError, BybitAccountValidator
from terminal.exchange.bybit_v5_mutation_adapter import BybitV5MutationAdapter
from terminal.persistence.credential_store import (
    CredentialStoreError, create_credential_store, credential_store_path,
)
from terminal.persistence.live_account_store import LiveAccountProjectionStore
from terminal.persistence.active_account_preference import ActiveAccountPreferenceStore
from terminal.application.live_account_reconciliation import LiveAccountReconciliationError


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
LIVE_MARKET_FIELDS = MARKET_FIELDS | {"account_id", "session_generation"}
LIVE_AUTHORITY_FIELDS = {"account_id", "session_generation"}
VOLUME_FIELDS = {"unit", "amount"}
FULL_CLOSE_FIELDS = {"client_action_id", "symbol"}
CLOSE_ALL_FIELDS = {"client_action_id"}
LIMIT_FIELDS = {
    "client_action_id", "symbol", "side", "volume", "sizing_reference_price",
    "limit_price", "time_in_force",
}
LIMIT_CANCEL_FIELDS = {"client_action_id", "symbol", "order_id"}
LIMIT_AMEND_FIELDS = {"client_action_id", "symbol", "order_id", "limit_price"}
STOP_MUTATION_FIELDS = {"client_action_id", "symbol", "trigger_price"}
LIVE_LIMIT_FIELDS = LIMIT_FIELDS | LIVE_AUTHORITY_FIELDS
LIVE_LIMIT_AMEND_FIELDS = LIMIT_AMEND_FIELDS | LIVE_AUTHORITY_FIELDS
LIVE_LIMIT_CANCEL_FIELDS = LIMIT_CANCEL_FIELDS | LIVE_AUTHORITY_FIELDS
LIVE_PROTECTION_FIELDS = {
    "client_action_id", "account_id", "session_generation", "symbol",
    "take_profit", "stop_loss", "tp_trigger_by", "sl_trigger_by",
}
LIVE_FULL_CLOSE_FIELDS = FULL_CLOSE_FIELDS | LIVE_AUTHORITY_FIELDS
ACCOUNT_CREATE_FIELDS = {"display_name", "api_key", "api_secret"}
ACCOUNT_ACTIVATE_FIELDS = {"expected_active_account_id", "expected_session_generation"}


def _account_route_id(path: str, action: str) -> str | None:
    prefix = "/api/accounts/"
    suffix = f"/{action}"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    account_id = path[len(prefix):-len(suffix)]
    if (
        not account_id or "/" in account_id
        or (action != "activate" and not account_id.startswith("bybit-"))
        or (action == "activate" and account_id != "paper" and not account_id.startswith("bybit-"))
    ):
        return None
    return account_id
ACCOUNT_DESCRIPTOR_FIELDS = {"id", "display_name", "provider", "environment", "status"}


def safe_account_catalog(value: object) -> dict[str, object]:
    """Validate and allow-list the credential-free account transport shape."""
    if not isinstance(value, dict):
        raise ValueError("account catalog must be an object")
    active_account_id = value.get("active_account_id")
    generation = value.get("session_generation")
    accounts = value.get("accounts")
    if (
        not isinstance(active_account_id, str)
        or not active_account_id
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
        or not isinstance(accounts, list)
        or not accounts
    ):
        raise ValueError("invalid account catalog authority")
    projected_accounts: list[dict[str, str]] = []
    for account in accounts:
        if not isinstance(account, dict) or not ACCOUNT_DESCRIPTOR_FIELDS.issubset(account):
            raise ValueError("invalid account descriptor")
        projected = {field: account[field] for field in ACCOUNT_DESCRIPTOR_FIELDS}
        if any(not isinstance(item, str) or not item for item in projected.values()):
            raise ValueError("invalid account descriptor value")
        projected_accounts.append(projected)
    if active_account_id not in {account["id"] for account in projected_accounts}:
        raise ValueError("active account is absent from catalog")
    return {
        "active_account_id": active_account_id,
        "session_generation": generation,
        "accounts": projected_accounts,
    }
STOP_DELETE_FIELDS = {"client_action_id", "symbol"}
WORKSPACE_SYMBOL_FIELDS = {"symbol"}
NATIVE_KLINE_INTERVALS = ("1", "5", "15", "60", "D")
BYBIT_WEBSOCKET_CONNECT_TIMEOUT = 10.0
INITIAL_WORKSPACE_READINESS_TIMEOUT = 30.0
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

    def apply_message(self, message: dict) -> str:
        if message.get("topic") != f"publicTrade.{self.symbol}":
            return "IGNORED"
        data = message.get("data")
        if not isinstance(data, list):
            return "IGNORED"
        normalized = []
        received_at_ms = int(time.time() * 1000)
        for index, trade in enumerate(data):
            if not isinstance(trade, dict):
                continue
            side = trade.get("S")
            price = trade.get("p")
            quantity = trade.get("v")
            if side not in ("Buy", "Sell") or price is None or quantity is None:
                continue
            try:
                timestamp = int(trade.get("T") or time.time() * 1000)
                seq = int(trade.get("seq") or timestamp * 1000 + index)
            except (TypeError, ValueError):
                continue
            normalized.append({
                "id": str(trade.get("i") or f"{timestamp}-{seq}-{index}"),
                "seq": seq, "timestamp": timestamp, "symbol": self.symbol,
                "side": "BUY" if side == "Buy" else "SELL",
                "price": str(price), "quantity": str(quantity),
                "received_at_ms": received_at_ms,
            })
        if not normalized:
            return "IGNORED"
        self.add_trades(normalized)
        return "APPLIED"

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

                    self.apply_message(message)

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

    def mark_connecting(self) -> None:
        self._clear("CONNECTING")

    def mark_disconnected(self) -> None:
        self._clear("DISCONNECTED")

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

    def wait_until_ready(self, timeout: float) -> bool:
        with self._condition:
            self._condition.wait_for(
                lambda: (
                    (self._state == "READY" and bool(self._bids) and bool(self._asks))
                    or self._stop.is_set()
                ),
                timeout=timeout,
            )
            return self._state == "READY" and bool(self._bids) and bool(self._asks)

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


def configure_bybit_proxy_environment() -> str:
    """Apply the optional Bybit proxy to this process and its child processes."""
    if "BYBITSCANNER_BYBIT_PROXY" in os.environ:
        proxy = os.environ["BYBITSCANNER_BYBIT_PROXY"].strip()
        if proxy:
            os.environ["ALL_PROXY"] = proxy
            os.environ["all_proxy"] = proxy
        else:
            os.environ.pop("ALL_PROXY", None)
            os.environ.pop("all_proxy", None)
        return proxy
    return os.environ.get("ALL_PROXY", os.environ.get("all_proxy", "")).strip()


def validate_bybit_proxy(proxy: str, *, timeout: float = 3.0) -> None:
    if not proxy:
        return
    parsed = urlparse(proxy)
    try:
        port = parsed.port
    except ValueError:
        port = None
    if parsed.scheme not in {"socks5", "socks5h"} or not parsed.hostname or not port:
        raise RuntimeError(
            "BYBITSCANNER_BYBIT_PROXY must be a socks5:// or socks5h:// URL with a port"
        )
    try:
        with socket.create_connection((parsed.hostname, port), timeout=timeout):
            return
    except OSError as exc:
        raise RuntimeError(
            f"Configured Bybit SOCKS proxy is unavailable at {parsed.hostname}:{port}"
        ) from exc


def create_bybit_websocket_connection(url: str, *, timeout: float):
    proxy = configure_bybit_proxy_environment()
    if not proxy:
        return websocket.create_connection(url, timeout=timeout)
    parsed = urlparse(proxy)
    target = urlparse(url)
    proxy_socket = socks.socksocket()
    proxy_socket.set_proxy(
        socks.SOCKS5,
        parsed.hostname,
        parsed.port,
        rdns=parsed.scheme == "socks5h",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
    )
    proxy_socket.settimeout(BYBIT_WEBSOCKET_CONNECT_TIMEOUT)
    active_socket = proxy_socket
    try:
        proxy_socket.connect((target.hostname, target.port or 443))
        active_socket = ssl.create_default_context().wrap_socket(
            proxy_socket, server_hostname=target.hostname,
        )
        connection = websocket.create_connection(
            url, timeout=BYBIT_WEBSOCKET_CONNECT_TIMEOUT, socket=active_socket,
        )
        connection.settimeout(timeout)
        return connection
    except BaseException:
        active_socket.close()
        raise


def create_bybit_rest_session() -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    proxy = configure_bybit_proxy_environment()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    return session


@dataclass
class MarketDataSession:
    symbol: str
    public_orderbook: PublicOrderBookBuffer
    public_trades: PublicTradeBuffer
    public_klines: dict[str, object]
    generation: int = 0

    def wait_until_ready(self, timeout: float) -> bool:
        return self.public_orderbook.wait_until_ready(timeout)

    def close(self) -> None:
        self.public_orderbook.set_update_consumer(None)
        self.public_orderbook.close()
        self.public_trades.close()
        for buffer in self.public_klines.values():
            buffer.close()


class WorkspaceMarketDataManager:
    def __init__(self, instruments: InstrumentRegistry, provider: LiveOrderBookProvider,
                 runtime: SerializedPaperRuntime, initial: MarketDataSession, *,
                 hub: MarketDataHub | None = None,
                 session_factory: Callable[[str, Decimal], MarketDataSession] | None = None,
                 readiness_timeout: float = 15.0,
                 initial_readiness_timeout: float | None = None) -> None:
        self._instruments = instruments
        self._provider = provider
        self._runtime = runtime
        self._active = initial
        self._hub = hub
        self._generation = 1
        self._active.generation = self._generation
        self._session_factory = session_factory or create_market_data_session
        self._readiness_timeout = readiness_timeout
        self._initial_readiness_timeout = (
            readiness_timeout
            if initial_readiness_timeout is None
            else initial_readiness_timeout
        )
        self._lock = threading.RLock()
        self._switch_lock = threading.Lock()
        self._controller = (
            WorkspaceController(hub, initial, self._activate_hub_context)
            if hub is not None else None
        )
        self._workspace_streams = WorkspaceStreamBroker(
            self.client_projection, self.client_instrument,
        )

    def _activate_hub_context(
        self, previous: SymbolContext, replacement: SymbolContext,
    ) -> None:
        try:
            replacement.public_orderbook.set_update_consumer(
                self._runtime.enqueue_book_update,
            )
            self._provider.set_buffer(replacement.public_orderbook)
            previous.public_orderbook.set_update_consumer(None)
        except Exception:
            replacement.public_orderbook.set_update_consumer(None)
            self._provider.set_buffer(previous.public_orderbook)
            previous.public_orderbook.set_update_consumer(
                self._runtime.enqueue_book_update,
            )
            raise

    def switch(self, symbol: str) -> MarketDataSession:
        if self._controller is not None:
            return self._controller.switch(symbol, self._readiness_timeout)
        if not isinstance(symbol, str) or not symbol.strip():
            raise UnsupportedWorkspaceInstrument(
                "Unsupported Workspace instrument",
                requested_symbol=symbol if isinstance(symbol, str) else None,
                active_symbol=self._active.symbol,
            )
        normalized = symbol.strip().upper()
        with self._switch_lock:
            with self._lock:
                if normalized == self._active.symbol:
                    return self._active
                try:
                    tick_size = self._instruments.get(normalized).tick_size
                except UnsupportedWorkspaceInstrument as exc:
                    if exc.active_symbol is None:
                        raise UnsupportedWorkspaceInstrument(
                            str(exc), requested_symbol=normalized,
                            active_symbol=self._active.symbol,
                        ) from exc
                    raise
                except LookupError as exc:
                    raise UnsupportedWorkspaceInstrument(
                        f"Unsupported Workspace instrument: {normalized}",
                        requested_symbol=normalized, active_symbol=self._active.symbol,
                    ) from exc
            try:
                replacement = self._session_factory(normalized, tick_size)
            except Exception as exc:
                raise WorkspaceInstrumentBootstrapFailure(
                    f"Workspace instrument bootstrap failed: {normalized}",
                    requested_symbol=normalized, active_symbol=self._active.symbol,
                ) from exc
            try:
                ready = replacement.wait_until_ready(self._readiness_timeout)
            except Exception as exc:
                replacement.close()
                raise UpstreamWorkspaceMarketDataFailure(
                    "Workspace candidate readiness failed at the upstream boundary",
                    requested_symbol=normalized, active_symbol=self._active.symbol,
                ) from exc
            if not ready:
                replacement.close()
                raise WorkspaceCandidateNotReady(
                    "Workspace candidate did not reach composite readiness",
                    requested_symbol=normalized, active_symbol=self._active.symbol,
                )
            with self._lock:
                previous = self._active
                try:
                    replacement.public_orderbook.set_update_consumer(
                        self._runtime.enqueue_book_update,
                    )
                    self._provider.set_buffer(replacement.public_orderbook)
                    previous.public_orderbook.set_update_consumer(None)
                except Exception as exc:
                    replacement.public_orderbook.set_update_consumer(None)
                    self._provider.set_buffer(previous.public_orderbook)
                    previous.public_orderbook.set_update_consumer(
                        self._runtime.enqueue_book_update,
                    )
                    replacement.close()
                    raise UpstreamWorkspaceMarketDataFailure(
                        "Workspace activation failed at the market-data boundary",
                        requested_symbol=normalized, active_symbol=previous.symbol,
                    ) from exc
                self._generation += 1
                replacement.generation = self._generation
                self._active = replacement
            if self._hub is None:
                previous.close()
            return replacement

    def get_active(self, symbol: str) -> tuple[MarketDataSession, int]:
        if self._controller is not None:
            return self._controller.get_active(symbol)
        normalized = symbol.strip().upper()
        with self._lock:
            if normalized != self._active.symbol:
                raise InactiveWorkspace(
                    "Requested instrument is not the active Workspace",
                    requested_symbol=normalized, active_symbol=self._active.symbol,
                )
            return self._active, self._generation

    def is_current(self, session: MarketDataSession, generation: int) -> bool:
        if self._controller is not None:
            return self._controller.is_current(session, generation)
        with self._lock:
            return self._active is session and self._generation == generation

    def client_projection(self, symbol: str) -> ClientMarketProjection:
        context, generation = self.get_active(symbol)
        return ClientMarketProjection(
            context, generation, is_current=self.is_current,
        )

    def client_instrument(self, symbol: str) -> dict[str, str]:
        instrument = self._instruments.get(symbol)
        return {
            "symbol": instrument.symbol,
            "tick_size": str(instrument.tick_size),
            "quantity_step": str(instrument.quantity_step),
            "min_quantity": str(instrument.min_order_quantity),
            "min_notional": str(instrument.min_notional_value),
            "price_precision": str(max(0, -instrument.tick_size.normalize().as_tuple().exponent)),
            "quantity_precision": str(max(0, -instrument.quantity_step.normalize().as_tuple().exponent)),
        }

    @property
    def workspace_streams(self) -> WorkspaceStreamBroker:
        return self._workspace_streams

    @property
    def instruments(self) -> list[dict[str, str]]:
        return self._instruments.api_projection()

    @property
    def workspace_state(self) -> object:
        if self._controller is None:
            return None
        return self._controller.state()

    @property
    def workspace_diagnostics(self) -> dict[str, object]:
        if self._controller is None:
            with self._lock:
                active = self._active
                generation = self._generation
            book = active.public_orderbook
            book_snapshot = book.snapshot() if hasattr(book, "snapshot") else {}
            ready = (
                book_snapshot.get("state") == "READY"
                if book_snapshot else bool(getattr(book, "ready", False))
            )
            diagnostic = {
                "requested_symbol": active.symbol,
                "active_symbol": active.symbol,
                "active_generation": generation,
                "switch_state": "READY",
                "pending_symbol": None,
                "last_error": None,
                "readiness": {
                    "ready": ready,
                    "book_ready": ready,
                },
                "upstream": None,
            }
        else:
            diagnostic = self._controller.diagnostics()
        return {**diagnostic, "streams": self._workspace_streams.diagnostics()}

    def ensure_initial_ready(self) -> MarketDataSession:
        if self._controller is not None:
            return self._controller.ensure_initial_ready(
                self._initial_readiness_timeout,
            )
        if not self._active.wait_until_ready(self._initial_readiness_timeout):
            raise TimeoutError("Initial market data did not become READY")
        return self._active

    def close(self) -> None:
        if self._hub is not None:
            if self._controller is not None:
                self._controller.close()
            self._hub.close()
        else:
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


def create_symbol_context(symbol: str, tick_size: Decimal) -> SymbolContext:
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
    for public_kline in public_klines.values():
        public_kline.start()
    return SymbolContext(symbol, public_orderbook, public_trades, public_klines)


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

        if parsed.path == "/api/accounts":
            try:
                catalog = safe_account_catalog(
                    self.server.runtime.call(lambda runtime: runtime.account_catalog())
                )
            except (RuntimeError, TimeoutError, TypeError, ValueError):
                self._json_response(503, {"ok": False, "error": "account_catalog_unavailable"})
                return
            self._json_response(200, {"ok": True, **catalog})
            return

        if parsed.path == "/api/workspace/account":
            symbols = parse_qs(parsed.query).get("symbol", [])
            if len(symbols) != 1:
                self._json_response(400, {"ok": False, "error": "symbol_required"})
                return
            try:
                projection = self.server.runtime.call(
                    lambda runtime: runtime.workspace_account_projection(symbols[0])
                )
            except Exception:
                self._json_response(503, {"ok": False, "error": "workspace_account_unavailable"})
                return
            self._json_response(200, {"ok": True, **projection})
            return

        account_summary_id = _account_route_id(parsed.path, "summary")
        if account_summary_id is not None:
            try:
                summary = self.server.runtime.call(
                    lambda runtime: runtime.live_account_summary(account_summary_id)
                )
            except (LookupError, ValueError):
                self._json_response(404, {"ok": False, "error": "account_not_found"})
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "account_summary_unavailable"})
                return
            self._json_response(200, {"ok": True, "summary": summary})
            return

        if parsed.path == "/api/workspace/state":
            self._json_response(200, {
                "ok": True,
                "workspace": self.server.market_data.workspace_diagnostics,
            })
            return

        if parsed.path == "/api/workspace/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]
            interval = query.get("interval", ["5"])[0]
            stream_id = query.get("stream_id", [None])[0]
            after_raw = query.get("after_sequence", [None])[0]
            try:
                after_sequence = int(after_raw) if after_raw is not None else None
            except ValueError:
                self._json_response(400, {"ok": False, "error": "invalid_resume_sequence"})
                return
            websocket_key = self.headers.get("Sec-WebSocket-Key", "").strip()
            if (
                self.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in self.headers.get("Connection", "").lower()
                or self.headers.get("Sec-WebSocket-Version") != "13"
                or not websocket_key
            ):
                self._json_response(426, {"ok": False, "error": "websocket_upgrade_required"})
                return
            try:
                opened = self.server.market_data.workspace_streams.open(
                    symbol, interval, stream_id=stream_id, after_sequence=after_sequence,
                )
            except WorkspaceSemanticError as exc:
                self._workspace_error_response(exc)
                return
            except WorkspaceStreamError:
                self._json_response(503, {"ok": False, "error": "workspace_not_ready"})
                return

            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", websocket_accept(websocket_key))
            self.end_headers()
            self.connection.settimeout(5.0)
            heartbeat_at = time.monotonic() + 10.0
            session = opened.session
            try:
                session.enqueue(opened.events)
                while True:
                    for event in session.drain():
                        self.wfile.write(websocket_text_frame(event))
                    self.wfile.flush()
                    events = session.poll()
                    if events:
                        session.enqueue(events)
                    elif time.monotonic() >= heartbeat_at:
                        session.enqueue((session.heartbeat(),))
                        heartbeat_at = time.monotonic() + 10.0
                    time.sleep(0.02)
            except (WorkspaceStreamBackpressure, StaleProjectionError, TimeoutError):
                self.server.market_data.workspace_streams.drop(session.stream_id)
                self.close_connection = True
                return
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.server.market_data.workspace_streams.detach(session.stream_id)
                self.close_connection = True
                return
            except OSError:
                self.server.market_data.workspace_streams.drop(session.stream_id)
                self.close_connection = True
                return

        if parsed.path == "/api/client-market-projection/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]
            kind = query.get("kind", ["book"])[0]
            interval = query.get("interval", ["5"])[0]
            if kind not in {"book", "trades", "candles"}:
                self._json_response(400, {"ok": False, "error": "unsupported_projection_kind"})
                return
            try:
                projection = self.server.market_data.client_projection(symbol)
                source = (
                    projection.context.public_orderbook if kind == "book"
                    else projection.context.public_klines.get(interval) if kind == "candles"
                    else projection.context.public_trades
                )
            except LookupError:
                self._json_response(409, {"ok": False, "error": "inactive_workspace_symbol"})
                return
            if source is None:
                self._json_response(400, {"ok": False, "error": "unsupported_projection_interval"})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            source_version = -1
            try:
                while True:
                    if kind == "trades":
                        event = projection.trades_event()
                        time.sleep(0.03)
                    else:
                        snapshot = source.snapshot_after(source_version)
                        source_version = int(snapshot.get("version", source_version))
                        event = (
                            projection.book_event()
                            if kind == "book" else projection.candles_event(interval)
                        )
                    if event is None:
                        self.wfile.write(b":keepalive\n\n")
                    else:
                        body = json.dumps(event, separators=(",", ":"))
                        self.wfile.write(f"data:{body}\n\n".encode("utf-8"))
                    self.wfile.flush()
            except StaleProjectionError:
                self.close_connection = True
                return
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

        if parsed.path == "/api/public-trades/stream":
            query = parse_qs(parsed.query)
            symbol = query.get("symbol", ["BTCUSDT"])[0]

            try:
                market, generation = self.server.market_data.get_active(symbol)
            except LookupError:
                self._json_response(
                    409,
                    {"ok": False, "error": "inactive_workspace_symbol"},
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
                    if not self.server.market_data.is_current(market, generation):
                        self.close_connection = True
                        return
                    trades = public_trades.snapshot_after(0)
                    if not self.server.market_data.is_current(market, generation):
                        self.close_connection = True
                        return

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
                            {"symbol": market.symbol, "generation": generation, "trades": fresh},
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
                market, generation = self.server.market_data.get_active(symbol)
            except LookupError:
                self._json_response(
                    409,
                    {"ok": False, "error": "inactive_workspace_symbol"},
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
                    if not self.server.market_data.is_current(market, generation):
                        self.close_connection = True
                        return
                    next_version = int(payload["version"])
                    if next_version > version:
                        version = next_version
                        body = json.dumps(
                            {**payload, "generation": generation}, separators=(",", ":"),
                        )
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
                market, generation = self.server.market_data.get_active(symbol)
            except LookupError:
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
                    if not self.server.market_data.is_current(market, generation):
                        return
                    next_version = int(payload["version"])
                    if next_version > version:
                        version = next_version
                        body = json.dumps(
                            {**payload, "generation": generation}, separators=(",", ":"),
                        )
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
                market, generation = self.server.market_data.get_active(symbol)
            except LookupError:
                self._json_response(
                    409,
                    {
                        "ok": False,
                        "error": "inactive_workspace_symbol",
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
            if not self.server.market_data.is_current(market, generation):
                self._json_response(
                    409,
                    {"ok": False, "error": "inactive_workspace_symbol"},
                )
                return

            self._json_response(
                200,
                {
                    "ok": True,
                    "symbol": market.symbol,
                    "generation": generation,
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
        account_activate_id = _account_route_id(urlparse(self.path).path, "activate")
        if account_activate_id is not None:
            try:
                payload = self._payload(ACCOUNT_ACTIVATE_FIELDS)
                result = self.server.runtime.call(
                    lambda runtime: runtime.activate_account(
                        account_activate_id,
                        payload["expected_active_account_id"],
                        payload["expected_session_generation"],
                    )
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json_response(400, {"ok": False, "error": "invalid_account_switch_payload"})
                return
            except LookupError:
                self._json_response(404, {"ok": False, "error": "account_not_found"})
                return
            except RuntimeError as exc:
                error = str(exc)
                if error not in {
                    "account_activation_not_ready", "live_account_snapshot_unavailable",
                    "stale_account_session",
                }:
                    error = "account_activation_failed"
                self._json_response(409, {"ok": False, "error": error})
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "account_activation_failed"})
                return
            self._json_response(200, {"ok": True, **result})
            return

        if urlparse(self.path).path == "/api/live/market":
            try:
                payload = self._payload(LIVE_MARKET_FIELDS)
                volume = payload["volume"]
                if not isinstance(volume, dict) or set(volume) != VOLUME_FIELDS:
                    raise ValueError("invalid volume fields")
                request = LiveMarketCommandRequest(
                    ClientActionId(payload["client_action_id"]), payload["account_id"],
                    payload["session_generation"], payload["symbol"], OrderSide(payload["side"]),
                    VolumeRequest(VolumeUnit(volume["unit"]), _decimal(volume["amount"])),
                    _decimal(payload["sizing_reference_price"]), payload["slippage_type"],
                    _decimal(payload["slippage_value"]),
                )
                result = self.server.runtime.call(lambda runtime: runtime.live_market(request))
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json_response(400, to_primitive(_validation_error()))
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "live_market_unavailable"})
                return
            status_code = 200 if result.status not in {CommandResultStatus.BLOCKED, CommandResultStatus.REJECTED} else 409
            self._json_response(status_code, {"ok": result.status not in {CommandResultStatus.BLOCKED}, **to_primitive(result)})
            return

        live_parity_paths = {
            "/api/live/limit", "/api/live/limit/amend", "/api/live/limit/cancel",
            "/api/live/stop", "/api/live/stop/amend", "/api/live/stop/delete",
            "/api/live/take", "/api/live/take/amend", "/api/live/take/delete",
            "/api/live/full-close",
        }
        if urlparse(self.path).path in live_parity_paths:
            try:
                fields = {
                    "/api/live/limit": LIVE_LIMIT_FIELDS,
                    "/api/live/limit/amend": LIVE_LIMIT_AMEND_FIELDS,
                    "/api/live/limit/cancel": LIVE_LIMIT_CANCEL_FIELDS,
                    "/api/live/stop": LIVE_PROTECTION_FIELDS,
                    "/api/live/stop/amend": LIVE_PROTECTION_FIELDS,
                    "/api/live/stop/delete": LIVE_PROTECTION_FIELDS,
                    "/api/live/take": LIVE_PROTECTION_FIELDS,
                    "/api/live/take/amend": LIVE_PROTECTION_FIELDS,
                    "/api/live/take/delete": LIVE_PROTECTION_FIELDS,
                    "/api/live/full-close": LIVE_FULL_CLOSE_FIELDS,
                }[urlparse(self.path).path]
                payload = self._payload(fields)
                account_id = payload["account_id"]
                session_generation = payload["session_generation"]
                path = urlparse(self.path).path
                if path == "/api/live/limit":
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
                    action = lambda api: api.limit(request)
                elif path == "/api/live/limit/amend":
                    request = AmendCommandRequest(
                        ClientActionId(payload["client_action_id"]), payload["symbol"],
                        order_id=payload["order_id"], changed_price=_decimal(payload["limit_price"]),
                    )
                    action = lambda api: api.amend(request)
                elif path == "/api/live/limit/cancel":
                    request = CancelCommandRequest(
                        ClientActionId(payload["client_action_id"]), payload["symbol"],
                        order_id=payload["order_id"],
                    )
                    action = lambda api: api.cancel(request)
                elif path.startswith("/api/live/stop") or path.startswith("/api/live/take"):
                    request = ProtectionCommandRequest(
                        ClientActionId(payload["client_action_id"]), payload["symbol"],
                        _optional_decimal(payload["take_profit"]),
                        _optional_decimal(payload["stop_loss"]),
                        payload["tp_trigger_by"], payload["sl_trigger_by"],
                    )
                    action = lambda api: api.protection(request)
                else:
                    request = FullCloseCommandRequest(
                        ClientActionId(payload["client_action_id"]), payload["symbol"],
                    )
                    action = lambda api: api.full_close(request)
                result = self.server.runtime.call(
                    lambda runtime: runtime.live_execute(
                        account_id, session_generation, payload["client_action_id"], action,
                    )
                )
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json_response(400, to_primitive(_validation_error()))
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "live_parity_unavailable"})
                return
            status_code = 200 if result.status not in {
                CommandResultStatus.BLOCKED, CommandResultStatus.REJECTED,
                CommandResultStatus.UNAVAILABLE, CommandResultStatus.VALIDATION_ERROR,
            } else 409
            self._json_response(status_code, {"ok": status_code == 200, **to_primitive(result)})
            return

        mutation_paths = {
            "/api/market", "/api/limit", "/api/limit/amend", "/api/limit/cancel",
            "/api/stop", "/api/stop/amend", "/api/stop/delete",
            "/api/take", "/api/take/amend", "/api/take/delete",
            "/api/full-close", "/api/close-all",
        }
        if urlparse(self.path).path in mutation_paths:
            try:
                self.server.runtime.call(lambda runtime: runtime.require_paper_mutations())
            except Exception:
                self._json_response(409, {"ok": False, "error": "live_mutations_disabled"})
                return

        account_refresh_id = _account_route_id(urlparse(self.path).path, "refresh")
        if account_refresh_id is not None:
            try:
                summary = self.server.runtime.call(
                    lambda runtime: runtime.refresh_live_account(account_refresh_id),
                    timeout=30.0,
                )
            except (LookupError, ValueError):
                self._json_response(404, {"ok": False, "error": "account_not_found"})
                return
            except LiveAccountReconciliationError:
                self._json_response(502, {"ok": False, "error": "live_account_reconciliation_failed"})
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "live_account_reconciliation_unavailable"})
                return
            self._json_response(200, {"ok": True, "summary": summary})
            return

        if self.path == "/api/accounts":
            try:
                payload = self._payload(ACCOUNT_CREATE_FIELDS)
                result = self.server.runtime.call(lambda runtime: runtime.add_bybit_account(
                    payload["display_name"], payload["api_key"], payload["api_secret"],
                ))
            except AccountValidationError:
                self._json_response(422, {"ok": False, "error": "bybit_validation_failed"})
                return
            except CredentialStoreError:
                self._json_response(503, {"ok": False, "error": "credential_storage_failed"})
                return
            except (ValueError, TypeError, json.JSONDecodeError):
                self._json_response(400, {"ok": False, "error": "invalid_account_payload"})
                return
            except Exception:
                self._json_response(503, {"ok": False, "error": "account_provisioning_unavailable"})
                return
            self._json_response(201 if result["created"] else 200, {"ok": True, **result})
            return

        if self.path == "/api/workspace/symbol":
            try:
                payload = self._payload(WORKSPACE_SYMBOL_FIELDS)
                market = self.server.market_data.switch(payload["symbol"])
            except WorkspaceSemanticError as exc:
                self._workspace_error_response(exc)
                return
            self._json_response(200, {
                "ok": True,
                "symbol": market.symbol,
                "generation": market.generation,
            })
            return

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
                    runtime.full_close(request),
                    runtime.paper_state(request.symbol),
                )
            )
            self._json_response(200, {
                **to_primitive(result),
                "paper_state": {"ok": True, **state},
            })
            return

        if self.path in {"/api/stop", "/api/stop/amend", "/api/take", "/api/take/amend"}:
            try:
                payload = self._payload(STOP_MUTATION_FIELDS)
                request = PaperStopMutationRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                    _decimal(payload["trigger_price"]),
                )
                operation = {
                    "/api/stop": PaperRuntime.create_stop,
                    "/api/stop/amend": PaperRuntime.amend_stop,
                    "/api/take": PaperRuntime.create_take,
                    "/api/take/amend": PaperRuntime.amend_take,
                }[self.path]
                result, state = self.server.runtime.call(
                    lambda runtime: (
                        operation(runtime, request),
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

        if self.path in {"/api/stop/delete", "/api/take/delete"}:
            try:
                payload = self._payload(STOP_DELETE_FIELDS)
                request = PaperStopDeleteRequest(
                    ClientActionId(payload["client_action_id"]), payload["symbol"],
                )
                result, state = self.server.runtime.call(
                    lambda runtime: (
                        (runtime.delete_stop(request)
                         if self.path == "/api/stop/delete"
                         else runtime.delete_take(request)),
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
                runtime.market(request),
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

    def _workspace_error_response(self, error: WorkspaceSemanticError) -> None:
        status = (
            400 if isinstance(error, UnsupportedWorkspaceInstrument)
            else 409 if isinstance(error, InactiveWorkspace)
            else 404 if error.code == "unknown_stream"
            else 503
        )
        request_id = self.headers.get("X-Request-ID", "").strip() or uuid4().hex
        self._json_response(status, {
            "ok": False,
            "error": error.code,
            "workspace_error": error.envelope(request_id=request_id),
        })

    def log_message(self, format: str, *args) -> None:
        return


def create_configured_paper_runtime(
    database_path: Path, *, book_provider, instrument_snapshot, instrument_provider,
    credential_store_factory=create_credential_store,
    account_validator_factory=BybitAccountValidator,
    live_account_store_factory=LiveAccountProjectionStore,
    active_account_preference_store_factory=ActiveAccountPreferenceStore,
    live_adapter_factory=None,
    live_mutation_adapter_factory=BybitV5MutationAdapter,
    live_market_mutations_enabled: bool = False,
    live_mainnet_authorized: bool = False,
    live_acceptance_notional_ceiling: Decimal = Decimal("0"),
    live_acceptance_single_flight: bool = False,
    live_parity_mutations_enabled: bool = False,
    account_manager=None,
) -> PaperRuntime:
    return PaperRuntime(
        database_path,
        book_provider=book_provider,
        instrument_snapshot=instrument_snapshot,
        instrument_provider=instrument_provider,
        credential_store=credential_store_factory(credential_store_path(database_path)),
        account_validator=account_validator_factory(),
        live_account_store=live_account_store_factory(
            database_path.with_suffix(".live_accounts.sqlite3")
        ),
        active_account_preference_store=active_account_preference_store_factory(
            database_path.with_suffix(".active_account.json")
        ),
        live_adapter_factory=live_adapter_factory,
        live_mutation_adapter_factory=live_mutation_adapter_factory,
        live_market_mutations_enabled=live_market_mutations_enabled,
        live_mainnet_authorized=live_mainnet_authorized,
        live_acceptance_notional_ceiling=live_acceptance_notional_ceiling,
        live_acceptance_single_flight=live_acceptance_single_flight,
        live_parity_mutations_enabled=live_parity_mutations_enabled,
        account_manager=account_manager,
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("BYBITSCANNER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_path = Path(os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3"))
    port = int(os.environ.get("BYBITSCANNER_PAPER_PORT", str(PORT)))
    validate_bybit_proxy(configure_bybit_proxy_environment())
    rest_session = create_bybit_rest_session()
    instruments = InstrumentRegistry(rest_session)
    instruments.refresh()
    instrument_snapshot = instruments.get("ONGUSDT")
    hub = MarketDataHub(
        instruments,
        create_symbol_context,
        connection_factory=create_bybit_websocket_connection,
    )
    initial_market = hub.subscribe("ONGUSDT")
    hub.start()
    book_provider = LiveOrderBookProvider(
        initial_market.public_orderbook,
        rest_session=rest_session,
    )
    runtime = SerializedPaperRuntime(lambda: create_configured_paper_runtime(
        database_path,
        book_provider=book_provider,
        instrument_snapshot=instrument_snapshot,
        instrument_provider=lambda symbol: instruments.get(symbol),
        live_market_mutations_enabled=os.environ.get("LIVE_MARKET_MUTATIONS_ENABLED", "").lower() == "true",
        live_mainnet_authorized=os.environ.get("LIVE_MAINNET_AUTHORIZED", "").lower() == "true",
        live_acceptance_notional_ceiling=Decimal(os.environ.get("LIVE_MARKET_ACCEPTANCE_NOTIONAL_CEILING", "0")),
        live_acceptance_single_flight=os.environ.get("LIVE_MARKET_ACCEPTANCE_SINGLE_FLIGHT", "").lower() == "true",
        live_parity_mutations_enabled=os.environ.get("LIVE_PARITY_MUTATIONS_ENABLED", "").lower() == "true",
    ))
    initial_market.public_orderbook.set_update_consumer(runtime.enqueue_book_update)
    market_data = WorkspaceMarketDataManager(
        instruments,
        book_provider,
        runtime,
        initial_market,
        hub=hub,
        initial_readiness_timeout=INITIAL_WORKSPACE_READINESS_TIMEOUT,
    )
    market_data.ensure_initial_ready()

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


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _validation_error() -> CommandResult:
    return CommandResult(
        "",
        CommandResultStatus.VALIDATION_ERROR,
        "validation_error",
        "command request is invalid",
    )


if __name__ == "__main__":
    main()
