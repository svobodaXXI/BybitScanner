"""Prepare the existing pinned, trade-derived M1 cache for local SIMULATION.

Only called by the local owner action under the viewer's SIM_LOCK. No second
market cache, trading API, account access or synthesis of missing minutes.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory, NamedTemporaryFile

from research.simulator_v2.history import MINUTE_MS
from research.simulator_v2.public_trade_download import fetch_public_trade_day
from research.simulator_v2.timeline import SYMBOL_RE
from research.simulator_v2.trade_archive import MAX_ARCHIVE_BYTES, import_trade_day_into_cache
from research.simulator_v2.trade_range import (
    DAY_MS, TradeDayProof, _ordered_proofs, iter_pinned_trade_chunks,
)

MAX_APPLY_DOWNLOAD_BYTES = 1_100_000_000
MANIFEST_SCHEMA = "SIMULATOR_V2_PUBLIC_TRADES_DERIVED_M1_RANGE_V1"


def required_trade_days(*, start_ms: int, end_inclusive_ms: int,
                        window_bars: int, latest_closed_boundary_ms: int) -> tuple[date, ...]:
    """Same day-rounded M5 lookback as the native Wedge/Box engines."""
    if (any(type(v) is not int for v in (
            start_ms, end_inclusive_ms, window_bars, latest_closed_boundary_ms))
            or not 1 <= window_bars <= 100_000
            or start_ms < 0 or end_inclusive_ms < start_ms
            or any(v % MINUTE_MS for v in (start_ms, end_inclusive_ms, latest_closed_boundary_ms))):
        raise ValueError("invalid M1 preparation window")
    first = (start_ms - window_bars * 5 * MINUTE_MS) // DAY_MS * DAY_MS
    last = (end_inclusive_ms // DAY_MS + 1) * DAY_MS
    count = (last - first) // DAY_MS
    if first < 0 or not 1 <= count <= 90:
        raise ValueError("M1 archive including Scanner warmup must cover 1..90 UTC days")
    if last > latest_closed_boundary_ms:
        raise ValueError("Публичный архив сделок M1 доступен только за завершённые UTC-сутки")
    day = datetime.fromtimestamp(first / 1000, tz=timezone.utc).date()
    return tuple(day + timedelta(days=i) for i in range(count))


def _read_proof(path: Path, *, symbol: str, day: date) -> TradeDayProof:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise ValueError("unsafe M1 daily provenance")
    row = json.loads(path.read_bytes())
    proof = TradeDayProof(day, row["raw_archive_sha256"], row["m1_sha256"])
    if row != proof.to_payload(symbol=symbol):
        raise ValueError("M1 daily provenance identity changed")
    return proof


def _save_proof(path: Path, *, symbol: str, proof: TradeDayProof) -> None:
    if path.exists() or path.is_symlink():
        if _read_proof(path, symbol=symbol, day=proof.utc_day) != proof:
            raise ValueError("conflicting M1 daily provenance")
        return
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            output.write(json.dumps(proof.to_payload(symbol=symbol), sort_keys=True).encode())
            output.flush()
            os.fsync(output.fileno())
        # Single writer under SIM_LOCK; only a completed proof becomes visible.
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _verify_day(cache_dir: Path, symbol: str, proof: TradeDayProof, latest: int) -> None:
    # Existing source/row/SHA verifier. FileNotFoundError means absence;
    # any mismatch/corruption is a hard failure, not an overwrite request.
    tuple(iter_pinned_trade_chunks(
        cache_dir=cache_dir, symbol=symbol, proofs=(proof,),
        latest_closed_boundary_ms=latest,
    ))


def prepare_m1_manifest(*, data_dir: Path, symbol: str, start_ms: int,
                        end_inclusive_ms: int, window_bars: int,
                        latest_closed_boundary_ms: int,
                        legacy_proofs: tuple[TradeDayProof, ...] = (),
                        fetch_day=fetch_public_trade_day) -> dict:
    """Reuse verified days, fetch missing days only, return a complete manifest.

    Existing imported manifest stays untouched. Persist per-day provenance
    adjacent to the existing M1 cache so overlapping/new requests reuse days
    even after a later day fails. Only a complete range is returned.
    """
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("invalid linear M1 symbol")
    days = required_trade_days(start_ms=start_ms, end_inclusive_ms=end_inclusive_ms,
                              window_bars=window_bars,
                              latest_closed_boundary_ms=latest_closed_boundary_ms)
    cache_dir, proofs_dir = data_dir / "m1-cache", data_dir / "m1-provenance"
    for folder in (data_dir, cache_dir, proofs_dir):
        if folder.is_symlink():
            raise ValueError("unsafe M1 preparation directory")
        folder.mkdir(parents=True, exist_ok=True)
    legacy = {proof.utc_day: proof for proof in legacy_proofs}
    result = []
    downloaded = 0
    for day in days:
        path = proofs_dir / f"{symbol}-{day.isoformat()}.json"
        proof = legacy.get(day)
        if path.exists() or path.is_symlink():
            recorded = _read_proof(path, symbol=symbol, day=day)
            if proof is not None and proof != recorded:
                raise ValueError("conflicting imported and cached M1 provenance")
            proof = recorded
        if proof is not None:
            try:
                _verify_day(cache_dir, symbol, proof, latest_closed_boundary_ms)
            except FileNotFoundError:
                pass
            else:
                _save_proof(path, symbol=symbol, proof=proof)
                result.append(proof)
                continue
        with TemporaryDirectory(prefix="machine-time-public-day-") as temp:
            destination = Path(temp) / f"{symbol}{day.isoformat()}.csv.gz"
            limit = min(MAX_ARCHIVE_BYTES, MAX_APPLY_DOWNLOAD_BYTES - downloaded)
            if limit <= 0:
                raise ValueError("M1 preparation download budget exhausted; verified days retained")
            fetched = fetch_day(destination, symbol=symbol, utc_day=day, byte_limit=limit)
            if type(fetched) is not int or not 0 < fetched <= limit:
                raise ValueError("invalid public archive download size")
            downloaded += fetched
            if proof is not None:
                digest = hashlib.sha256()
                with destination.open("rb") as raw:
                    for block in iter(lambda: raw.read(1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != proof.raw_archive_sha256:
                    raise ValueError("downloaded public day differs from pinned raw SHA")
            chunk, raw_sha = import_trade_day_into_cache(
                destination, cache_dir=cache_dir, symbol=symbol, utc_day=day,
                latest_closed_boundary_ms=latest_closed_boundary_ms,
            )
            verified = TradeDayProof(day, raw_sha, chunk.sha256)
            if proof is not None and verified != proof:
                raise ValueError("downloaded public day differs from pinned M1 SHA")
            _verify_day(cache_dir, symbol, verified, latest_closed_boundary_ms)
            _save_proof(path, symbol=symbol, proof=verified)
            result.append(verified)
    pinned = tuple(result)
    identity, first, last = _ordered_proofs(
        pinned, symbol=symbol, latest_closed_boundary_ms=latest_closed_boundary_ms)
    return {
        "schema": MANIFEST_SCHEMA, "namespace": "SIMULATION", "symbol": symbol,
        "start_day": pinned[0].utc_day.isoformat(), "days": len(pinned),
        "start_ms": first, "end_ms": last, "source_id": identity,
        "raw_trade_archives_embedded": False,
        "day_provenance": [proof.to_payload(symbol=symbol) for proof in pinned],
    }
