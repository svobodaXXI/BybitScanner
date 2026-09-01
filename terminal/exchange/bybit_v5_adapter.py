"""Lazy read-only Bybit V5 REST and private-stream adapter."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from terminal.domain.models import TradingAccountId

from .events import (
    ExecutionEvent,
    InstrumentSnapshot,
    OrderEvent,
    PositionEvent,
    StreamLifecycleEvent,
    StreamLifecycleKind,
)
from .normalization import (
    PayloadNormalizationError,
    normalize_execution,
    normalize_execution_message,
    normalize_instrument,
    normalize_order,
    normalize_order_message,
    normalize_position,
    normalize_position_message,
)


class BybitAdapterError(RuntimeError):
    """Normalized adapter failure without secret or raw-payload exposure."""


class AuthenticationError(BybitAdapterError):
    pass


class RateLimitError(BybitAdapterError):
    pass


class TransportError(BybitAdapterError):
    pass


class TransportTimeout(TransportError):
    pass


class MalformedResponse(BybitAdapterError):
    pass


class UnsupportedPayload(BybitAdapterError):
    pass


class WebSocketDisconnected(BybitAdapterError):
    pass


class BybitResponseError(BybitAdapterError):
    def __init__(self, ret_code: int, ret_msg: str):
        super().__init__(f"Bybit read failed with retCode={ret_code}: {ret_msg}")
        self.ret_code = ret_code
        self.ret_msg = ret_msg


@dataclass(frozen=True, slots=True, repr=False)
class BybitCredentials:
    api_key: str
    api_secret: str

    def __post_init__(self) -> None:
        if not self.api_key or not self.api_secret:
            raise ValueError("Bybit credentials must be supplied explicitly")

    def __repr__(self) -> str:
        return "BybitCredentials(<redacted>)"


@dataclass(frozen=True, slots=True)
class BybitWalletSnapshot:
    wallet_balance_usdt: Decimal
    total_equity_usdt: Decimal
    available_balance_usdt: Decimal
    exchange_time_ms: int | None
    balance_provenance: Mapping[str, str | None] = field(default_factory=dict)


HttpFactory = Callable[..., Any]
WebSocketFactory = Callable[..., Any]
OrderCallback = Callable[[OrderEvent], None]
ExecutionCallback = Callable[[ExecutionEvent], None]
PositionCallback = Callable[[PositionEvent], None]
LifecycleCallback = Callable[[StreamLifecycleEvent], None]


_AUTHENTICATION_CODES = frozenset({10003, 10004, 10005, 10007, 10010})
_RATE_LIMIT_CODE = 10006
_MAX_HISTORY_WINDOW_MS = 7 * 24 * 60 * 60 * 1000


def _default_http_factory(**kwargs):
    from pybit.unified_trading import HTTP

    return HTTP(**kwargs)


def _default_websocket_factory(**kwargs):
    from pybit.unified_trading import WebSocket

    return WebSocket(**kwargs)


class BybitV5ReadAdapter:
    """Read and subscription facade; it intentionally exposes no mutations."""

    def __init__(
        self,
        trading_account_id: TradingAccountId,
        credentials: BybitCredentials,
        *,
        testnet: bool,
        http_factory: HttpFactory | None = None,
        websocket_factory: WebSocketFactory | None = None,
    ) -> None:
        if not isinstance(testnet, bool):
            raise TypeError("testnet must be selected explicitly as bool")
        self.trading_account_id = trading_account_id
        self._credentials = credentials
        self._testnet = testnet
        self._http_factory = http_factory or _default_http_factory
        self._websocket_factory = websocket_factory or _default_websocket_factory
        self._http_session = None
        self._private_socket = None
        self._lifecycle_callback: LifecycleCallback | None = None

    def _http(self):
        if self._http_session is None:
            self._http_session = self._http_factory(
                testnet=self._testnet,
                api_key=self._credentials.api_key,
                api_secret=self._credentials.api_secret,
                timeout=10,
                force_retry=False,
                max_retries=1,
                log_requests=False,
            )
        return self._http_session

    def list_active_orders(self, symbol: str) -> tuple[OrderEvent, ...]:
        return self._paginated_events(
            method_name="get_open_orders",
            normalizer=normalize_order,
            category="linear",
            symbol=symbol.upper(),
            openOnly=0,
            limit=50,
        )

    def list_all_active_orders(self) -> tuple[OrderEvent, ...]:
        return self._paginated_events(
            method_name="get_open_orders", normalizer=normalize_order,
            category="linear", settleCoin="USDT", openOnly=0, limit=50,
        )

    def list_open_positions(self) -> tuple[PositionEvent, ...]:
        positions = self._paginated_events(
            method_name="get_positions", normalizer=normalize_position,
            category="linear", settleCoin="USDT", limit=200,
        )
        return tuple(position for position in positions if position.size > 0)

    def get_wallet_snapshot(self) -> BybitWalletSnapshot:
        response = self._read("get_wallet_balance", accountType="UNIFIED", coin="USDT")
        try:
            accounts = response["result"]["list"]
            account = accounts[0]
            if account["accountType"] != "UNIFIED":
                raise ValueError("wallet account type is not unified")
            coin = next(item for item in account.get("coin", ()) if item.get("coin") == "USDT")
            provenance = {
                f"account.{name}": str(account[name]) if account.get(name) is not None else None
                for name in (
                    "accountType", "totalWalletBalance", "totalEquity", "totalMarginBalance",
                    "totalAvailableBalance", "accountIMRate", "totalInitialMargin", "totalPerpUPL",
                )
            }
            provenance.update({
                f"USDT.{name}": str(coin[name]) if coin.get(name) is not None else None
                for name in (
                    "walletBalance", "equity", "availableToWithdraw", "availableToBorrow",
                    "locked", "unrealisedPnl", "spotBorrow", "borrowAmount", "usdValue",
                )
            })
            return BybitWalletSnapshot(
                _finite_decimal(account["totalWalletBalance"]),
                _finite_decimal(account["totalEquity"]),
                _finite_decimal(account["totalEquity"]),
                int(response["time"]) if response.get("time") is not None else None,
                provenance,
            )
        except (KeyError, IndexError, StopIteration, TypeError, ValueError) as exc:
            raise MalformedResponse("wallet response is incomplete") from exc

    def list_order_history(
        self,
        symbol: str,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> tuple[OrderEvent, ...]:
        _validate_history_window(start_time_ms, end_time_ms)
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": 50,
        }
        _add_time_window(params, start_time_ms, end_time_ms)
        return self._paginated_events(
            method_name="get_order_history",
            normalizer=normalize_order,
            **params,
        )

    def get_position(self, symbol: str) -> PositionEvent:
        response = self._read(
            "get_positions",
            category="linear",
            symbol=symbol.upper(),
        )
        items, category, _ = _response_items(response)
        if not items:
            raise MalformedResponse("position response did not contain a position")
        normalized: list[PositionEvent] = []
        for item in items:
            normalized.append(
                self._normalize(normalize_position, _with_category(item, category))
            )
        if len(normalized) != 1:
            raise UnsupportedPayload("selected symbol returned multiple position legs")
        return normalized[0]

    def list_executions(
        self,
        symbol: str,
        *,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> tuple[ExecutionEvent, ...]:
        _validate_history_window(start_time_ms, end_time_ms)
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol.upper(),
            "limit": 100,
        }
        _add_time_window(params, start_time_ms, end_time_ms)
        return self._paginated_events(
            method_name="get_executions",
            normalizer=normalize_execution,
            **params,
        )

    def get_instrument(self, symbol: str) -> InstrumentSnapshot:
        response = self._read(
            "get_instruments_info",
            category="linear",
            symbol=symbol.upper(),
        )
        items, category, _ = _response_items(response)
        if len(items) != 1:
            raise MalformedResponse("instrument response must contain exactly one item")
        try:
            return normalize_instrument(_with_category(items[0], category))
        except PayloadNormalizationError as exc:
            raise UnsupportedPayload(str(exc)) from exc

    def _paginated_events(self, method_name: str, normalizer, **params):
        events = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            request = dict(params)
            if cursor:
                request["cursor"] = cursor
            response = self._read(method_name, **request)
            items, category, next_cursor = _response_items(response)
            for item in items:
                events.append(self._normalize(normalizer, _with_category(item, category)))
            if not next_cursor:
                break
            if next_cursor in seen_cursors:
                raise MalformedResponse("pagination cursor repeated")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return tuple(events)

    def _normalize(self, normalizer, payload):
        try:
            return normalizer(payload, self.trading_account_id)
        except PayloadNormalizationError as exc:
            raise UnsupportedPayload(str(exc)) from exc

    def _read(self, method_name: str, **kwargs) -> Mapping[str, Any]:
        session = self._http()
        method = getattr(session, method_name, None)
        if method is None or not callable(method):
            raise TransportError(f"read client does not support {method_name}")
        try:
            response = method(**kwargs)
        except BybitAdapterError:
            raise
        except Exception as exc:
            raise _normalized_transport_exception(exc, method_name) from exc
        if not isinstance(response, Mapping):
            raise MalformedResponse("Bybit read response must be an object")
        _validate_response_code(response)
        return response

    def start_private_streams(
        self,
        *,
        on_order: OrderCallback,
        on_execution: ExecutionCallback,
        on_position: PositionCallback,
        on_lifecycle: LifecycleCallback,
    ) -> StreamLifecycleEvent:
        if self._private_socket is not None:
            raise BybitAdapterError("private streams already started")
        self._lifecycle_callback = on_lifecycle
        buffering = self._lifecycle(
            StreamLifecycleKind.BUFFERING,
            "private evidence is untrusted until REST reconciliation",
        )
        on_lifecycle(buffering)
        socket = None
        try:
            socket = self._websocket_factory(
                channel_type="private",
                testnet=self._testnet,
                api_key=self._credentials.api_key,
                api_secret=self._credentials.api_secret,
            )
            socket.subscribe("order.linear", self._order_handler(on_order, on_lifecycle))
            socket.subscribe(
                "execution.linear",
                self._execution_handler(on_execution, on_lifecycle),
            )
            socket.subscribe(
                "position.linear",
                self._position_handler(on_position, on_lifecycle),
            )
            self._private_socket = socket
        except TimeoutError as exc:
            if socket is not None:
                _quietly_close(socket)
            on_lifecycle(self._lifecycle(StreamLifecycleKind.DISCONNECTED, "connection timeout"))
            raise TransportTimeout("private WebSocket connection timed out") from exc
        except Exception as exc:
            if socket is not None:
                _quietly_close(socket)
            on_lifecycle(self._lifecycle(StreamLifecycleKind.DISCONNECTED, "connection failed"))
            raise TransportError(
                f"private WebSocket connection failed ({type(exc).__name__})"
            ) from exc
        if not self.private_stream_connected():
            event = self._lifecycle(StreamLifecycleKind.DISCONNECTED, "socket is not connected")
            on_lifecycle(event)
            raise WebSocketDisconnected(event.reason)
        connected = self._lifecycle(
            StreamLifecycleKind.CONNECTED_UNTRUSTED,
            "stream connected; reconciliation still required",
        )
        on_lifecycle(connected)
        return connected

    def _order_handler(self, callback, lifecycle_callback):
        def handle(message):
            self._dispatch_message(
                normalize_order_message,
                message,
                callback,
                lifecycle_callback,
            )

        return handle

    def _execution_handler(self, callback, lifecycle_callback):
        def handle(message):
            self._dispatch_message(
                normalize_execution_message,
                message,
                callback,
                lifecycle_callback,
            )

        return handle

    def _position_handler(self, callback, lifecycle_callback):
        def handle(message):
            self._dispatch_message(
                normalize_position_message,
                message,
                callback,
                lifecycle_callback,
            )

        return handle

    def _dispatch_message(self, normalizer, message, callback, lifecycle_callback):
        try:
            events = normalizer(message, self.trading_account_id)
        except PayloadNormalizationError:
            lifecycle_callback(
                self._lifecycle(
                    StreamLifecycleKind.RECONCILIATION_REQUIRED,
                    "unsupported private-stream payload",
                )
            )
            return
        for event in events:
            callback(event)

    def private_stream_connected(self) -> bool:
        socket = self._private_socket
        if socket is None:
            return False
        try:
            return bool(socket.is_connected())
        except Exception:
            return False

    def observe_private_stream(self) -> StreamLifecycleEvent:
        if self.private_stream_connected():
            return self._lifecycle(
                StreamLifecycleKind.CONNECTED_UNTRUSTED,
                "stream transport connected; reconciliation status is external",
            )
        event = self._lifecycle(
            StreamLifecycleKind.DISCONNECTED,
            "private stream disconnected; reconciliation required",
        )
        if self._lifecycle_callback is not None:
            self._lifecycle_callback(event)
        return event

    def close_private_streams(self) -> StreamLifecycleEvent:
        socket = self._private_socket
        self._private_socket = None
        if socket is not None:
            try:
                socket.exit()
            except Exception as exc:
                raise TransportError(
                    f"private WebSocket close failed ({type(exc).__name__})"
                ) from exc
        event = self._lifecycle(StreamLifecycleKind.DISCONNECTED, "private streams closed")
        if self._lifecycle_callback is not None:
            self._lifecycle_callback(event)
        return event

    def _lifecycle(self, kind: StreamLifecycleKind, reason: str) -> StreamLifecycleEvent:
        return StreamLifecycleEvent(self.trading_account_id, kind, reason)


def _validate_response_code(response: Mapping[str, Any]) -> None:
    ret_code = response.get("retCode")
    ret_msg = response.get("retMsg", "")
    if not isinstance(ret_code, int) or not isinstance(ret_msg, str):
        raise MalformedResponse("Bybit response code/message is malformed")
    if ret_code == 0:
        return
    if ret_code in _AUTHENTICATION_CODES:
        raise AuthenticationError(f"Bybit authentication failed with retCode={ret_code}")
    if ret_code == _RATE_LIMIT_CODE:
        raise RateLimitError("Bybit read rate limit exceeded")
    raise BybitResponseError(ret_code, ret_msg)


def _finite_decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("decimal must be finite")
    return result


def _response_items(
    response: Mapping[str, Any]
) -> tuple[list[Mapping[str, Any]], str, str | None]:
    result = response.get("result")
    if not isinstance(result, Mapping):
        raise MalformedResponse("Bybit result must be an object")
    category = result.get("category")
    if category != "linear":
        raise UnsupportedPayload(f"unsupported response category: {category}")
    items = result.get("list")
    if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
        raise MalformedResponse("Bybit result list must contain objects")
    cursor = result.get("nextPageCursor")
    if cursor in (None, ""):
        cursor = None
    elif not isinstance(cursor, str):
        raise MalformedResponse("Bybit pagination cursor must be a string")
    return items, category, cursor


def _with_category(item: Mapping[str, Any], category: str) -> Mapping[str, Any]:
    if "category" in item:
        return item
    merged = dict(item)
    merged["category"] = category
    return merged


def _validate_history_window(start_time_ms: int | None, end_time_ms: int | None) -> None:
    for value in (start_time_ms, end_time_ms):
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise ValueError("history timestamps must be non-negative integers")
    if start_time_ms is not None and end_time_ms is not None:
        if end_time_ms < start_time_ms:
            raise ValueError("history end must not precede start")
        if end_time_ms - start_time_ms > _MAX_HISTORY_WINDOW_MS:
            raise ValueError("Bybit execution/order history window must not exceed seven days")


def _add_time_window(
    params: dict[str, Any], start_time_ms: int | None, end_time_ms: int | None
) -> None:
    if start_time_ms is not None:
        params["startTime"] = start_time_ms
    if end_time_ms is not None:
        params["endTime"] = end_time_ms


def _normalized_transport_exception(exc: Exception, method_name: str) -> BybitAdapterError:
    if isinstance(exc, TimeoutError):
        return TransportTimeout(f"Bybit read timed out: {method_name}")
    status_code = getattr(exc, "status_code", None)
    if status_code in _AUTHENTICATION_CODES:
        return AuthenticationError(
            f"Bybit authentication failed with retCode={status_code}"
        )
    if status_code == _RATE_LIMIT_CODE:
        return RateLimitError("Bybit read rate limit exceeded")
    return TransportError(
        f"Bybit read transport failed: {method_name} ({type(exc).__name__})"
    )


def _quietly_close(socket: Any) -> None:
    try:
        socket.exit()
    except Exception:
        pass
