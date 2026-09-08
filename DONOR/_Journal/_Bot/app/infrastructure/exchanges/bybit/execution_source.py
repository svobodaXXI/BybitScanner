"""Bybit V5 execution-history adapter and payload normalization."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation

from app.application.ports.exchange_execution_source import ExchangeExecutionSource
from app.application.ports.repositories.instrument_repository import InstrumentRepository
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution_fact import ExecutionFact
from app.core.imports import CompatibilityResult, HistoryProgress, check_bybit_execution
from app.core.imports import HistoricalInstrumentIdentity
from app.core.instruments import Instrument

from .client import BybitRestClient
from .config import BybitSettings
from .errors import (
    BybitAuthenticationError,
    BybitInstrumentMappingError,
    BybitPayloadError,
    BybitRateLimitError,
    BybitRequestError,
)
from .instrument_catalog import stable_bybit_instrument_id
from .market_data import BybitMarketDataProvider


logger = logging.getLogger(__name__)


class BybitExecutionSource(ExchangeExecutionSource):
    """Fetch all pages from Bybit and return deterministic normalized facts."""

    # Bybit V5 execution history is queried in bounded windows.  Keep a
    # one-millisecond gap-free progression because both boundaries are
    # inclusive at the API boundary.
    MAX_HISTORY_WINDOW = timedelta(days=7)

    def __init__(
        self,
        settings: BybitSettings,
        instrument_repository: InstrumentRepository,
        client=None,
    ) -> None:
        self._settings = settings
        self._instruments = instrument_repository
        self._client = client or BybitRestClient(settings)
        self._historical_instruments: dict[object, HistoricalInstrumentIdentity] = {}

    @property
    def account_id(self):
        """Account identity exposed for account-scoped discovery persistence."""
        return self._settings.account_id

    @property
    def market_data_provider(self) -> BybitMarketDataProvider:
        """Expose an exchange-neutral provider backed by this same client."""
        return BybitMarketDataProvider(self._settings, self._instruments, self._client)

    async def fetch_executions(
        self,
        *,
        cursor: str | None = None,
        since: datetime | None = None,
        end_at: datetime | None = None,
        include_inactive: bool = False,
    ) -> tuple[ExecutionFact, ...]:
        since_utc = _aware_utc(since) if since is not None else None
        end_utc = _aware_utc(end_at) if end_at is not None else None
        if since_utc is not None and end_utc is not None and since_utc > end_utc:
            raise ValueError("since must be less than or equal to end_at")
        next_cursor = cursor.strip() if isinstance(cursor, str) and cursor.strip() else None
        facts_by_id: dict[str, ExecutionFact] = {}
        for _ in range(self._settings.max_pages):
            params = {
                "category": "linear",
                "settleCoin": "USDT",
                "limit": str(self._settings.page_limit),
                "execType": "Trade",
            }
            if next_cursor:
                params["cursor"] = next_cursor
            if since_utc is not None:
                params["startTime"] = str(_epoch_millis(since_utc))
            if end_utc is not None:
                params["endTime"] = str(_epoch_millis(end_utc))
            _log_request(params)
            payload = await self._request(params)
            page, next_cursor = await self._normalize_page(payload, since_utc, end_utc, include_inactive)
            for fact in page:
                previous = facts_by_id.get(fact.external_execution_id)
                if previous is not None and previous != fact:
                    raise BybitPayloadError(f"conflicting duplicate Bybit execution: {fact.external_execution_id}")
                facts_by_id[fact.external_execution_id] = fact
            if not next_cursor:
                break
        else:
            raise BybitRequestError("Bybit pagination exceeded the configured page limit")
        return tuple(sorted(facts_by_id.values(), key=lambda item: (item.executed_at, item.external_execution_id)))

    async def fetch_raw_historical_executions(
        self,
        *,
        start_at: datetime,
        end_at: datetime | None = None,
        progress_callback=None,
    ) -> tuple[dict, ...]:
        """Read raw Trade rows for boundary discovery without normalizing them.

        This deliberately lives beside the normal source rather than adding a
        second Bybit client.  In particular, a missing ``feeCurrency`` is
        observable by discovery and is never guessed into a Money value.
        """
        start = _aware_utc(start_at)
        end = _aware_utc(end_at) if end_at is not None else datetime.now(timezone.utc)
        if start >= end:
            raise ValueError("start_at must be less than end_at")
        windows = _history_windows(start, end)
        chunks = await _run_window_workers(
            windows,
            self._fetch_raw_window,
            concurrency=self._settings.history_concurrency,
            progress_callback=progress_callback,
        )
        rows_by_id: dict[str, dict] = {}
        for chunk in chunks:
            for item in chunk:
                execution_id = item.get("execId")
                if not isinstance(execution_id, str) or not execution_id.strip():
                    execution_id = f"__invalid__{len(rows_by_id)}"
                previous = rows_by_id.get(execution_id)
                if previous is not None and previous != item:
                    raise BybitPayloadError(f"conflicting duplicate Bybit execution: {execution_id}")
                rows_by_id[execution_id] = dict(item)
        return tuple(sorted(rows_by_id.values(), key=_raw_sort_key))

    async def _fetch_raw_window(self, window: tuple[datetime, datetime]) -> tuple[dict, ...]:
        window_start, window_end = window
        rows: list[dict] = []
        cursor = None
        for _ in range(self._settings.max_pages):
            params = {
                "category": "linear", "settleCoin": "USDT", "limit": str(self._settings.page_limit),
                "execType": "Trade", "startTime": str(_epoch_millis(window_start)),
                "endTime": str(_epoch_millis(window_end)),
            }
            if cursor:
                params["cursor"] = cursor
            _log_request(params)
            payload = await self._request(params)
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("list"), list):
                raise BybitPayloadError("Bybit response lacks result.list")
            rows.extend(dict(item) for item in result["list"] if isinstance(item, dict) and _is_trade_item(item))
            next_cursor = result.get("nextPageCursor")
            if next_cursor in (None, ""):
                return tuple(rows)
            if not isinstance(next_cursor, str) or not next_cursor.strip():
                raise BybitPayloadError("Bybit nextPageCursor must be a non-empty string or null")
            cursor = next_cursor.strip()
        raise BybitRequestError("Bybit pagination exceeded the configured page limit")

    async def fetch_historical_executions(
        self,
        *,
        start_at: datetime,
        end_at: datetime | None = None,
        progress_callback=None,
    ) -> tuple[ExecutionFact, ...]:
        """Fetch a complete range using bounded windows and per-window cursors."""
        start = _aware_utc(start_at)
        end = _aware_utc(end_at) if end_at is not None else datetime.now(timezone.utc)
        if start > end:
            raise ValueError("start_at must be less than or equal to end_at")
        if start == end:
            # NEW_ONLY has an empty historical interval. Do not issue an
            # invalid equal-boundary Bybit request.
            return ()

        windows = _history_windows(start, end)
        chunks = await _run_window_workers(
            windows,
            lambda window: self.fetch_executions(since=window[0], end_at=window[1], include_inactive=True),
            concurrency=self._settings.history_concurrency,
            progress_callback=progress_callback,
        )
        facts_by_id: dict[str, ExecutionFact] = {}
        for chunk in chunks:
            for fact in chunk:
                previous = facts_by_id.get(fact.external_execution_id)
                if previous is not None and previous != fact:
                    raise BybitPayloadError(
                        f"conflicting duplicate Bybit execution: {fact.external_execution_id}"
                    )
                facts_by_id[fact.external_execution_id] = fact
        return tuple(sorted(facts_by_id.values(), key=lambda item: (item.executed_at, item.external_execution_id)))

    async def normalize_raw_historical_executions(self, rows) -> tuple[ExecutionFact, ...]:
        """Normalize a snapshot without performing another exchange request."""
        facts_by_id: dict[str, ExecutionFact] = {}
        for item in rows:
            if not _is_trade_item(item):
                continue
            fact = await self._normalize_item(item, active_only=False)
            previous = facts_by_id.get(fact.external_execution_id)
            if previous is not None and previous != fact:
                raise BybitPayloadError(f"conflicting duplicate Bybit execution: {fact.external_execution_id}")
            facts_by_id[fact.external_execution_id] = fact
        return tuple(sorted(facts_by_id.values(), key=lambda item: (item.executed_at, item.external_execution_id)))

    async def check_historical_compatibility(self, item: object) -> CompatibilityResult:
        result = check_bybit_execution(item)
        if not result.supported:
            return result
        symbol = str(item["symbol"]).strip().upper()
        matches = await self._instruments.get_by_exchange_symbol("BYBIT", symbol, active_only=False)
        if len(matches) > 1:
            return CompatibilityResult(False, "instrument unresolved")
        # Inactive records and absent current records are both valid historical
        # identities; absent records are materialized deterministically during
        # normalization and persisted only after confirmation.
        return result

    @property
    def historical_instrument_identities(self) -> tuple[HistoricalInstrumentIdentity, ...]:
        return tuple(sorted(self._historical_instruments.values(), key=lambda item: item.symbol))

    async def _request(self, params: dict[str, str]) -> dict:
        for attempt in range(self._settings.max_retries + 1):
            try:
                payload = await self._client.get("/v5/execution/list", params)
                if not isinstance(payload, dict):
                    raise BybitPayloadError("Bybit response must be an object")
                ret_code = payload.get("retCode")
                if ret_code in {10003, 10004, 10005}:
                    raise BybitAuthenticationError("Bybit authentication or permission check failed")
                if ret_code in {10006, 10429}:
                    raise BybitRateLimitError("Bybit API rate limit reached")
                if ret_code != 0:
                    request_error = BybitRequestError(
                        "Bybit API request failed:\n"
                        f"retCode={ret_code}\n"
                        f"retMsg={_sanitize_ret_msg(payload.get('retMsg'))}"
                    )
                    request_error.retryable = False
                    raise request_error
                return payload
            except BybitAuthenticationError:
                raise
            except BybitPayloadError:
                raise
            except (BybitRateLimitError, BybitRequestError) as error:
                if isinstance(error, BybitRequestError) and getattr(error, "retryable", True) is False:
                    raise
                if attempt >= self._settings.max_retries:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        raise AssertionError("unreachable")

    async def _normalize_page(
        self,
        payload: dict,
        since: datetime | None,
        end_at: datetime | None,
        include_inactive: bool,
    ) -> tuple[tuple[ExecutionFact, ...], str | None]:
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise BybitPayloadError("Bybit response lacks result.list")
        facts = []
        for item in result["list"]:
            # The request is explicitly Trade-only, but keep a defensive
            # response filter so a mixed/legacy response can never turn a
            # Funding event into a BUY/SELL ExecutionFact.
            if not _is_trade_item(item):
                continue
            fact = await self._normalize_item(item, active_only=not include_inactive)
            if (since is None or fact.executed_at >= since) and (end_at is None or fact.executed_at <= end_at):
                facts.append(fact)
        next_cursor = result.get("nextPageCursor")
        if next_cursor in (None, ""):
            return tuple(facts), None
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            raise BybitPayloadError("Bybit nextPageCursor must be a non-empty string or null")
        return tuple(facts), next_cursor.strip()

    async def _normalize_item(self, item: object, *, active_only: bool = True) -> ExecutionFact:
        if not isinstance(item, dict):
            raise BybitPayloadError("Bybit execution item must be an object")
        compatibility = check_bybit_execution(item)
        if not compatibility.supported:
            raise BybitPayloadError(f"Bybit execution is incompatible: {compatibility.reason}")
        execution_id = _required_text(item, "execId")
        symbol = _required_text(item, "symbol").upper()
        # Historical fills may belong to a delisted instrument.  Catalog sync
        # keeps that row inactive instead of deleting it, so import resolves
        # both active and preserved historical mappings.
        matches = await self._instruments.get_by_exchange_symbol("BYBIT", symbol, active_only=active_only)
        if not matches:
            if active_only:
                all_matches = await self._instruments.get_by_exchange_symbol("BYBIT", symbol, active_only=False)
                if all_matches:
                    raise BybitInstrumentMappingError(f"instrument inactive for BYBIT/{symbol}")
            else:
                historical_id = stable_bybit_instrument_id("LINEAR", symbol)
                matches = (Instrument(historical_id, symbol, f"{symbol} (historical)", "BYBIT", "LINEAR", False),)
                self._historical_instruments[historical_id] = HistoricalInstrumentIdentity(historical_id, symbol)
            if not matches:
                raise BybitInstrumentMappingError(f"no active Journal instrument for BYBIT/{symbol}")
        if len(matches) > 1:
            raise BybitInstrumentMappingError(f"ambiguous Journal instruments for BYBIT/{symbol}")
        side_text = _required_text(item, "side")
        try:
            side = {"Buy": ExecutionSide.BUY, "Sell": ExecutionSide.SELL}[side_text]
        except KeyError as error:
            raise BybitPayloadError(f"unsupported Bybit execution side: {side_text!r}") from error
        raw_fee_currency = item.get("feeCurrency")
        if not isinstance(raw_fee_currency, str) or raw_fee_currency.strip().upper() != "USDT":
            logger.debug(
                "BYBIT historical fee currency anomaly execTime=%s symbol=%s execId=%s raw_feeCurrency=%s",
                item.get("execTime"), symbol, execution_id, raw_fee_currency,
            )
        # The request scope is settleCoin=USDT.  feeCurrency is optional and
        # historically inconsistent in this endpoint, so it is diagnostic
        # metadata only and never changes the economic currency.
        fee_currency = "USDT"
        fee_amount = _decimal(item, "execFee")
        if fee_amount < 0:
            raise BybitPayloadError("negative Bybit execution fees/rebates are not representable by Money")
        try:
            return ExecutionFact(
                exchange="BYBIT",
                account_id=self._settings.account_id,
                instrument_id=matches[0].instrument_id,
                side=side,
                quantity=Quantity(_decimal(item, "execQty")),
                price=Price(_decimal(item, "execPrice")),
                fee=Money(fee_amount, fee_currency),
                executed_at=_timestamp(item.get("execTime")),
                external_execution_id=execution_id,
                external_order_id=_optional_text(item.get("orderId")),
                position_id=_optional_text(item.get("positionId")),
            )
        except (TypeError, ValueError, ArithmeticError) as error:
            raise BybitPayloadError(f"invalid Bybit execution payload for {execution_id}") from error


def _required_text(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BybitPayloadError(f"Bybit execution field {key} is required")
    return value.strip()


def _is_trade_item(item: object) -> bool:
    if not isinstance(item, dict):
        raise BybitPayloadError("Bybit execution item must be an object")
    exec_type = item.get("execType")
    if exec_type is None:
        # Keep compatibility with older recorded fixtures; real Bybit rows
        # include execType and are still protected by the request parameter.
        return True
    if not isinstance(exec_type, str):
        raise BybitPayloadError("Bybit execType must be a string")
    return exec_type.strip().lower() == "trade"


def _optional_text(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise BybitPayloadError("optional Bybit execution reference must be a string")
    return value.strip() or None


def _decimal(item: dict, key: str) -> Decimal:
    value = item.get(key)
    if not isinstance(value, (str, Decimal, int)) or isinstance(value, bool):
        raise BybitPayloadError(f"Bybit execution field {key} must be a decimal string")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise BybitPayloadError(f"Bybit execution field {key} is not a valid Decimal") from error
    if not result.is_finite():
        raise BybitPayloadError(f"Bybit execution field {key} must be finite")
    return result


def _timestamp(value: object) -> datetime:
    milliseconds = _decimal({"execTime": value}, "execTime")
    if milliseconds != milliseconds.to_integral_value():
        raise BybitPayloadError("Bybit execTime must be an integer millisecond timestamp")
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(milliseconds))


def _aware_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("since must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("since must be timezone-aware")
    return value.astimezone(timezone.utc)


def _epoch_millis(value: datetime) -> int:
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86_400_000) + (delta.seconds * 1_000) + (delta.microseconds // 1_000)


def _raw_sort_key(item: dict) -> tuple[datetime, str]:
    value = item.get("execTime")
    try:
        timestamp = _timestamp(value)
    except (TypeError, ValueError, BybitPayloadError):
        # Invalid rows sort first and therefore cannot accidentally become a
        # supported boundary.  They remain classified as incompatible.
        timestamp = datetime.min.replace(tzinfo=timezone.utc)
    execution_id = item.get("execId")
    return timestamp, execution_id.strip() if isinstance(execution_id, str) else ""


def _log_request(params: dict[str, str]) -> None:
    """Log only non-sensitive execution query metadata."""
    start = params.get("startTime")
    end = params.get("endTime")
    range_ms = None
    if start is not None and end is not None:
        try:
            range_ms = int(end) - int(start)
        except ValueError:
            range_ms = "invalid"
    logger.debug(
        "BYBIT execution request category=%s settleCoin=%s execType=%s "
        "startTime=%s endTime=%s range_ms=%s cursor_present=%s",
        params.get("category"), params.get("settleCoin"), params.get("execType"),
        start, end, range_ms, bool(params.get("cursor")),
    )


def _sanitize_ret_msg(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return "<empty>"
    sanitized = " ".join(value.strip().split())
    sanitized = re.sub(
        r"(?i)(api[_ -]?(?:key|secret)|authorization|signature|auth[_ -]?headers?)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        sanitized,
    )
    return sanitized[:300]


def _history_windows(start: datetime, end: datetime) -> tuple[tuple[datetime, datetime], ...]:
    """Build inclusive, gap-free API windows of at most seven days."""
    windows = []
    window_start = start
    while window_start < end:
        window_end = min(window_start + BybitExecutionSource.MAX_HISTORY_WINDOW - timedelta(milliseconds=1), end)
        start_ms = _epoch_millis(window_start)
        end_ms = _epoch_millis(window_end)
        if start_ms >= end_ms:
            raise ValueError("historical request must have startTime < endTime")
        if end_ms - start_ms > 7 * 86_400_000:
            raise ValueError("historical request exceeds seven days")
        windows.append((window_start, window_end))
        if window_end >= end:
            break
        window_start = window_end + timedelta(milliseconds=1)
    return tuple(windows)


async def _run_window_workers(windows, worker, *, concurrency: int, progress_callback=None):
    """Run independent windows through a bounded worker pool."""
    queue = asyncio.Queue()
    for index, window in enumerate(windows):
        await queue.put((index, window))
    results = [None] * len(windows)
    completed = 0
    found = 0
    lock = asyncio.Lock()

    async def one_worker():
        nonlocal completed, found
        while True:
            try:
                index, window = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                value = await worker(window)
                results[index] = value
                count = len(value)
                async with lock:
                    completed += 1
                    found += count
                    if progress_callback is not None:
                        event = HistoryProgress("fetch", len(windows), completed, found)
                        callback_result = progress_callback(event)
                        if hasattr(callback_result, "__await__"):
                            await callback_result
            finally:
                queue.task_done()

    worker_count = min(max(1, concurrency), len(windows))
    await asyncio.gather(*(one_worker() for _ in range(worker_count)))
    return tuple(results)
