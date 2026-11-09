"""One-shot 30-day real XRPUSDT public archive proof for Simulator V2.

This script is intentionally run ONLY in a separately opted-in research CI.
Downloads immutable dated public trade archives from the exact official
public.bybit.com/trading host. No exchange keys, account API, trading endpoint,
Robot/Scanner runtime, PAPER/MAIN, or H-017 access.

It saves ONLY validated, trade-derived M1 cache, per-day raw SHA-256 provenance
and a zero-order virtual financial report; never claims official Kline parity
or a profitable strategy. No synthetic fallback for missing real data.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

from research.simulator_v2.trade_archive import MAX_ARCHIVE_BYTES
from research.simulator_v2.trade_range import (
    import_local_trade_range, run_cached_trade_range,
)

SYMBOL = "XRPUSDT"
START_DAY = date(2026, 10, 1)
DAYS = 30
START_MS = 1_790_812_800_000  # Explicit range verified against each date below.
END_MS = 1_793_404_800_000
MAX_TOTAL_ARCHIVE_BYTES = 900_000_000
OUT_DIR = Path("simulator-v2-xrp-real-30days-202610")


def fetch_archives(archive_dir: Path) -> int:
    total = 0
    for i in range(DAYS):
        day = START_DAY + timedelta(days=i)
        name = f"{SYMBOL}{day.isoformat()}.csv.gz"
        url = f"https://public.bybit.com/trading/{SYMBOL}/{name}"
        destination = archive_dir / name
        request = Request(
            url, method="GET",
            headers={"User-Agent": "BybitScanner-SimulatorV2-Research/1.0"},
        )
        daily = 0
        with urlopen(request, timeout=30) as response, destination.open("xb") as output:
            if response.geturl() != url:
                raise ValueError("unapproved public archive redirect")
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                daily += len(block)
                total += len(block)
                if daily > MAX_ARCHIVE_BYTES or total > MAX_TOTAL_ARCHIVE_BYTES:
                    raise ValueError("bounded public trade archives exceed size limit")
                output.write(block)
        if daily == 0:
            raise ValueError("empty public Bybit daily archive")
        print(f"PUBLIC_ARCHIVE_DOWNLOADED utc_day={day.isoformat()} compressed_bytes={daily}",
              flush=True)
    return total


def main() -> None:
    # Date proof is explicit: 2026-10-01 00:00 to 2026-10-31 00:00 UTC.
    from datetime import datetime, timezone
    actual_start = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()*1000)
    actual_end = int(datetime(2026, 10, 31, tzinfo=timezone.utc).timestamp()*1000)
    if (START_MS, END_MS) != (actual_start, actual_end):
        raise ValueError("incorrect fixed UTC range")
    with tempfile.TemporaryDirectory(prefix="sim-v2-xrp-30d-") as temp:
        root = Path(temp)
        incoming = root / "official-raw"
        incoming.mkdir()
        cache = root / "derived-m1-cache"
        total_bytes = fetch_archives(incoming)
        proofs = import_local_trade_range(
            archive_dir=incoming, cache_dir=cache, symbol=SYMBOL,
            start_day=START_DAY, days=DAYS,
            latest_closed_boundary_ms=END_MS,
        )
        if len(proofs) != DAYS or len(tuple(cache.glob("*.json"))) != DAYS:
            raise ValueError("incomplete raw provenance / derived M1 cache")
        # Actual strategy not wired yet. No implicit test orders or fabricated PnL.
        report = run_cached_trade_range(
            cache_dir=cache, symbol=SYMBOL, proofs=proofs,
            latest_closed_boundary_ms=END_MS,
            simulation_run_id="xrp_public_trades_202610_30d",
            initial_balance=Decimal("1000"),
        )
        if (
            report.minutes != 43_200 or report.chunks != 30
            or len(report.daily_equity) != 30
            or report.virtual_fills != 0
            or report.total_net_pnl != 0
            or report.pending_order_id is not None
        ):
            raise ValueError("incomplete or untrue SIMULATION real-history result")
        # Only valid complete snapshots leave ephemeral CI directories.
        OUT_DIR.mkdir(exist_ok=False)
        shutil.copytree(cache, OUT_DIR / "m1-cache")
        manifest = {
            "schema": "SIMULATOR_V2_PUBLIC_TRADES_DERIVED_M1_RANGE_V1",
            "namespace": "SIMULATION",
            "symbol": SYMBOL, "start_day": START_DAY.isoformat(),
            "days": DAYS, "start_ms": START_MS, "end_ms": END_MS,
            "raw_downloaded_bytes": total_bytes,
            "source_id": report.source_id,
            "raw_trade_archives_embedded": False,
            "raw_archives_recoverable_via_each_source_url_and_sha256": True,
            "day_provenance": [p.to_payload(symbol=SYMBOL) for p in proofs],
            "warning": (
                "Trade-derived OHLCV, not original Bybit Kline. "
                "No Scanner/Robot strategy, no virtual orders, no profitability test."
            ),
        }
        with (OUT_DIR / "manifest.json").open("x", encoding="utf-8") as fp:
            json.dump(manifest, fp, sort_keys=True, indent=2)
        with (OUT_DIR / "virtual_report.json").open("x", encoding="utf-8") as fp:
            json.dump(report.to_payload(), fp, sort_keys=True, indent=2)
    print(
        "REAL_BYBIT_TRADES_30_DAYS_VERIFIED"
        f" symbol={SYMBOL} days={DAYS} minutes=43200"
        f" compressed_bytes={total_bytes} source_id={report.source_id}"
        " fills=0 strategy=NONE",
        flush=True,
    )


if __name__ == "__main__":
    main()
