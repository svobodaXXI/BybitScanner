"""Authoritative, atomically refreshed Workspace instrument universe."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol

from terminal.domain.models import Category, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.exchange.normalization import PayloadNormalizationError, normalize_instrument
from terminal.market_data.workspace_errors import UnsupportedWorkspaceInstrument


class InstrumentRegistryError(RuntimeError):
    """A complete authoritative registry refresh could not be produced."""


class _Response(Protocol):
    def raise_for_status(self) -> None: ...
    def json(self) -> object: ...


class _Session(Protocol):
    def get(self, url: str, *, params: dict[str, object], timeout: int) -> _Response: ...


@dataclass(frozen=True, slots=True)
class InstrumentRegistrySnapshot:
    version: int
    instruments: tuple[InstrumentSnapshot, ...]
    by_symbol: Mapping[str, InstrumentSnapshot]


_EMPTY_SNAPSHOT = InstrumentRegistrySnapshot(0, (), MappingProxyType({}))


class InstrumentRegistry:
    """Own one immutable, transport-compatible Bybit linear instrument snapshot."""

    URL = "https://api.bybit.com/v5/market/instruments-info"

    def __init__(self, session: _Session) -> None:
        self._session = session
        self._snapshot = _EMPTY_SNAPSHOT
        self._publish_lock = threading.RLock()
        self._refresh_lock = threading.Lock()

    def refresh(self) -> InstrumentRegistrySnapshot:
        with self._refresh_lock:
            candidate = self._fetch_complete_candidate()
            with self._publish_lock:
                published = InstrumentRegistrySnapshot(
                    version=self._snapshot.version + 1,
                    instruments=candidate,
                    by_symbol=MappingProxyType({item.symbol: item for item in candidate}),
                )
                self._snapshot = published
                return published

    def snapshot(self) -> InstrumentRegistrySnapshot:
        with self._publish_lock:
            return self._snapshot

    def get(self, symbol: str) -> InstrumentSnapshot:
        try:
            normalized = Symbol(symbol).value
        except (TypeError, ValueError) as exc:
            raise UnsupportedWorkspaceInstrument(
                "Unsupported Workspace instrument",
                requested_symbol=symbol if isinstance(symbol, str) else None,
            ) from exc
        with self._publish_lock:
            instrument = self._snapshot.by_symbol.get(normalized)
        if instrument is None:
            raise UnsupportedWorkspaceInstrument(
                f"Unsupported Workspace instrument: {normalized}",
                requested_symbol=normalized,
            )
        return instrument

    def supports(self, symbol: str) -> bool:
        try:
            normalized = Symbol(symbol).value
        except (TypeError, ValueError):
            return False
        with self._publish_lock:
            return normalized in self._snapshot.by_symbol

    def list_supported(self) -> tuple[InstrumentSnapshot, ...]:
        with self._publish_lock:
            return self._snapshot.instruments

    def api_projection(self) -> list[dict[str, str]]:
        return [
            {"symbol": item.symbol, "tick_size": str(item.tick_size)}
            for item in self.list_supported()
        ]

    def _fetch_complete_candidate(self) -> tuple[InstrumentSnapshot, ...]:
        cursor = ""
        seen_cursors: set[str] = set()
        by_symbol: dict[str, InstrumentSnapshot] = {}
        while True:
            params: dict[str, object] = {"category": "linear", "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            try:
                response = self._session.get(self.URL, params=params, timeout=10)
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                raise InstrumentRegistryError("Bybit instrument refresh failed") from exc
            if not isinstance(payload, dict) or payload.get("retCode") != 0:
                raise InstrumentRegistryError("Bybit instrument response is unsuccessful")
            result = payload.get("result")
            items = result.get("list") if isinstance(result, dict) else None
            if not isinstance(items, list):
                raise InstrumentRegistryError("Bybit instrument page is malformed")
            for raw in items:
                instrument = self._normalize_supported(raw)
                if instrument is None:
                    continue
                if instrument.symbol in by_symbol:
                    raise InstrumentRegistryError(
                        f"duplicate instrument across pages: {instrument.symbol}"
                    )
                by_symbol[instrument.symbol] = instrument
            next_cursor = result.get("nextPageCursor", "")
            if next_cursor in (None, ""):
                break
            if not isinstance(next_cursor, str):
                raise InstrumentRegistryError("Bybit pagination cursor is malformed")
            if next_cursor == cursor or next_cursor in seen_cursors:
                raise InstrumentRegistryError("Bybit pagination cursor loop detected")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        if not by_symbol:
            raise InstrumentRegistryError("Bybit refresh produced no supported instruments")
        return tuple(by_symbol[symbol] for symbol in sorted(by_symbol))

    @staticmethod
    def _normalize_supported(raw: object) -> InstrumentSnapshot | None:
        if not isinstance(raw, dict):
            return None
        if (
            raw.get("status") != "Trading"
            or raw.get("quoteCoin") != "USDT"
            or raw.get("contractType") != "LinearPerpetual"
        ):
            return None
        candidate = dict(raw)
        candidate["category"] = Category.LINEAR.value
        try:
            instrument = normalize_instrument(candidate)
        except (PayloadNormalizationError, TypeError, ValueError):
            return None
        positive_values = (
            instrument.min_price,
            instrument.max_price,
            instrument.tick_size,
            instrument.min_order_quantity,
            instrument.max_order_quantity,
            instrument.max_market_order_quantity,
            instrument.quantity_step,
            instrument.min_notional_value,
        )
        if any(value <= 0 for value in positive_values):
            return None
        if (
            instrument.min_price > instrument.max_price
            or instrument.min_order_quantity > instrument.max_order_quantity
        ):
            return None
        return instrument
