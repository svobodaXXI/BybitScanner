"""Bounded client projections derived from one authoritative SymbolContext."""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Callable

from terminal.market_data.hub import SymbolContext


DEFAULT_CLIENT_BOOK_DEPTH = 250
DEFAULT_CLIENT_TRADE_LIMIT = 80
DEFAULT_CLIENT_CANDLE_LIMIT = 1000


class StaleProjectionError(LookupError):
    """The projection no longer belongs to the authoritative Workspace generation."""


class ClientMarketProjection:
    """Stateful snapshot/delta projection for one symbol and Workspace generation."""

    def __init__(
        self,
        context: SymbolContext,
        workspace_generation: int,
        *,
        is_current: Callable[[SymbolContext, int], bool] | None = None,
        book_depth: int = DEFAULT_CLIENT_BOOK_DEPTH,
        trade_limit: int = DEFAULT_CLIENT_TRADE_LIMIT,
        candle_limit: int = DEFAULT_CLIENT_CANDLE_LIMIT,
    ) -> None:
        if book_depth <= 0 or trade_limit <= 0 or candle_limit <= 0:
            raise ValueError("projection limits must be positive")
        self.context = context
        self.symbol = context.symbol
        self.workspace_generation = workspace_generation
        self.book_depth = book_depth
        self.trade_limit = trade_limit
        self.candle_limit = candle_limit
        self._is_current = is_current or (lambda _context, _generation: True)
        self._book_levels: tuple[dict[str, str], dict[str, str]] | None = None
        self._book_source_version = 0
        self._book_source_update_id = 0
        self._book_source_sequence = 0
        self._book_health: str | None = None
        self._book_projection_version = 0
        self._trade_seen_order: deque[str] = deque()
        self._trade_seen: set[str] = set()
        self._trade_bootstrapped = False
        self._trade_projection_version = 0
        self._candle_state: dict[str, tuple[dict, ...]] = {}
        self._candle_source_versions: dict[str, int] = {}
        self._candle_projection_versions: dict[str, int] = {}

    def book_event(self, *, base_version: int | None = None) -> dict | None:
        self._require_current()
        source = self.context.public_orderbook.snapshot()
        health = str(source.get("state") or "NOT_READY")
        if health != "READY" or not source.get("bids") or not source.get("asks"):
            self._book_levels = None
            if health == self._book_health:
                return None
            self._book_health = health
            self._book_projection_version += 1
            return self._event(
                "book_health", self._book_projection_version, source,
                state=health, resync_required=True,
            )

        bids = self._bounded_levels(source.get("bids"), reverse=True)
        asks = self._bounded_levels(source.get("asks"), reverse=False)
        source_version = self._positive_int(source.get("version"))
        update_id = self._positive_int(source.get("updateId"))
        sequence = self._positive_int(source.get("sequence"))
        identity_regressed = (
            self._book_source_version
            and (
                source_version < self._book_source_version
                or update_id < self._book_source_update_id
                or sequence < self._book_source_sequence
            )
        )
        source_gap = (
            self._book_source_version
            and source_version > self._book_source_version + 1
        )
        client_mismatch = base_version is not None and base_version != self._book_projection_version
        needs_snapshot = self._book_levels is None or identity_regressed or source_gap or client_mismatch
        if not needs_snapshot and (bids, asks) == self._book_levels:
            self._remember_book(source_version, update_id, sequence, bids, asks, health)
            return None

        previous_version = self._book_projection_version
        self._book_projection_version += 1
        if needs_snapshot:
            event = self._event(
                "book_snapshot", self._book_projection_version, source,
                state=health, depth=self.book_depth, bids=list(bids), asks=list(asks),
                resync=bool(self._book_levels is not None),
            )
        else:
            old_bids, old_asks = self._book_levels
            event = self._event(
                "book_delta", self._book_projection_version, source,
                state=health, depth=self.book_depth, base_version=previous_version,
                new_version=self._book_projection_version,
                bids=self._level_delta(old_bids, bids),
                asks=self._level_delta(old_asks, asks),
            )
        self._remember_book(source_version, update_id, sequence, bids, asks, health)
        return event

    def trades_event(self) -> dict | None:
        self._require_current()
        trades = self.context.public_trades.snapshot_after(0)
        unique = self._unique_trades(trades)
        if not self._trade_bootstrapped:
            bootstrap = unique[-self.trade_limit:]
            self._remember_trades(unique)
            self._trade_bootstrapped = True
            self._trade_projection_version += 1
            return self._simple_event(
                "trade_bootstrap", self._trade_projection_version,
                source_timestamp=max((int(item.get("ended_at_ms", 0)) for item in bootstrap), default=0),
                state="READY", trades=bootstrap,
            )
        fresh = [item for item in unique if str(item.get("id")) not in self._trade_seen]
        self._remember_trades(unique)
        if not fresh:
            return None
        fresh = fresh[-self.trade_limit:]
        self._trade_projection_version += 1
        return self._simple_event(
            "trade_batch", self._trade_projection_version,
            source_timestamp=max((int(item.get("ended_at_ms", 0)) for item in fresh), default=0),
            state="READY", trades=fresh,
        )

    def candles_event(self, interval: str) -> dict | None:
        self._require_current()
        buffer = self.context.public_klines.get(interval)
        if buffer is None or not hasattr(buffer, "snapshot"):
            raise LookupError(f"unsupported candle interval: {interval}")
        source = buffer.snapshot()
        state = str(source.get("state") or "NOT_READY")
        candles = tuple(dict(item) for item in source.get("candles", [])[-self.candle_limit:])
        source_version = self._positive_int(source.get("version"))
        previous = self._candle_state.get(interval)
        projection_version = self._candle_projection_versions.get(interval, 0) + 1
        if state != "READY" or not candles:
            if previous is None and self._candle_source_versions.get(interval) == source_version:
                return None
            self._candle_state.pop(interval, None)
            self._candle_source_versions[interval] = source_version
            self._candle_projection_versions[interval] = projection_version
            return self._candle_event("candle_health", projection_version, source, interval, state,
                                      resync_required=True)
        if previous is None:
            event = self._candle_event(
                "candle_bootstrap", projection_version, source, interval, state,
                candles=list(candles), limit=self.candle_limit,
            )
        else:
            old_by_time = {int(item["startTime"]): item for item in previous}
            new_by_time = {int(item["startTime"]): item for item in candles}
            missing_times = set(old_by_time) - set(new_by_time)
            oldest_new = min(new_by_time) if new_by_time else 0
            history_mismatch = any(start_time >= oldest_new for start_time in missing_times)
            if history_mismatch:
                event = self._candle_event(
                    "candle_bootstrap", projection_version, source, interval, state,
                    candles=list(candles), limit=self.candle_limit, resync=True,
                )
            else:
                changes = [
                    {"action": "replace" if int(item["startTime"]) in old_by_time else "append", **item}
                    for item in candles
                    if old_by_time.get(int(item["startTime"])) != item
                ]
                if not changes:
                    self._candle_source_versions[interval] = source_version
                    return None
                event = self._candle_event(
                    "candle_update", projection_version, source, interval, state,
                    candles=changes,
                )
        self._candle_state[interval] = candles
        self._candle_source_versions[interval] = source_version
        self._candle_projection_versions[interval] = projection_version
        return event

    def _require_current(self) -> None:
        if not self._is_current(self.context, self.workspace_generation):
            raise StaleProjectionError("stale Workspace projection generation")

    def assert_current(self) -> None:
        """Fail closed if this projection lost active Workspace authority."""
        self._require_current()

    @staticmethod
    def _positive_int(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, parsed)

    def _bounded_levels(self, raw: object, *, reverse: bool) -> tuple[dict[str, str], ...]:
        levels = [
            {"price": str(item["price"]), "size": str(item["size"])}
            for item in raw if isinstance(item, dict) and "price" in item and "size" in item
        ] if isinstance(raw, list) else []
        levels.sort(key=lambda item: Decimal(item["price"]), reverse=reverse)
        return tuple(levels[:self.book_depth])

    @staticmethod
    def _level_delta(old: tuple[dict[str, str], ...], new: tuple[dict[str, str], ...]) -> list[dict[str, str]]:
        old_map = {item["price"]: item["size"] for item in old}
        new_map = {item["price"]: item["size"] for item in new}
        deleted = [{"price": price, "size": "0"} for price in old_map if price not in new_map]
        changed = [
            {"price": price, "size": size}
            for price, size in new_map.items() if old_map.get(price) != size
        ]
        return deleted + changed

    def _remember_book(self, source_version: int, update_id: int, sequence: int,
                       bids: tuple[dict[str, str], ...], asks: tuple[dict[str, str], ...], health: str) -> None:
        self._book_source_version = source_version
        self._book_source_update_id = update_id
        self._book_source_sequence = sequence
        self._book_levels = (bids, asks)
        self._book_health = health

    @staticmethod
    def _unique_trades(trades: list[dict]) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for trade in trades:
            trade_id = str(trade.get("id"))
            if trade_id not in seen:
                seen.add(trade_id)
                result.append(dict(trade))
        return result

    def _remember_trades(self, trades: list[dict]) -> None:
        for trade in trades:
            trade_id = str(trade.get("id"))
            if trade_id in self._trade_seen:
                continue
            self._trade_seen.add(trade_id)
            self._trade_seen_order.append(trade_id)
        while len(self._trade_seen_order) > max(1000, self.trade_limit * 4):
            self._trade_seen.discard(self._trade_seen_order.popleft())

    def _event(self, kind: str, version: int, source: dict, **payload: object) -> dict:
        return self._simple_event(
            kind, version,
            source_timestamp=int(source.get("receivedAt") or source.get("timestamp") or 0),
            source_version=self._positive_int(source.get("version")),
            upstream_update_id=self._positive_int(source.get("updateId")),
            upstream_sequence=self._positive_int(source.get("sequence")),
            **payload,
        )

    def _candle_event(self, kind: str, version: int, source: dict,
                      interval: str, state: str, **payload: object) -> dict:
        return self._simple_event(
            kind, version, source_timestamp=int(source.get("receivedAt") or 0),
            source_version=self._positive_int(source.get("version")),
            interval=interval, state=state, **payload,
        )

    def _simple_event(self, kind: str, version: int, *, source_timestamp: int,
                      **payload: object) -> dict:
        return {
            "symbol": self.symbol,
            "workspace_generation": self.workspace_generation,
            "kind": kind,
            "projection_version": version,
            "source_timestamp": source_timestamp,
            **payload,
        }
