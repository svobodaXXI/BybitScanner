"""Bounded, checksum-pinned public Bybit trade tape for read-only Robot flow replay.

Optional input for the existing SIMULATION Wedge run. Does not infer trade
aggressor side from candles and never downloads or changes the raw archive.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
from pathlib import Path

from robot_entry_flow_evidence import TakerPrint, normalize_bybit_taker_print
from research.simulator_v2.history import MINUTE_MS
from research.simulator_v2.trade_archive import MAX_ARCHIVE_BYTES, MAX_RECORDS
from research.simulator_v2.trade_range import TradeDayProof, _ordered_proofs

MAX_FOCUSED_PRINTS = 200_000
DAY_MS = 1440 * MINUTE_MS


def pinned_taker_minutes(
    *, archive_dir: Path, symbol: str, proofs: tuple[TradeDayProof, ...],
    start_ms: int, end_ms: int, latest_closed_boundary_ms: int,
) -> dict[int, tuple[TakerPrint, ...]]:
    """Load only selected completed M1 intervals, with a strict memory budget.

    The caller must provide the exact raw compressed files matching the
    immutable, already verified M1 manifest. Whole-day raw checksums are
    checked before any replay evidence is returned. Archives can be in
    reverse chronological order; sort by (timestamp, trade_id) only inside
    each minute. Timestamp ties are not proof of exchange execution order.
    """
    _, proof_start_ms, proof_end_ms = _ordered_proofs(
        proofs, symbol=symbol,
        latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if (type(start_ms) is not int or type(end_ms) is not int
            or start_ms < proof_start_ms or not start_ms < end_ms <= proof_end_ms
            or start_ms % MINUTE_MS or end_ms % MINUTE_MS):
        raise ValueError("focused trade window must be completed pinned M1")
    if (not isinstance(archive_dir, Path) or archive_dir.is_symlink()
            or not archive_dir.is_dir()):
        raise ValueError("explicit safe local trade archive directory required")

    # Preflight all required selected days. Never replay on a partial or
    # different source; only the selected days are read.
    sources: list[Path] = []
    for i, proof in enumerate(proofs):
        day_start_ms = proof_start_ms + i * DAY_MS
        if day_start_ms >= end_ms or day_start_ms + DAY_MS <= start_ms:
            continue
        path = archive_dir / f"{symbol}{proof.utc_day.isoformat()}.csv.gz"
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES):
            raise ValueError("missing or unsafe pinned raw trade archive")
        sha = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                sha.update(block)
        if sha.hexdigest() != proof.raw_archive_sha256:
            raise ValueError("pinned raw trade archive SHA-256 mismatch")
        sources.append(path)

    minutes: dict[int, list[TakerPrint]] = {}
    total = 0
    seen: set[str] = set()
    for path in sources:
        with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"timestamp", "symbol", "trdMatchID", "price", "size", "side"}
            if (not reader.fieldnames
                    or len(reader.fieldnames) != len(set(reader.fieldnames))
                    or not required.issubset(reader.fieldnames)):
                raise ValueError("pinned Bybit trade archive lacks actual taker side")
            count = 0
            for row in reader:
                count += 1
                if count > MAX_RECORDS:
                    raise ValueError("pinned public trade archive row limit exceeded")
                # Parse only rows in the focused window; input is an already
                # hash-verified original used for the derived M1 cache.
                try:
                    from decimal import Decimal
                    stamp = Decimal(str(row["timestamp"]))
                    if not stamp.is_finite() or stamp < 0:
                        raise ValueError("invalid pinned trade timestamp")
                    ts_ms = int(stamp * 1000)
                except (ArithmeticError, ValueError, TypeError) as exc:
                    raise ValueError("invalid pinned trade timestamp") from exc
                if not start_ms <= ts_ms < end_ms:
                    continue
                trade = normalize_bybit_taker_print(row, layout="PUBLIC_TRADE_ARCHIVE")
                if trade.symbol != symbol or trade.trade_id in seen:
                    raise ValueError("foreign or duplicated pinned taker print")
                seen.add(trade.trade_id)
                total += 1
                if total > MAX_FOCUSED_PRINTS:
                    raise ValueError("focused taker tape exceeds bounded memory budget")
                minute = ts_ms // MINUTE_MS * MINUTE_MS
                minutes.setdefault(minute, []).append(trade)

    expected = range(start_ms, end_ms, MINUTE_MS)
    if any(minute not in minutes for minute in expected):
        raise ValueError("raw taker tape has missing minutes in the pinned M1 range")
    return {
        minute: tuple(sorted(minutes[minute], key=lambda p: (p.event_ms, p.trade_id)))
        for minute in expected
    }
