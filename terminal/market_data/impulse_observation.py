"""Non-executing observation of Bybit V5 publicTrade for an existing symbol context.

Public WebSocket prints do not carry a replayable gap-free sequence. Consequently
this observer NEVER asserts complete flow, even after a healthy subscribe ACK.
No candidates, Robot commands, PnL or admission are produced here.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Lock


@dataclass(frozen=True, slots=True)
class ObservedPrint:
    trade_id: str
    timestamp_ms: int
    sequence: int
    side: str
    price: Decimal
    quantity: Decimal

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


class PublicTradeObservation:
    """Bounded, generation-fenced, atomic per-frame read-only observation."""

    LIMIT = 512
    FRAME_LIMIT = 1024

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._lock = Lock()
        self._generation = 0
        self._prints: deque[ObservedPrint] = deque(maxlen=self.LIMIT)
        self._ids: dict[str, ObservedPrint] = {}
        self._last_ms: int | None = None
        self._last_sequence: int | None = None
        self._frames = 0
        self._invalid_frames = 0
        self._gap = True  # startup/subscription history is unproven

    def mark_gap(self) -> None:
        """A disconnect/reconnect invalidates continuity and per-generation IDs."""
        with self._lock:
            self._generation += 1
            self._gap = True
            self._prints.clear()
            self._ids.clear()
            self._last_ms = None
            self._last_sequence = None

    @staticmethod
    def _positive(value: object) -> Decimal:
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ValueError("invalid numeric type")
        try:
            parsed = Decimal(str(value))
        except (ValueError, InvalidOperation) as error:
            raise ValueError("invalid decimal") from error
        if not parsed.is_finite() or parsed <= 0:
            raise ValueError("non-positive or non-finite value")
        return parsed

    def _parse(self, message: object) -> list[ObservedPrint]:
        if not isinstance(message, dict) or message.get("topic") != f"publicTrade.{self.symbol}":
            raise ValueError("unexpected publicTrade topic")
        data = message.get("data")
        if not isinstance(data, list) or len(data) > self.FRAME_LIMIT:
            raise ValueError("invalid trade batch")
        parsed: list[ObservedPrint] = []
        for item in data:
            if not isinstance(item, dict) or item.get("s") != self.symbol:
                raise ValueError("trade symbol mismatch")
            identifier = item.get("i")
            timestamp = item.get("T")
            side = item.get("S")
            sequence = item.get("seq")
            if (not isinstance(identifier, str) or not identifier or len(identifier) > 128
                    or type(timestamp) is not int or timestamp < 0
                    or type(sequence) is not int or sequence < 0
                    or side not in ("Buy", "Sell")):
                raise ValueError("invalid exact trade identity, time or side")
            parsed.append(ObservedPrint(
                identifier, timestamp, sequence, side,
                self._positive(item.get("p")), self._positive(item.get("v")),
            ))
        return parsed

    def observe(self, message: object) -> bool:
        """Return false on invalid/stale frames, without accepting any partial batch."""
        try:
            parsed = self._parse(message)
        except (TypeError, ValueError):
            with self._lock:
                self._invalid_frames += 1
                self._gap = True
            return False
        with self._lock:
            # A frame must be atomic: duplicates with conflicting contents, backward
            # timestamps, and conflicting IDs *inside* the frame are all rejected.
            pending: dict[str, ObservedPrint] = {}
            timestamp = self._last_ms
            sequence = self._last_sequence
            for item in parsed:
                old = pending.get(item.trade_id) or self._ids.get(item.trade_id)
                if old is not None:
                    if old != item:
                        self._invalid_frames += 1
                        self._gap = True
                        return False
                    continue
                if (timestamp is not None and item.timestamp_ms < timestamp) or (sequence is not None and item.sequence < sequence):
                    self._invalid_frames += 1
                    self._gap = True
                    return False
                pending[item.trade_id] = item
                timestamp = item.timestamp_ms
                sequence = item.sequence
            for item in pending.values():
                if len(self._prints) == self.LIMIT:
                    evicted = self._prints.popleft()
                    self._ids.pop(evicted.trade_id, None)
                    self._gap = True  # evicted evidence cannot support full-history claims
                self._prints.append(item)
                self._ids[item.trade_id] = item
            self._last_ms = timestamp
            self._last_sequence = sequence
            self._frames += 1
            return True

    def snapshot(self) -> dict:
        """Diagnostic only: NO signal eligibility or inferred completeness."""
        with self._lock:
            return {
                "symbol": self.symbol,
                "generation": self._generation,
                "observed_prints": len(self._prints),
                "observed_frames": self._frames,
                "invalid_frames": self._invalid_frames,
                "last_trade_ms": self._last_ms,
                "last_cross_sequence": self._last_sequence,
                "gap_or_truncation": self._gap,
                "continuity": "UNPROVEN",  # seq is not a gap-free counter
                "order_authority": False,
                "prints": tuple(self._prints),
            }


@dataclass(frozen=True, slots=True)
class RecentTradeOverlapAudit:
    """Cross-source diagnostic, NEVER source completeness or entry authority."""

    status: str
    matched_count: int = 0
    source_complete: bool = False
    trading_authorized: bool = False


def audit_recent_trade_overlap(
    snapshot: object, rest_response: object, *, start_ms: int, end_ms: int,
) -> RecentTradeOverlapAudit:
    """Compare exact prints in a *past*, REST-bracketed window, without IO.

    REST recent-trade is at most the latest 1000 prints, without a time-range
    cursor. A verified response containing executions strictly before start
    AND at/after end can independently corroborate the observed IDs and their
    facts inside [start, end); neither source is a gap-free live feed.

    The caller must separately establish REST provenance. Even EXACT_MATCH
    never clears observer gap flags or authorizes a FlowWindow/Robot entry.
    """
    unknown = RecentTradeOverlapAudit("UNPROVEN")
    if (type(start_ms) is not int or type(end_ms) is not int
            or start_ms < 0 or end_ms <= start_ms):
        raise ValueError("invalid past overlap window")
    if not isinstance(snapshot, dict) or not isinstance(rest_response, dict):
        return unknown
    symbol = snapshot.get("symbol")
    observed = snapshot.get("prints")
    result = rest_response.get("result")
    if (not isinstance(symbol, str) or not symbol.endswith("USDT")
            or not isinstance(observed, tuple)
            or len(observed) > PublicTradeObservation.LIMIT
            or type(snapshot.get("generation")) is not int
            or snapshot["generation"] < 0
            or rest_response.get("retCode") != 0
            or type(rest_response.get("retCode")) is not int
            or not isinstance(result, dict)
            or result.get("category") != "linear"):
        return unknown
    records = result.get("list")
    if not isinstance(records, list) or not 2 <= len(records) <= 1000:
        return unknown

    rest: dict[str, ObservedPrint] = {}
    oldest, newest = None, None
    for record in records:
        if not isinstance(record, dict) or record.get("symbol") != symbol:
            return unknown
        identifier = record.get("execId")
        stamp, sequence = record.get("time"), record.get("seq")
        side = record.get("side")
        if (not isinstance(identifier, str) or not identifier
                or len(identifier) > 128 or identifier in rest
                or not isinstance(stamp, str) or not stamp.isascii()
                or not stamp.isdecimal() or not isinstance(sequence, str)
                or not sequence.isascii() or not sequence.isdecimal()
                or side not in ("Buy", "Sell")):
            return unknown
        timestamp_ms, seq = int(stamp), int(sequence)
        if timestamp_ms < 0 or seq < 0 or timestamp_ms >= 2**63:
            return unknown
        try:
            item = ObservedPrint(
                identifier, timestamp_ms, seq, side,
                PublicTradeObservation._positive(record.get("price")),
                PublicTradeObservation._positive(record.get("size")),
            )
        except ValueError:
            return unknown
        rest[identifier] = item
        oldest = timestamp_ms if oldest is None else min(oldest, timestamp_ms)
        newest = timestamp_ms if newest is None else max(newest, timestamp_ms)

    # Boundary trades must be present beyond both ends; a latest-1000 page
    # lacking either boundary cannot prove this interval is wholly represented.
    if oldest is None or oldest >= start_ms or newest is None or newest < end_ms:
        return unknown
    expected = {
        key: item for key, item in rest.items()
        if start_ms <= item.timestamp_ms < end_ms
    }
    selected: dict[str, ObservedPrint] = {}
    for item in observed:
        if not isinstance(item, ObservedPrint):
            return unknown
        if start_ms <= item.timestamp_ms < end_ms:
            if item.trade_id in selected:
                return unknown
            selected[item.trade_id] = item
    if not expected or selected != expected:
        return unknown
    return RecentTradeOverlapAudit("EXACT_OVERLAP_MATCH", matched_count=len(expected))
