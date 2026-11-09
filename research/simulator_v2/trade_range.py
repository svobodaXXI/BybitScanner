"""Bounded multi-day BYBIT PUBLIC TRADES archive -> cached M1 -> SIMULATION.

Every UTC day retains its own raw-archive and derived-M1 SHA-256. A combined
source identity binds the ordered day manifest, without pretending that
trade-derived M1 is the exchange's native Kline stream.

No networking, authentication, trading, Scanner/Robot runtime, or H-017 IO.
No missing-minute or missing-day backfill. A failed range never yields a report.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from research.simulator_v2.cache import iter_cached_m1_chunks
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.report import ReplayReport, run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_archive import (
    SOURCE_ID, import_trade_day_into_cache,
)
from research.simulator_v2.timeline import SYMBOL_RE

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
DAY_MS = 1440 * MINUTE_MS


@dataclass(frozen=True)
class TradeDayProof:
    utc_day: date
    raw_archive_sha256: str
    m1_sha256: str

    def __post_init__(self) -> None:
        if type(self.utc_day) is not date or not all(
            isinstance(x, str) and _SHA256.fullmatch(x)
            for x in (self.raw_archive_sha256, self.m1_sha256)
        ):
            raise ValueError("invalid SIMULATION trade-day provenance")

    @property
    def source_id(self) -> str:
        return f"{SOURCE_ID}_{self.raw_archive_sha256[:24]}"

    def to_payload(self, *, symbol: str) -> dict[str, str]:
        return {
            "utc_day": self.utc_day.isoformat(),
            "source_url": (
                f"https://public.bybit.com/trading/{symbol}/"
                f"{symbol}{self.utc_day.isoformat()}.csv.gz"
            ),
            "source_type": "BYBIT_PUBLIC_TRADES_DERIVED_M1_NOT_OFFICIAL_KLINE",
            "raw_archive_sha256": self.raw_archive_sha256,
            "m1_sha256": self.m1_sha256,
            "cache_source_id": self.source_id,
        }


def _day_start(day: date) -> int:
    return int(datetime(day.year, day.month, day.day,
                        tzinfo=timezone.utc).timestamp() * 1000)


def _validate_range(symbol: str, start_day: date, days: int,
                    latest_closed_boundary_ms: int) -> None:
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("invalid linear archive symbol")
    if type(start_day) is not date or type(days) is not int or not 1 <= days <= 90:
        raise ValueError("only a 1..90 day UTC archive range is supported")
    if type(latest_closed_boundary_ms) is not int or latest_closed_boundary_ms % MINUTE_MS:
        raise ValueError("invalid closed-M1 boundary")
    if _day_start(start_day) < 0 or _day_start(start_day) + days * DAY_MS > latest_closed_boundary_ms:
        raise ValueError("archive range includes incomplete future M1")


def import_local_trade_range(
    *, archive_dir: Path, cache_dir: Path, symbol: str,
    start_day: date, days: int, latest_closed_boundary_ms: int,
) -> tuple[TradeDayProof, ...]:
    """Cache only valid entire UTC days, one day at a time.

    Input files must already be locally downloaded by an approved caller.
    Strictly no network fallback. Only the dedicated cache is written.
    """
    _validate_range(symbol, start_day, days, latest_closed_boundary_ms)
    if not isinstance(archive_dir, Path) or not archive_dir.is_dir() or archive_dir.is_symlink():
        raise ValueError("explicit non-symlink local archive directory required")
    if not isinstance(cache_dir, Path) or cache_dir.is_symlink():
        raise ValueError("explicit dedicated non-symlink SIMULATION cache required")
    expected_paths = tuple(
        archive_dir / f"{symbol}{(start_day + timedelta(days=i)).isoformat()}.csv.gz"
        for i in range(days)
    )
    # Avoid even partial cache creation when an expected day is absent.
    if any(not path.is_file() or path.is_symlink() for path in expected_paths):
        raise FileNotFoundError("SIMULATION range has missing or unsafe daily archive")

    proofs: list[TradeDayProof] = []
    for i, path in enumerate(expected_paths):
        day = start_day + timedelta(days=i)
        chunk, raw_sha = import_trade_day_into_cache(
            path, cache_dir=cache_dir, symbol=symbol, utc_day=day,
            latest_closed_boundary_ms=latest_closed_boundary_ms,
        )
        proofs.append(TradeDayProof(day, raw_sha, chunk.sha256))
    return tuple(proofs)


def _ordered_proofs(
    proofs: tuple[TradeDayProof, ...], *, symbol: str,
    latest_closed_boundary_ms: int,
) -> tuple[str, int, int]:
    if not isinstance(proofs, tuple) or not proofs or len(proofs) > 90:
        raise ValueError("expected 1..90 ordered trade days")
    if any(not isinstance(item, TradeDayProof) for item in proofs):
        raise ValueError("invalid provenance item")
    if any(
        item.utc_day != proofs[0].utc_day + timedelta(days=i)
        for i, item in enumerate(proofs)
    ):
        raise ValueError("missing, reordered or duplicate public trade days")
    _validate_range(symbol, proofs[0].utc_day, len(proofs), latest_closed_boundary_ms)
    manifest = json.dumps(
        [item.to_payload(symbol=symbol) for item in proofs],
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")
    identity = hashlib.sha256(manifest).hexdigest()
    return f"BYBIT_PUBLIC_TRADES_RANGE_{identity[:32]}", _day_start(proofs[0].utc_day), (
        _day_start(proofs[0].utc_day) + len(proofs) * DAY_MS
    )


def run_cached_trade_range(
    *, cache_dir: Path, symbol: str,
    proofs: tuple[TradeDayProof, ...], latest_closed_boundary_ms: int,
    simulation_run_id: str, initial_balance: Decimal,
    taker_fee_rate: Decimal = Decimal("0.0006"),
) -> ReplayReport:
    """Replay the exact pinned daily cache manifest; never read network or raw CSV.

    The combined dataset ID makes the source homogeneous for the pre-existing
    report contract, while raw/day hashes remain in the separate caller-owned
    manifest. This does not grant permission to execute real trades.
    """
    dataset_source, start_ms, end_ms = _ordered_proofs(
        proofs, symbol=symbol, latest_closed_boundary_ms=latest_closed_boundary_ms,
    )
    if not isinstance(cache_dir, Path) or cache_dir.is_symlink():
        raise ValueError("dedicated local cache directory required")

    def no_network(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("a pinned SIMULATION trade-day cache is absent")

    def chunks():
        for i, proof in enumerate(proofs):
            start = start_ms + i * DAY_MS
            found = tuple(iter_cached_m1_chunks(
                cache_dir=cache_dir, symbol=symbol,
                start_ms=start, end_ms=start + DAY_MS,
                latest_closed_boundary_ms=latest_closed_boundary_ms,
                chunk_minutes=1440, source_id=proof.source_id,
                fetch_candles=no_network,
            ))
            if len(found) != 1 or found[0].sha256 != proof.m1_sha256:
                raise ValueError("pinned SIMULATION archive checksum differs")
            yield replace(found[0], source_id=dataset_source)

    session = VirtualReplaySession(
        simulation_run_id=simulation_run_id, symbol=symbol,
        initial_balance=initial_balance, taker_fee_rate=taker_fee_rate,
    )
    report = run_verified_chunks(session, chunks())
    if (
        report.first_open_ms != start_ms or report.last_closed_ms != end_ms
        or report.minutes != len(proofs) * 1440
        or len(report.daily_equity) != len(proofs)
        or report.virtual_fills != 0 or report.pending_order_id is not None
    ):
        raise ValueError("SIMULATION month did not close deterministically")
    return report
