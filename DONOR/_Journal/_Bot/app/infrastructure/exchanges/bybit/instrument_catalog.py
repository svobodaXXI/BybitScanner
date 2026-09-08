"""Read-only Bybit instrument catalog source and explicit sync operation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid5

from app.core.instruments import Instrument, InstrumentId
from app.infrastructure.persistence.repositories.instrument_repository import SqlAlchemyInstrumentRepository

from .client import BybitRestClient
from .config import BybitSettings
from .errors import BybitAuthenticationError, BybitPayloadError, BybitRateLimitError, BybitRequestError


_BYBIT_INSTRUMENT_NAMESPACE = UUID("4c6fd2b9-4ea1-4a40-92d8-00a907b3d3d1")
_ACTIVE_STATUSES = {"TRADING", "PRELAUNCH"}


@dataclass(frozen=True, slots=True)
class BybitInstrumentCatalogResult:
    instruments: tuple[Instrument, ...]
    pages: int


@dataclass(frozen=True, slots=True)
class InstrumentCatalogSyncSummary:
    fetched: int
    upserted: int
    deactivated: int
    pages: int


class BybitInstrumentCatalogSource:
    """Fetch all pages from the public ``instruments-info`` endpoint."""

    def __init__(self, settings: BybitSettings, client=None) -> None:
        self._settings = settings
        self._client = client or BybitRestClient(settings)

    @property
    def category(self) -> str:
        return self._settings.category

    async def fetch_instruments(self) -> BybitInstrumentCatalogResult:
        cursor = None
        items: dict[str, Instrument] = {}
        pages = 0
        while pages < self._settings.max_pages:
            params = {
                "category": self._settings.category,
                "limit": str(self._settings.page_limit),
            }
            if cursor:
                params["cursor"] = cursor
            payload = await self._request(params)
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("list"), list):
                raise BybitPayloadError("Bybit instruments response lacks result.list")
            for item in result["list"]:
                instrument = _normalize_instrument(item, category=self._settings.category)
                previous = items.get(instrument.symbol)
                if previous is not None and previous != instrument:
                    raise BybitPayloadError(f"conflicting duplicate Bybit instrument: {instrument.symbol}")
                items[instrument.symbol] = instrument
            pages += 1
            cursor = result.get("nextPageCursor")
            if cursor in (None, ""):
                return BybitInstrumentCatalogResult(
                    tuple(sorted(items.values(), key=lambda value: value.symbol)), pages
                )
            if not isinstance(cursor, str) or not cursor.strip():
                raise BybitPayloadError("Bybit nextPageCursor must be a non-empty string or null")
            cursor = cursor.strip()
        raise BybitRequestError("Bybit instrument pagination exceeded the configured page limit")

    async def _request(self, params: dict[str, str]) -> dict:
        for attempt in range(self._settings.max_retries + 1):
            try:
                getter = getattr(self._client, "get_public", self._client.get)
                payload = await getter("/v5/market/instruments-info", params)
                if not isinstance(payload, dict):
                    raise BybitPayloadError("Bybit response must be an object")
                ret_code = payload.get("retCode")
                if ret_code in {10003, 10004, 10005}:
                    raise BybitAuthenticationError("Bybit public catalog permission check failed")
                if ret_code in {10006, 10429}:
                    raise BybitRateLimitError("Bybit API rate limit reached")
                if ret_code != 0:
                    raise BybitRequestError(f"Bybit API request failed with code {ret_code}")
                return payload
            except (BybitAuthenticationError, BybitPayloadError):
                raise
            except (BybitRateLimitError, BybitRequestError):
                if attempt >= self._settings.max_retries:
                    raise
                import asyncio
                await asyncio.sleep(0.25 * (2**attempt))
        raise AssertionError("unreachable")


class BybitInstrumentCatalogSync:
    """Explicit admin/bootstrap operation; never called by Telegram startup."""

    def __init__(self, source: BybitInstrumentCatalogSource, repository_factory=SqlAlchemyInstrumentRepository) -> None:
        self._source = source
        self._repository_factory = repository_factory

    async def execute(self, session) -> InstrumentCatalogSyncSummary:
        result = await self._source.fetch_instruments()
        repository = self._repository_factory(session)
        for instrument in result.instruments:
            await repository.save(instrument)
        deactivated = await repository.deactivate_missing(
            "BYBIT", self._source.category.upper(), tuple(item.symbol for item in result.instruments)
        )

        return InstrumentCatalogSyncSummary(
            fetched=len(result.instruments),
            upserted=len(result.instruments),
            deactivated=deactivated,
            pages=result.pages,
        )


def stable_bybit_instrument_id(category: str, symbol: str) -> InstrumentId:
    return InstrumentId(uuid5(_BYBIT_INSTRUMENT_NAMESPACE, f"BYBIT:{category.strip().upper()}:{symbol.strip().upper()}"))


def _normalize_instrument(item: object, *, category: str) -> Instrument:
    if not isinstance(item, dict):
        raise BybitPayloadError("Bybit instrument item must be an object")
    symbol = _required_text(item, "symbol").upper()
    status = _required_text(item, "status").upper()
    base = _optional_text(item.get("baseCoin"))
    quote = _optional_text(item.get("quoteCoin")) or _optional_text(item.get("settleCoin"))
    name = f"{base}/{quote}" if base and quote else symbol
    return Instrument(
        stable_bybit_instrument_id(category, symbol),
        symbol,
        name,
        "BYBIT",
        category.upper(),
        status in _ACTIVE_STATUSES,
    )


def _required_text(item: dict, key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BybitPayloadError(f"Bybit instrument field {key} is required")
    return value.strip()


def _optional_text(value: object) -> str | None:
    return value.strip().upper() if isinstance(value, str) and value.strip() else None
