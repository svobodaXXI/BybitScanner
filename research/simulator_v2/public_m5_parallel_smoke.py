"""Windows packaged smoke: same original Wedge observations, bounded CPU spawn.

No HTTP, private API, trades, PnL, writes or external market access.
"""
from __future__ import annotations

from research.simulator_v2.public_m5_scan import scan_public_closed_m5


def main() -> None:
    doc = {
        "source": "SIMULATION", "mode": "MARKET_ONLY",
        "market_data_source": "BYBIT_PUBLIC_KLINE",
        "simulation_run_id": "windows_spawn_smoke",
        "symbol": "BTCUSDT", "timeframe": "5m",
        "events": [{
            "kind": "CANDLE_CLOSED", "time_ms": (i+1)*300_000,
            "candle": {
                "start_ms": i*300_000, "end_ms": (i+1)*300_000,
                "open": 100, "high": 101, "low": 99, "close": 100,
                "volume": 1,
            },
        } for i in range(54)],
    }
    serial_ready: list[int] = []
    parallel_ready: list[int] = []
    serial = scan_public_closed_m5(
        doc, ("WEDGE_RISING", "WEDGE_FALLING"),
        on_ready=lambda count, _: serial_ready.append(count),
        parallel_workers=1,
    )
    parallel = scan_public_closed_m5(
        doc, ("WEDGE_RISING", "WEDGE_FALLING"),
        on_ready=lambda count, _: parallel_ready.append(count),
        parallel_workers=2,
    )
    if serial != parallel or serial_ready != parallel_ready or (
        parallel_ready != list(range(1, 55))
    ):
        raise AssertionError("parallel M5 native Scanner differs from serial frontier")
    print("PUBLIC_M5_SPAWN_ORDER_EQUIVALENCE_OK")


if __name__ == "__main__":
    main()
