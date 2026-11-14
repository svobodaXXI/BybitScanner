"""One-shot public Bybit trade archive proof for isolated Simulator V2 CI.

Only this script accesses public.bybit.com/trading, with no account, token,
credentials, remote commands, trading endpoints or data fallback. Its single
UTC day is fixed; both the acquired file and the trade-derived M1 report
are exported ONLY after the offline parser validates all 1440 minutes.

This is a research smoke, NOT evidence of Kline parity or Robot profitability.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

from research.simulator_v2.cache import _rows
from research.simulator_v2.report import run_verified_chunks
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.trade_archive import (
    MAX_ARCHIVE_BYTES, parse_local_trade_day,
)
from research.simulator_v2.virtual_exchange import MarketRequest

SYMBOL = "BTCUSDT"
UTC_DAY = date(2026, 10, 1)
ARCHIVE_NAME = f"{SYMBOL}{UTC_DAY.isoformat()}.csv.gz"
OFFICIAL_PUBLIC_URL = (
    f"https://public.bybit.com/trading/{SYMBOL}/{ARCHIVE_NAME}"
)
DAY_START_MS = 1_790_812_800_000
DAY_END_MS = DAY_START_MS + 1440 * 60_000


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sim-v2-bybit-archive-") as temporary:
        input_path = Path(temporary) / ARCHIVE_NAME
        request = Request(
            OFFICIAL_PUBLIC_URL, method="GET",
            headers={"User-Agent": "BybitScanner-SimulatorV2-Research/1.0"},
        )
        total = 0
        with urlopen(request, timeout=30) as response, input_path.open("xb") as output:
            if response.geturl() != OFFICIAL_PUBLIC_URL:
                raise ValueError("unapproved public archive redirect")
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError("public trade archive exceeds size bound")
                output.write(block)
        chunk, archive_sha256 = parse_local_trade_day(
            input_path, symbol=SYMBOL, utc_day=UTC_DAY,
            latest_closed_boundary_ms=DAY_END_MS,
        )
        account = VirtualReplaySession(
            simulation_run_id="public_trades_20261001",
            symbol=SYMBOL, initial_balance=Decimal("1000"),
            taker_fee_rate=Decimal("0"),
        )
        report = run_verified_chunks(account, [chunk])
        if (
            report.minutes != 1440 or report.virtual_fills
            or report.total_net_pnl != 0 or report.final_position_quantity
        ):
            raise ValueError("unexpected trades in no-strategy market replay")

        # Only fully validated public market history is promoted to CI artifact.
        destination = Path("simulator-v2-bybit-public-trades-20261001")
        destination.mkdir(exist_ok=False)
        shutil.copyfile(input_path, destination / ARCHIVE_NAME)
        provenance = {
            "namespace": "SIMULATION",
            "source_url": OFFICIAL_PUBLIC_URL,
            "source_type": "BYBIT_PUBLIC_TRADES_DERIVED_M1_NOT_OFFICIAL_KLINE",
            "raw_archive_sha256": archive_sha256,
            "derived_candles_sha256": chunk.sha256,
            "symbol": SYMBOL, "utc_day": UTC_DAY.isoformat(),
            "start_ms": chunk.start_ms, "end_ms": chunk.end_ms,
            "compressed_bytes": total, "candles": _rows(chunk.candles),
            "warning": "No Scanner/Robot strategy or virtual orders executed",
        }
        with (destination / "derived_m1_with_provenance.json").open(
            "x", encoding="utf-8",
        ) as output:
            json.dump(provenance, output, sort_keys=True, indent=2)
        with (destination / "virtual_report.json").open(
            "x", encoding="utf-8",
        ) as output:
            json.dump(report.to_payload(), output, sort_keys=True, indent=2)

    print(
        "REAL_PUBLIC_BYBIT_TRADES_VERIFIED"
        f" url={OFFICIAL_PUBLIC_URL}"
        f" raw_sha256={archive_sha256}"
        f" derived_m1_sha256={chunk.sha256}"
        " minutes=1440 virtual_fills=0 strategy=NONE"
    )


if __name__ == "__main__":
    main()
