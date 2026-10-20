"""MIRROR-INTEGRATION-4: live read-only inputs for the OBSERVE_ONLY sidecar.

* ``BybitClosedKlineSource`` — closed 5m/1m candles from the public Bybit
  ``/v5/market/kline`` endpoint (no keys, no trading endpoint), fetched on the
  sidecar's own thread through the existing ``create_bybit_rest_session``
  (same proxy configuration as the PAPER backend). Only candles whose interval
  ended at or before the *exchange* time of the response are returned (no
  look-ahead); a response whose exchange time disagrees with the local clock
  by more than one interval, or whose newest closed candle is not the latest
  one that should exist, is stale and returns nothing. Malformed, duplicated or
  misaligned rows make the whole response unavailable. A missing candle inside
  the range is passed through: ``geometry.naked_retest`` flags it as a data gap
  and the sidecar holds its cursor.
* ``ProtectionHealthGate`` — read-only adapter for the existing
  ``GET /api/robot/protection-health``. The sidecar may work only when the
  backend answers ``ok`` and ``healthy`` with no unhealthy symbol and no pending
  protection ingress; anything else (unknown, timeout, unreachable backend)
  means protection has priority and the cycle is skipped.

Neither class writes anywhere or talks to the PAPER owner.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import time
from typing import Any, Callable, Mapping

KLINE_URL = "https://api.bybit.com/v5/market/kline"
PROTECTION_HEALTH_PATH = "/api/robot/protection-health"
DEFAULT_BACKEND_URL = "http://127.0.0.1:8765"
INTERVAL_MS = {"1": 60_000, "5": 300_000}
PAGE_LIMIT = 1000          # Bybit maximum rows per kline request
MAX_PAGES_PER_CALL = 3     # bounds one call; the rest is fetched on the next cycle
HTTP_TIMEOUT_S = 10.0


class CandleSourceUnavailable(RuntimeError):
    """The response cannot be trusted; the caller must not consume any candle from it."""


def _default_session():
    from terminal.runtime.paper_http_server import create_bybit_rest_session
    return create_bybit_rest_session()


def _price(value: Any) -> float:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CandleSourceUnavailable("kline price is not numeric") from exc
    if not number.is_finite() or number <= 0:
        raise CandleSourceUnavailable("kline price is not positive")
    return float(number)


def parse_closed_klines(payload: Any, interval: str, *, local_now_ms: int) -> list[dict]:
    """Validate one Bybit kline response and return its closed candles, ascending.

    Raises ``CandleSourceUnavailable`` for anything that is not provably correct.
    """

    step = INTERVAL_MS[interval]
    if not isinstance(payload, Mapping) or payload.get("retCode") != 0:
        raise CandleSourceUnavailable("kline request rejected")
    exchange_ms = payload.get("time")
    if isinstance(exchange_ms, bool) or not isinstance(exchange_ms, int) or exchange_ms <= 0:
        raise CandleSourceUnavailable("kline response has no exchange time")
    if abs(exchange_ms - local_now_ms) > step:
        raise CandleSourceUnavailable("exchange and local clocks disagree")
    result = payload.get("result")
    rows = result.get("list") if isinstance(result, Mapping) else None
    if not isinstance(rows, list):
        raise CandleSourceUnavailable("kline list is missing")
    candles: dict[int, dict] = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 5:
            raise CandleSourceUnavailable("kline row is malformed")
        try:
            start = int(row[0])
        except (TypeError, ValueError) as exc:
            raise CandleSourceUnavailable("kline start is malformed") from exc
        if start % step:
            raise CandleSourceUnavailable("kline start is not aligned to the interval")
        if start in candles:
            raise CandleSourceUnavailable("kline response has duplicate intervals")
        o, h, l, c = (_price(value) for value in row[1:5])
        if h < max(o, c) or l > min(o, c) or l > h:
            raise CandleSourceUnavailable("kline OHLC is inconsistent")
        if start + step > exchange_ms:
            continue                                  # still forming at exchange time: never used
        candles[start] = {"open_time_ms": start, "close_time_ms": start + step,
                          "open": o, "high": h, "low": l, "close": c, "closed": True}
    return [candles[start] for start in sorted(candles)]


class BybitClosedKlineSource:
    """Closed public candles for the sidecar (5m stream, 1m inside one 5m candle)."""

    def __init__(
        self, *, http_get: Callable[..., Any] | None = None,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._get = http_get
        self._clock = clock_ms if clock_ms is not None else (lambda: int(time.time() * 1000))
        self.unavailable = 0
        self.stale = 0

    def _request(self, symbol: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
        if self._get is None:
            self._get = _default_session().get
        try:
            response = self._get(KLINE_URL, params={
                "category": "linear", "symbol": symbol, "interval": interval,
                "start": start_ms, "end": end_ms, "limit": PAGE_LIMIT,
            }, timeout=HTTP_TIMEOUT_S)
            response.raise_for_status()
            payload = response.json()
        except CandleSourceUnavailable:
            raise
        except Exception as exc:
            raise CandleSourceUnavailable(f"kline request failed: {type(exc).__name__}") from exc
        return parse_closed_klines(payload, interval, local_now_ms=self._clock())

    def _range(self, symbol: str, interval: str, after_close_ms: int, until_ms: int) -> list[dict]:
        step = INTERVAL_MS[interval]
        out: list[dict] = []
        start = after_close_ms
        for _ in range(MAX_PAGES_PER_CALL):
            if start + step > until_ms:
                break
            end = min(until_ms, start + step * PAGE_LIMIT) - 1
            page = [c for c in self._request(symbol, interval, start, end) if c["open_time_ms"] >= start]
            if not page:
                break
            out.extend(page)
            start = page[-1]["close_time_ms"]
            if len(page) < PAGE_LIMIT:
                break
        return out

    def closed_candles(self, candidate_id: str, symbol: str, after_close_ms: int | None) -> list[dict]:
        """5m closed candles after ``after_close_ms``; [] when stale or unavailable (cursor holds)."""

        if after_close_ms is None:
            raise CandleSourceUnavailable("a start cursor is required for the live source")
        now = self._clock()
        latest_close = now - now % INTERVAL_MS["5"]
        try:
            candles = self._range(symbol, "5", after_close_ms, now)
        except CandleSourceUnavailable:
            self.unavailable += 1
            return []
        if candles and candles[-1]["close_time_ms"] < latest_close - INTERVAL_MS["5"]:
            # The newest closed candle should end at or one interval before ``latest_close``.
            self.stale += 1
            return []
        return candles

    def fine_candles(self, symbol: str, coarse: Mapping[str, Any]) -> list[dict]:
        """1m candles fully inside one closed 5m candle; raises when they cannot be proven."""

        start, end = int(coarse["open_time_ms"]), int(coarse["close_time_ms"])
        candles = [c for c in self._range(symbol, "1", start, end) if c["close_time_ms"] <= end]
        expected = list(range(start, end, INTERVAL_MS["1"]))
        if [c["open_time_ms"] for c in candles] != expected:
            raise CandleSourceUnavailable("1m coverage of the 5m candle is incomplete")
        return candles


class ProtectionHealthGate:
    """``protection_busy()`` for the sidecar from the existing protection-health GET."""

    def __init__(self, *, backend_url: str = DEFAULT_BACKEND_URL,
                 http_get: Callable[..., Any] | None = None, timeout_s: float = 2.0) -> None:
        self._url = backend_url.rstrip("/") + PROTECTION_HEALTH_PATH
        self._timeout = timeout_s
        if http_get is None:
            import requests
            session = requests.Session()
            session.trust_env = False                 # local backend: never through a proxy
            http_get = session.get
        self._get = http_get
        self.last_reason: str | None = None

    def busy(self) -> bool:
        """True unless protection is provably idle and healthy right now."""

        try:
            response = self._get(self._url, timeout=self._timeout)
            if getattr(response, "status_code", None) != 200:
                return self._block("http_status")
            body = response.json()
        except Exception:
            return self._block("backend_unreachable")
        if not isinstance(body, Mapping) or body.get("ok") is not True:
            return self._block("not_ok")
        if body.get("healthy") is not True:
            return self._block("protection_unhealthy")
        if body.get("unhealthy_symbols") != {}:
            return self._block("unhealthy_symbols")
        ingress = body.get("ingress")
        pending = ingress.get("current_pending") if isinstance(ingress, Mapping) else None
        if isinstance(pending, bool) or not isinstance(pending, int) or pending != 0:
            return self._block("ingress_pending_unknown_or_nonzero")
        self.last_reason = None
        return False

    def _block(self, reason: str) -> bool:
        self.last_reason = reason
        return True
