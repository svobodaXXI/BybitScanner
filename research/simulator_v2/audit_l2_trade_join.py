"""Pinned, offline cross-channel timing audit for original Bybit L2 + trades.

Determines timestamp ties and as-of-book age. It cannot establish trade/book
venue ordering at equal timestamps, prove execution queue, or simulate P&L.
Inputs are read-only and streamed; at most one day's timestamps stay in RAM.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import Counter
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import csv
import gzip
import hashlib
import json
from pathlib import Path
from typing import BinaryIO, Iterator
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED, ZIP_STORED
import argparse

# Standalone and offline: can be fetched as one immutable Python file to a PC.
DAY_BEGIN_MS = 1794268800000
DAY_END_MS = 1794355200000
SYMBOL = "ICNTUSDT"
DEPTH = 200

L2_MAX_BYTES = 512_000_000
TRADES_MAX_BYTES = 150_000_000
MAX_UNPACKED = 8_000_000_000
MAX_RECORD_BYTES = 1_000_000
MAX_L2_EVENTS = 8_000_000
MAX_TRADES = 2_000_000


def _pin_sha(path: Path, expected: str, max_bytes: int) -> None:
    if (not isinstance(path, Path) or path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= max_bytes):
        raise ValueError("missing, linked or oversized source archive")
    if not isinstance(expected, str) or len(expected) != 64 or any(
        c not in "0123456789abcdef" for c in expected
    ):
        raise ValueError("explicit lowercase source SHA-256 required")
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1_048_576), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ValueError("source SHA-256 mismatch")


@contextmanager
def _zip_member(path: Path, *, extension: str) -> Iterator[BinaryIO]:
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise ValueError("source ZIP must have one original member")
            item = members[0]
            if (item.is_dir() or item.filename != Path(item.filename).name
                    or "\\" in item.filename or not item.filename.endswith(extension)
                    or item.flag_bits & 1 or item.compress_type not in
                    (ZIP_DEFLATED, ZIP_STORED)
                    or not 0 < item.file_size <= MAX_UNPACKED):
                raise ValueError("unsafe original source ZIP member")
            with archive.open(item) as handle:
                yield handle
    except BadZipFile as exc:
        raise ValueError("source ZIP invalid or CRC mismatch") from exc


@contextmanager
def _original_trades(path: Path, sha256: str) -> Iterator[BinaryIO]:
    """Pin original compressed ICNT tape, including inside the 3-member bundle."""
    if path.name.endswith(".csv.gz"):
        _pin_sha(path, sha256, TRADES_MAX_BYTES)
        with path.open("rb") as raw:
            yield raw
        return
    if path.suffix != ".zip" or path.is_symlink() or not path.is_file():
        raise ValueError("original .csv.gz or source ZIP required")
    if not 0 < path.stat().st_size <= TRADES_MAX_BYTES:
        raise ValueError("original source ZIP size invalid")
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if (not 1 <= len(members) <= 5
                    or any(m.is_dir() or m.filename != Path(m.filename).name
                           or "\\" in m.filename or m.flag_bits & 1
                           or m.compress_type not in (ZIP_DEFLATED, ZIP_STORED)
                           for m in members)):
                raise ValueError("unsafe public-trade source ZIP")
            item = next(
                (m for m in members if m.filename == "ICNTUSDT2026-11-10.csv.gz"),
                None,
            )
            if item is None or not 0 < item.file_size <= TRADES_MAX_BYTES:
                raise ValueError("original ICNT compressed trade member missing")
            digest = hashlib.sha256()
            with archive.open(item) as verify:
                for block in iter(lambda: verify.read(1_048_576), b""):
                    digest.update(block)
            if digest.hexdigest() != sha256:
                raise ValueError("original inner trade gzip SHA-256 mismatch")
            with archive.open(item) as raw:
                yield raw
    except BadZipFile as exc:
        raise ValueError("invalid source bundle ZIP/CRC") from exc


def _trade_timestamps(path: Path, sha256: str) -> tuple[Counter[int], int]:
    """Read exact original compressed public trades, no extraction."""
    counts: Counter[int] = Counter()
    unique_ids: set[str] = set()
    with _original_trades(path, sha256) as raw, gzip.GzipFile(fileobj=raw) as compressed:
        from io import TextIOWrapper
        with TextIOWrapper(compressed, encoding="utf-8-sig", newline="") as reader:
            trades = csv.DictReader(reader)
            required = {"timestamp", "trdMatchID", "symbol", "side", "price", "size"}
            if (not trades.fieldnames or not required.issubset(trades.fieldnames)
                    or len(trades.fieldnames) != len(set(trades.fieldnames))):
                raise ValueError("original Bybit public trade fields missing")
            for row in trades:
                if len(unique_ids) >= MAX_TRADES:
                    raise ValueError("public trade record budget exceeded")
                trade_id = row["trdMatchID"]
                if (not trade_id or trade_id in unique_ids or row["symbol"] != SYMBOL
                        or row["side"] not in ("Buy", "Sell")):
                    raise ValueError("foreign, duplicate or malformed original trade")
                unique_ids.add(trade_id)
                try:
                    timestamp = Decimal(str(row["timestamp"]))
                    price = Decimal(str(row["price"]))
                    size = Decimal(str(row["size"]))
                except (InvalidOperation, ValueError, TypeError) as exc:
                    raise ValueError("malformed original trade fields") from exc
                if (not timestamp.is_finite() or not price.is_finite()
                        or not size.is_finite() or price <= 0 or size <= 0):
                    raise ValueError("invalid original public trade")
                ms = int((timestamp * 1000).to_integral_value(rounding=ROUND_FLOOR))
                if not DAY_BEGIN_MS <= ms < DAY_END_MS:
                    raise ValueError("foreign UTC trade date")
                counts[ms] += 1
    return counts, len(unique_ids)


def _book_times(path: Path) -> tuple[Counter[int], Counter[int], int]:
    available: Counter[int] = Counter()
    engine: Counter[int] = Counter()
    count = 0
    last_ts = None
    with _zip_member(path, extension=".data") as raw:
        while True:
            line = raw.readline(MAX_RECORD_BYTES + 1)
            if not line:
                break
            count += 1
            if count > MAX_L2_EVENTS or len(line) > MAX_RECORD_BYTES:
                raise ValueError("L2 line/record budget exceeded")
            try:
                event = json.loads(line)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError("invalid original L2 JSONL") from exc
            if (not isinstance(event, dict)
                    or event.get("topic") != f"orderbook.{DEPTH}.{SYMBOL}"
                    or event.get("type") not in ("snapshot", "delta")
                    or not isinstance(event.get("data"), dict)
                    or event["data"].get("s") != SYMBOL):
                raise ValueError("invalid original L2 message identity")
            ts, cts = event.get("ts"), event.get("cts")
            if (type(ts) is not int or type(cts) is not int
                    or cts > ts or ts < DAY_BEGIN_MS
                    or ts >= DAY_END_MS + 5000):
                raise ValueError("invalid historical book clock")
            if last_ts is not None and ts < last_ts:
                raise ValueError("L2 archive reversed its availability timestamps")
            last_ts = ts
            available[ts] += 1
            engine[cts] += 1
    return available, engine, count


def _collisions(a: Counter[int], b: Counter[int]) -> dict[str, object]:
    shared = sorted(a.keys() & b.keys())
    return {
        "millisecond_buckets": len(shared),
        "trade_prints_in_shared_buckets": sum(a[t] for t in shared),
        "book_messages_in_shared_buckets": sum(b[t] for t in shared),
        "first_12_shared_ms": shared[:12],
    }


def _book_ages(trades: Counter[int], book_ts: Counter[int]) -> dict[str, object]:
    sorted_book = sorted(book_ts)
    without_prior = older_than_250 = older_than_1000 = count = 0
    age_samples: list[dict[str, int]] = []
    for t, quantity in trades.items():
        index = bisect_right(sorted_book, t) - 1
        if index < 0:
            without_prior += quantity
            continue
        age = t - sorted_book[index]
        count += quantity
        if age > 250:
            older_than_250 += quantity
        if age > 1000:
            older_than_1000 += quantity
            if len(age_samples) < 10:
                age_samples.append({"trade_ms": t, "book_age_ms": age})
    return {
        "trades_before_first_book": without_prior,
        "trades_with_preceding_book": count,
        "trades_book_older_than_250ms": older_than_250,
        "trades_book_older_than_1000ms": older_than_1000,
        "age_over_1s_samples": sorted(age_samples, key=lambda d: d["trade_ms"]),
    }


def inspect(
    *, l2_zip: Path, l2_sha256: str,
    trade_source: Path, trade_sha256: str,
    expected_books: int = 569169, expected_trades: int = 152429,
) -> dict[str, object]:
    _pin_sha(l2_zip, l2_sha256, L2_MAX_BYTES)
    trades, trade_count = _trade_timestamps(trade_source, trade_sha256)
    books, engine, book_count = _book_times(l2_zip)
    if trade_count != expected_trades or book_count != expected_books:
        raise ValueError("original market record count differs from pinned sources")
    actual = _collisions(trades, books)
    return {
        "schema": "BYBIT_L2_TAKER_CROSS_CHANNEL_AUDIT_V1",
        "symbol": SYMBOL, "utc_day": "2026-11-10",
        "l2_sha256": l2_sha256, "trade_source_sha256": trade_sha256,
        "l2_messages": book_count, "public_trades": trade_count,
        "l2_distinct_available_ms": len(books),
        "trade_distinct_ms": len(trades),
        "same_ms_trade_vs_book_ts": actual,
        "same_ms_trade_vs_book_cts": _collisions(trades, engine),
        "book_asof_trade_ts": _book_ages(trades, books),
        "same_ms_cross_channel_order": (
            "UNPROVEN_WHEN_COINCIDENT" if actual["millisecond_buckets"]
            else "NO_EQUAL_TIMESTAMP_DETECTED"
        ),
        "capture_completeness": "UNPROVEN_FROM_ARCHIVES_ALONE",
        "virtual_fills": "NOT_EXECUTED",
        "virtual_pnl": "NOT_COMPUTED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--l2", type=Path, required=True)
    parser.add_argument("--l2-sha", required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--trade-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(
        l2_zip=args.l2, l2_sha256=args.l2_sha,
        trade_source=args.trades, trade_sha256=args.trade_sha,
    )
    if args.out.exists():
        raise ValueError("refusing overwrite of existing cross-channel report")
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("CROSS_CHANNEL_AUDIT=" + str(args.out))
    print("EQUAL_TS_BUCKETS=" + str(report["same_ms_trade_vs_book_ts"]["millisecond_buckets"]))
    print("FILLS=NOT_EXECUTED")


if __name__ == "__main__":
    main()
