"""Local-only Bybit L2 snapshot/delta replay. No OHLC fills or network access.

The input must be an original, immutable orderbook stream. Public trade archives
are NOT book evidence. A SHA-256 proves file identity, not capture completeness,
queue position, or cross-channel trade/book ordering.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import BinaryIO, Iterator
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED, ZIP_STORED


MAX_SOURCE_BYTES = 512_000_000
MAX_EVENT_BYTES = 1_000_000
MAX_EVENTS = 8_000_000
MAX_UNCOMPRESSED_BYTES = 8_000_000_000


@dataclass(frozen=True, slots=True)
class BookState:
    """A completed, causal L2 message, not evidence of an individual order."""

    symbol: str
    available_at_ms: int
    engine_at_ms: int
    update_id: int
    sequence: int
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]

    @property
    def best_bid(self) -> tuple[Decimal, Decimal]:
        return self.bids[0]

    @property
    def best_ask(self) -> tuple[Decimal, Decimal]:
        return self.asks[0]


def _positive_decimal(value: object, *, allow_zero: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("Bybit L2 price/size must be original decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("malformed Bybit L2 number") from exc
    if not number.is_finite() or number < 0 or (number == 0 and not allow_zero):
        raise ValueError("invalid Bybit L2 price/size")
    return number


class HistoricalBybitOrderBook:
    """One-symbol top-N book, strictly advanced by complete original WS messages.

    Depth 50/200/1000 only: Bybit depth-1 snapshots cannot reconstruct L2.
    The standard WS update ID is monotone, but unlike the full-depth feed,
    consecutive IDs are not assumed; gaps in source recording still need
    independent provenance and must never be silently called verified.
    """

    def __init__(self, *, symbol: str, depth: int = 50) -> None:
        if not isinstance(symbol, str) or not symbol.isalnum() or not symbol.endswith("USDT"):
            raise ValueError("invalid historical book symbol")
        if type(depth) is not int or depth not in (50, 200, 1000):
            raise ValueError("Bybit historical L2 requires depth 50, 200 or 1000")
        self.symbol = symbol
        self.depth = depth
        self._bids: dict[Decimal, Decimal] = {}
        self._asks: dict[Decimal, Decimal] = {}
        self._last_u: int | None = None
        self._last_seq: int | None = None
        self._last_at: int | None = None

    def apply(self, message: object) -> BookState:
        if not isinstance(message, dict) or message.get("topic") != (
            f"orderbook.{self.depth}.{self.symbol}"
        ) or message.get("type") not in ("snapshot", "delta"):
            raise ValueError("wrong Bybit L2 topic or message type")
        data = message.get("data")
        if not isinstance(data, dict) or data.get("s") != self.symbol:
            raise ValueError("foreign or invalid Bybit L2 payload")
        available = message.get("ts")
        engine = message.get("cts")
        u, seq = data.get("u"), data.get("seq")
        if (type(available) is not int or type(engine) is not int
                or type(u) is not int or type(seq) is not int
                or not 0 <= engine <= available or u < 1 or seq < 1):
            raise ValueError("Bybit L2 timestamps/sequence invalid")
        if self._last_at is not None and available < self._last_at:
            raise ValueError("Bybit L2 event time went backward")
        snapshot = message["type"] == "snapshot"
        if not snapshot and self._last_u is None:
            raise ValueError("L2 delta without initial snapshot")
        if not snapshot and (u <= self._last_u or seq <= self._last_seq):
            raise ValueError("L2 delta reversed, repeated or reset without snapshot")
        if not snapshot and u != self._last_u + 1:
            raise ValueError("L2 delta update ID gap; historical book state unproven")
        if snapshot and self._last_seq is not None and seq < self._last_seq and u != 1:
            raise ValueError("L2 snapshot reversed without declared exchange reset")
        bids = {} if snapshot else self._bids.copy()
        asks = {} if snapshot else self._asks.copy()
        for side, target in (("b", bids), ("a", asks)):
            rows = data.get(side)
            if not isinstance(rows, list):
                raise ValueError("missing Bybit L2 side")
            seen: set[Decimal] = set()
            for row in rows:
                if not isinstance(row, list) or len(row) != 2:
                    raise ValueError("invalid Bybit L2 price level")
                price = _positive_decimal(row[0])
                size = _positive_decimal(row[1], allow_zero=True)
                if price in seen:
                    raise ValueError("duplicate price in one Bybit L2 update")
                seen.add(price)
                if size == 0:
                    target.pop(price, None)
                else:
                    target[price] = size
        if (not bids or not asks or len(bids) > 10_000 or len(asks) > 10_000
                or max(bids) >= min(asks)):
            raise ValueError("empty, oversized or crossed Bybit L2 book")
        # Atomic publication: a malformed message must not advance either side.
        self._bids, self._asks = bids, asks
        self._last_u, self._last_seq, self._last_at = u, seq, available
        return BookState(
            symbol=self.symbol, available_at_ms=available, engine_at_ms=engine,
            update_id=u, sequence=seq,
            bids=tuple(sorted(bids.items(), reverse=True)),
            asks=tuple(sorted(asks.items())),
        )


@contextmanager
def _original_orderbook_lines(path: Path) -> Iterator[BinaryIO]:
    """Read Bybit's single-member .data.zip directly, bounded and CRC-tested.

    The archive is not extracted on disk or expanded into RAM. A complete
    first scan verifies the *entire* member CRC, including events after a
    selected short replay window; the second scan streams source JSONL.
    """
    if path.suffix != ".zip":
        with path.open("rb") as handle:
            yield handle
        return
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ValueError("historical L2 ZIP must contain exactly one .data file")
            member = members[0]
            name = member.filename
            if (member.is_dir() or not name.endswith(".data")
                    or name != Path(name).name or "\\" in name
                    or member.flag_bits & 1
                    or member.compress_type not in (ZIP_DEFLATED, ZIP_STORED)
                    or not 0 < member.file_size <= MAX_UNCOMPRESSED_BYTES):
                raise ValueError("unsafe or unsupported historical L2 ZIP member")
            with archive.open(member) as verify:
                while verify.read(1024 * 1024):
                    pass  # ZipExtFile raises BadZipFile on a CRC mismatch.
            with archive.open(member) as handle:
                yield handle
    except BadZipFile as exc:
        raise ValueError("corrupt historical L2 ZIP or CRC mismatch") from exc


def iter_pinned_orderbook(
    path: Path, *, symbol: str, depth: int, sha256: str,
    start_ms: int, end_exclusive_ms: int,
) -> Iterator[BookState]:
    """Stream immutable original Bybit WS JSONL or single-member .data.zip.

    Messages before start_ms warm the book. A snapshot after the requested
    start is not sufficient to backfill earlier decisions. File identity is
    pinned; capture gap attestations must be established by the caller.
    """
    if (not isinstance(path, Path) or path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_SOURCE_BYTES):
        raise ValueError("missing, linked or oversized historical L2 archive")
    if (not isinstance(sha256, str) or len(sha256) != 64
            or any(c not in "0123456789abcdef" for c in sha256)):
        raise ValueError("explicit L2 SHA-256 required")
    if (type(start_ms) is not int or type(end_exclusive_ms) is not int
            or not 0 <= start_ms < end_exclusive_ms):
        raise ValueError("invalid historical L2 range")
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    if hasher.hexdigest() != sha256:
        raise ValueError("historical L2 archive SHA mismatch")
    book = HistoricalBybitOrderBook(symbol=symbol, depth=depth)
    initialized_at_or_before_start = False
    total = 0
    with _original_orderbook_lines(path) as handle:
        for line in handle:
            total += 1
            if total > MAX_EVENTS or len(line) > MAX_EVENT_BYTES:
                raise ValueError("historical L2 event budget exceeded")
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid historical L2 JSONL event") from exc
            state = book.apply(event)
            if state.available_at_ms <= start_ms:
                initialized_at_or_before_start = True
                if state.available_at_ms < start_ms:
                    continue
            if not initialized_at_or_before_start:
                raise ValueError("historical L2 has no at-or-before-window snapshot/book state")
            if state.available_at_ms >= end_exclusive_ms:
                break
            yield state
