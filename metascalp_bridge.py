"""
metascalp_bridge

TG-METASCALP-2: open a NEW MetaScalp order book (combo) for a Scanner signal symbol.

Owner decision (CR-TRADING-WORKSPACE-001 §24.3-24.4): one owner tap on a Telegram
signal opens a new MetaScalp combo through the official local API
`POST /api/combo {"Ticker": SYMBOL}`; MetaScalp's own placement is accepted,
existing order books, tickers and link groups are never touched.

`/api/combo` has no connection selector ("opens on the currently active exchange and
market connection"), so every call is gated on exactly ONE connection that is
Connected Bybit USDT Perpetual and lists the ticker. Only these local routes exist
here: GET /ping, GET /api/connections, GET /api/connections/{id}/tickers and
POST /api/combo. No order, position, change-ticker, panel or link-group route.
The POST is sent at most once per call and is never retried.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

HOST = "127.0.0.1"
PORTS = tuple(range(17845, 17856))
# Worst case (11 silent ports + both reads + POST) stays near 11 s, inside the time
# Telegram allows for answering a callback; a running local MetaScalp answers at once.
PING_TIMEOUT_SECONDS = 0.3
READ_TIMEOUT_SECONDS = 2.0
COMBO_TIMEOUT_SECONDS = 4.0

BYBIT_EXCHANGE_ID = 6
USDT_PERPETUAL_MARKET_TYPE = 5
CONNECTED_STATE = 2

CALLBACK_PREFIX = "ms:open:"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,26}USDT$")


class MetaScalpError(Exception):
    """Owner-facing reason the order book was not opened."""


def valid_symbol(symbol) -> bool:
    return isinstance(symbol, str) and bool(_SYMBOL_PATTERN.fullmatch(symbol))


def callback_data(symbol: str) -> str | None:
    return CALLBACK_PREFIX + symbol if valid_symbol(symbol) else None


def parse_callback(data) -> str | None:
    text = str(data or "")
    if not text.startswith(CALLBACK_PREFIX):
        return None
    symbol = text[len(CALLBACK_PREFIX):]
    return symbol if valid_symbol(symbol) else ""


def _url(port: int, path: str) -> str:
    return f"http://{HOST}:{int(port)}{path}"


def _get_json(port: int, path: str, timeout: float):
    with urllib.request.urlopen(_url(port, path), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_port() -> int:
    for port in PORTS:
        try:
            payload = _get_json(port, "/ping", PING_TIMEOUT_SECONDS)
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("app") == "MetaScalp":
            return port
    raise MetaScalpError("MetaScalp не запущен")


def _single_bybit_perpetual(port: int) -> int:
    try:
        payload = _get_json(port, "/api/connections", READ_TIMEOUT_SECONDS)
    except Exception as exc:
        raise MetaScalpError("MetaScalp: не удалось получить подключения") from exc
    connections = payload.get("connections") if isinstance(payload, dict) else None
    if not isinstance(connections, list) or len(connections) != 1:
        raise MetaScalpError("MetaScalp: нужно ровно одно подключение Bybit USDT Perpetual")
    connection = connections[0] if isinstance(connections[0], dict) else {}
    if (
        connection.get("ExchangeId") != BYBIT_EXCHANGE_ID
        or connection.get("MarketType") != USDT_PERPETUAL_MARKET_TYPE
    ):
        raise MetaScalpError("MetaScalp: подключение не Bybit USDT Perpetual")
    if connection.get("State") != CONNECTED_STATE:
        raise MetaScalpError("MetaScalp: подключение Bybit не в состоянии Connected")
    connection_id = connection.get("Id")
    if not isinstance(connection_id, int) or isinstance(connection_id, bool):
        raise MetaScalpError("MetaScalp: некорректный идентификатор подключения")
    return connection_id


def _ticker_listed(port: int, connection_id: int, symbol: str) -> bool:
    try:
        payload = _get_json(port, f"/api/connections/{connection_id}/tickers", READ_TIMEOUT_SECONDS)
    except Exception as exc:
        raise MetaScalpError("MetaScalp: не удалось получить список инструментов") from exc
    tickers = payload.get("tickers") if isinstance(payload, dict) else None
    return any(isinstance(item, dict) and item.get("Name") == symbol for item in tickers or [])


def _post_combo(port: int, symbol: str) -> None:
    request = urllib.request.Request(
        _url(port, "/api/combo"),
        data=json.dumps({"Ticker": symbol}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=COMBO_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raise MetaScalpError(f"MetaScalp отклонил запрос (HTTP {exc.code})") from exc
    except Exception as exc:
        # The request may have reached MetaScalp; never resend it.
        raise MetaScalpError("MetaScalp не ответил; проверьте окно MetaScalp") from exc
    if not (isinstance(payload, dict) and payload.get("status") == "ok"):
        raise MetaScalpError("MetaScalp: неожиданный ответ")


def open_order_book(symbol: str) -> str:
    """Open one new MetaScalp combo for `symbol`; returns the owner-facing result."""

    if not valid_symbol(symbol):
        raise MetaScalpError("Некорректный тикер сигнала")
    port = discover_port()
    connection_id = _single_bybit_perpetual(port)
    if not _ticker_listed(port, connection_id, symbol):
        raise MetaScalpError(f"MetaScalp: {symbol} нет в Bybit USDT Perpetual")
    _post_combo(port, symbol)
    return f"MetaScalp: открыт стакан {symbol}"
