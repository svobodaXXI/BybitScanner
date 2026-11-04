"""Read-only Bybit OHLCV -> standalone SIMULATION viewer JSON.

Market-only export deliberately produces NO trades or fabricated strategy signals.
Account credentials, PAPER database, Robot and order endpoints are never used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets

from research.historical_candle_feed import (
    FIVE_MINUTES_MS, load_closed_five_minute_history, replay_with_closed_context,
)

SIMULATION_OUTPUT = Path(__file__).resolve().parent / "simulation_runs"
MAX_BARS = 50_000
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,30}$")


def build_market_only_document(
    *, symbol: str, start_ms: int, end_ms: int, run_id: str, fetch_candles,
) -> dict[str, object]:
    """Pure conversion with injected public-market fetch, no filesystem effects."""
    if not SYMBOL_RE.fullmatch(symbol):
        raise ValueError("invalid Bybit symbol")
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("invalid SIMULATION run ID")
    if end_ms <= start_ms or (end_ms - start_ms) // FIVE_MINUTES_MS > MAX_BARS:
        raise ValueError("history range exceeds 50000 5m bars or is empty")
    if (end_ms - start_ms) % FIVE_MINUTES_MS:
        raise ValueError("history boundaries must align to 5m")
    # A bar whose start is in the future must never become a completed candle.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if end_ms > (now_ms // FIVE_MINUTES_MS) * FIVE_MINUTES_MS:
        raise ValueError("future/forming candles are not valid history")
    candles = load_closed_five_minute_history(
        symbol=symbol, start_ms=start_ms, end_ms=end_ms,
        fetch_candles=fetch_candles,
    )
    events = []
    geometry: list[dict[str, object]] = []
    dmi_points: list[dict[str, object]] = []
    versions: dict[str, tuple[int, int, int]] = {}

    def collect_lines(view) -> None:
        def collect(kind: str, line, side: str, trend_version: int) -> None:
            identity = (line.first.at_ms, line.second.at_ms, trend_version)
            if versions.get(kind) == identity:
                return
            if line.available_at_ms > view.five_minute.signal_time_ms:
                raise ValueError("future geometry in simulated market archive")
            versions[kind] = identity
            geometry.append({
                "kind": kind, "side": side,
                "available_at_ms": view.five_minute.signal_time_ms,
                "from_ms": line.first.at_ms, "to_ms": line.second.at_ms,
                "from_price": str(line.first.price), "to_price": str(line.second.price),
                "trend_version": trend_version,
                "classification": "UNVALIDATED_GEOMETRY_ONLY",
            })

        trend = view.hourly_trend
        if trend is not None:
            collect("MAIN_1H", trend.main, trend.side, trend.available_at_ms)
            collect("TARGET_1H", trend.target, trend.side, trend.available_at_ms)
            if view.reference_5m is not None:
                collect("REFERENCE_5M", view.reference_5m, trend.side, trend.available_at_ms)

    def collect_context(view) -> None:
        snapshot = view.dmi_5m
        # The 5m candle and its DMI snapshot become visible at the same close.
        if snapshot is None or snapshot.time_ms != view.five_minute.signal_time_ms:
            raise ValueError("DMI snapshot does not match last closed five-minute bar")
        dmi_points.append({
            "time_ms": snapshot.time_ms,
            "plus_di": str(snapshot.plus_di) if snapshot.plus_di is not None else None,
            "minus_di": str(snapshot.minus_di) if snapshot.minus_di is not None else None,
            "adx": str(snapshot.adx) if snapshot.adx is not None else None,
        })
        collect_lines(view)

    result = replay_with_closed_context(
        simulation_run_id=run_id,
        candles=candles,
        on_closed_context=collect_context,
        on_visual_event=lambda event: events.append(event.to_payload()),
    )
    if result.trades or result.open_position or len(events) != len(candles):
        raise ValueError("market-only replay unexpectedly produced trading state")
    if len(dmi_points) != len(candles):
        raise ValueError("market-only DMI timeline does not match completed candles")
    return {
        "source": "SIMULATION", "simulation_run_id": run_id,
        "mode": "MARKET_ONLY", "market_data_source": "BYBIT_PUBLIC_KLINE",
        "symbol": symbol, "timeframe": "5m",
        "from_ms": start_ms, "until_ms": end_ms,
        "events": events,
        "geometry": geometry,
        "dmi_5m": {
            "source": "SIMULATION", "timeframe": "5m",
            "di_length": 14, "adx_smoothing": 14,
            "points": dmi_points,
        },
    }


def write_run_document(document: dict[str, object], root: Path = SIMULATION_OUTPUT) -> Path:
    """Write only new SIMULATION files to the dedicated output root.

    No caller-controlled output filename/path and no replacement of previous
    runs. An existing symlinked output directory is rejected.
    """
    run_id = document.get("simulation_run_id")
    if document.get("source") != "SIMULATION" or not isinstance(run_id, str) or not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("refusing non-SIMULATION output")
    if root.is_symlink():
        raise ValueError("simulation output cannot be a symlink")
    root.mkdir(exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("simulation output is not a safe directory")
    target = root / f"{run_id}.json"
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Exclusive open: never overwrite a previous run or any existing PAPER file.
    with target.open("x", encoding="utf-8") as handle:
        handle.write(payload)
        handle.write("\n")
    return target


def parse_date_utc(value: str) -> int:
    parsed = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export historical Bybit 5m candles for offline SIMULATION viewer; no trades",
    )
    parser.add_argument("--symbol", required=True, help="Bybit linear symbol, e.g. BTCUSDT")
    parser.add_argument("--start", required=True, help="UTC day inclusive: YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="UTC day exclusive: YYYY-MM-DD")
    parser.add_argument("--run-id", help="Safe unique research run identifier")
    args = parser.parse_args()
    run_id = args.run_id or ("market_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + secrets.token_hex(4))
    # Import solely the repository's existing PUBLIC GET kline wrapper at actual
    # execution time; no order/account credentials and no runtime startup.
    from bybit_api import get_candles
    document = build_market_only_document(
        symbol=args.symbol, start_ms=parse_date_utc(args.start),
        end_ms=parse_date_utc(args.end), run_id=run_id,
        fetch_candles=get_candles,
    )
    output = write_run_document(document)
    print(f"SIMULATION MARKET_ONLY: {len(document['events'])} closed candles; file={output}")
    print("Open terminal/frontend/replay.html via the standalone frontend dev/preview server, then select this JSON.")


if __name__ == "__main__":
    main()
