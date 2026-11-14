"""Owner-selected LOCAL Bybit public trade archive -> chart-only M1 and 15s.

No remote fetching, trading, PAPER, cached state, synthetic OHLC or fill
matching. Accept only a single UTC day of original .csv.gz (or a ZIP
containing its exact-named gzip member). Parse all prints with bounded
streaming memory; retain only the requested short visual window.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import csv
import gzip
import hashlib
from pathlib import Path
import re
import zipfile

from research.simulator_v2.trade_archive import NEEDED_COLUMNS, MAX_RECORDS

MAX_ARCHIVE_BYTES = 128_000_000
MAX_FINE_WINDOW_MS = 6 * 3_600_000
PINNED_ICNT_TRADE_SHA = "47f3d3ea153374fe759adc81d2b340f5557d0fef84e90d28862d1a1239b0718a"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}USDT$")
DAY_MS = 86_400_000


def _read_archive(path: Path, filename: str):
    if filename.endswith(".csv.gz"):
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    if filename.endswith(".zip"):
        name = filename[:-4]  # Label is not used as an archive member path.
        del name
        raise ValueError("ZIP requires explicit member inspection")
    raise ValueError("Expected a Bybit .csv.gz or .zip archive")


def aggregate_owner_trade_bars(
    path: Path, *, filename: str, symbol: str, start_ms: int, end_ms: int,
) -> dict[str, object]:
    if not SYMBOL_RE.fullmatch(symbol) or not (
        type(start_ms) is int and type(end_ms) is int
    ) or start_ms < 0 or end_ms <= start_ms or end_ms - start_ms > MAX_FINE_WINDOW_MS:
        raise ValueError("Selected fine chart requires a bounded 1..360 minute UTC window")
    if start_ms % 15_000 or end_ms % 15_000:
        raise ValueError("Fine-chart bounds must align to 15 seconds")
    day_ms = start_ms // DAY_MS * DAY_MS
    if end_ms > day_ms + DAY_MS or end_ms > int(datetime.now(timezone.utc).timestamp() * 1000):
        raise ValueError("Fine chart cannot cross UTC day or include future trades")
    if (not path.is_file() or path.is_symlink()
            or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES):
        raise ValueError("Invalid or oversized original owner archive")
    date = datetime.fromtimestamp(day_ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    member = f"{symbol}{date}.csv.gz"
    if filename not in (member, f"{symbol}_{date}_sources.zip", f"{symbol}{date}.zip"):
        raise ValueError("Archive name does not match the selected symbol and UTC day")
    raw_hash = hashlib.sha256()
    values: dict[int, dict[str, object]] = {}
    rows = 0

    def scan(stream) -> None:
        nonlocal rows
        with stream:
            reader = csv.DictReader(stream)
            if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                    or not NEEDED_COLUMNS.issubset(reader.fieldnames)):
                raise ValueError("Unsupported Bybit public trade columns")
            for line in reader:
                rows += 1
                if rows > MAX_RECORDS:
                    raise ValueError("Public trades exceeded the safe row bound")
                if line.get("symbol") != symbol or any(
                    line.get(key) is None for key in NEEDED_COLUMNS
                ) or not line["trdMatchID"]:
                    raise ValueError("Foreign/malformed public trade row")
                try:
                    stamp = Decimal(line["timestamp"])
                    price = Decimal(line["price"])
                    quantity = Decimal(line["size"])
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError("Malformed public trade number") from exc
                if (not stamp.is_finite() or not price.is_finite()
                        or not quantity.is_finite()
                        or stamp < 0 or price <= 0 or quantity <= 0):
                    raise ValueError("Non-finite or nonpositive public trade")
                ms = int((stamp * 1000).to_integral_value(rounding=ROUND_FLOOR))
                if not day_ms <= ms < day_ms + DAY_MS:
                    raise ValueError("Foreign UTC day in public trade archive")
                if not start_ms <= ms < end_ms:
                    continue
                bucket = ms // 15_000 * 15_000
                key = (stamp, line["trdMatchID"])
                current = values.get(bucket)
                if current is None:
                    values[bucket] = {
                        "first": key, "last": key,
                        "open": price, "high": price, "low": price,
                        "close": price, "volume": quantity,
                    }
                    continue
                if key < current["first"]:
                    current["first"], current["open"] = key, price
                if key > current["last"]:
                    current["last"], current["close"] = key, price
                current["high"] = max(current["high"], price)
                current["low"] = min(current["low"], price)
                current["volume"] += quantity

    if filename == member:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1_048_576), b""):
                raw_hash.update(chunk)
        scan(gzip.open(path, "rt", encoding="utf-8-sig", newline=""))
    else:
        with zipfile.ZipFile(path) as archive:
            matching = [info for info in archive.infolist() if info.filename == member]
            if len(matching) != 1 or not 0 < matching[0].file_size <= MAX_ARCHIVE_BYTES:
                raise ValueError("Expected one bounded original public trade gzip in ZIP")
            with archive.open(matching[0]) as compressed:
                # Hash the actual compressed CSV.gz member, not its ZIP wrapper.
                import tempfile
                with tempfile.TemporaryFile() as copy:
                    received = 0
                    for chunk in iter(lambda: compressed.read(1_048_576), b""):
                        received += len(chunk)
                        if received > MAX_ARCHIVE_BYTES:
                            raise ValueError("Oversized trade ZIP member")
                        raw_hash.update(chunk)
                        copy.write(chunk)
                    copy.seek(0)
                    import io
                    scan(io.TextIOWrapper(gzip.GzipFile(fileobj=copy),
                        encoding="utf-8-sig", newline=""))
    if not rows:
        raise ValueError("Empty public trade archive")
    def chartbar(at: int, interval: int, item: dict) -> dict:
        return {"start_ms": at, "end_ms": at + interval,
            **{k: float(item[k]) for k in ("open","high","low","close","volume")}}
    s15 = [chartbar(at, 15_000, values[at]) for at in sorted(values)]
    m1 = []
    if start_ms % 60_000 or end_ms % 60_000:
        raise ValueError("M1 requires minute-aligned selected bounds")
    for minute in range(start_ms, end_ms, 60_000):
        quarter = [values[at] for at in range(minute, minute+60_000, 15_000)
                   if at in values]
        if not quarter:
            continue  # No prints: NO invented zero-volume M1.
        first = quarter[0]
        last = quarter[-1]
        m1.append({"start_ms": minute, "end_ms": minute+60_000,
            "open": float(first["open"]), "high": float(max(q["high"] for q in quarter)),
            "low": float(min(q["low"] for q in quarter)),
            "close": float(last["close"]),
            "volume": float(sum((q["volume"] for q in quarter), Decimal(0)))})
    digest = raw_hash.hexdigest()
    return {
        "source": "BYBIT_PUBLIC_TRADES_DERIVED_OHLC_LOCAL_ARCHIVE",
        "symbol": symbol, "start_ms": start_ms, "end_ms": end_ms,
        "raw_trade_sha256": digest,
        "pinned_original_icnt": symbol == "ICNTUSDT" and date == "2026-11-10"
            and digest == PINNED_ICNT_TRADE_SHA,
        "trades_scanned": rows, "m1": m1, "s15": s15,
        "missing_m1": (end_ms-start_ms)//60_000 - len(m1),
        "missing_15s": (end_ms-start_ms)//15_000 - len(s15),
        "l2_executions_unchanged": True,
    }
