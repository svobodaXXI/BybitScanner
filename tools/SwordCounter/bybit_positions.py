"""SwordCounter S1: read-only access to Bybit V5 open positions.

One signed GET to ``/v5/position/list`` and nothing else. It never places,
changes or removes orders, never touches the BybitScanner trading runtime and
keeps no state: every call reads the exchange's current positions, so a
restarted application simply calls it again.

Occupied margin
---------------
Bybit documents ``positionIM`` as the position's initial margin (identical to
``positionIMByMp``, calculated by mark price). ``positionBalance`` is documented
as deprecated and pointing at ``positionIM``. The module therefore reports
exactly ``positionIM`` and never derives margin from ``positionValue / leverage``:
leverage is carried only as reported information. In portfolio margin mode the
API returns ``""`` for ``positionIM`` and ``leverage``; that stays ``None``.

Failure semantics
-----------------
Zero open positions is returned only for a well-formed successful reply with an
empty list. An API error, HTTP error, timeout, malformed reply or any unparsable
row raises a ``BybitPositionsError`` subclass; nothing is substituted or skipped.

Credentials come from the environment (``SWORDCOUNTER_BYBIT_API_KEY`` and
``SWORDCOUNTER_BYBIT_API_SECRET``), are never logged, never part of a URL and
hidden from ``repr``. Use a key with read-only permission.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable, ClassVar, Protocol
from urllib.parse import urlencode, urlsplit

import requests

BASE_URL = "https://api.bybit.com"
# Official Bybit V5 REST hosts (mainnet and its alternative, testnet). The signed request carries
# the API key and signature in headers, so it may never be sent anywhere else.
ALLOWED_API_HOSTS = frozenset({"api.bybit.com", "api.bytick.com", "api-testnet.bybit.com"})
POSITION_LIST_PATH = "/v5/position/list"
SUPPORTED_CATEGORY = "linear"
DEFAULT_SETTLE_COINS = ("USDT", "USDC")
DEFAULT_RECV_WINDOW_MS = 5000
MAX_RECV_WINDOW_MS = 60000
DEFAULT_TIMEOUT_S = 10.0
PAGE_LIMIT = 200
MAX_PAGES = 50
API_KEY_ENV = "SWORDCOUNTER_BYBIT_API_KEY"
API_SECRET_ENV = "SWORDCOUNTER_BYBIT_API_SECRET"
_SIDES = {"Buy", "Sell"}
_COIN = re.compile(r"^[A-Z0-9]{2,10}$")


class BybitPositionsError(RuntimeError):
    """Base class: the open positions could not be read reliably."""


class BybitCredentialsError(BybitPositionsError):
    """API credentials are missing or blank (only variable names are reported)."""


class BybitTransportError(BybitPositionsError):
    """The request did not complete (timeout, connection, proxy). Only the error class is kept."""


class BybitApiError(BybitPositionsError):
    """Bybit answered with an error: a non-zero retCode or a non-200 HTTP status."""

    def __init__(self, message: str, *, ret_code: int | None = None,
                 ret_msg: str | None = None, http_status: int | None = None) -> None:
        super().__init__(message)
        self.ret_code = ret_code
        self.ret_msg = ret_msg
        self.http_status = http_status


class BybitResponseError(BybitPositionsError):
    """The reply was received but is malformed or internally inconsistent."""


@dataclass(frozen=True)
class Credentials:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip() \
                or not isinstance(self.api_secret, str) or not self.api_secret.strip():
            raise BybitCredentialsError(f"{API_KEY_ENV} and {API_SECRET_ENV} must both be set")

    def __repr__(self) -> str:
        return "Credentials(api_key=<hidden>, api_secret=<hidden>)"

    __str__ = __repr__

    @classmethod
    def from_env(cls) -> "Credentials":
        return cls(os.environ.get(API_KEY_ENV, ""), os.environ.get(API_SECRET_ENV, ""))


@dataclass(frozen=True)
class OpenPosition:
    """One open linear position exactly as Bybit reports it."""

    MARGIN_FIELD: ClassVar[str] = "positionIM"

    symbol: str
    side: str                      # "Buy" long / "Sell" short
    position_idx: int              # 0 one-way, 1 hedge buy leg, 2 hedge sell leg
    settle_coin: str
    size: Decimal                  # always > 0
    avg_price: Decimal
    position_value: Decimal
    position_status: str
    mark_price: Decimal | None
    position_im: Decimal | None    # Bybit initial margin (by mark price) = occupied margin
    position_mm: Decimal | None
    leverage: Decimal | None       # informational only, never used to compute margin
    unrealised_pnl: Decimal | None
    updated_time_ms: int | None

    @property
    def occupied_margin(self) -> Decimal | None:
        """Occupied margin: exactly ``positionIM``; ``None`` when the API does not provide it."""
        return self.position_im

    @property
    def margin_available(self) -> bool:
        return self.position_im is not None


class _Session(Protocol):
    def get(self, url: str, headers: dict | None = ..., timeout: float | None = ...): ...


def fetch_open_positions(
    credentials: Credentials,
    *,
    category: str = SUPPORTED_CATEGORY,
    settle_coins: tuple[str, ...] = DEFAULT_SETTLE_COINS,
    base_url: str = BASE_URL,
    recv_window_ms: int = DEFAULT_RECV_WINDOW_MS,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    session: _Session | None = None,
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
) -> tuple[OpenPosition, ...]:
    """Read every currently open linear position, or raise. Never returns a guess."""
    if category != SUPPORTED_CATEGORY:
        raise ValueError("only the linear category is supported")
    coins = tuple(settle_coins)
    if not coins or any(not isinstance(c, str) or not _COIN.match(c) for c in coins) \
            or len(set(coins)) != len(coins):
        raise ValueError("settle_coins must be unique upper-case coin codes")
    if not isinstance(recv_window_ms, int) or not 1 <= recv_window_ms <= MAX_RECV_WINDOW_MS:
        raise ValueError("recv_window_ms must be between 1 and 60000")
    if not timeout_s > 0:
        raise ValueError("timeout_s must be positive")
    origin = _api_origin(base_url)

    http = session if session is not None else requests.Session()
    positions: list[OpenPosition] = []
    seen: set[tuple[str, int]] = set()
    for coin in coins:
        cursor = ""
        used_cursors: set[str] = set()
        for _ in range(MAX_PAGES):
            params = {"category": category, "settleCoin": coin, "limit": str(PAGE_LIMIT)}
            if cursor:
                params["cursor"] = cursor
            body = _signed_get(http, credentials, origin, params, recv_window_ms, timeout_s, clock_ms)
            result = _result(body)
            for item in result["list"]:
                position = _parse_row(item, coin)
                if position is None:
                    continue
                key = (position.symbol, position.position_idx)
                if key in seen:
                    raise BybitResponseError("duplicate open position in the Bybit reply")
                seen.add(key)
                positions.append(position)
            next_cursor = result.get("nextPageCursor", "")
            if not isinstance(next_cursor, str):
                raise BybitResponseError("nextPageCursor is not a string")
            if not next_cursor:
                break
            if next_cursor in used_cursors:
                raise BybitResponseError("Bybit returned a repeated page cursor")
            used_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise BybitResponseError("too many result pages")
    return tuple(positions)


def _api_origin(base_url: object) -> str:
    """Return ``https://<host>`` for an official Bybit API host, else raise before any request."""
    if not isinstance(base_url, str):
        raise ValueError("base_url must be an official Bybit API host")
    parts = urlsplit(base_url)
    try:
        port = parts.port
    except ValueError:
        port = -1
    host = parts.hostname or ""
    if (parts.scheme != "https" or "@" in parts.netloc or parts.username is not None
            or parts.password is not None or port not in (None, 443)
            or parts.path not in ("", "/") or parts.query or parts.fragment
            or host not in ALLOWED_API_HOSTS):
        raise ValueError("base_url must be https://<official Bybit API host> without port, "
                         "credentials, path, query or fragment")
    return f"https://{host}"


def _signed_get(http, credentials, origin, params, recv_window_ms, timeout_s, clock_ms):
    query = urlencode(params)
    timestamp = str(clock_ms())
    payload = f"{timestamp}{credentials.api_key}{recv_window_ms}{query}"
    signature = hmac.new(credentials.api_secret.encode("utf-8"), payload.encode("utf-8"),
                         hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": credentials.api_key,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": str(recv_window_ms),
        "X-BAPI-SIGN": signature,
    }
    failure = None
    try:
        # Never follow redirects: requests would forward the X-BAPI key/signature headers.
        response = http.get(f"{origin}{POSITION_LIST_PATH}?{query}", headers=headers,
                            timeout=timeout_s, allow_redirects=False)
    except requests.RequestException as error:
        failure = type(error).__name__
    if failure is not None:
        # Raised outside the except block on purpose: the transport exception (whose message
        # may embed proxy credentials) must not stay reachable through __cause__/__context__.
        raise BybitTransportError(f"Bybit request failed: {failure}")
    final_url = getattr(response, "url", None)
    if getattr(response, "history", None) or (
            isinstance(final_url, str) and f"https://{urlsplit(final_url).hostname or ''}" != origin):
        raise BybitResponseError("Bybit reply came through a redirect or from another host")
    status = getattr(response, "status_code", None)
    if status != 200:
        raise BybitApiError(f"Bybit HTTP status {status}", http_status=status)
    body, malformed = None, False
    try:
        body = response.json()
    except ValueError:
        malformed = True
    if malformed:
        raise BybitResponseError("Bybit reply is not valid JSON")
    if not isinstance(body, dict):
        raise BybitResponseError("Bybit reply is not a JSON object")
    return body


def _result(body: dict) -> dict:
    ret_code = body.get("retCode")
    if isinstance(ret_code, bool) or not isinstance(ret_code, int):
        raise BybitResponseError("Bybit reply has no integer retCode")
    if ret_code != 0:
        ret_msg = body.get("retMsg")
        ret_msg = ret_msg if isinstance(ret_msg, str) else ""
        raise BybitApiError(f"Bybit retCode {ret_code}: {ret_msg}", ret_code=ret_code, ret_msg=ret_msg)
    result = body.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("list"), list):
        raise BybitResponseError("Bybit reply has no result list")
    return result


def _decimal(item: dict, name: str, *, optional: bool = False) -> Decimal | None:
    value = item.get(name)
    if value is None or (isinstance(value, str) and value.strip() == ""):
        if optional:
            return None
        raise BybitResponseError(f"position field {name} is missing")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BybitResponseError(f"position field {name} is not numeric")
    try:
        parsed = Decimal(str(value).strip())
    except InvalidOperation:
        raise BybitResponseError(f"position field {name} is not numeric") from None
    if not parsed.is_finite():
        raise BybitResponseError(f"position field {name} is not finite")
    return parsed


def _parse_row(item: object, settle_coin: str) -> OpenPosition | None:
    if not isinstance(item, dict):
        raise BybitResponseError("position row is not an object")
    size = _decimal(item, "size")
    if size < 0:
        raise BybitResponseError("position size is negative")
    if size == 0:
        return None  # Bybit lists empty positions with size 0 and an empty side
    symbol = item.get("symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        raise BybitResponseError("position symbol is missing")
    side = item.get("side")
    if side not in _SIDES:
        raise BybitResponseError("position side is not Buy or Sell")
    idx = item.get("positionIdx")
    if isinstance(idx, bool) or not isinstance(idx, int) or idx not in (0, 1, 2):
        raise BybitResponseError("positionIdx is not 0, 1 or 2")
    status = item.get("positionStatus")
    if not isinstance(status, str):
        raise BybitResponseError("positionStatus is missing")
    position_im = _decimal(item, "positionIM", optional=True)
    by_mark_price = _decimal(item, "positionIMByMp", optional=True)
    if position_im is not None and by_mark_price is not None and position_im != by_mark_price:
        raise BybitResponseError("positionIM and positionIMByMp disagree")
    updated = item.get("updatedTime")
    updated_ms = None
    if updated not in (None, ""):
        try:
            updated_ms = int(str(updated))
        except ValueError:
            raise BybitResponseError("updatedTime is not an integer") from None
    return OpenPosition(
        symbol=symbol.strip(), side=side, position_idx=idx, settle_coin=settle_coin, size=size,
        avg_price=_decimal(item, "avgPrice"), position_value=_decimal(item, "positionValue"),
        position_status=status,
        mark_price=_decimal(item, "markPrice", optional=True),
        position_im=position_im if position_im is not None else by_mark_price,
        position_mm=_decimal(item, "positionMM", optional=True),
        leverage=_decimal(item, "leverage", optional=True),
        unrealised_pnl=_decimal(item, "unrealisedPnl", optional=True),
        updated_time_ms=updated_ms,
    )
