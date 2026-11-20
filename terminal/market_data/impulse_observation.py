"""Non-executing observation of Bybit V5 publicTrade for an existing symbol context.

Public WebSocket prints do not carry a replayable gap-free sequence. Consequently
this observer NEVER asserts complete flow, even after a healthy subscribe ACK.
No candidates, Robot commands, PnL or admission are produced here.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
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
    # Ingress receipt time is local causal metadata, not part of exchange
    # trade identity. REST ID/fact comparison must ignore it.
    received_at_ms: int | None = field(default=None, compare=False)

    @property
    def notional(self) -> Decimal:
        return self.price * self.quantity


class PublicTradeObservation:
    """Bounded, generation-fenced, atomic per-frame read-only observation."""

    LIMIT = 512
    # Bybit recent-trade offers at most 1000 exact IDs in a single response.
    # This capacity is only available after explicit PAPER flow opt-in.
    # REST still has to bracket BOTH closed minutes; capacity alone cannot
    # prove completeness or increase the amount REST can attest.
    CERTIFICATION_LIMIT = 1000
    FRAME_LIMIT = 1024

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._lock = Lock()
        self._generation = 0
        self._capacity = self.LIMIT
        self._prints: deque[ObservedPrint] = deque(maxlen=self._capacity)
        self._ids: dict[str, ObservedPrint] = {}
        self._last_ms: int | None = None
        self._last_sequence: int | None = None
        self._frames = 0
        self._invalid_frames = 0
        self._gap = True  # startup/subscription history is unproven

    def enable_certification_buffer(self) -> bool:
        """Opt-in only: one bounded two-closed-minute exact-print window.

        No new subscription or queue, and zero extra per-print hashing.
        Resetting source state cannot retroactively certify prints observed
        before the opt-in. A fresh two-minute window must arrive naturally.
        """
        with self._lock:
            if self._capacity == self.CERTIFICATION_LIMIT:
                return False
            self._capacity = self.CERTIFICATION_LIMIT
            self._prints = deque(maxlen=self._capacity)
            self._ids.clear()
            self._generation += 1  # fence any earlier source proof
            self._gap = True
            return True

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

    def observe(self, message: object, *, received_at_ms: int | None = None) -> bool:
        """Atomically record a frame and its local arrival time, if supplied."""
        try:
            if (received_at_ms is not None and
                    (type(received_at_ms) is not int or received_at_ms < 0)):
                raise ValueError("invalid local ingress receipt time")
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
                pending[item.trade_id] = replace(item, received_at_ms=received_at_ms)
                timestamp = item.timestamp_ms
                sequence = item.sequence
            if pending and self._capacity == self.CERTIFICATION_LIMIT:
                # Retain at most the current M1 plus the previous two
                # completed minutes, never an unbounded historical tape.
                # One added print after the M1 boundary must not discard
                # the two completed minutes required for certification.
                latest = next(reversed(pending.values())).timestamp_ms
                cutoff = latest // 60_000 * 60_000 - 120_000
                while self._prints and self._prints[0].timestamp_ms < cutoff:
                    retired = self._prints.popleft()
                    self._ids.pop(retired.trade_id, None)
            for item in pending.values():
                if len(self._prints) == self._capacity:
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
                "buffer_capacity": self._capacity,
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
    capacity = snapshot.get("buffer_capacity", PublicTradeObservation.LIMIT)
    result = rest_response.get("result")
    if (not isinstance(symbol, str) or not symbol.endswith("USDT")
            or not isinstance(observed, tuple)
            or type(capacity) is not int
            or capacity not in (PublicTradeObservation.LIMIT,
                                PublicTradeObservation.CERTIFICATION_LIMIT)
            or len(observed) > capacity
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


@dataclass(frozen=True, slots=True)
class ClosedMinuteTradeParity:
    """Independent OHLC/volume/turnover agreement, not trade-source authority."""

    status: str
    matched_prints: int = 0
    known_at_ms: int | None = None
    source_complete: bool = False
    trading_authorized: bool = False


def audit_closed_m1_trade_parity(
    snapshot: object, kline_response: object, *,
    start_ms: int, observed_at_ms: int,
) -> ClosedMinuteTradeParity:
    """Check one just-closed linear M1 candle against observed taker prints.

    A caller must establish that the REST response came from Bybit under
    trusted TLS. Exact M1 OHLC/base-volume/quote-turnover parity is useful
    corroboration, not a proof of every individual trade ID or guaranteed
    live-feed availability. No caller may grant Scanner/Robot entry authority
    based on this optional, after-close read-only research check.

    Fail closed on partial buffers, invalid frames, mismatched facts or a
    stale/unclosed REST candle. Decimal equality is intentional: if the
    exchange rounds its fields differently, the result stays UNPROVEN.
    """
    unknown = ClosedMinuteTradeParity("UNPROVEN")
    minute_ms = 60_000
    if (type(start_ms) is not int or start_ms < 0
            or start_ms % minute_ms != 0
            or type(observed_at_ms) is not int
            or observed_at_ms < start_ms + minute_ms):
        raise ValueError("closed aligned M1 and causal observation time required")
    if not isinstance(snapshot, dict) or not isinstance(kline_response, dict):
        return unknown
    symbol = snapshot.get("symbol")
    prints = snapshot.get("prints")
    capacity = snapshot.get("buffer_capacity", PublicTradeObservation.LIMIT)
    if (not isinstance(symbol, str) or not symbol.isalnum()
            or not symbol.endswith("USDT")
            or not isinstance(prints, tuple)
            or type(capacity) is not int
            or capacity not in (PublicTradeObservation.LIMIT,
                                PublicTradeObservation.CERTIFICATION_LIMIT)
            or not 0 < len(prints) <= capacity
            or type(snapshot.get("generation")) is not int
            or snapshot["generation"] < 0
            or type(snapshot.get("observed_frames")) is not int
            or snapshot["observed_frames"] <= 0
            or type(snapshot.get("invalid_frames")) is not int
            or snapshot["invalid_frames"] != 0
            or snapshot.get("continuity") != "UNPROVEN"
            or snapshot.get("order_authority") is not False):
        return unknown
    if (type(kline_response.get("retCode")) is not int
            or kline_response["retCode"] != 0):
        return unknown
    server_time_ms = kline_response.get("time")
    end_ms = start_ms + minute_ms
    if (type(server_time_ms) is not int
            or not end_ms <= server_time_ms <= observed_at_ms
            or observed_at_ms - server_time_ms > 30_000):
        return unknown
    result = kline_response.get("result")
    if (not isinstance(result, dict)
            or result.get("category") != "linear"
            or result.get("symbol") != symbol):
        return unknown
    rows = result.get("list")
    if not isinstance(rows, list) or len(rows) != 1:
        return unknown
    row = rows[0]
    if (not isinstance(row, list) or len(row) != 7
            or row[0] != str(start_ms)):
        return unknown
    try:
        if not all(isinstance(value, str) for value in row[1:]):
            return unknown
        open_px, high_px, low_px, close_px, volume, turnover = (
            Decimal(value) for value in row[1:]
        )
    except (InvalidOperation, TypeError, ValueError):
        return unknown
    if (not all(value.is_finite() for value in
                (open_px, high_px, low_px, close_px, volume, turnover))
            or min(open_px, high_px, low_px, close_px, volume, turnover) <= 0
            or not low_px <= min(open_px, close_px) <= high_px
            or not low_px <= max(open_px, close_px) <= high_px):
        return unknown

    selected: list[ObservedPrint] = []
    ids: set[str] = set()
    prior_time, prior_seq = -1, -1
    for item in prints:
        if not isinstance(item, ObservedPrint):
            return unknown
        if not start_ms <= item.timestamp_ms < end_ms:
            continue
        if (not item.trade_id or item.trade_id in ids
                or item.timestamp_ms < prior_time
                or item.sequence < prior_seq
                or not item.price.is_finite() or item.price <= 0
                or not item.quantity.is_finite() or item.quantity <= 0):
            return unknown
        ids.add(item.trade_id)
        prior_time, prior_seq = item.timestamp_ms, item.sequence
        selected.append(item)
    if not selected:
        return unknown
    if (selected[0].price != open_px or selected[-1].price != close_px
            or min(x.price for x in selected) != low_px
            or max(x.price for x in selected) != high_px
            or sum((x.quantity for x in selected), Decimal(0)) != volume
            or sum((x.notional for x in selected), Decimal(0)) != turnover):
        return unknown
    return ClosedMinuteTradeParity(
        status="EXACT_CLOSED_M1_AGGREGATE_PARITY",
        matched_prints=len(selected), known_at_ms=observed_at_ms,
    )


def audit_closed_m1_triple_parity(
    snapshot: object, recent_trade_response: object,
    kline_response: object, *, start_ms: int, observed_at_ms: int,
) -> ClosedMinuteTradeParity:
    """Corroborate a past minute against BOTH REST executions and M1 totals.

    Recent-trade must contain the full bracketed interval; closed M1 must
    exactly match observed OHLC, base volume and quote turnover. The REST
    page must be current after minute close. This verifies a *bounded
    comparison of provided sources*, not continuous source delivery,
    authenticity of untrusted payloads or permission to trade.

    Both endpoints are caller-supplied: this function performs no network
    access, side effects, background polling or Scanner/Robot actions.
    """
    unknown = ClosedMinuteTradeParity("UNPROVEN")
    kline = audit_closed_m1_trade_parity(
        snapshot, kline_response,
        start_ms=start_ms, observed_at_ms=observed_at_ms,
    )
    if kline.status != "EXACT_CLOSED_M1_AGGREGATE_PARITY":
        return unknown
    rest = audit_recent_trade_overlap(
        snapshot, recent_trade_response,
        start_ms=start_ms, end_ms=start_ms + 60_000,
    )
    if (rest.status != "EXACT_OVERLAP_MATCH"
            or rest.matched_count != kline.matched_prints
            or not isinstance(recent_trade_response, dict)):
        return unknown
    rest_server_ms = recent_trade_response.get("time")
    if (type(rest_server_ms) is not int
            or not start_ms + 60_000 <= rest_server_ms <= observed_at_ms
            or observed_at_ms - rest_server_ms > 30_000):
        return unknown
    return ClosedMinuteTradeParity(
        "EXACT_CLOSED_M1_TRIPLE_PARITY",
        matched_prints=kline.matched_prints,
        known_at_ms=observed_at_ms,
    )


@dataclass(frozen=True, slots=True)
class CausalReceiptAudit:
    """Local receipt-time visibility only; NEVER source or order authority."""

    status: str
    observed_prints: int = 0
    latest_received_at_ms: int | None = None
    source_complete: bool = False
    trading_authorized: bool = False


def audit_closed_m1_receipt_cutoff(
    snapshot: object, *, start_ms: int, decision_ms: int,
) -> CausalReceiptAudit:
    """Was each *observed* M1 print locally received by the decision cutoff?

    A print's exchange event time is NOT evidence that the Scanner had it.
    Only a timestamp recorded at the actual WebSocket ingress is usable here.
    This audit cannot identify unobserved missing executions, prove external
    clock synchronization, or retroactively make REST/kline data available.
    A timely result is not FlowWindow eligibility or an entry signal.
    """
    result = CausalReceiptAudit("UNPROVEN")
    if (type(start_ms) is not int or start_ms < 0 or start_ms % 60_000
            or type(decision_ms) is not int or decision_ms < start_ms + 60_000):
        raise ValueError("aligned closed M1 and non-future decision cutoff required")
    if not isinstance(snapshot, dict):
        return result
    prints = snapshot.get("prints")
    if (not isinstance(prints, tuple)
            or not isinstance(snapshot.get("symbol"), str)
            or type(snapshot.get("generation")) is not int
            or snapshot["generation"] < 0
            or type(snapshot.get("invalid_frames")) is not int
            or snapshot["invalid_frames"] != 0
            or snapshot.get("continuity") != "UNPROVEN"
            or snapshot.get("order_authority") is not False):
        return result
    selected: list[ObservedPrint] = []
    seen: set[str] = set()
    end_ms = start_ms + 60_000
    for item in prints:
        if not isinstance(item, ObservedPrint):
            return result
        if start_ms <= item.timestamp_ms < end_ms:
            if (item.trade_id in seen or not isinstance(item.received_at_ms, int)
                    or type(item.received_at_ms) is not int or item.received_at_ms < 0):
                return result
            seen.add(item.trade_id)
            selected.append(item)
    if not selected:
        return result
    latest = max(item.received_at_ms for item in selected)
    # Late trades are evidence AGAINST causality, not automatically repaired
    # by a future archive/REST parity. No synthetic on-time timestamp.
    return CausalReceiptAudit(
        status=("LATE_OBSERVED_PRINT" if latest > decision_ms
                else "TIMELY_OBSERVED_ONLY"),
        observed_prints=len(selected), latest_received_at_ms=latest,
    )
