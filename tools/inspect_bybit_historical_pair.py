"""Offline-only Bybit historical trade/L2 archive pair inspection.

Input is a *locally obtained* UTC-day CSV.gz and orderbook .data.zip.
No network, database, Robot, WebSocket or order action. This scanner checks
format/visible temporal overlap, NOT live receipt-time provenance, exact
feed completeness, fill attribution, or a profitable reversal.

The archives are sourced from public.bybit.com/trading and
quote-saver.bycsi.com/orderbook/linear. A Bybit book delta of size zero
means filled OR cancelled; it is NOT a proven aggressive execution.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import gzip
import io
import json
from pathlib import Path
from zipfile import ZipFile, BadZipFile

UTC = timezone.utc
MAX_ARCHIVE_RECORDS = 2_000_000


class ArchiveEvidenceError(ValueError):
    """No historical evidence should be promoted on a bad or partial scan."""


def _timestamp_ms(value: object) -> int:
    """CSV times can be seconds/fractional seconds; WS/L2 timestamps are ms."""
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ArchiveEvidenceError("invalid timestamp") from exc
    if not n.is_finite() or n <= 0:
        raise ArchiveEvidenceError("invalid timestamp")
    value_ms = n * 1000 if n < 100_000_000_000 else n
    if value_ms != value_ms.to_integral_value():
        raise ArchiveEvidenceError("sub-millisecond timestamp")
    return int(value_ms)


def _positive(value: object, *, allow_zero: bool = False) -> Decimal:
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ArchiveEvidenceError("invalid price or quantity") from exc
    if not n.is_finite() or n < 0 or (n == 0 and not allow_zero):
        raise ArchiveEvidenceError("invalid price or quantity")
    return n


@dataclass(frozen=True)
class ArchivePairInspection:
    symbol: str
    day: str
    window_start_ms: int
    window_end_ms: int
    trade_rows: int
    orderbook_rows: int
    trades_in_window: int
    book_events_in_window: int
    snapshots_seen_before_window_end: int
    book_delete_updates_in_window: int
    scan_complete: bool
    # The old archive is useful for offline study, but cannot prove what a
    # live Robot received at decision time; never enable a trade with this.
    historical_archive_only: bool = True
    exchange_receipt_time_proven: bool = False
    orderbook_execution_attribution_proven: bool = False
    source_complete_for_live_entry: bool = False
    trading_authorized: bool = False


def inspect_archive_pair(
    symbol: str, day: str, trades_path: Path, book_path: Path,
    *, start_ms: int, end_ms: int, max_records: int = MAX_ARCHIVE_RECORDS,
) -> ArchivePairInspection:
    if (not isinstance(symbol, str) or not symbol.isalnum()
            or symbol.upper() != symbol or not symbol.endswith("USDT")
            or not isinstance(day, str) or type(max_records) is not int
            or not 1 <= max_records <= MAX_ARCHIVE_RECORDS):
        raise ArchiveEvidenceError("invalid instrument or scan limit")
    try:
        parsed_day = date.fromisoformat(day)
    except ValueError as exc:
        raise ArchiveEvidenceError("invalid UTC date") from exc
    if parsed_day.isoformat() != day:
        raise ArchiveEvidenceError("noncanonical UTC date")
    day_start = int(datetime(parsed_day.year, parsed_day.month, parsed_day.day,
                             tzinfo=UTC).timestamp() * 1000)
    day_end = day_start + 86_400_000
    if (type(start_ms) is not int or type(end_ms) is not int
            or not day_start <= start_ms < end_ms <= day_end
            or end_ms - start_ms > 3_600_000):
        raise ArchiveEvidenceError("window must lie within one UTC day and <= 1h")
    trades_path, book_path = Path(trades_path), Path(book_path)
    if (trades_path.name != f"{symbol}{day}.csv.gz"
            or book_path.name != f"{day}_{symbol}_ob200.data.zip"):
        raise ArchiveEvidenceError("expected matching daily Bybit trade and 200-level book archives")

    seen_ids: set[str] = set()
    trades_total = 0
    trades_in = 0
    try:
        with gzip.open(trades_path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"timestamp", "symbol", "side", "price", "size", "trdMatchID"}
            if not required.issubset(reader.fieldnames or []):
                raise ArchiveEvidenceError("missing public-trade archive columns")
            for row in reader:
                trades_total += 1
                if trades_total > max_records:
                    raise ArchiveEvidenceError("trade archive scan limit reached")
                stamp = _timestamp_ms(row["timestamp"])
                if (not day_start <= stamp < day_end or row["symbol"] != symbol
                        or row["side"].capitalize() not in ("Buy", "Sell")
                        or not row["trdMatchID"]):
                    raise ArchiveEvidenceError("foreign or malformed public trade")
                _positive(row["price"])
                _positive(row["size"])
                if start_ms <= stamp < end_ms:
                    if row["trdMatchID"] in seen_ids:
                        raise ArchiveEvidenceError("duplicate in-window public trade ID")
                    seen_ids.add(row["trdMatchID"])
                    trades_in += 1
    except (OSError, UnicodeError, csv.Error, EOFError) as exc:
        raise ArchiveEvidenceError("corrupt or unreadable public-trade gzip") from exc

    book_total = book_in = snapshots = deletes = 0
    last_seq = -1
    have_snapshot = False
    try:
        with ZipFile(book_path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if (len(members) != 1 or not members[0].filename.endswith(".data")
                    or members[0].file_size > 6_000_000_000):
                raise ArchiveEvidenceError("book ZIP must contain one bounded .data JSONL file")
            with archive.open(members[0], "r") as raw, io.TextIOWrapper(
                raw, encoding="utf-8"
            ) as handle:
                for line in handle:
                    book_total += 1
                    if book_total > max_records:
                        raise ArchiveEvidenceError("orderbook archive scan limit reached")
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError) as exc:
                        raise ArchiveEvidenceError("invalid orderbook JSONL") from exc
                    if not isinstance(event, dict) or not isinstance(event.get("data"), dict):
                        raise ArchiveEvidenceError("unsupported orderbook archive layout")
                    data = event["data"]
                    if (event.get("topic") != f"orderbook.200.{symbol}"
                            or data.get("s") != symbol
                            or event.get("type") not in ("snapshot", "delta")):
                        raise ArchiveEvidenceError("foreign orderbook topic/symbol/type")
                    stamp = _timestamp_ms(event.get("cts", event.get("ts")))
                    if not day_start <= stamp < day_end:
                        raise ArchiveEvidenceError("foreign orderbook event date")
                    seq, update = data.get("seq"), data.get("u")
                    if (type(seq) is not int or type(update) is not int
                            or seq < 0 or update < 0):
                        raise ArchiveEvidenceError("invalid book seq/update ID")
                    # Bybit u=1 means service-restart resnapshot even when
                    # the envelope says delta. A pre-restart sequence must
                    # never be compared to the new orderbook generation.
                    if event["type"] == "snapshot" or update == 1:
                        have_snapshot = True
                        last_seq = seq
                        if stamp < end_ms:
                            snapshots += 1
                    elif not have_snapshot or seq < last_seq:
                        raise ArchiveEvidenceError("book delta lacks ordered snapshot lineage")
                    else:
                        last_seq = seq
                    for side in ("b", "a"):
                        levels = data.get(side)
                        if not isinstance(levels, list):
                            raise ArchiveEvidenceError("missing book side")
                        for level in levels:
                            if (not isinstance(level, list) or len(level) != 2):
                                raise ArchiveEvidenceError("malformed book price level")
                            _positive(level[0])
                            size = _positive(level[1], allow_zero=True)
                            if start_ms <= stamp < end_ms and size == 0:
                                deletes += 1  # cancellation OR execution; never infer which
                    if start_ms <= stamp < end_ms:
                        book_in += 1
    except (OSError, UnicodeError, BadZipFile, EOFError) as exc:
        raise ArchiveEvidenceError("corrupt or unreadable orderbook ZIP") from exc
    return ArchivePairInspection(
        symbol, day, start_ms, end_ms, trades_total, book_total,
        trades_in, book_in, snapshots, deletes, scan_complete=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--trades", type=Path, required=True)
    parser.add_argument("--orderbook", type=Path, required=True)
    parser.add_argument("--start-ms", type=int, required=True)
    parser.add_argument("--end-ms", type=int, required=True)
    parser.add_argument("--max-records", type=int, default=MAX_ARCHIVE_RECORDS)
    args = parser.parse_args()
    try:
        result = inspect_archive_pair(
            args.symbol, args.day, args.trades, args.orderbook,
            start_ms=args.start_ms, end_ms=args.end_ms,
            max_records=args.max_records,
        )
    except ArchiveEvidenceError as exc:
        print(json.dumps({
            "result": "DATA_BLOCKED", "reason": str(exc),
            "trading_authorized": False,
        }))
        return 2
    print(json.dumps({"result": "HISTORICAL_PAIR_INSPECTED", **asdict(result)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
